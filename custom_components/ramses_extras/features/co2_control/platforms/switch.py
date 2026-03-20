"""CO2 Control Switch Platform."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)

_LOGGER = logging.getLogger(__name__)


class CO2ControlSwitch(ExtrasSwitchEntity):
    """CO2 Control switch entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control switch.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Entity configuration
        """
        super().__init__(hass, device_id, "co2_control", config)
        self._attr_is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if CO2 control is on."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on CO2 control."""
        self._attr_is_on = True
        self.async_write_ha_state()
        _LOGGER.info("CO2 control enabled for device %s", self.device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off CO2 control."""
        self._attr_is_on = False
        self.async_write_ha_state()
        _LOGGER.info("CO2 control disabled for device %s", self.device_id)


def create_co2_switch(
    hass: HomeAssistant,
    device_id: str,
    config: dict[str, Any],
) -> CO2ControlSwitch:
    """Create CO2 control switch entity.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config: Entity configuration

    Returns:
        CO2ControlSwitch entity
    """
    return CO2ControlSwitch(hass, device_id, config)


async def switch_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control switch entities.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    # Implementation will be completed in Phase 4


__all__ = ["CO2ControlSwitch", "create_co2_switch", "switch_async_setup_entry"]
