"""Temp control select platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSelectEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)

from ..const import TEMP_CONTROL_SELECT_CONFIGS

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

    entities: list[ExtrasSelectEntity] = []
    for device_id in filtered_devices:
        if not is_supported_temp_control_device(hass, device_id):
            continue
        entities.extend(
            await create_temp_control_desired_speed_select(
                hass, device_id, config_entry
            )
        )

    if entities:
        async_add_entities(entities, True)


async def create_temp_control_desired_speed_select(
    hass: HomeAssistant,
    device_id: str,
    config_entry: ConfigEntry | None = None,
) -> list[ExtrasSelectEntity]:
    selects: list[ExtrasSelectEntity] = []

    for select_type, config in TEMP_CONTROL_SELECT_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            selects.append(
                TempControlDesiredSpeedSelect(
                    hass,
                    device_id,
                    select_type,
                    config,
                    config_entry,
                )
            )

    return selects


class TempControlDesiredSpeedSelect(ExtrasSelectEntity, RestoreEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        select_type: str,
        config: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        super().__init__(
            hass,
            device_id,
            select_type,
            config,
            options=list(config.get("options") or ["low", "medium", "high"]),
        )
        self.config_entry = config_entry

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in set(self._attr_options or []):
            self._attr_current_option = last.state
            self.async_write_ha_state()
            return

        restored = self._load_value_from_config()
        if restored in set(self._attr_options or []):
            self._attr_current_option = restored
            self.async_write_ha_state()

    def _load_value_from_config(self) -> str:
        config_entry = self.config_entry
        if config_entry is None:
            return str(self._attr_current_option or "high")

        latest = self.hass.config_entries.async_get_entry(config_entry.entry_id)
        if latest is not None:
            config_entry = latest

        device_key = str(self.device_id).replace(":", "_")

        legacy_store = config_entry.options.get("temp_control")
        legacy_store = legacy_store if isinstance(legacy_store, dict) else {}
        legacy_device = legacy_store.get(device_key)
        legacy_device = legacy_device if isinstance(legacy_device, dict) else {}

        canonical_root = config_entry.options.get("ramses_extras")
        canonical_root = canonical_root if isinstance(canonical_root, dict) else {}
        canonical_features = canonical_root.get("features")
        canonical_features = (
            canonical_features if isinstance(canonical_features, dict) else {}
        )
        canonical_feature = canonical_features.get("temp_control")
        canonical_feature = (
            canonical_feature if isinstance(canonical_feature, dict) else {}
        )
        canonical_device = canonical_feature.get(device_key)
        canonical_device = (
            canonical_device if isinstance(canonical_device, dict) else {}
        )

        stored = legacy_device.get("desired_speed")
        if stored is None:
            stored = canonical_device.get("desired_speed")

        return str(stored or self._attr_current_option or "high")

    async def async_select_option(self, option: str) -> None:
        await super().async_select_option(option)
        await self._save_value_to_config(option)

    async def _save_value_to_config(self, option: str) -> None:
        config_entry = self.config_entry
        if config_entry is None:
            return

        latest = self.hass.config_entries.async_get_entry(config_entry.entry_id)
        if latest is not None:
            config_entry = latest

        device_key = str(self.device_id).replace(":", "_")
        options = dict(config_entry.options)

        legacy_store = options.get("temp_control")
        legacy_store = legacy_store if isinstance(legacy_store, dict) else {}
        legacy_store = dict(legacy_store)
        legacy_device = legacy_store.get(device_key)
        legacy_device = legacy_device if isinstance(legacy_device, dict) else {}
        legacy_device = dict(legacy_device)
        legacy_device["desired_speed"] = option
        legacy_store[device_key] = legacy_device
        options["temp_control"] = legacy_store

        root = options.get("ramses_extras")
        root = root if isinstance(root, dict) else {}
        root = dict(root)
        features = root.get("features")
        features = features if isinstance(features, dict) else {}
        features = dict(features)
        canonical = features.get("temp_control")
        canonical = canonical if isinstance(canonical, dict) else {}
        canonical = dict(canonical)
        canonical_device = canonical.get(device_key)
        canonical_device = (
            canonical_device if isinstance(canonical_device, dict) else {}
        )
        canonical_device = dict(canonical_device)
        canonical_device["desired_speed"] = option
        canonical[device_key] = canonical_device
        features["temp_control"] = canonical
        root["features"] = features
        options["ramses_extras"] = root

        self.hass.config_entries.async_update_entry(config_entry, options=options)


from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,
)

register_feature_platform("select", "temp_control", async_setup_entry)

__all__ = [
    "TempControlDesiredSpeedSelect",
    "async_setup_entry",
    "create_temp_control_desired_speed_select",
]
