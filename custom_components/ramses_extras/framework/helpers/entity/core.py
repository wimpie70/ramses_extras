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

    # First try to get required_entities from the const data
    const_key = f"{feature_id.upper()}_CONST"
    if hasattr(feature_module, const_key):
        const_data = getattr(feature_module, const_key, {})
        required_entities: dict[str, list[str]] = const_data.get(
            "required_entities", {}
        )
        if required_entities:
            return required_entities

    # Fallback to device entity mapping for backwards compatibility
    mapping_key = f"{feature_id.upper()}_DEVICE_ENTITY_MAPPING"
    device_mapping = getattr(feature_module, mapping_key, {})

    # Convert device mapping to required entities format
    required_entities = {}
    for device_type, entity_names in device_mapping.items():
        entity_type = f"{device_type.lower()}s"  # Convert to plural
        required_entities[entity_type] = entity_names

    return required_entities


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
            Generated entity ID (e.g., "sensor.32_153289_indoor_absolute_humidity")
        """
        return f"{entity_type}.{device_id}_{entity_name}"

    @staticmethod
    def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
        """Parse entity ID to extract type, name, and device ID.

        Args:
            entity_id: Entity identifier
            (e.g., "sensor.32_153289_indoor_absolute_humidity")

        Returns:
            Tuple of (entity_type, entity_name, device_id) or None if parsing fails
        """
        # Handle the new pattern: type.device_id_name
        # Example: "sensor.32_153289_indoor_absolute_humidity"
        if "." in entity_id:
            dot_index = entity_id.index(".")
            entity_type = entity_id[:dot_index]
            remainder = entity_id[dot_index + 1 :]

            # Split remainder into device_id and entity_name
            parts = remainder.split("_", 1)  # Split only on first underscore
            if len(parts) >= 2:
                device_id = parts[0]
                entity_name = parts[1]
                return entity_type, entity_name, device_id

        # Fallback: simple pattern for other cases
        pattern = r"^(\w+)\.([\w:]+)_(.+)$"
        match = re.match(pattern, entity_id)
        if match:
            return match.group(1), match.group(3), match.group(2)
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
                # Pattern for matching entities with device_id prefix
                patterns.append(f"{entity_base_type}.*_{entity_name}")

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
                        entity_type, entity_name, device_id
                    )
                    if entity_id:
                        entity_ids.append(entity_id)

        except Exception as e:
            _LOGGER.debug(f"Could not get entity IDs from registry: {e}")
            # Fallback: return empty list if registry is not available
            # This maintains backward compatibility while avoiding hardcoded values

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
    config_types = [
        "SENSOR_CONFIGS",
        "SWITCH_CONFIGS",
        "NUMBER_CONFIGS",
        "BOOLEAN_CONFIGS",
    ]

    for config_type in config_types:
        config_key = f"{feature_id.upper()}_{config_type}"
        if hasattr(feature_module, config_key):
            configs = getattr(feature_module, config_key, {})

            for entity_name, config in configs.items():
                entity_template = config.get("entity_template", "")
                if entity_template:
                    # Replace {device_id} placeholder with the actual device_id
                    entity_id = entity_template.replace(
                        "{device_id}", device_id_underscore
                    )
                    # Use the entity_name as the state key
                    mappings[entity_name] = entity_id

    return mappings


# Export all functions and classes
__all__ = [
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


async def generate_entity_patterns_for_feature(feature_id: str) -> list[str]:
    """Generate entity patterns for a specific feature.

    This is a convenience wrapper around
    EntityHelpers.generate_entity_patterns_for_feature.
    """
    return await EntityHelpers.generate_entity_patterns_for_feature(feature_id)
