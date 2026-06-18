"""Validation utilities for Ramses Extras framework.

This module provides reusable validation utilities and decorators
shared across the framework and features.
"""

import asyncio
import logging
import re
from typing import Any, Callable, cast

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""


class RamsesValidator:
    """Collection of validation utilities for Ramses Extras."""

    @staticmethod
    def validate_device_id(device_id: str) -> bool:
        """Validate device ID format.

        :param device_id: Device identifier to validate
        :return: True if valid format, False otherwise
        """
        # Accept formats like "32:153289", "32_153289", or just "32"
        patterns = [
            r"^\d+:\d+$",  # 32:153289
            r"^\d+_\d+$",  # 32_153289
            r"^\d+$",  # 32
        ]

        return any(re.match(pattern, device_id) for pattern in patterns)

    @staticmethod
    def validate_entity_id(entity_id: str) -> bool:
        """Validate entity ID format.

        :param entity_id: Entity identifier to validate
        :return: True if valid format, False otherwise
        """
        # Basic entity ID format: domain.entity_name_device_id
        pattern = r"^[a-z_]+\.[a-z_]+(_\d+(_\d+)?)?$"
        return bool(re.match(pattern, entity_id))

    @staticmethod
    def validate_feature_id(feature_id: str) -> bool:
        """Validate feature ID format.

        :param feature_id: Feature identifier to validate
        :return: True if valid format, False otherwise
        """
        # Feature ID should be alphanumeric with underscores
        pattern = r"^[a-z_][a-z0-9_]*$"
        return bool(re.match(pattern, feature_id))

    @staticmethod
    def validate_numeric_value(
        value: str | int | float,
        min_val: float | None = None,
        max_val: float | None = None,
    ) -> float:
        """Validate and convert a value to numeric.

        :param value: Value to validate
        :param min_val: Minimum allowed value
        :param max_val: Maximum allowed value
        :return: Numeric value
        :raises ValidationError: If value is invalid or out of range
        """
        try:
            num_value = float(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Value '{value}' is not numeric: {e}") from e

        if min_val is not None and num_value < min_val:
            raise ValidationError(f"Value {num_value} is below minimum {min_val}")

        if max_val is not None and num_value > max_val:
            raise ValidationError(f"Value {num_value} is above maximum {max_val}")

        return num_value

    @staticmethod
    def validate_entity_states(
        hass: HomeAssistant,
        entity_ids: list[str],
        required_states: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate that entities exist and have expected states.

        :param hass: Home Assistant instance
        :param entity_ids: List of entity IDs to validate
        :param required_states: Dict mapping entity_id to required state value
        :return: Dictionary with entity states
        :raises ValidationError: If validation fails
        """
        states = {}
        missing_entities = []
        invalid_states = []

        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            if not state:
                missing_entities.append(entity_id)
                continue

            if state.state in ["unavailable", "unknown"]:
                invalid_states.append(f"{entity_id} (unavailable/unknown)")
                continue

            states[entity_id] = {
                "state": state.state,
                "attributes": state.attributes,
                "last_changed": state.last_changed,
                "last_updated": state.last_updated,
            }

            # Check required state if specified
            if required_states and entity_id in required_states:
                required_state = required_states[entity_id]
                if state.state != required_state:
                    invalid_states.append(
                        f"{entity_id} (expected '{required_state}', "
                        f"got '{state.state}')"
                    )

        # Report validation results
        if missing_entities:
            _LOGGER.warning(f"Missing entities: {missing_entities}")

        if invalid_states:
            _LOGGER.warning(f"Invalid entity states: {invalid_states}")

        if missing_entities or invalid_states:
            raise ValidationError(
                f"Entity validation failed - missing: {missing_entities}, "
                f"invalid states: {invalid_states}"
            )

        return states

    @staticmethod
    def validate_device_type(device_type: str, supported_types: list[str]) -> bool:
        """Validate that a device type is supported.

        :param device_type: Device type to validate
        :param supported_types: List of supported device types
        :return: True if device type is supported
        """
        return device_type in supported_types

    @staticmethod
    def validate_humidity_value(humidity: str | int | float) -> float:
        """Validate humidity percentage.

        :param humidity: Humidity value to validate
        :return: Validated humidity value
        :raises ValidationError: If humidity is invalid
        """
        return RamsesValidator.validate_numeric_value(humidity, 0.0, 100.0)

    @staticmethod
    def validate_temperature_value(temp: str | int | float) -> float:
        """Validate temperature value.

        :param temp: Temperature value to validate
        :return: Validated temperature value
        :raises ValidationError: If temperature is invalid
        """
        return RamsesValidator.validate_numeric_value(temp, -50.0, 100.0)

    @staticmethod
    def validate_entity_template(template: str, device_id: str) -> str:
        """Validate and expand an entity template.

        :param template: Entity template with {device_id} placeholder
        :param device_id: Device ID to substitute
        :return: Expanded entity ID
        :raises ValidationError: If template is invalid
        """
        if "{device_id}" not in template:
            raise ValidationError(
                f"Template '{template}' does not contain {{device_id}} placeholder"
            )

        if not RamsesValidator.validate_device_id(device_id):
            raise ValidationError(f"Invalid device ID: {device_id}")

        return template.format(device_id=device_id)

    @staticmethod
    def validate_entity_mappings(mappings: dict[str, str]) -> bool:
        """Validate entity mappings configuration.

        :param mappings: Entity mappings to validate
        :return: True if mappings are valid
        :raises ValidationError: If mappings are invalid
        """
        for state_name, entity_template in mappings.items():
            # Check state name format
            if not re.match(r"^[a-z_][a-z0-9_]*$", state_name):
                raise ValidationError(f"Invalid state name format: {state_name}")

            # Check entity template format
            if not entity_template or "{device_id}" not in entity_template:
                raise ValidationError(
                    f"Invalid entity template for {state_name}: {entity_template}"
                )

        return True


# Decorators for validation
def validate_device_id(func: Callable) -> Callable:
    """Decorator to validate device_id parameter."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Assume device_id is first argument after self
        if len(args) > 1:
            device_id = args[1]
        elif "device_id" in kwargs:
            device_id = kwargs["device_id"]
        else:
            raise ValidationError("device_id parameter not found")

        if not RamsesValidator.validate_device_id(device_id):
            raise ValidationError(f"Invalid device_id format: {device_id}")

        return func(*args, **kwargs)

    return wrapper


def async_validate_entity_states(required_entity_ids: list[str]) -> Callable:
    """Decorator to validate entity states in async functions.

    :param required_entity_ids: List of entity IDs that must exist and be available
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if hasattr(self, "hass"):
                RamsesValidator.validate_entity_states(self.hass, required_entity_ids)
            return await func(self, *args, **kwargs)

        return cast(Callable[..., Any], wrapper)

    return decorator


# Validation context manager
class ValidationContext:
    """Context manager for validation operations."""

    def __init__(self, validation_name: str):
        """Initialize validation context.

        :param validation_name: Name of the validation operation
        """
        self.validation_name = validation_name
        self.errors: list[str] = []

    def __enter__(self) -> ValidationContext:
        """Enter validation context."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit validation context."""
        if exc_type is ValidationError:
            _LOGGER.error(f"Validation failed for {self.validation_name}: {exc_val}")
        elif exc_type is not None:
            _LOGGER.error(f"Unexpected error during {self.validation_name}: {exc_val}")

    def add_error(self, error: str) -> None:
        """Add a validation error."""
        self.errors.append(error)

    def validate_all(self) -> bool:
        """Validate all collected errors.

        :return: True if no errors, False otherwise
        """
        if self.errors:
            _LOGGER.error(
                f"Validation {self.validation_name} failed with "
                f"{len(self.errors)} errors: {self.errors}"
            )
            return False
        return True


def create_validation_context(validation_name: str) -> ValidationContext:
    """Create a validation context manager.

    :param validation_name: Name of the validation operation
    :return: ValidationContext instance
    """
    return ValidationContext(validation_name)


__all__ = [
    "ValidationError",
    "RamsesValidator",
    "ValidationContext",
    "create_validation_context",
    "validate_device_id",
    "async_validate_entity_states",
]
