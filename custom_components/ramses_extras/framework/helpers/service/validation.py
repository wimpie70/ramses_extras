"""Service validation framework for Ramses Extras.

This module provides utilities for validating service calls, parameters,
and service execution results across features.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Union

from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """Validation categories."""

    PARAMETER = "parameter"
    DEVICE = "device"
    ENTITY = "entity"
    PERMISSION = "permission"
    CAPABILITY = "capability"
    TIMING = "timing"


@dataclass
class ValidationResult:
    """Result of a service validation."""

    is_valid: bool
    severity: ValidationSeverity
    category: ValidationCategory
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to dictionary.

        Returns:
            Dictionary representation of the validation result
        """
        return {
            "is_valid": self.is_valid,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ServiceValidator:
    """Validator for service calls and parameters."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize service validator.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._validation_cache: dict[str, list[ValidationResult]] = {}
        self._parameter_schemas: dict[str, dict[str, Any]] = {}
        self._device_patterns: dict[str, re.Pattern] = {}
        self._entity_patterns: dict[str, re.Pattern] = {}

    def register_parameter_schema(
        self, service_name: str, schema: dict[str, Any]
    ) -> None:
        """Register parameter validation schema for a service.

        Args:
            service_name: Name of the service
            schema: JSON schema for service parameters
        """
        self._parameter_schemas[service_name] = schema
        _LOGGER.debug(f"Registered parameter schema for service: {service_name}")

    def register_device_pattern(self, feature_id: str, pattern: str) -> None:
        """Register device ID pattern for validation.

        Args:
            feature_id: Feature identifier
            pattern: Regex pattern for device IDs
        """
        try:
            compiled_pattern = re.compile(pattern)
            self._device_patterns[feature_id] = compiled_pattern
            _LOGGER.debug(f"Registered device pattern for feature: {feature_id}")
        except re.error as e:
            _LOGGER.error(f"Invalid device pattern '{pattern}' for {feature_id}: {e}")

    def register_entity_pattern(self, entity_type: str, pattern: str) -> None:
        """Register entity ID pattern for validation.

        Args:
            entity_type: Type of entity (sensor, switch, etc.)
            pattern: Regex pattern for entity IDs
        """
        try:
            compiled_pattern = re.compile(pattern)
            self._entity_patterns[entity_type] = compiled_pattern
            _LOGGER.debug(f"Registered entity pattern for type: {entity_type}")
        except re.error as e:
            _LOGGER.error(f"Invalid entity pattern '{pattern}' for {entity_type}: {e}")

    def validate_service_call(
        self,
        service_call: ServiceCall,
        service_name: str,
        feature_id: str | None = None,
    ) -> list[ValidationResult]:
        """Validate a service call.

        Args:
            service_call: Home Assistant service call
            service_name: Name of the service being called
            feature_id: Optional feature identifier

        Returns:
            List of validation results
        """
        cache_key = (
            f"{service_name}:{service_call.data.get(ATTR_DEVICE_ID, 'no_device')}"
        )

        # Check cache first (basic cache)
        if cache_key in self._validation_cache:
            _LOGGER.debug(f"Using cached validation for: {cache_key}")
            return self._validation_cache[cache_key]

        results: list[ValidationResult] = []

        # Validate service parameters
        results.extend(self._validate_parameters(service_call, service_name))

        # Validate device if provided
        device_id = service_call.data.get(ATTR_DEVICE_ID)
        if device_id:
            results.extend(self._validate_device(device_id, feature_id))

        # Validate entity if provided
        entity_id = service_call.data.get(ATTR_ENTITY_ID)
        if entity_id:
            results.extend(self._validate_entity(entity_id))

        # Validate timing constraints
        results.extend(self._validate_timing(service_call, service_name))

        # Cache results
        self._validation_cache[cache_key] = results

        return results

    def _validate_parameters(
        self, service_call: ServiceCall, service_name: str
    ) -> list[ValidationResult]:
        """Validate service call parameters.

        Args:
            service_call: Service call to validate
            service_name: Name of the service

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        # Get schema if registered
        schema = self._parameter_schemas.get(service_name)
        if not schema:
            return results

        # Validate required parameters
        required_params = schema.get("required", [])
        for param in required_params:
            if param not in service_call.data:
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.PARAMETER,
                        message=f"Required parameter '{param}' missing",
                        details={"parameter": param, "service": service_name},
                    )
                )

        # Validate parameter types
        param_types = schema.get("properties", {})
        for param, value in service_call.data.items():
            if param in param_types:
                type_info = param_types[param]
                expected_type = type_info.get("type")

                if expected_type and not self._validate_parameter_type(
                    value, expected_type
                ):
                    results.append(
                        ValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.PARAMETER,
                            message=f"Parameter '{param}' has wrong type",
                            details={
                                "parameter": param,
                                "expected_type": expected_type,
                                "actual_type": type(value).__name__,
                                "value": str(value),
                            },
                        )
                    )

        return results

    def _validate_parameter_type(self, value: Any, expected_type: str) -> bool:
        """Validate parameter type.

        Args:
            value: Value to validate
            expected_type: Expected type name

        Returns:
            True if type matches, False otherwise
        """
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected_python_type = type_mapping.get(expected_type)
        if not expected_python_type:
            return True  # Unknown type, skip validation

        return isinstance(value, expected_python_type)  # type: ignore[arg-type]

    def _validate_device(
        self, device_id: str, feature_id: str | None
    ) -> list[ValidationResult]:
        """Validate device ID.

        Args:
            device_id: Device ID to validate
            feature_id: Feature identifier

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        if not feature_id:
            return results

        # Check device pattern if registered
        pattern = self._device_patterns.get(feature_id)
        if pattern and not pattern.match(device_id):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.DEVICE,
                    message=f"Device ID format invalid for feature '{feature_id}'",
                    details={
                        "device_id": device_id,
                        "feature_id": feature_id,
                        "pattern": pattern.pattern,
                    },
                )
            )

        # Check if device exists in device registry
        try:
            device_reg = self.hass.helpers.device_registry.async_get()
            device = device_reg.async_get(device_id)
            if not device:
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.DEVICE,
                        message="Device not found in registry",
                        details={"device_id": device_id},
                    )
                )
        except Exception as e:
            _LOGGER.error(f"Error checking device registry: {e}")
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.DEVICE,
                    message="Could not validate device in registry",
                    details={"device_id": device_id, "error": str(e)},
                )
            )

        return results

    def _validate_entity(self, entity_id: str) -> list[ValidationResult]:
        """Validate entity ID.

        Args:
            entity_id: Entity ID to validate

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        # Check entity existence
        entity_state = self.hass.states.get(entity_id)
        if not entity_state:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.ENTITY,
                    message="Entity not found",
                    details={"entity_id": entity_id},
                )
            )
            return results

        # Check entity pattern
        entity_type = entity_id.split(".")[0]
        pattern = self._entity_patterns.get(entity_type)
        if pattern and not pattern.match(entity_id):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.ENTITY,
                    message=f"Entity ID format unexpected for type '{entity_type}'",
                    details={
                        "entity_id": entity_id,
                        "entity_type": entity_type,
                        "pattern": pattern.pattern,
                    },
                )
            )

        return results

    def _validate_timing(
        self, service_call: ServiceCall, service_name: str
    ) -> list[ValidationResult]:
        """Validate timing constraints.

        Args:
            service_call: Service call to validate
            service_name: Name of the service

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        # Check for timing parameters
        timing_params = {"timeout", "retry_count", "delay", "batch_size"}
        timing_data = {}

        for param in timing_params:
            if param in service_call.data:
                timing_data[param] = service_call.data[param]

        if timing_data:
            # Validate timeout
            if "timeout" in timing_data:
                timeout = timing_data["timeout"]
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    results.append(
                        ValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.TIMING,
                            message="Timeout must be a positive number",
                            details={"timeout": timeout},
                        )
                    )
                elif timeout > 60:  # Max 60 seconds
                    results.append(
                        ValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.TIMING,
                            message="Timeout exceeds recommended maximum (60s)",
                            details={"timeout": timeout},
                        )
                    )

            # Validate retry count
            if "retry_count" in timing_data:
                retry_count = timing_data["retry_count"]
                if not isinstance(retry_count, int) or retry_count < 0:
                    results.append(
                        ValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.TIMING,
                            message="Retry count must be a non-negative integer",
                            details={"retry_count": retry_count},
                        )
                    )
                elif retry_count > 5:  # Max 5 retries
                    results.append(
                        ValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.TIMING,
                            message="Retry count exceeds recommended maximum (5)",
                            details={"retry_count": retry_count},
                        )
                    )

        return results

    def validate_service_result(
        self, service_name: str, result: Any, execution_time: float | None = None
    ) -> list[ValidationResult]:
        """Validate service execution result.

        Args:
            service_name: Name of the service
            result: Service execution result
            execution_time: Optional execution time in seconds

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []

        # Check result type
        if result is None:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.CAPABILITY,
                    message="Service returned None result",
                    details={"service_name": service_name},
                )
            )
        elif isinstance(result, bool) and not result:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.CAPABILITY,
                    message="Service execution failed",
                    details={"service_name": service_name},
                )
            )

        # Check execution time if provided
        if execution_time is not None:
            if execution_time > 10:  # Max 10 seconds
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.TIMING,
                        message="Service execution exceeded 10 seconds",
                        details={
                            "service_name": service_name,
                            "execution_time": execution_time,
                        },
                    )
                )
            elif execution_time < 0.01:  # Min 0.01 seconds
                results.append(
                    ValidationResult(
                        is_valid=True,
                        severity=ValidationSeverity.INFO,
                        category=ValidationCategory.TIMING,
                        message="Very fast service execution",
                        details={
                            "service_name": service_name,
                            "execution_time": execution_time,
                        },
                    )
                )

        return results

    def get_validation_summary(
        self, validation_results: list[ValidationResult]
    ) -> dict[str, Any]:
        """Get summary of validation results.

        Args:
            validation_results: List of validation results

        Returns:
            Dictionary with validation summary
        """
        if not validation_results:
            return {
                "is_valid": True,
                "total_results": 0,
                "by_severity": {},
                "by_category": {},
                "messages": [],
            }

        # Count by severity and category
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        messages: list[dict[str, Any]] = []

        for result in validation_results:
            # Count by severity
            severity = result.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

            # Count by category
            category = result.category.value
            by_category[category] = by_category.get(category, 0) + 1

            # Collect messages
            messages.append(
                {
                    "message": result.message,
                    "severity": severity,
                    "category": category,
                    "details": result.details,
                }
            )

        # Overall validity
        has_errors = (
            by_severity.get("error", 0) > 0 or by_severity.get("critical", 0) > 0
        )
        is_valid = not has_errors

        return {
            "is_valid": is_valid,
            "total_results": len(validation_results),
            "by_severity": by_severity,
            "by_category": by_category,
            "messages": messages,
        }

    def clear_cache(self) -> None:
        """Clear validation cache."""
        self._validation_cache.clear()
        _LOGGER.debug("Cleared validation cache")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get validation cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_size": len(self._validation_cache),
            "registered_schemas": len(self._parameter_schemas),
            "device_patterns": len(self._device_patterns),
            "entity_patterns": len(self._entity_patterns),
            "cache_keys": list(self._validation_cache.keys()),
        }


def validate_service_call(
    service_call: ServiceCall,
    service_name: str,
    hass: HomeAssistant,
    feature_id: str | None = None,
    validator: ServiceValidator | None = None,
) -> list[ValidationResult]:
    """Standalone function to validate a service call.

    Args:
        service_call: Home Assistant service call
        service_name: Name of the service being called
        hass: Home Assistant instance
        feature_id: Optional feature identifier
        validator: Optional validator instance

    Returns:
        List of validation results
    """
    if validator is None:
        validator = ServiceValidator(hass)

    return validator.validate_service_call(service_call, service_name, feature_id)
