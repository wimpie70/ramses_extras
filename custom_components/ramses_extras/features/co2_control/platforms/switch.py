"""CO2 Control Switch Platform."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.ramses_extras.const import register_feature_platform
from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)
from custom_components.ramses_extras.framework.helpers.platform import PlatformSetup

_LOGGER = logging.getLogger(__name__)


class CO2ControlSwitch(ExtrasSwitchEntity, RestoreEntity):
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

    async def async_added_to_hass(self) -> None:
        """Restore previous switch state when entity is (re)added."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

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
    """Create CO2 control switch entity."""
    return CO2ControlSwitch(hass, device_id, config)


async def create_co2_switch_entities(
    hass: HomeAssistant,
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None,
) -> list[SwitchEntity]:
    """Factory to create CO2 control switch entities."""
    from ..const import CO2_SWITCH_CONFIGS

    entities: list[SwitchEntity] = []
    config = CO2_SWITCH_CONFIGS.get("co2_control")
    if config:
        entities.append(create_co2_switch(hass, device_id, config))
    return entities


async def switch_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control switch entities."""
    from ..const import CO2_SWITCH_CONFIGS

    await PlatformSetup.async_create_and_add_platform_entities(
        platform="switch",
        hass=hass,
        config_entry=entry,
        async_add_entities=async_add_entities,
        entity_configs=CO2_SWITCH_CONFIGS,
        entity_factory=create_co2_switch_entities,
        feature_id="co2_control",
    )


register_feature_platform("switch", "co2_control", switch_async_setup_entry)

__all__ = [
    "CO2ControlSwitch",
    "create_co2_switch",
    "switch_async_setup_entry",
]
