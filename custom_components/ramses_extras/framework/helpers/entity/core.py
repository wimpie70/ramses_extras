"""Core entity helper functions for Ramses Extras framework.

This module provides reusable entity utilities that are shared across
all features, including entity ID generation, state management, and
pattern matching functionality.

Note: Base entity classes are now in framework.base_classes.base_entity
to maintain proper architectural separation.
"""

import asyncio
import importlib
import logging
import re
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

# AVAILABLE_FEATURES import removed to avoid blocking imports
# from ....const import AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


class EntityNamingError(Exception):
    """Base exception for entity naming operations."""


class InvalidEntityFormatError(EntityNamingError):
    """Raised when entity format is invalid or cannot be determined."""


class TemplateValidationError(EntityNamingError):
    """Raised when template validation fails."""


# Performance optimization caches
_DEVICE_ID_CACHE: dict[str, tuple[str | None, int]] = {}
_FORMAT_CACHE: dict[str, str] = {}


async def _get_required_entities_from_feature(feature_id: str) -> dict[str, list[str]]:
    """Get required entities from the feature's own const.py module.

    Args:
        feature_id: Feature identifier

    Returns:
        Dictionary mapping entity types to entity names
    """
    try:
        # Run the blocking import operation in a thread pool
        loop = asyncio.get_event_loop()
        required_entities = await loop.run_in_executor(
            None, _import_required_entities_sync, feature_id
        )

        _LOGGER.debug(f"Found required entities for {feature_id}: {required_entities}")
        return required_entities
    except Exception as e:
        _LOGGER.debug(f"Could not get required entities for {feature_id}: {e}")
        return {}


def _import_required_entities_sync(feature_id: str) -> dict[str, list[str]]:
    """Synchronous import of required entities (blocking operation).

    Args:
        feature_id: Feature identifier

    Returns:
        Dictionary mapping entity types to entity names
    """
    # Import the feature's const module
    feature_module_path = f"custom_components.ramses_extras.features.{feature_id}.const"

    feature_module = importlib.import_module(feature_module_path)

    # Get required_entities from the const data
    const_key = f"{feature_id.upper()}_CONST"
    if hasattr(feature_module, const_key):
        const_data = getattr(feature_module, const_key, {})
        required_entities: dict[str, list[str]] = const_data.get(
            "required_entities", {}
        )
        if required_entities:
            return required_entities

    # Return empty dict if no required_entities found
    return {}


def _singularize_entity_type(entity_type: str) -> str:
    """Convert plural entity type to singular form.

    Args:
        entity_type: Plural entity type (e.g., "switch", "sensor", "number")

    Returns:
        Singular entity type (e.g., "switch", "sensor", "number")
    """
    # Handle common entity type plurals
    entity_type_mapping = {
        "sensor": "sensor",
        "switch": "switch",
        "binary_sensor": "binary_sensor",
        "number": "number",
        "devices": "device",
        "entities": "entity",
    }

    return entity_type_mapping.get(entity_type, entity_type)


class EntityHelpers:
    """Enhanced entity helpers with automatic format detection."""

    @staticmethod
    def _clear_caches() -> None:
        """Clear internal caches for memory management."""
        _DEVICE_ID_CACHE.clear()
        _FORMAT_CACHE.clear()
        _LOGGER.debug("Entity naming caches cleared")

    @staticmethod
    def _extract_device_id_cached(entity_name: str) -> tuple[str | None, int]:
        """Cached version of device ID extraction for improved performance."""
        if entity_name in _DEVICE_ID_CACHE:
            return _DEVICE_ID_CACHE[entity_name]

        result = EntityHelpers._extract_device_id(entity_name)
        _DEVICE_ID_CACHE[entity_name] = result

        # Limit cache size to prevent memory issues
        if len(_DEVICE_ID_CACHE) > 1000:
            _DEVICE_ID_CACHE.clear()

        return result

    @staticmethod
    def _extract_device_id(entity_name: str) -> tuple[str | None, int]:
        """Extract device ID and return (device_id, position).

        Args:
            entity_name: Entity name that may contain a device ID

        Returns:
            Tuple of (device_id, position) or (None, -1) if not found
        """
        # Match device ID patterns: 12_345678 or 12:345678
        pattern = r"(\d+[:_]\d+)"
        match = re.search(pattern, entity_name)
        if match:
            device_id = match.group(1).replace(":", "_")  # Convert : to _
            position = match.start()  # Position in entity name
            return device_id, position
        return None, -1

    @staticmethod
    def _calculate_format_confidence(
        position: int, entity_name: str, format_type: str
    ) -> float:
        """Calculate confidence score for format detection based on multiple factors."""
        if position == -1:
            return 0.0

        length = len(entity_name)
        relative_position = position / length if length > 0 else 0

        # Base confidence on position clarity
        if format_type == "cc" and relative_position <= 0.1:
            return 0.95  # Very confident - device_id at very beginning
        if format_type == "extras" and relative_position >= 0.7:
            return 0.95  # Very confident - device_id at very end
        if format_type == "cc" and relative_position <= 0.3:
            return 0.85  # Confident - device_id in first 30%
        if format_type == "extras" and relative_position >= 0.3:
            return 0.85  # Confident - device_id in last 70%
        return 0.6  # Moderate confidence - boundary case

    @staticmethod
    def _detect_format_by_position(position: int, entity_name: str) -> str:
        """Detect format based on device_id position."""
        if position <= len(entity_name) * 0.3:  # First 30% → CC format
            return "cc"
        # Last portion → Extras format
        return "extras"

    @staticmethod
    def _get_format_hint_from_template(template: str) -> str:
        """Analyze template structure to provide format hints."""
        device_id_pos = template.find("{device_id}")
        if device_id_pos == 0:
            return "cc"  # Device ID at beginning suggests CC format
        if device_id_pos > 0:
            # Check if device_id is at the end
            remaining = template[device_id_pos:].replace("{device_id}", "")
            if not remaining or remaining.endswith(("_", "-")):
                return "extras"  # Device ID at end suggests Extras format
        return "unknown"

    @staticmethod
    def detect_and_parse(entity_id: str) -> dict | None:
        """Complete automatic format detection and parsing with enhanced validation.

        Returns comprehensive information about the entity including:
        - entity_type, parsed_name, device_id
        - format detection confidence
        - position analysis for debugging
        - validation status
        """
        # Step 1: Validate entity_id format
        if not entity_id or "." not in entity_id:
            return None

        # Step 2: Extract components with validation
        try:
            entity_type, entity_name = entity_id.split(".", 1)
        except ValueError:
            return None

        # Step 3: Advanced device ID extraction with multiple patterns
        device_id, position = EntityHelpers._extract_device_id_cached(entity_name)
        if not device_id:
            return None

        # Step 4: Enhanced format detection with confidence scoring
        format_type = EntityHelpers._detect_format_by_position(position, entity_name)

        # Step 5: Parse based on detected format with validation
        if format_type == "cc":
            # CC Format: device_id at beginning
            identifier = entity_name[position + len(device_id) :].lstrip("_")
            parsed_name = identifier if identifier else "unknown"
        else:
            # Extras Format: device_id at end
            parsed_name = entity_name[:position]

        # Step 6: Validation and confidence assessment
        confidence = EntityHelpers._calculate_format_confidence(
            position, entity_name, format_type
        )

        return {
            "entity_type": entity_type,
            "parsed_name": parsed_name,
            "device_id": device_id,
            "format": format_type,
            "position": position,
            "confidence": confidence,
            "is_valid": confidence > 0.7,
        }

    @staticmethod
    def generate_entity_name_from_template(
        entity_type: str, template: str, validate_format: bool = True, **kwargs: Any
    ) -> str:
        """Enhanced universal template with validation and error handling.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            template: Template string with placeholders
            validate_format: Whether to validate the generated format
            **kwargs: Template placeholder values

        Returns:
            Generated entity ID with automatic format detection

        Raises:
            ValueError: If template is invalid or required placeholders missing
        """
        # Validate template structure
        if not template or not isinstance(template, str):
            raise ValueError("Template must be a non-empty string")

        # Validate entity_type
        valid_types = {
            "sensor",
            "switch",
            "number",
            "binary_sensor",
            "climate",
            "select",
        }
        if entity_type not in valid_types:
            raise ValueError(
                f"Invalid entity_type: {entity_type}. Must be one of {valid_types}"
            )

        # Extract placeholders and validate required values
        placeholders = re.findall(r"\{(\w+)\}", template)
        missing_placeholders = [p for p in placeholders if p not in kwargs]
        if missing_placeholders:
            raise ValueError(f"Missing required placeholders: {missing_placeholders}")

        # Handle device_id with enhanced detection
        if "device_id" in kwargs and "{device_id}" in template:
            device_id = kwargs["device_id"]

            # Validate device_id format
            if not re.match(r"\d+[:_]\d+", device_id):
                raise ValueError(f"Invalid device_id format: {device_id}")

            # Detect format by template position
            device_pos = template.find("{device_id}")  # noqa: F841
            format_hint = EntityHelpers._get_format_hint_from_template(template)  # noqa: F841

            # Generate entity name with format validation
            entity_name = template.format(**kwargs)
            full_entity_id = f"{entity_type}.{entity_name}"

            # Optional format validation
            if validate_format:
                parsed = EntityHelpers.parse_entity_id(full_entity_id)
                if not parsed:
                    raise ValueError(
                        f"Generated entity_id failed validation: {full_entity_id}"
                    )

            return full_entity_id

        # Simple template processing for non-device_id templates
        try:
            entity_name = template.format(**kwargs)
            return f"{entity_type}.{entity_name}"
        except KeyError as e:
            raise ValueError(f"Template processing failed for placeholder: {e}")  # noqa: B904

    @staticmethod
    def validate_entity_name(entity_id: str) -> dict[str, Any]:
        """Comprehensive entity name validation with detailed feedback.

        Returns:
            dict with validation results including:
            - is_valid: Overall validation status
            - format_confidence: Confidence in format detection
            - issues: List of specific issues found
            - suggestions: List of suggested fixes
        """
        result: dict[str, Any] = {
            "is_valid": False,
            "format_confidence": 0.0,
            "issues": [],
            "suggestions": [],
            "detected_format": None,
            "entity_type": None,
            "device_id": None,
        }

        # Basic structure validation
        if not entity_id or "." not in entity_id:
            result["issues"].append("Entity ID must contain a dot separator")
            result["suggestions"].append("Use format: entity_type.entity_name")
            return result

        try:
            entity_type, entity_name = entity_id.split(".", 1)
        except ValueError:
            result["issues"].append("Invalid entity ID structure")
            result["suggestions"].append("Ensure exactly one dot separator")
            return result

        # Validate entity type
        valid_types = {
            "sensor",
            "switch",
            "number",
            "binary_sensor",
            "climate",
            "select",
        }
        if entity_type not in valid_types:
            result["issues"].append(f"Invalid entity type: {entity_type}")
            result["suggestions"].append(f"Use one of: {', '.join(valid_types)}")
            return result

        # Enhanced parsing with confidence
        parsed = EntityHelpers.detect_and_parse(entity_id)
        if not parsed:
            result["issues"].append("Could not parse entity name")
            result["suggestions"].append(
                "Ensure entity name contains a valid device_id"
            )
            return result

        # Update result with parsing details
        result.update(
            {
                "format_confidence": parsed["confidence"],
                "detected_format": parsed["format"],
                "entity_type": entity_type,
                "device_id": parsed["device_id"],
            }
        )

        # Validation checks
        if parsed["confidence"] < 0.7:
            result["issues"].append(
                f"Low format detection confidence: {parsed['confidence']:.2f}"
            )
            result["suggestions"].append(
                "Consider repositioning device_id in entity name"
            )

        if not parsed["is_valid"]:
            result["issues"].append("Entity name failed validation checks")
            result["suggestions"].append("Check device_id format and position")

        result["is_valid"] = len(result["issues"]) == 0
        return result

    @staticmethod
    def parse_entity_id_with_validation(entity_id: str) -> tuple[str, str, str]:
        """Parse entity ID with comprehensive validation and error handling."""
        try:
            result = EntityHelpers.detect_and_parse(entity_id)
            if not result:
                raise InvalidEntityFormatError(f"Cannot parse entity ID: {entity_id}")

            if result["confidence"] < 0.5:
                _LOGGER.warning(
                    f"Low confidence format detection for {entity_id}: "
                    f"{result['confidence']:.2f}"
                )

            return result["entity_type"], result["parsed_name"], result["device_id"]

        except Exception as e:
            _LOGGER.error(f"Entity parsing failed for {entity_id}: {e}")
            raise InvalidEntityFormatError(f"Failed to parse entity ID: {e}") from e

    @staticmethod
    def generate_entity_name_with_validation(
        entity_type: str, template: str, **kwargs: Any
    ) -> str:
        """Generate entity name with comprehensive validation and error handling."""
        try:
            result = EntityHelpers.generate_entity_name_from_template(
                entity_type, template, validate_format=True, **kwargs
            )

            _LOGGER.debug(f"Generated entity: {result} from template: {template}")
            return result

        except ValueError as e:
            _LOGGER.error(f"Template validation failed: {e}")
            raise TemplateValidationError(f"Template generation failed: {e}") from e
        except Exception as e:
            _LOGGER.error(f"Unexpected error during entity generation: {e}")
            raise EntityNamingError(f"Entity generation failed: {e}") from e

    @staticmethod
    def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
        """Parse entity ID with automatic format detection.

        Args:
            entity_id: Entity identifier
                    (e.g., "sensor.indoor_absolute_humidity_32_153289"
                      or "number.32_153289_param_7c00")

        Returns:
            Tuple of (entity_type, entity_name, device_id) or None if parsing fails
        """
        # Use enhanced detection
        result = EntityHelpers.detect_and_parse(entity_id)
        if result and result["is_valid"]:
            return result["entity_type"], result["parsed_name"], result["device_id"]
        return None

    @staticmethod
    def filter_entities_by_patterns(
        entities: list[Any], patterns: list[str]
    ) -> list[str]:
        """Filter entity IDs that match given patterns.

        Args:
            entities: List of entity states or IDs
            patterns: List of patterns to match against

        Returns:
            List of matching entity IDs
        """
        matching_entities = []
        for entity in entities:
            entity_id = (
                entity.entity_id if hasattr(entity, "entity_id") else str(entity)
            )
            for pattern in patterns:
                if pattern.endswith("*"):
                    prefix = pattern[:-1]
                    if entity_id.startswith(prefix):
                        matching_entities.append(entity_id)
                        break
                elif entity_id == pattern:
                    matching_entities.append(entity_id)
                    break
        return matching_entities

    @staticmethod
    async def generate_entity_patterns_for_feature(feature_id: str) -> list[str]:
        """Generate entity patterns for a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of entity patterns
        """
        patterns = []
        required_entities = await _get_required_entities_from_feature(feature_id)

        for entity_type, entity_names in required_entities.items():
            entity_base_type = _singularize_entity_type(entity_type)
            for entity_name in entity_names:
                patterns.append(f"{entity_base_type}.{entity_name}_*")

        return patterns

    @staticmethod
    def get_entities_for_device(hass: HomeAssistant, device_id: str) -> list[str]:
        """Get all entities for a specific device.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier

        Returns:
            List of entity IDs for the device
        """
        entity_ids = []
        all_states = hass.states.async_all()

        for state in all_states:
            entity_id = state.entity_id
            parsed = EntityHelpers.parse_entity_id(entity_id)
            if parsed and parsed[2] == device_id:
                entity_ids.append(entity_id)

        return entity_ids

    @staticmethod
    def cleanup_orphaned_entities(hass: HomeAssistant, device_ids: list[str]) -> int:
        """Clean up orphaned entities for given device IDs.

        Args:
            hass: Home Assistant instance
            device_ids: List of device IDs to check

        Returns:
            Number of orphaned entities cleaned up
        """
        # This is a placeholder implementation
        # In a real implementation, this would check for entities
        # that no longer have corresponding devices and remove them
        _LOGGER.info(f"Would cleanup orphaned entities for devices: {device_ids}")
        return 0

    @staticmethod
    def get_entity_device_id(entity_id: str) -> str | None:
        """Extract device ID from entity ID.

        Args:
            entity_id: Entity identifier

        Returns:
            Device ID or None if extraction fails
        """
        parsed = EntityHelpers.parse_entity_id(entity_id)
        return parsed[2] if parsed else None

    @staticmethod
    def get_all_required_entity_ids_for_device(device_id: str) -> list[str]:
        """Get all required entity IDs for a device based on its capabilities.

        This method uses the registry system to get all possible entities
        for a device, regardless of which features are enabled.

        Args:
            device_id: Device identifier in underscore format (e.g., "32_153289")

        Returns:
            List of all required entity IDs for this device
        """
        entity_ids: list[str] = []

        # Use the registry system to get all entity configs
        # This is feature-agnostic and will get all possible entities
        try:
            # Import the registry at runtime to avoid blocking imports
            from custom_components.ramses_extras.extras_registry import (
                extras_registry,
            )

            all_configs = {
                "sensor": extras_registry.get_all_sensor_configs(),
                "switch": extras_registry.get_all_switch_configs(),
                "number": extras_registry.get_all_number_configs(),
                "binary_sensor": extras_registry.get_all_boolean_configs(),
            }
            for entity_type, configs in all_configs.items():
                for entity_name in configs.keys():
                    entity_id = EntityHelpers.generate_entity_name_from_template(
                        entity_type, entity_name, device_id=device_id
                    )
                    if entity_id:
                        entity_ids.append(entity_id)

        except Exception as e:
            _LOGGER.debug(f"Could not get entity IDs from registry: {e}")

        return entity_ids


async def get_feature_entity_mappings(
    feature_id: str, device_id: str
) -> dict[str, str]:
    """Get entity mappings for a feature and device.

    Args:
        feature_id: Feature identifier
        device_id: Device identifier (can contain colons like "32:153289")

    Returns:
        Dictionary mapping state names to entity IDs
    """
    mappings: dict[str, str] = {}

    # Get feature entity mappings from the feature's own module
    feature_entity_mappings = await _get_entity_mappings_from_feature(
        feature_id, device_id
    )
    mappings.update(feature_entity_mappings)

    _LOGGER.debug(f"Feature {feature_id} mappings for {device_id}: {mappings}")
    return mappings


async def _get_entity_mappings_from_feature(
    feature_id: str, device_id: str
) -> dict[str, str]:
    """Get entity mappings from the feature's own const.py module.

    Args:
        feature_id: Feature identifier
        device_id: Device identifier (can contain colons like "32:153289")

    Returns:
        Dictionary mapping state names to entity IDs
    """
    try:
        # Run the blocking import operation in a thread pool
        loop = asyncio.get_event_loop()
        mappings = await loop.run_in_executor(
            None, _import_entity_mappings_sync, feature_id, device_id
        )

        _LOGGER.debug(
            f"Found entity mappings for {feature_id}: {list(mappings.keys())}"
        )
        return mappings
    except Exception as e:
        _LOGGER.debug(f"Could not get entity mappings for {feature_id}: {e}")
        return {}


def _import_entity_mappings_sync(feature_id: str, device_id: str) -> dict[str, str]:
    """Synchronous import of entity mappings (blocking operation).

    Args:
        feature_id: Feature identifier
        device_id: Device identifier (can contain colons like "32:153289")

    Returns:
        Dictionary mapping state names to entity IDs
    """
    # Import the feature's const module
    feature_module_path = f"custom_components.ramses_extras.features.{feature_id}.const"

    feature_module = importlib.import_module(feature_module_path)

    mappings: dict[str, str] = {}
    device_id_underscore = device_id.replace(":", "_")

    # First try to get entity mappings from the const data
    const_key = f"{feature_id.upper()}_CONST"
    if hasattr(feature_module, const_key):
        const_data = getattr(feature_module, const_key, {})
        entity_mappings = const_data.get("entity_mappings", {})
        for state_key, entity_template in entity_mappings.items():
            # Replace {device_id} placeholder with the actual device_id
            entity_id = entity_template.replace("{device_id}", device_id_underscore)
            mappings[state_key] = entity_id

    # Check for feature-specific entity templates in various config types
    # Try both with and without "_CARD" suffix for backwards compatibility
    config_types = [
        "SENSOR_CONFIGS",
        "SWITCH_CONFIGS",
        "NUMBER_CONFIGS",
        "BINARY_SENSOR_CONFIGS",  # Also try without "BOOLEAN" alias
        "BOOLEAN_CONFIGS",
    ]

    config_type_domains = {
        "SENSOR_CONFIGS": "sensor",
        "SWITCH_CONFIGS": "switch",
        "NUMBER_CONFIGS": "number",
        "BINARY_SENSOR_CONFIGS": "binary_sensor",
        "BOOLEAN_CONFIGS": "binary_sensor",
    }

    for config_type in config_types:
        domain = config_type_domains[config_type]
        # Try with "_CARD" suffix first (for hello_world -> hello_world_SWITCH_CONFIGS)
        config_key = f"{feature_id.upper()}_{config_type}"
        if hasattr(feature_module, config_key):
            configs = getattr(feature_module, config_key, {})

            for entity_name, config in configs.items():
                entity_template = config.get("entity_template", "")
                if entity_template:
                    # Replace {device_id} placeholder with the actual device_id
                    entity_name_only = entity_template.replace(
                        "{device_id}", device_id_underscore
                    )
                    # Use the entity_name as the state key
                    if "." in entity_name_only:
                        mappings[entity_name] = entity_name_only
                    else:
                        mappings[entity_name] = f"{domain}.{entity_name_only}"

        # Also try without "_CARD" suffix
        # (for hello_world -> HELLO_WORLD_SWITCH_CONFIGS)
        if "_CARD" in feature_id:
            base_feature_id = feature_id.replace("_CARD", "")
            config_key = f"{base_feature_id.upper()}_{config_type}"
            if hasattr(feature_module, config_key):
                configs = getattr(feature_module, config_key, {})

                for entity_name, config in configs.items():
                    entity_template = config.get("entity_template", "")
                    if entity_template:
                        # Replace {device_id} placeholder with the actual device_id
                        entity_name_only = entity_template.replace(
                            "{device_id}", device_id_underscore
                        )
                        # Use the entity_name as the state key
                        if "." in entity_name_only:
                            mappings[entity_name] = entity_name_only
                        else:
                            mappings[entity_name] = f"{domain}.{entity_name_only}"

    return mappings


# Export all functions and classes
__all__ = [
    "EntityHelpers",
    "get_feature_entity_mappings",
    "generate_entity_from_template",
    "generate_entity_patterns_for_feature",
    "get_entities_for_device",
    "get_entity_device_id",
    "parse_entity_id",
    "filter_entities_by_patterns",
]


# Additional utility functions


def generate_entity_from_template(
    entity_type: str, template: str, **kwargs: Any
) -> str:
    """Generate entity ID using template with automatic format detection.

    This is a convenience wrapper around
    EntityHelpers.generate_entity_name_from_template.
    """
    return EntityHelpers.generate_entity_name_from_template(
        entity_type, template, **kwargs
    )


def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse entity ID with automatic format detection.

    This is a convenience wrapper around EntityHelpers.parse_entity_id.
    """
    return EntityHelpers.parse_entity_id(entity_id)


def get_entity_device_id(entity_id: str) -> str | None:
    """Extract device ID from entity ID.

    This is a convenience wrapper around EntityHelpers.get_entity_device_id.
    """
    return EntityHelpers.get_entity_device_id(entity_id)


def get_entities_for_device(hass: HomeAssistant, device_id: str) -> list[str]:
    """Get all entities for a specific device.

    This is a convenience wrapper around EntityHelpers.get_entities_for_device.
    """
    return EntityHelpers.get_entities_for_device(hass, device_id)


def filter_entities_by_patterns(entities: list[Any], patterns: list[str]) -> list[str]:
    """Filter entity IDs that match given patterns.

    This is a convenience wrapper around EntityHelpers.filter_entities_by_patterns.
    """
    return EntityHelpers.filter_entities_by_patterns(entities, patterns)


async def generate_entity_patterns_for_feature(feature_id: str) -> list[str]:
    """Generate entity patterns for a specific feature.

    This is a convenience wrapper around
    EntityHelpers.generate_entity_patterns_for_feature.
    """
    return await EntityHelpers.generate_entity_patterns_for_feature(feature_id)
