"""Temp control switch platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)

from ..const import TEMP_CONTROL_SWITCH_CONFIGS

_LOGGER = logging.getLogger(__name__)


def is_supported_temp_control_device(hass: object, device_id: str) -> bool:
    normalized_device_id = device_id.replace("_", ":")
    device = find_ramses_device(hass, normalized_device_id)
    return get_device_type(device) == "HvacVentilator"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from custom_components.ramses_extras.framework.helpers import platform

    filtered_devices = platform.PlatformSetup.get_filtered_devices_for_feature(
        hass, "temp_control", config_entry
    )

    if not filtered_devices:
        return

    entities: list[ExtrasSwitchEntity] = []
    for device_id in filtered_devices:
        if not is_supported_temp_control_device(hass, device_id):
            continue
        entities.extend(await create_temp_control_switch(hass, device_id, config_entry))

    if entities:
        async_add_entities(entities, True)


async def create_temp_control_switch(
    hass: HomeAssistant,
    device_id: str,
    config_entry: ConfigEntry | None = None,
) -> list[ExtrasSwitchEntity]:
    switches: list[ExtrasSwitchEntity] = []

    for switch_type, config in TEMP_CONTROL_SWITCH_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            switches.append(TempControlSwitch(hass, device_id, switch_type, config))

    return switches


class TempControlSwitch(ExtrasSwitchEntity, RestoreEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ) -> None:
        super().__init__(hass, device_id, switch_type, config)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == STATE_ON
            self.async_write_ha_state()


from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,
)

register_feature_platform("switch", "temp_control", async_setup_entry)

__all__ = ["TempControlSwitch", "async_setup_entry", "create_temp_control_switch"]
