"""Humidity Control Binary Sensor Platform.

This module provides Home Assistant binary sensor platform integration
for humidity control feature.
"""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes import ExtrasBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control binary sensor platform."""
    _LOGGER.info("Setting up humidity control binary sensors")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])

    binary_sensors = []
    for device_id in devices:
        # Create humidity control binary sensors
        binary_sensors.extend(
            await create_humidity_control_binary_sensors(hass, device_id, config_entry)
        )

    async_add_entities(binary_sensors, True)


async def create_humidity_control_binary_sensors(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[BinarySensorEntity]:
    """Create humidity control binary sensors for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of binary sensor entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, config_entry)
    binary_sensors = []

    # Create dehumidifying_active binary sensor
    config = entity_manager.get_entity_config("binary_sensors", "dehumidifying_active")
    if config:
        binary_sensor = HumidityControlBinarySensor(
            hass, device_id, "dehumidifying_active", config
        )
        binary_sensors.append(binary_sensor)

    return binary_sensors


def create_humidity_control_binary_sensor(
    hass: HomeAssistant, device_id: str, binary_type: str, config: dict[str, Any]
) -> BinarySensorEntity:
    """Create a humidity control binary sensor (legacy function for compatibility)."""
    return HumidityControlBinarySensor(hass, device_id, binary_type, config)


class HumidityControlBinarySensor(BinarySensorEntity, ExtrasBaseEntity):
    """Binary sensor for humidity control feature.

    This class handles the state of dehumidifying equipment and
    tracks humidity control automation state.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        binary_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity control binary sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            binary_type: Type of binary sensor
            config: Binary sensor configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, binary_type, config)

        # Set binary sensor-specific attributes
        self._binary_type = binary_type
        self._attr_device_class = config.get("device_class")

        # Set unique_id and name
        device_id_underscore = device_id.replace(":", "_")
        self._attr_unique_id = f"{binary_type}_{device_id_underscore}"

        name_template = config.get(
            "name_template", f"{binary_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        # Initialize state
        self._is_on = False
        self._current_fan_speed = "auto"  # Track current fan speed

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._binary_type} {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()

        # Register this binary sensor with the automation manager
        await self._register_with_automation()

        _LOGGER.debug("Binary sensor %s added to hass", self._attr_name)

    async def _register_with_automation(self) -> None:
        """Register this binary sensor with the humidity automation manager."""
        try:
            # First, ensure the automation storage exists (legacy compatibility)
            ramses_data = self.hass.data.setdefault("ramses_extras", {})
            automations = ramses_data.setdefault("automations", {})

            # Import automation creation functions
            from ..automation import create_humidity_control_automation
            from ..config import HumidityConfig

            # Get or create automation for this device
            if self._device_id not in automations:
                # Create the automation manager
                config_entries = self.hass.config_entries.async_entries("ramses_extras")
                if config_entries:
                    config_entry = config_entries[0]
                    automation = create_humidity_control_automation(
                        self.hass, config_entry
                    )

                    # Start the automation
                    await automation.start()
                    automations[self._device_id] = automation
                    _LOGGER.info(
                        "Created new humidity automation for device %s", self._device_id
                    )
                else:
                    _LOGGER.error("Could not get config entry for automation creation")
                    return

            # Set the binary sensor reference in the automation
            automation = automations[self._device_id]
            automation.set_binary_sensor(self)

            _LOGGER.info(
                "Registered binary sensor %s with humidity automation for device %s",
                self._attr_name,
                self._device_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to register binary sensor %s with automation: %s",
                self._attr_name,
                e,
            )

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor state is on."""
        # For dehumidifying_active: read-only, controlled by automation
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the binary sensor - controlled by automation only."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned ON by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the binary sensor - controlled by automation only."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned OFF by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    def set_state(self, is_on: bool) -> None:
        """Set the binary sensor state (used by automation)."""
        self._is_on = is_on
        self.async_write_ha_state()
        _LOGGER.debug("Binary sensor %s state set to %s", self._attr_name, is_on)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "binary_type": self._binary_type,
            "controlled_by": "automation",
            "current_fan_speed": self._current_fan_speed,
        }


__all__ = [
    "HumidityControlBinarySensor",
    "async_setup_entry",
    "create_humidity_control_binary_sensor",
    "create_humidity_control_binary_sensors",
]
