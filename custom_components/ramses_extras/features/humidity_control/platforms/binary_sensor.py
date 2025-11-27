"""Humidity Control Binary Sensor Platform.

This module provides Home Assistant binary sensor platform integration
for humidity control feature.
"""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control binary sensor platform."""
    from custom_components.ramses_extras.framework.base_classes import (
        platform_entities,
    )

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        f"Humidity control binary sensor platform: found {len(devices)} "
        f"devices: {devices}"
    )

    if not devices:
        _LOGGER.warning(
            "No devices found for humidity control binary sensors "
            "- automation will not start"
        )
        return

    binary_sensor = []
    for device_id in devices:
        try:
            # Create humidity control binary sensor
            device_sensor = await create_humidity_control_binary_sensor(
                hass, device_id, config_entry
            )
            binary_sensor.extend(device_sensor)
            _LOGGER.info(
                f"Created {len(device_sensor)} binary sensor for device {device_id}"
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create binary sensor for device {device_id}: {e}")

    _LOGGER.info(f"Total binary sensor created: {len(binary_sensor)}")
    if binary_sensor:
        async_add_entities(binary_sensor, True)
        _LOGGER.info("Humidity control binary sensors added to Home Assistant")

        # Store entities for automation access
        if "ramses_extras" not in hass.data:
            hass.data["ramses_extras"] = {}
        if "entities" not in hass.data["ramses_extras"]:
            hass.data["ramses_extras"]["entities"] = {}
        for entity in binary_sensor:
            hass.data["ramses_extras"]["entities"][entity.entity_id] = entity
            _LOGGER.debug(
                f"Stored binary sensor entity {entity.entity_id} for automation access"
            )
    else:
        _LOGGER.warning("No binary sensors created - automation will not start")


async def create_humidity_control_binary_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasBinarySensorEntity]:
    """Create humidity control binary sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of binary sensor entities
    """
    # Import entity configurations from registry
    from ..const import HUMIDITY_BOOLEAN_CONFIGS

    binary_sensor = []

    # Create dehumidifying_active binary sensor
    for binary_type, config in HUMIDITY_BOOLEAN_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            binary_sensor_entity = HumidityControlBinarySensor(
                hass, device_id, binary_type, config
            )
            binary_sensor.append(binary_sensor_entity)

    return binary_sensor


class HumidityControlBinarySensor(ExtrasBinarySensorEntity):
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
        super().__init__(hass, device_id, binary_type, config)

        # Initialize state
        self._current_fan_speed = "auto"  # Track current fan speed

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.info(
            f"HumidityControlBinarySensor async_added_to_hass called for "
            f"{self.entity_id}"
        )

        _LOGGER.debug("Binary sensor %s added to hass", self._attr_name)

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
            "binary_type": self._entity_type,
            "controlled_by": "automation",
            "current_fan_speed": self._current_fan_speed,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("binary_sensor", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlBinarySensor",
    "async_setup_entry",
    "create_humidity_control_binary_sensor",
]
