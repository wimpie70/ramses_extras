"""Humidity Control Switch Platform.

This module provides Home Assistant switch platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up humidity control switch platform."""
    _LOGGER.info("Setting up humidity control switches")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])

    switches = []
    for device_id in devices:
        # Create humidity control switches
        switches.extend(await create_humidity_switches(hass, device_id, config_entry))

    async_add_entities(switches, True)


async def create_humidity_switches(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[SwitchEntity]:
    """Create humidity control switches for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, config_entry)
    switches = []

    # Create dehumidify switch
    config = entity_manager.get_entity_config("switches", "dehumidify")
    if config:
        switch = HumidityControlSwitch(hass, device_id, "dehumidify", config)
        switches.append(switch)

    return switches


def create_humidity_switch(
    hass: HomeAssistant, device_id: str, switch_type: str, config: dict[str, Any]
) -> SwitchEntity:
    """Create a humidity control switch (legacy function for compatibility)."""
    return HumidityControlSwitch(hass, device_id, switch_type, config)


class HumidityControlSwitch(SwitchEntity, ExtrasBaseEntity):
    """Switch for humidity control feature.

    This class handles the manual control of dehumidifying equipment
    and can be overridden by automation logic.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity control switch.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            switch_type: Type of switch
            config: Switch configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, switch_type, config)

        # Set switch-specific attributes
        self._switch_type = switch_type

        # Set unique_id and name
        device_id_underscore = device_id.replace(":", "_")
        self._attr_unique_id = f"{switch_type}_{device_id_underscore}"

        name_template = config.get(
            "name_template", f"{switch_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        # Initialize state
        self._is_on = False
        self._last_manual_change: str | None = None

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._switch_type} {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.debug("Switch %s added to hass", self._attr_name)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        self._is_on = True
        self._last_manual_change = "on"
        self.async_write_ha_state()
        _LOGGER.info(
            "Switch %s turned ON manually (is_on: %s)", self._attr_name, self._is_on
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        self._is_on = False
        self._last_manual_change = "off"
        self.async_write_ha_state()
        _LOGGER.info(
            "Switch %s turned OFF manually (is_on: %s)", self._attr_name, self._is_on
        )

    def set_state(self, is_on: bool, source: str = "automation") -> None:
        """Set the switch state (used by automation)."""
        if source == "automation":
            # Automation can override manual setting
            self._is_on = is_on
            self.async_write_ha_state()
            _LOGGER.debug(
                "Switch %s state set to %s by automation", self._attr_name, is_on
            )
        else:
            # Manual change takes precedence
            self._is_on = is_on
            self._last_manual_change = source
            self.async_write_ha_state()
            _LOGGER.info(
                "Switch %s state set to %s manually (last_manual: %s)",
                self._attr_name,
                is_on,
                source,
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "switch_type": self._switch_type,
            "last_manual_change": self._last_manual_change,
        }


__all__ = [
    "HumidityControlSwitch",
    "async_setup_entry",
    "create_humidity_switch",
    "create_humidity_switches",
]
