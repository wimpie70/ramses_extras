"""Humidity Control Switch Platform.

This module provides Home Assistant switch platform integration
for humidity control feature.
"""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up humidity control switch platform."""
    from custom_components.ramses_extras.framework.base_classes import (
        platform_entities,
    )

    await platform_entities.generic_platform_setup(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        feature_id="humidity_control",
        platform_configs={},
        entity_factory=create_humidity_switch,
        platform_type="switch",
    )


async def create_humidity_switch(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasSwitchEntity]:
    """Create humidity switch for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    # Import entity configurations from registry
    from custom_components.ramses_extras.extras_registry import extras_registry

    from ..const import HUMIDITY_SWITCH_CONFIGS

    switch_list = []

    for switch_type, config in HUMIDITY_SWITCH_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            switch_entity = HumidityControlSwitch(hass, device_id, switch_type, config)
            switch_list.append(switch_entity)

    return switch_list


class HumidityControlSwitch(ExtrasSwitchEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity with platform type
        super().__init__(hass, device_id, switch_type, config)

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.info("switch added to hass")

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if dehumidify is active."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidify mode."""
        _LOGGER.info("Activating dehumidify mode for %s", self._attr_name)

        try:
            # Get the actual device object for communication
            from ...framework.helpers.device.core import find_ramses_device

            device = find_ramses_device(self.hass, self.device_id)

            if device:
                _LOGGER.info(
                    "Found device %s for dehumidification control", self.device_id
                )
                # Set fan to high speed to activate dehumidification
                # This is the actual device command that was missing
                await self._set_device_fan_speed(device, "high")
            else:
                _LOGGER.warning(
                    "Could not find device %s for dehumidification control. "
                    "Switch will remain virtual only.",
                    self.device_id,
                )

        except Exception as e:
            _LOGGER.error(
                "Failed to activate dehumidification for %s: %e", self._attr_name, e
            )

        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidify mode."""
        _LOGGER.info("Deactivating dehumidify mode for %s", self._attr_name)

        try:
            # Get the actual device object for communication
            from ...framework.helpers.device.core import find_ramses_device

            device = find_ramses_device(self.hass, self.device_id)

            if device:
                _LOGGER.info(
                    "Found device %s for dehumidification control", self.device_id
                )
                # Set fan to auto speed to stop dehumidification
                await self._set_device_fan_speed(device, "auto")
            else:
                _LOGGER.warning(
                    "Could not find device %s for dehumidification control. "
                    "Switch will remain virtual only.",
                    self.device_id,
                )

        except Exception as e:
            _LOGGER.error(
                "Failed to deactivate dehumidification for %s: %e", self._attr_name, e
            )

        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "dehumidifying": self.is_on}

    async def _set_device_fan_speed(self, device: Any, speed: str) -> None:
        """Set fan speed on the actual device.

        Args:
            device: The Ramses device object
            speed: Fan speed to set ("high", "auto", "low", etc.)
        """
        _LOGGER.debug("simulating set_device_fan_speed")
        return
        # dont remove the return, we don't want to actually
        # set the speed on a live device yet !

        # try:
        #     # Check what methods are available on the device object
        #     device_type = device.__class__.__name__
        #     _LOGGER.debug("Device type: %s", device_type)

        #     # Try different methods that might be available on HVAC devices
        #     if hasattr(device, "set_fan_speed") and callable(device.set_fan_speed):
        #         _LOGGER.info("Using device.set_fan_speed() method")
        #         await device.set_fan_speed(speed)
        #     elif hasattr(device, "set_fan_mode") and callable(device.set_fan_mode):
        #         _LOGGER.info("Using device.set_fan_mode() method")
        #         await device.set_fan_mode(speed)
        #     elif hasattr(device, "fan_speed") and hasattr(device, "fan_mode"):
        #         # Try setting attributes directly
        #         _LOGGER.info("Setting device.fan_speed attribute directly")
        #         device.fan_speed = speed
        #     else:
        #         _LOGGER.warning(
        #             "No suitable fan control method found on device %s (%s). "
        #             "Available attributes: %s",
        #             self.device_id,
        #             device_type,
        #             [attr for attr in dir(device) if not attr.startswith("_")],
        #         )
        #         # As a fallback, try to send a generic command
        #         if hasattr(device, "send_command") and callable(device.send_command):
        #             _LOGGER.info("Using device.send_command() fallback")
        #             await device.send_command(f"set_fan_speed:{speed}")

        # except Exception as e:
        #     _LOGGER.error(
        #         "Failed to set fan speed to %s on device %s: %e",
        #         speed,
        #         self.device_id,
        #         e,
        #     )
        #     raise


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("switch", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlSwitch",
    "async_setup_entry",
    "create_humidity_switch",
]
