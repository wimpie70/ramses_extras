from __future__ import annotations

from copy import deepcopy
from typing import Any

from .model import (
    CONFIG_DEVICES_KEY,
    CONFIG_FANS_KEY,
    REMOTE_BINDING_BINDINGS_KEY,
    REMOTE_BINDING_REM_ID_KEY,
    REMOTE_BINDING_REMOTE_ID_KEY,
    SENSOR_CONTROL_SECTION_KEYS,
    get_feature_section,
    make_empty_config_model,
    normalize_device_id,
    set_feature_section,
)

# Feature IDs used by this module
FEATURE_SENSOR_CONTROL = "sensor_control"
FEATURE_ZONES = "zones"
FEATURE_REMOTE_BINDING = "remote_binding"


def migrate_to_canonical_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    canonical = make_empty_config_model()

    for feature_id, section in raw_config.items():
        if feature_id == "ramses_extras":
            continue
        if not isinstance(section, dict):
            continue

        migrated_section = migrate_feature_section(feature_id, section)
        set_feature_section(canonical, feature_id, migrated_section)

    root_section = raw_config.get("ramses_extras")
    if isinstance(root_section, dict):
        features = root_section.get("features")
        if isinstance(features, dict):
            for feature_id, section in features.items():
                if not isinstance(section, dict):
                    continue
                migrated_section = migrate_feature_section(feature_id, section)
                set_feature_section(canonical, feature_id, migrated_section)

    return canonical


def migrate_feature_section(feature_id: str, section: dict[str, Any]) -> dict[str, Any]:
    if feature_id == FEATURE_SENSOR_CONTROL:
        return migrate_sensor_control_section(section)
    if feature_id == FEATURE_REMOTE_BINDING:
        return migrate_remote_binding_section(section)
    if feature_id == FEATURE_ZONES:
        return migrate_zones_section(section)
    return deepcopy(section)


def migrate_sensor_control_section(section: dict[str, Any]) -> dict[str, Any]:
    devices = section.get(CONFIG_DEVICES_KEY)
    if isinstance(devices, dict):
        migrated_devices: dict[str, Any] = {}
        for device_id, device_section in devices.items():
            if not isinstance(device_section, dict):
                continue
            migrated_devices[normalize_device_id(device_id)] = deepcopy(device_section)
        return {CONFIG_DEVICES_KEY: migrated_devices}

    legacy_devices: dict[str, dict[str, Any]] = {}
    for config_key in SENSOR_CONTROL_SECTION_KEYS:
        config_group = section.get(config_key)
        if not isinstance(config_group, dict):
            continue
        for device_id, value in config_group.items():
            normalized_device_id = normalize_device_id(device_id)
            device_section = legacy_devices.setdefault(normalized_device_id, {})
            device_section[config_key] = deepcopy(value)

    return {CONFIG_DEVICES_KEY: legacy_devices}


def migrate_remote_binding_section(section: dict[str, Any]) -> dict[str, Any]:
    migrated_fans: dict[str, dict[str, Any]] = {}
    fan_groups = section.get(CONFIG_FANS_KEY)
    if not isinstance(fan_groups, dict):
        fan_groups = section.get("fans")

    if isinstance(fan_groups, dict):
        for fan_id, fan_section in fan_groups.items():
            if not isinstance(fan_section, dict):
                continue
            migrated_fans[normalize_device_id(fan_id)] = (
                _migrate_remote_binding_fan_section(fan_section)
            )
        return {CONFIG_FANS_KEY: migrated_fans}

    bindings = section.get(REMOTE_BINDING_BINDINGS_KEY)
    if not isinstance(bindings, list):
        return {CONFIG_FANS_KEY: migrated_fans}

    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        fan_id = binding.get("fan_id")
        rem_id = binding.get(REMOTE_BINDING_REM_ID_KEY) or binding.get(
            REMOTE_BINDING_REMOTE_ID_KEY
        )
        if not isinstance(fan_id, str) or not isinstance(rem_id, str):
            continue

        normalized_fan_id = normalize_device_id(fan_id)
        fan_section = migrated_fans.setdefault(normalized_fan_id, {"REMs": []})
        rem_section = deepcopy(binding)
        rem_section.pop("fan_id", None)
        rem_section.pop(REMOTE_BINDING_REMOTE_ID_KEY, None)
        rem_section[REMOTE_BINDING_REM_ID_KEY] = normalize_device_id(rem_id)
        fan_section.setdefault("REMs", []).append(rem_section)

    return {CONFIG_FANS_KEY: migrated_fans}


def _migrate_remote_binding_fan_section(fan_section: dict[str, Any]) -> dict[str, Any]:
    rems = fan_section.get("REMs")
    if not isinstance(rems, list):
        rems = fan_section.get("rems")

    migrated_rems: list[dict[str, Any]] = []
    if isinstance(rems, list):
        for rem in rems:
            if not isinstance(rem, dict):
                continue
            rem_section = deepcopy(rem)
            remote_id = rem_section.pop(REMOTE_BINDING_REMOTE_ID_KEY, None)
            if REMOTE_BINDING_REM_ID_KEY not in rem_section and isinstance(
                remote_id, str
            ):
                rem_section[REMOTE_BINDING_REM_ID_KEY] = normalize_device_id(remote_id)
            rem_id = rem_section.get(REMOTE_BINDING_REM_ID_KEY)
            if isinstance(rem_id, str):
                rem_section[REMOTE_BINDING_REM_ID_KEY] = normalize_device_id(rem_id)
            migrated_rems.append(rem_section)

    migrated_section = deepcopy(fan_section)
    migrated_section.pop("rems", None)
    migrated_section["REMs"] = migrated_rems
    return migrated_section


def migrate_zones_section(section: dict[str, Any]) -> dict[str, Any]:
    fan_groups = section.get(CONFIG_FANS_KEY)
    if not isinstance(fan_groups, dict):
        fan_groups = section.get("fans")

    if not isinstance(fan_groups, dict):
        return {CONFIG_FANS_KEY: {}}

    migrated_fans: dict[str, Any] = {}
    for fan_id, zones in fan_groups.items():
        if not isinstance(zones, list):
            continue
        migrated_fans[normalize_device_id(fan_id)] = deepcopy(zones)

    return {CONFIG_FANS_KEY: migrated_fans}


def get_migrated_feature_section(
    raw_config: dict[str, Any], feature_id: str
) -> dict[str, Any]:
    canonical = migrate_to_canonical_config(raw_config)
    return get_feature_section(canonical, feature_id)


__all__ = [
    "get_migrated_feature_section",
    "migrate_feature_section",
    "migrate_remote_binding_section",
    "migrate_sensor_control_section",
    "migrate_to_canonical_config",
    "migrate_zones_section",
]
