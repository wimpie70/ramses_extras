"""Generic platform entity base classes for Ramses Extras framework.

This module provides reusable base classes that extract common patterns from
platform implementations across all features, reducing code duplication and
ensuring consistency.

Common patterns extracted:
- Entity ID generation and naming
- Device discovery and filtering
- Configuration handling
- State management
- Base entity attributes
"""

import logging
from typing import Any, Awaitable, Callable

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, StateType

from ..helpers.entity.core import EntityHelpers
from .base_entity import ExtrasBaseEntity

_LOGGER = logging.getLogger(__name__)


class ExtrasPlatformEntity(ExtrasBaseEntity, Entity):
    """Generic base class for all platform entities.

    This class provides common functionality for all platform entities including
    device filtering, entity naming, and configuration handling.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        entity_type: str,
        config: dict[str, Any],
        platform_type: str,
    ) -> None:
        """Initialize platform entity.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param entity_type: Type of entity (e.g., "switch", "number")
        :param config: Entity configuration dictionary
        :param platform_type: Platform type (e.g., "switch", "number", "sensor")
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, entity_type, config)
        # Initialize Entity
        Entity.__init__(self)

        self._platform_type = platform_type
        self._entity_config = config

        # Generate entity ID and name using EntityHelpers
        self._setup_entity_identity()

    def _setup_entity_identity(self) -> None:
        """Setup entity ID, unique ID, and name from configuration.

        This method extracts the common entity identity setup pattern
        that was duplicated across all platform files.
        """
        # Convert device_id to underscore format for entity generation
        device_id_underscore = self.device_id.replace(":", "_")

        # Get entity template from config (fallback to default pattern)
        entity_template = self._entity_config.get(
            "entity_template", "{entity_type}_{device_id}"
        )

        try:
            # Generate entity_id using automatic format detection
            self.entity_id = EntityHelpers.generate_entity_name_from_template(
                self._platform_type,
                entity_template,
                device_id=device_id_underscore,
            )
            self._attr_unique_id = self.entity_id.replace(f"{self._platform_type}.", "")
        except Exception as e:
            _LOGGER.warning(
                f"Entity name generation failed for {self._entity_type} "
                f"on device {device_id_underscore}: {e}. "
                "This indicates a configuration issue that needs to be resolved."
            )

        # Set display name from template
        name_template = self._entity_config.get(
            "name_template", f"{self._entity_type} {{device_id}}"
        )
        self._attr_name = name_template.format(
            device_id=device_id_underscore, entity_type=self._entity_type
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name or f"{self._entity_type} {self.device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Entity added to Home Assistant."""
        _LOGGER.debug(
            "%s entity %s added to hass", self._platform_type, self._attr_name
        )
        await super().async_added_to_hass()

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from device."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "entity_type": self._entity_type,
            "platform_type": self._platform_type,
            "device_id": self.device_id,
        }


class ExtrasSwitchEntity(ExtrasPlatformEntity, SwitchEntity):
    """Generic switch entity for all features.

    This class provides common switch functionality that can be inherited
    by feature-specific switch implementations.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize switch entity.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param switch_type: Type of switch entity
        :param config: Entity configuration
        """
        super().__init__(hass, device_id, switch_type, config, "switch")

        # Initialize switch-specific attributes
        self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info("Switch %s turned ON", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info("Switch %s turned OFF", self._attr_name)


class ExtrasNumberEntity(ExtrasPlatformEntity, NumberEntity):
    """Generic number entity for all features.

    This class provides common number entity functionality that can be inherited
    by feature-specific number implementations.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        number_type: str,
        config: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize number entity.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param number_type: Type of number entity
        :param config: Entity configuration
        :param config_entry: Configuration entry
        """
        super().__init__(hass, device_id, number_type, config, "number")

        self.config_entry = config_entry

        # Set number-specific attributes from config
        self._attr_native_unit_of_measurement = config.get("unit", "%")
        self._attr_device_class = config.get("device_class")
        self._attr_native_min_value = config.get("min_value", 0.0)
        self._attr_native_max_value = config.get("max_value", 100.0)
        self._attr_native_step = config.get("step", 1.0)

        # Initialize value
        self._native_value: float = config.get("default_value", 50.0)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._native_value = value
        self.async_write_ha_state()

        # Save to config entry if available
        if self.config_entry:
            await self._save_value_to_config(value)

        _LOGGER.info(
            "Number %s value set to %s (min: %s, max: %s, step: %s)",
            self._attr_name,
            value,
            self._attr_native_min_value,
            self._attr_native_max_value,
            self._attr_native_step,
        )

    async def _save_value_to_config(self, value: float) -> None:
        """Save number value to config entry.

        :param value: Value to save
        """
        if not self.config_entry:
            return

        device_key = self.device_id.replace(":", "_")
        feature_id = self._entity_config.get("feature_id", "default")

        options = dict(self.config_entry.options)
        if feature_id not in options:
            options[feature_id] = {}
        if device_key not in options[feature_id]:
            options[feature_id][device_key] = {}

        options[feature_id][device_key][self._entity_type] = value
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "number_type": self._entity_type,
            "min_value": self._attr_native_min_value,
            "max_value": self._attr_native_max_value,
            "step": self._attr_native_step,
        }


class ExtrasBinarySensorEntity(ExtrasPlatformEntity, BinarySensorEntity):
    """Generic binary sensor entity for all features.

    This class provides common binary sensor functionality that can be inherited
    by feature-specific binary sensor implementations.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        binary_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize binary sensor entity.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param binary_type: Type of binary sensor
        :param config: Entity configuration
        """
        super().__init__(hass, device_id, binary_type, config, "binary_sensor")

        # Set binary sensor-specific attributes
        self._attr_device_class = config.get("device_class")

        # Initialize state
        self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if binary sensor is on."""
        return self._is_on

    def set_state(self, is_on: bool) -> None:
        """Set the binary sensor state (used by automation)."""
        self._is_on = is_on
        self.async_write_ha_state()
        _LOGGER.debug("Binary sensor %s state set to %s", self._attr_name, is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the binary sensor."""
        self.set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the binary sensor."""
        self.set_state(False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "binary_type": self._entity_type,
        }


class ExtrasSensorEntity(ExtrasPlatformEntity, SensorEntity):
    """Generic sensor entity for all features.

    This class provides common sensor functionality that can be inherited
    by feature-specific sensor implementations.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize sensor entity.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param sensor_type: Type of sensor entity
        :param config: Entity configuration
        """
        super().__init__(hass, device_id, sensor_type, config, "sensor")

        # Set sensor-specific attributes from config
        self._attr_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_icon = config.get("icon")
        self._attr_entity_category = config.get("entity_category")

        # Initialize state
        self._attr_native_value: StateType = None

    @property
    def state(self) -> Any:
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def native_value(self) -> StateType:
        """Return the native value of the sensor."""
        return self._attr_native_value

    def set_native_value(self, value: StateType) -> None:
        """Set the native value of the sensor."""
        self._attr_native_value = value
        self.async_write_ha_state()


# Platform setup helper functions


async def generic_platform_setup(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    feature_id: str,
    platform_configs: dict[str, dict[str, Any]],
    entity_factory: Callable[
        [HomeAssistant, str, ConfigEntry | None], Awaitable[list[Entity]]
    ],
    platform_type: str,
) -> None:
    """Set up platform entities for a feature.

    This function extracts the common setup pattern used across all platform files,
    reducing code duplication and ensuring consistency.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry
    :param async_add_entities: Add entities callback
    :param feature_id: Feature identifier for logging
    :param platform_configs: Dictionary of platform configurations
    :param entity_factory: Factory function to create entities
    :param platform_type: Type of platform (e.g., "switch", "number")
    """
    _LOGGER.info("Setting up %s %s platform", feature_id, platform_type)

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        "%s %s platform: found %d devices: %s",
        feature_id,
        platform_type,
        len(devices),
        devices,
    )

    entities = []
    for device_id in devices:
        try:
            # Create entities for this device
            device_entities = await entity_factory(hass, device_id, config_entry)
            entities.extend(device_entities)
            _LOGGER.info(
                "Created %d %s entities for device %s",
                len(device_entities),
                platform_type,
                device_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to create %s entities for device %s: %s",
                platform_type,
                device_id,
                e,
            )

    _LOGGER.info("Total %s entities created: %d", platform_type, len(entities))
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info(
            "%s %s entities added to Home Assistant", feature_id, platform_type
        )


def filter_devices_by_config(devices: list[str], config: dict[str, Any]) -> list[str]:
    """Filter devices based on configuration supported device types.

    :param devices: List of device IDs
    :param config: Configuration dictionary with supported_device_types
    :return: Filtered list of device IDs
    """
    supported_types = config.get("supported_device_types", [])
    if not supported_types:
        return devices

    filtered_devices = []
    for device_id in devices:
        # Simple filtering logic - can be enhanced based on actual device type detection
        # For now, this assumes all devices are supported if they match the pattern
        if any(supported_type in device_id for supported_type in supported_types):
            filtered_devices.append(device_id)

    return filtered_devices


__all__ = [
    "ExtrasPlatformEntity",
    "ExtrasSwitchEntity",
    "ExtrasNumberEntity",
    "ExtrasBinarySensorEntity",
    "ExtrasSensorEntity",
    "generic_platform_setup",
    "filter_devices_by_config",
]
