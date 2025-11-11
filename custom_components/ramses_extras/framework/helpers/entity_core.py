"""Entity helper utilities for Ramses Extras framework.

This module provides reusable entity utilities that are shared across
all features, including entity ID generation, state management, and
pattern matching functionality.
"""

import logging
import re
from collections.abc import Callable
from typing import Any, Dict, List, Optional, Set, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.ramses_extras.framework import (
    get_all_entities,
    get_device_mapping,
    get_entity_config,
)
from custom_components.ramses_extras.framework.helpers.entity.registry import (
    entity_registry,
)

_LOGGER = logging.getLogger(__name__)


def _singularize_entity_type(entity_type: str) -> str:
    """Convert plural entity type to singular form.

    Args:
        entity_type: Plural entity type (e.g., "switches", "sensors", "numbers")

    Returns:
        Singular entity type (e.g., "switch", "sensor", "number")
    """
    # Handle common entity type plurals
    entity_type_mapping = {
        "sensors": "sensor",
        "switches": "switch",
        "binary_sensors": "binary_sensor",
        "numbers": "number",
        "devices": "device",
        "entities": "entity",
    }

    return entity_type_mapping.get(entity_type, entity_type.rstrip("s"))


class EntityHelpers:
    """Static helper methods for entity ID generation and parsing.

    This class provides utility methods for working with entities across
    the Ramses Extras framework, including entity ID generation, parsing,
    and validation.
    """

    @staticmethod
    def generate_entity_id(entity_type: str, entity_name: str, device_id: str) -> str:
        """Generate a consistent entity ID from type, name, and device ID.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of entity from config (e.g., "indoor_absolute_humidity")
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            Full entity ID (e.g., "sensor.indoor_absolute_humidity_32_153289")
        """
        return f"{entity_type}.{entity_name}_{device_id}"

    @staticmethod
    def get_entity_template(entity_type: str, entity_name: str) -> str | None:
        """Get the entity template for a specific entity type and name.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of entity from config (e.g., "indoor_absolute_humidity")

        Returns:
            Entity template string with {device_id} placeholder, or None if not found
        """
        # First try to get from entity registry
        config = get_entity_config(entity_name)
        if config:
            template = config.get("entity_template")
            return str(template) if template is not None else None

        # Get from entity registry
        all_entities = (
            entity_registry.get_all_sensor_configs()
            if entity_type == "sensor"
            else entity_registry.get_all_switch_configs()
            if entity_type == "switch"
            else entity_registry.get_all_number_configs()
            if entity_type == "number"
            else entity_registry.get_all_boolean_configs()
            if entity_type == "binary_sensor"
            else {}
        )
        entity_config = all_entities.get(entity_name, {})
        template = entity_config.get("entity_template")
        return template if template is not None else None

    @staticmethod
    def generate_entity_name_from_template(
        entity_type: str, entity_name: str, device_id: str
    ) -> str | None:
        """Generate a full entity ID using the configured template.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of entity from config (e.g., "indoor_absolute_humidity")
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            Full entity ID using the template, or None if template not found
        """
        template = EntityHelpers.get_entity_template(entity_type, entity_name)
        if not template:
            return None

        # Replace {device_id} placeholder with actual device ID
        entity_id_part = template.format(device_id=device_id)

        return f"{entity_type}.{entity_id_part}"

    @staticmethod
    def get_all_required_entity_ids_for_device(device_id: str) -> list[str]:
        """Get all entity IDs required for a device based on its capabilities.

        Args:
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            List of all required entity IDs for this device
        """
        entity_ids = []

        # Try to get from entity registry first
        all_entities = get_all_entities()
        for entity_name, config in all_entities.items():
            if device_id in config.get("supported_device_types", []):
                entity_type = config.get("entity_type", "sensor")
                entity_id = EntityHelpers.generate_entity_name_from_template(
                    entity_type, entity_name, device_id
                )
                if entity_id:
                    entity_ids.append(entity_id)

        # If no registry results, get from all entity configs
        if not entity_ids:
            all_configs = {
                "sensor": entity_registry.get_all_sensor_configs(),
                "switch": entity_registry.get_all_switch_configs(),
                "number": entity_registry.get_all_number_configs(),
                "binary_sensor": entity_registry.get_all_boolean_configs(),
            }
            for entity_type, configs in all_configs.items():
                for entity_name in configs.keys():
                    entity_id = EntityHelpers.generate_entity_name_from_template(
                        entity_type, entity_name, device_id
                    )
                    if entity_id:
                        entity_ids.append(entity_id)

        return entity_ids

    @staticmethod
    def cleanup_orphaned_entities(
        platform: str,
        hass: "HomeAssistant",
        devices: list[str],
        required_entities: set[str],
        all_possible_types: list[str],
    ) -> int:
        """Clean up orphaned entities from the registry.

        Args:
            platform: Platform type ('sensor', 'switch', 'binary_sensor')
            hass: Home Assistant instance
            devices: List of device IDs
            required_entities: Set of currently required entity IDs
            all_possible_types: List of all possible entity types for this platform

        Returns:
            Number of entities removed
        """
        _LOGGER.info(f"Starting {platform} cleanup for devices: {devices}")

        # Get entity registry
        if "entity_registry" not in hass.data:
            _LOGGER.warning("Entity registry not available")
            return 0

        entity_registry: er.EntityRegistry = hass.data["entity_registry"]
        _LOGGER.info(f"Entity registry available: {entity_registry is not None}")

        orphaned_entities: list[str] = []

        for entity_id, _entity_entry in entity_registry.entities.items():
            if not entity_id.startswith(f"{platform}."):
                continue

            # Extract device_id from entity_id
            # Format: {platform}.{entity_type}_{device_id} where device_id is 32_153289
            parts = entity_id.split(".")
            if len(parts) >= 2:
                entity_name_and_device = parts[1]  # entity_type_device_id

                # Check if this entity belongs to one of our devices
                for device_id in devices:
                    # Convert device_id from colon format (32:153289)
                    # to underscore format (32_153289)
                    device_id_underscore = device_id.replace(":", "_")

                    # Check if the entity belongs to this device (device_id at the end)
                    if entity_name_and_device.endswith(f"_{device_id_underscore}"):
                        # This entity belongs to our device, check if it's still needed
                        entity_type = entity_name_and_device[
                            : -len(f"_{device_id_underscore}") - 1
                        ]  # Remove "_32_153289"

                        # Check if this entity_type is still required
                        expected_entity_id = (
                            f"{platform}.{entity_type}_" + f"{device_id_underscore}"
                        )
                        if expected_entity_id not in required_entities:
                            orphaned_entities.append(entity_id)
                            _LOGGER.info(
                                "Will remove orphaned %s: %s (type: %s)",
                                platform,
                                entity_id,
                                entity_type,
                            )
                        break

        _LOGGER.info(
            f"Found {len(orphaned_entities)} orphaned {platform} entities to remove"
        )

        removed_count = 0
        for entity_id in orphaned_entities:
            try:
                entity_registry.async_remove(entity_id)
                _LOGGER.info(f"Removed orphaned {platform} entity: {entity_id}")
                removed_count += 1
            except Exception as e:
                _LOGGER.warning(f"Failed to remove {platform} entity {entity_id}: {e}")

        return removed_count

    @staticmethod
    def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
        """Parse an entity ID to extract entity type, name, and device ID.

        Args:
            entity_id: Full entity ID (e.g., "sensor.indoor_abs_humidity_32_153289")

        Returns:
            Tuple of (entity_type, entity_name, device_id) or None if parsing fails
        """
        try:
            # Split on first dot to get type and rest
            if "." not in entity_id:
                return None

            entity_type, rest = entity_id.split(".", 1)

            # Device ID patterns we expect: 32_153289, 10_456789, etc.
            # Look for device ID pattern: _ followed by digits,
            # underscore, digits at the end
            device_id_match = re.search(r"_(\d+_\d+)$", rest)
            if device_id_match:
                device_id = device_id_match.group(
                    1
                )  # The actual device ID part (e.g., "32_153289")
                # Remove the device ID and underscore from the entity name
                entity_name = rest[: device_id_match.start(0)]
            else:
                # No device ID found, return as is
                return entity_type, rest, ""

            # Check if this entity type is known
            known_types = {"sensor", "switch", "binary_sensor", "number"}
            if entity_type not in known_types:
                return None

            return entity_type, entity_name, device_id

        except (ValueError, IndexError):
            return None

    @staticmethod
    def validate_entity_exists(hass: HomeAssistant, entity_id: str) -> bool:
        """Check if an entity exists and is available.

        Args:
            hass: Home Assistant instance
            entity_id: Entity ID to validate

        Returns:
            True if entity exists and is available, False otherwise
        """
        state = hass.states.get(entity_id)
        if not state:
            return False

        return state.state not in ["unavailable", "unknown"]

    @staticmethod
    def get_entity_device_id(entity_id: str) -> str | None:
        """Extract device ID from entity ID.

        Args:
            entity_id: Entity ID to parse

        Returns:
            Device ID in underscore format (e.g., "32_153289") or None if parsing fails
        """
        parsed = EntityHelpers.parse_entity_id(entity_id)
        if parsed:
            _, _, device_id = parsed
            return device_id

        return None

    @staticmethod
    def get_entities_for_device(
        hass: HomeAssistant, device_id: str, entity_type: str | None = None
    ) -> list[str]:
        """Get all entity IDs for a specific device.

        Args:
            hass: Home Assistant instance
            device_id: Device ID to search for
            entity_type: Optional entity type filter

        Returns:
            List of entity IDs for the device
        """
        entity_ids = []

        # Get all states
        all_states = hass.states.async_all()

        for state in all_states:
            entity_id = state.entity_id

            # Filter by entity type if specified
            if entity_type and not entity_id.startswith(f"{entity_type}."):
                continue

            # Check if this entity belongs to the device
            if EntityHelpers.get_entity_device_id(entity_id) == device_id:
                entity_ids.append(entity_id)

        return entity_ids

    @staticmethod
    def filter_entities_by_patterns(
        entity_ids: list[str], patterns: list[str]
    ) -> list[str]:
        """Filter entity IDs by wildcard patterns.

        Args:
            entity_ids: List of entity IDs to filter
            patterns: List of patterns (with * wildcards)

        Returns:
            List of entity IDs that match any pattern
        """
        matching_entities = []

        for entity_id in entity_ids:
            for pattern in patterns:
                if pattern.endswith("*"):
                    prefix = pattern[:-1]  # Remove the *
                    if entity_id.startswith(prefix):
                        matching_entities.append(entity_id)
                        break
                elif entity_id == pattern:
                    matching_entities.append(entity_id)
                    break

        return matching_entities

    @staticmethod
    def generate_entity_patterns_for_feature(
        feature_config: dict[str, Any],
    ) -> list[str]:
        """Generate entity patterns for a feature configuration.

        Args:
            feature_config: Feature configuration dictionary

        Returns:
            List of entity patterns
        """
        patterns = []
        required_entities = feature_config.get("required_entities", {})

        for entity_type, entity_names in required_entities.items():
            for entity_name in entity_names:
                # Use proper singularization for entity types
                entity_base_type = _singularize_entity_type(entity_type)
                patterns.append(f"{entity_base_type}.{entity_name}_*")

        return patterns


# Convenience functions for easy access
def generate_entity_id(entity_type: str, entity_name: str, device_id: str) -> str:
    """Generate a consistent entity ID from type, name, and device ID."""
    return EntityHelpers.generate_entity_id(entity_type, entity_name, device_id)


def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse an entity ID to extract entity type, name, and device ID."""
    return EntityHelpers.parse_entity_id(entity_id)


def get_entity_device_id(entity_id: str) -> str | None:
    """Extract device ID from entity ID."""
    return EntityHelpers.get_entity_device_id(entity_id)


def get_entities_for_device(
    hass: HomeAssistant, device_id: str, entity_type: str | None = None
) -> list[str]:
    """Get all entity IDs for a specific device."""
    return EntityHelpers.get_entities_for_device(hass, device_id, entity_type)


def filter_entities_by_patterns(
    entity_ids: list[str], patterns: list[str]
) -> list[str]:
    """Filter entity IDs by wildcard patterns."""
    return EntityHelpers.filter_entities_by_patterns(entity_ids, patterns)


def generate_entity_patterns_for_feature(feature_config: dict[str, Any]) -> list[str]:
    """Generate entity patterns for a feature configuration."""
    return EntityHelpers.generate_entity_patterns_for_feature(feature_config)


__all__ = [
    "EntityHelpers",
    "generate_entity_id",
    "parse_entity_id",
    "get_entity_device_id",
    "get_entities_for_device",
    "filter_entities_by_patterns",
    "generate_entity_patterns_for_feature",
]
