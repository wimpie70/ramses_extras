"""Core entity helper functions and classes for Ramses Extras framework.

This module provides reusable entity utilities that are shared across
all features, including entity ID generation, state management, and
pattern matching functionality.
"""

import logging
import re
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from ....const import AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


class ExtrasBaseEntity:
    """Base entity class for Ramses Extras entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        entity_type: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize base entity.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            entity_type: Optional entity type (for compatibility with legacy platforms)
            config: Optional entity configuration (for compatibility
             with legacy platforms)
        """
        self.hass = hass
        self.device_id = device_id
        self._device_id = device_id  # Also set with underscore for compatibility
        self._entity_type = entity_type
        self._config = config
        self._attr_name = ""
        self._attr_unique_id = ""

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return self._attr_unique_id


class EntityHelpers:
    """Static helper methods for entity ID generation and parsing."""

    @staticmethod
    def generate_entity_name_from_template(
        entity_type: str, entity_name: str, device_id: str
    ) -> str:
        """Generate a consistent entity ID from type, name, and device ID.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of the entity from config
            (e.g., "indoor_absolute_humidity")
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Generated entity ID (e.g., "sensor.indoor_absolute_humidity_32_153289")
        """
        return f"{entity_type}.{entity_name}_{device_id}"

    @staticmethod
    def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
        """Parse entity ID to extract type, name, and device ID.

        Args:
            entity_id: Entity identifier
            (e.g., "sensor.indoor_absolute_humidity_32_153289")

        Returns:
            Tuple of (entity_type, entity_name, device_id) or None if parsing fails
        """
        # Handle the specific pattern: type.name_number_number
        # Example: "sensor.indoor_absolute_humidity_32_153289"
        parts = entity_id.split("_")
        if len(parts) >= 3:
            # The last two parts are the device_id components
            device_id = f"{parts[-2]}_{parts[-1]}"
            # Everything before that is the type.name part
            type_and_name = "_".join(parts[:-2])

            # Split type_and_name into type and name
            if "." in type_and_name:
                dot_index = type_and_name.index(".")
                entity_type = type_and_name[:dot_index]
                entity_name = type_and_name[dot_index + 1 :]
                return entity_type, entity_name, device_id

        # Fallback: simple pattern for other cases
        pattern = r"^(\w+)\.(.+)_([\w:]+)$"
        match = re.match(pattern, entity_id)
        if match:
            return match.group(1), match.group(2), match.group(3)
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
    def generate_entity_patterns_for_feature(feature_id: str) -> list[str]:
        """Generate entity patterns for a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of entity patterns
        """
        patterns = []
        feature = cast(dict[str, Any], AVAILABLE_FEATURES.get(feature_id, {}))
        required_entities = cast(
            dict[str, list[str]], feature.get("required_entities", {})
        )

        for entity_type, entity_names in required_entities.items():
            entity_base_type = entity_type.rstrip("s")  # "sensors" -> "sensor"
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
        """Get all required entity IDs for a device.

        Args:
            device_id: Device identifier

        Returns:
            List of all required entity IDs for the device
        """
        entity_ids = []

        # Define the standard entity types and names for humidity control
        entity_types = {
            "sensor": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
            "number": [
                "relative_humidity_minimum",
                "relative_humidity_maximum",
                "absolute_humidity_offset",
            ],
            "switch": ["dehumidify"],
            "binary_sensor": ["dehumidifying_active"],
        }

        for entity_type, entity_names in entity_types.items():
            for entity_name in entity_names:
                entity_id = EntityHelpers.generate_entity_name_from_template(
                    entity_type, entity_name, device_id
                )
                entity_ids.append(entity_id)

        return entity_ids


def get_feature_entity_mappings(feature_id: str, device_id: str) -> dict[str, str]:
    """Get entity mappings for a feature and device.

    Args:
        feature_id: Feature identifier
        device_id: Device identifier

    Returns:
        Dictionary mapping state names to entity IDs
    """
    # This is a placeholder implementation
    # The actual implementation would look up mappings from const.py
    # or configuration files based on the feature and device

    mappings = {}

    # Get feature definition
    feature = cast(dict[str, Any], AVAILABLE_FEATURES.get(feature_id, {}))
    required_entities = cast(dict[str, list[str]], feature.get("required_entities", {}))

    # Generate entity IDs for each required entity type
    for entity_type, entity_names in required_entities.items():
        entity_base_type = entity_type.rstrip("s")
        for entity_name in entity_names:
            entity_id = f"{entity_base_type}.{entity_name}_{device_id}"
            # Use the entity_name as the state key
            state_key = entity_name
            mappings[state_key] = entity_id

    return mappings


# Export all functions and classes
__all__ = [
    "ExtrasBaseEntity",
    "EntityHelpers",
    "get_feature_entity_mappings",
    "generate_entity_id",
    "generate_entity_patterns_for_feature",
    "get_entities_for_device",
    "get_entity_device_id",
    "parse_entity_id",
    "filter_entities_by_patterns",
]


# Additional utility functions
def generate_entity_id(entity_type: str, entity_name: str, device_id: str) -> str:
    """Generate a consistent entity ID from type, name, and device ID.

    This is a convenience wrapper around
    EntityHelpers.generate_entity_name_from_template.
    """
    return EntityHelpers.generate_entity_name_from_template(
        entity_type, entity_name, device_id
    )


def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse entity ID to extract type, name, and device ID.

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


def generate_entity_patterns_for_feature(feature_id: str) -> list[str]:
    """Generate entity patterns for a specific feature.

    This is a convenience wrapper around
    EntityHelpers.generate_entity_patterns_for_feature.
    """
    return EntityHelpers.generate_entity_patterns_for_feature(feature_id)
