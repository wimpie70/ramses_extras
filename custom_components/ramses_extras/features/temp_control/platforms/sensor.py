"""Temp control sensor platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSensorEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)

from ..const import TEMP_CONTROL_SENSOR_CONFIGS

_LOGGER = logging.getLogger(__name__)


def is_supported_temp_control_device(hass: object, device_id: str) -> bool:
    normalized_device_id = device_id.replace("_", ":")
    device = find_ramses_device(hass, normalized_device_id)
    return bool(get_device_type(device) == "HvacVentilator")


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

    entities: list[ExtrasSensorEntity] = []
    for device_id in filtered_devices:
        if not is_supported_temp_control_device(hass, device_id):
            continue
        entities.extend(await create_temp_control_status_sensor(hass, device_id))

    if entities:
        async_add_entities(entities, True)

        from custom_components.ramses_extras.framework.helpers.platform import (
            PlatformSetup,
        )

        PlatformSetup._store_entities_for_automation(hass, entities)


async def create_temp_control_status_sensor(
    hass: HomeAssistant,
    device_id: str,
) -> list[ExtrasSensorEntity]:
    sensors: list[ExtrasSensorEntity] = []

    for sensor_type, config in TEMP_CONTROL_SENSOR_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            sensors.append(
                TempControlStatusSensor(hass, device_id, sensor_type, config)
            )

    return sensors


class TempControlStatusSensor(ExtrasSensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        super().__init__(hass, device_id, sensor_type, config)
        self._attr_native_value = "disabled"
        self._status_attrs: dict[str, Any] = {}

    def set_status(self, status: str, attrs: dict[str, Any] | None = None) -> None:
        self._attr_native_value = status
        self._status_attrs = dict(attrs or {})
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base = super().extra_state_attributes or {}
        return {**base, **self._status_attrs}


from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,
)

register_feature_platform("sensor", "temp_control", async_setup_entry)

__all__ = [
    "TempControlStatusSensor",
    "async_setup_entry",
    "create_temp_control_status_sensor",
]
