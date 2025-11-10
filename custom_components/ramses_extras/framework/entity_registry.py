"""Core entity registry shared across all features.

This module provides a registry pattern for managing entity definitions
across the Ramses Extras framework, avoiding duplication while maintaining
clean feature boundaries.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)


# Core entity definitions that can be used by multiple features
CORE_ENTITY_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
        "entity_type": "sensor",  # Type classification for registry
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
        "entity_type": "sensor",  # Type classification for registry
    },
    "dehumidify": {
        "name_template": "Dehumidify",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
        "entity_type": "switch",  # Type classification for registry
    },
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
        "entity_type": "binary_sensor",  # Type classification for registry
    },
}

# Core device type mappings
CORE_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": ["dehumidify"],
        "binary_sensors": ["dehumidifying_active"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
    },
}


class EntityRegistry:
    """Registry for managing entity definitions across features.

    This class provides a centralized registry for entity configurations,
    allowing features to register entities without duplication while
    maintaining clean boundaries between core and feature-specific entities.
    """

    def __init__(self) -> None:
        """Initialize the entity registry with core configurations."""
        self._entities: dict[str, dict[str, Any]] = CORE_ENTITY_CONFIGS.copy()
        self._device_mappings: dict[str, dict[str, list[str]]] = (
            CORE_DEVICE_ENTITY_MAPPING.copy()
        )
        self._registered_features: set[str] = set()
        self._feature_implementations: dict[str, dict[str, Any]] = {}
        _LOGGER.info(
            "EntityRegistry initialized with %d core entities", len(self._entities)
        )

    def register_entity(self, entity_name: str, config: dict[str, Any]) -> None:
        """Register a new entity definition.

        Args:
            entity_name: Unique name for the entity
            config: Entity configuration dictionary
        """
        if entity_name in self._entities:
            _LOGGER.warning(
                "Entity '%s' already registered, overwriting existing configuration",
                entity_name,
            )

        self._entities[entity_name] = config
        _LOGGER.debug("Registered entity: %s", entity_name)

    def register_device_mapping(
        self, device_type: str, mapping: dict[str, list[str]]
    ) -> None:
        """Register a new device type to entity mapping.

        Args:
            device_type: Type of device (e.g., "HvacVentilator")
            mapping: Dictionary mapping entity types to entity names
        """
        if device_type in self._device_mappings:
            _LOGGER.warning(
                "Device type '%s' already registered, merging mappings", device_type
            )
            # Merge with existing mapping
            existing_mapping = self._device_mappings[device_type]
            for entity_type, entities in mapping.items():
                if entity_type in existing_mapping:
                    # Merge entity lists, avoiding duplicates
                    existing_entities = set(existing_mapping[entity_type])
                    new_entities = set(entities)
                    existing_mapping[entity_type] = list(
                        existing_entities.union(new_entities)
                    )
                else:
                    existing_mapping[entity_type] = entities
        else:
            self._device_mappings[device_type] = mapping

        _LOGGER.debug("Registered device mapping: %s", device_type)

    def register_feature(self, feature_name: str) -> None:
        """Mark a feature as registered for tracking purposes.

        Args:
            feature_name: Name of the feature being registered
        """
        self._registered_features.add(feature_name)
        _LOGGER.debug("Registered feature: %s", feature_name)

    def register_feature_implementation(
        self, feature_id: str, implementation_config: dict[str, Any]
    ) -> None:
        """Register a feature implementation with the framework.

        Args:
            feature_id: Unique identifier for the feature
            implementation_config: Feature implementation configuration
        """
        self._feature_implementations[feature_id] = implementation_config
        self.register_feature(feature_id)
        _LOGGER.info("Registered feature implementation: %s", feature_id)

    def get_feature_implementation(self, feature_id: str) -> dict[str, Any] | None:
        """Get feature implementation configuration.

        Args:
            feature_id: Feature identifier

        Returns:
            Feature implementation configuration or None if not found
        """
        return self._feature_implementations.get(feature_id)

    def get_entity_config(self, entity_name: str) -> dict[str, Any] | None:
        """Get entity configuration by name.

        Args:
            entity_name: Name of the entity

        Returns:
            Entity configuration dictionary or None if not found
        """
        return self._entities.get(entity_name)

    def get_device_mapping(self, device_type: str) -> dict[str, list[str]] | None:
        """Get device type to entity mapping.

        Args:
            device_type: Type of device

        Returns:
            Device mapping dictionary or None if not found
        """
        return self._device_mappings.get(device_type)

    def get_all_entities(self) -> dict[str, dict[str, Any]]:
        """Get all registered entity configurations.

        Returns:
            Dictionary mapping entity names to configurations
        """
        return self._entities.copy()

    def get_entities_by_type(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Get all entities of a specific type.

        Args:
            entity_type: Type of entity ("sensor", "switch", "binary_sensor", "number")

        Returns:
            Dictionary of entities of the specified type
        """
        filtered_entities = {}
        for entity_name, config in self._entities.items():
            if config.get("entity_type") == entity_type:
                filtered_entities[entity_name] = config
        return filtered_entities

    def get_registered_features(self) -> set[str]:
        """Get Set of all registered features.

        Returns:
            Set of feature names
        """
        return self._registered_features.copy()

    def is_entity_registered(self, entity_name: str) -> bool:
        """Check if an entity is registered.

        Args:
            entity_name: Name of the entity

        Returns:
            True if entity is registered, False otherwise
        """
        return entity_name in self._entities

    def get_entity_type(self, entity_name: str) -> str | None:
        """Get the type of a specific entity.

        Args:
            entity_name: Name of the entity

        Returns:
            Entity type string or None if not found
        """
        config = self._entities.get(entity_name)
        return config.get("entity_type") if config else None

    def validate_entity_config(self, entity_name: str, config: dict[str, Any]) -> bool:
        """Validate entity configuration completeness.

        Args:
            entity_name: Name of the entity
            config: Configuration to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        required_fields = [
            "name_template",
            "supported_device_types",
            "entity_template",
            "entity_type",
        ]
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            _LOGGER.error(
                "Entity '%s' configuration missing required fields: %s",
                entity_name,
                missing_fields,
            )
            return False

        # Validate entity type
        valid_types = ["sensor", "switch", "binary_sensor", "number"]
        if config["entity_type"] not in valid_types:
            _LOGGER.error(
                "Entity '%s' has invalid type '%s', must be one of: %s",
                entity_name,
                config["entity_type"],
                valid_types,
            )
            return False

        return True

    def get_statistics(self) -> dict[str, Any]:
        """Get registry statistics for debugging/monitoring.

        Returns:
            Dictionary containing registry statistics
        """
        entity_types = {}
        for entity_name, config in self._entities.items():
            entity_type = config.get("entity_type", "unknown")
            if entity_type not in entity_types:
                entity_types[entity_type] = 0
            entity_types[entity_type] += 1

        return {
            "total_entities": len(self._entities),
            "entity_types": entity_types,
            "device_types": len(self._device_mappings),
            "registered_features": len(self._registered_features),
            "feature_names": list(self._registered_features),
        }


# Global registry instance - singleton pattern
entity_registry = EntityRegistry()


# Convenience functions for easy access
def get_entity_config(entity_name: str) -> dict[str, Any] | None:
    """Get entity configuration from registry.

    Args:
        entity_name: Name of the entity

    Returns:
        Entity configuration dictionary or None if not found
    """
    return entity_registry.get_entity_config(entity_name)


def get_device_mapping(device_type: str) -> dict[str, list[str]] | None:
    """Get device type to entity mapping from registry.

    Args:
        device_type: Type of device

    Returns:
        Device mapping dictionary or None if not found
    """
    return entity_registry.get_device_mapping(device_type)


def get_all_entities() -> dict[str, dict[str, Any]]:
    """Get all registered entity configurations.

    Returns:
        Dictionary mapping entity names to configurations
    """
    return entity_registry.get_all_entities()


def register_entity(entity_name: str, config: dict[str, Any]) -> None:
    """Register a new entity with the registry.

    Args:
        entity_name: Unique name for the entity
        config: Entity configuration dictionary
    """
    entity_registry.register_entity(entity_name, config)


def get_entity_type(entity_name: str) -> str | None:
    """Get the type of a specific entity.

    Args:
        entity_name: Name of the entity

    Returns:
        Entity type string or None if not found
    """
    return entity_registry.get_entity_type(entity_name)


def register_feature_implementation(
    feature_id: str, implementation_config: dict[str, Any]
) -> None:
    """Register a feature implementation with the framework.

    Args:
        feature_id: Unique identifier for the feature
        implementation_config: Feature implementation configuration
    """
    entity_registry.register_feature_implementation(feature_id, implementation_config)


def get_feature_implementation(feature_id: str) -> dict[str, Any] | None:
    """Get feature implementation configuration.

    Args:
        feature_id: Feature identifier

    Returns:
        Feature implementation configuration or None if not found
    """
    return entity_registry.get_feature_implementation(feature_id)


def get_registry_statistics() -> dict[str, Any]:
    """Get registry statistics.

    Returns:
        Dictionary containing registry statistics
    """
    return entity_registry.get_statistics()
