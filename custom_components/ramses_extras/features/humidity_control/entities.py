"""Humidity Control Entities.

This module provides entity definitions specific to humidity control functionality,
including sensors, switches, numbers, and binary sensors for humidity management.
"""

import logging
from typing import Any

from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_registry import async_get

from ...helpers.entity import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class HumidityEntities:
    """Manages humidity control entities.

    This class handles the creation, registration, and management of all
    humidity-related entities including sensors, switches, numbers, and binary sensors.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize humidity entities manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        self.hass = hass
        self.config_entry = config_entry

        # Entity registry
        self._entities: dict[str, dict[str, Any]] = {}
        self._entity_configs = self._get_entity_configs()

        _LOGGER.info("HumidityControl entities initialized")

    def _get_entity_configs(self) -> dict[str, dict[str, Any]]:
        """Get configuration for all humidity control entities.

        Returns:
            Dictionary mapping entity types to configurations
        """
        return {
            "sensors": {
                "indoor_absolute_humidity": {
                    "name": "Indoor Absolute Humidity",
                    "unit": "g/m³",
                    "device_class": None,
                    "icon": "mdi:water-percent",
                    "category": "diagnostic",
                },
                "outdoor_absolute_humidity": {
                    "name": "Outdoor Absolute Humidity",
                    "unit": "g/m³",
                    "device_class": None,
                    "icon": "mdi:weather-partly-cloudy",
                    "category": "diagnostic",
                },
            },
            "switches": {
                "dehumidify": {
                    "name": "Dehumidify",
                    "icon": "mdi:air-humidifier",
                    "category": "control",
                },
            },
            "numbers": {
                "relative_humidity_minimum": {
                    "name": "Relative Humidity Minimum",
                    "unit": "%",
                    "device_class": None,
                    "icon": "mdi:water-minus",
                    "category": "config",
                    "min_value": 30,
                    "max_value": 80,
                    "step": 1,
                    "default_value": 40,
                },
                "relative_humidity_maximum": {
                    "name": "Relative Humidity Maximum",
                    "unit": "%",
                    "device_class": None,
                    "icon": "mdi:water-plus",
                    "category": "config",
                    "min_value": 50,
                    "max_value": 90,
                    "step": 1,
                    "default_value": 60,
                },
                "absolute_humidity_offset": {
                    "name": "Absolute Humidity Offset",
                    "unit": "g/m³",
                    "device_class": None,
                    "icon": "mdi:swap-horizontal",
                    "category": "config",
                    "min_value": -3.0,
                    "max_value": 3.0,
                    "step": 0.1,
                    "default_value": 0.4,
                },
            },
            "binary_sensors": {
                "dehumidifying_active": {
                    "name": "Dehumidifying Active",
                    "device_class": "running",
                    "icon": "mdi:air-humidifier",
                    "category": "diagnostic",
                },
            },
        }

    async def async_setup_entities(self, device_id: str) -> dict[str, list[str]]:
        """Set up all humidity control entities for a device.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary mapping entity types to created entity IDs
        """
        _LOGGER.info(f"Setting up humidity entities for device {device_id}")

        created_entities: dict[str, list[str]] = {
            "sensors": [],
            "switches": [],
            "numbers": [],
            "binary_sensors": [],
        }

        try:
            # Create sensors
            for sensor_type in self._entity_configs["sensors"]:
                sensor_entity_id: str | None = await self._create_sensor_entity(
                    device_id, sensor_type
                )
                if sensor_entity_id:
                    created_entities["sensors"].append(sensor_entity_id)

            # Create switches
            for switch_type in self._entity_configs["switches"]:
                switch_entity_id: str | None = await self._create_switch_entity(
                    device_id, switch_type
                )
                if switch_entity_id:
                    created_entities["switches"].append(switch_entity_id)

            # Create number entities
            for number_type in self._entity_configs["numbers"]:
                number_entity_id: str | None = await self._create_number_entity(
                    device_id, number_type
                )
                if number_entity_id:
                    created_entities["numbers"].append(number_entity_id)

            # Create binary sensors
            for binary_type in self._entity_configs["binary_sensors"]:
                binary_entity_id: str | None = await self._create_binary_sensor_entity(
                    device_id, binary_type
                )
                if binary_entity_id:
                    created_entities["binary_sensors"].append(binary_entity_id)
            _LOGGER.info(
                f"Created {sum(len(entities) for entities in created_entities.values())} "  # noqa: E501
                f"humidity entities for device {device_id}",
            )

            return created_entities

        except Exception as e:
            _LOGGER.error(f"Failed to set up humidity entities: {e}")
            return created_entities

    async def _create_sensor_entity(
        self, device_id: str, sensor_type: str
    ) -> str | None:
        """Create a sensor entity.

        Args:
            device_id: Device identifier
            sensor_type: Type of sensor

        Returns:
            Entity ID or None if creation failed
        """
        try:
            config = self._entity_configs["sensors"][sensor_type]
            entity_id = f"sensor.{sensor_type}_{device_id}"

            # This would register the entity with Home Assistant
            # For now, we'll just log the creation
            _LOGGER.debug(f"Creating sensor: {entity_id}")

            # Store entity information
            self._entities[entity_id] = {
                "device_id": device_id,
                "type": "sensor",
                "subtype": sensor_type,
                "config": config,
            }

            return entity_id

        except Exception as e:
            _LOGGER.error(f"Failed to create sensor entity: {e}")
            return None

    async def _create_switch_entity(
        self, device_id: str, switch_type: str
    ) -> str | None:
        """Create a switch entity.

        Args:
            device_id: Device identifier
            switch_type: Type of switch

        Returns:
            Entity ID or None if creation failed
        """
        try:
            config = self._entity_configs["switches"][switch_type]
            entity_id = f"switch.{switch_type}_{device_id}"

            _LOGGER.debug(f"Creating switch: {entity_id}")

            self._entities[entity_id] = {
                "device_id": device_id,
                "type": "switch",
                "subtype": switch_type,
                "config": config,
            }

            return entity_id

        except Exception as e:
            _LOGGER.error(f"Failed to create switch entity: {e}")
            return None

    async def _create_number_entity(
        self, device_id: str, number_type: str
    ) -> str | None:
        """Create a number entity.

        Args:
            device_id: Device identifier
            number_type: Type of number entity

        Returns:
            Entity ID or None if creation failed
        """
        try:
            config = self._entity_configs["numbers"][number_type]
            entity_id = f"number.{number_type}_{device_id}"

            _LOGGER.debug(f"Creating number: {entity_id}")

            self._entities[entity_id] = {
                "device_id": device_id,
                "type": "number",
                "subtype": number_type,
                "config": config,
            }

            return entity_id

        except Exception as e:
            _LOGGER.error(f"Failed to create number entity: {e}")
            return None

    async def _create_binary_sensor_entity(
        self, device_id: str, binary_type: str
    ) -> str | None:
        """Create a binary sensor entity.

        Args:
            device_id: Device identifier
            binary_type: Type of binary sensor

        Returns:
            Entity ID or None if creation failed
        """
        try:
            config = self._entity_configs["binary_sensors"][binary_type]
            entity_id = f"binary_sensor.{binary_type}_{device_id}"

            _LOGGER.debug(f"Creating binary sensor: {entity_id}")

            self._entities[entity_id] = {
                "device_id": device_id,
                "type": "binary_sensor",
                "subtype": binary_type,
                "config": config,
            }

            return entity_id

        except Exception as e:
            _LOGGER.error(f"Failed to create binary sensor entity: {e}")
            return None

    async def async_remove_entities(self, device_id: str) -> None:
        """Remove all humidity entities for a device.

        Args:
            device_id: Device identifier
        """
        _LOGGER.info(f"Removing humidity entities for device {device_id}")

        # Find entities for this device
        device_entities: list[str] = [
            entity_id
            for entity_id, info in self._entities.items()
            if info["device_id"] == device_id
        ]

        # Remove entities
        for entity_id in device_entities:
            try:
                if entity_id in self._entities:
                    del self._entities[entity_id]
                    _LOGGER.info(f"Removed entity: {entity_id}")
            except Exception as e:
                _LOGGER.error(f"Failed to remove entity {entity_id}: {e}")

        _LOGGER.info(f"Removed {len(device_entities)} humidity entities")

    def get_entity_config(
        self, entity_type: str, entity_subtype: str
    ) -> dict[str, Any] | None:
        """Get configuration for a specific entity type.

        Args:
            entity_type: Type of entity (sensor, switch, number, binary_sensor)
            entity_subtype: Subtype of entity

        Returns:
            Entity configuration or None if not found
        """
        return self._entity_configs.get(entity_type, {}).get(entity_subtype)

    def get_device_entities(self, device_id: str) -> dict[str, list[str]]:
        """Get all entities for a specific device.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary mapping entity types to entity IDs
        """
        device_entities: dict[str, list[str]] = {
            "sensors": [],
            "switches": [],
            "numbers": [],
            "binary_sensors": [],
        }

        for entity_id, info in self._entities.items():
            if info["device_id"] == device_id:
                entity_type = info["type"]
                if entity_type in device_entities:
                    device_entities[entity_type].append(entity_id)

        return device_entities

    def get_all_entities(self) -> dict[str, dict[str, Any]]:
        """Get all managed entities.

        Returns:
            Dictionary mapping entity IDs to entity information
        """
        return self._entities.copy()

    def get_entity_statistics(self) -> dict[str, int]:
        """Get entity statistics.

        Returns:
            Dictionary with entity counts by type
        """
        stats = {
            "sensors": 0,
            "switches": 0,
            "numbers": 0,
            "binary_sensors": 0,
            "total": 0,
        }

        for entity_id, info in self._entities.items():
            entity_type = info["type"]
            if entity_type in stats:
                stats[entity_type] += 1
            stats["total"] += 1

        return stats


# Entity factory function
def create_humidity_entities(
    hass: HomeAssistant, config_entry: Any
) -> HumidityEntities:
    """Create humidity entities instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HumidityEntities instance
    """
    return HumidityEntities(hass, config_entry)


__all__ = [
    "HumidityEntities",
    "create_humidity_entities",
]
