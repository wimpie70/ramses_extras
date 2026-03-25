from __future__ import annotations

from copy import deepcopy
from typing import Any

CONFIG_ROOT_KEY = "ramses_extras"
CONFIG_SCHEMA_VERSION_KEY = "schema_version"
CONFIG_SCHEMA_VERSION = 1
CONFIG_FEATURES_KEY = "features"
CONFIG_FANS_KEY = "FANs"
CONFIG_REMS_KEY = "REMs"
CONFIG_DEVICES_KEY = "devices"
FEATURE_DEFAULT = "default"
FEATURE_SENSOR_CONTROL = "sensor_control"
FEATURE_REMOTE_BINDING = "remote_binding"
FEATURE_ZONES = "zones"
SENSOR_CONTROL_SOURCES_KEY = "sources"
SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY = "abs_humidity_inputs"
SENSOR_CONTROL_AREA_SENSORS_KEY = "area_sensors"
REMOTE_BINDING_BINDINGS_KEY = "bindings"
REMOTE_BINDING_REMOTE_ID_KEY = "remote_id"
REMOTE_BINDING_REM_ID_KEY = "rem_id"
ZONE_ID_KEY = "zone_id"
ZONE_TEMPERATURE_ENTITY_KEY = "temperature_entity"
ZONE_HUMIDITY_ENTITY_KEY = "humidity_entity"
ZONE_CO2_ENTITY_KEY = "co2_entity"

SENSOR_CONTROL_SECTION_KEYS = (
    SENSOR_CONTROL_SOURCES_KEY,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
)
ZONE_ENTITY_KEYS = (
    ZONE_TEMPERATURE_ENTITY_KEY,
    ZONE_HUMIDITY_ENTITY_KEY,
    ZONE_CO2_ENTITY_KEY,
)


def normalize_device_id(device_id: str) -> str:
    return device_id.strip().replace("_", ":")


def legacy_device_key(device_id: str) -> str:
    return normalize_device_id(device_id).replace(":", "_")


def make_empty_config_model() -> dict[str, Any]:
    return {
        CONFIG_ROOT_KEY: {
            CONFIG_SCHEMA_VERSION_KEY: CONFIG_SCHEMA_VERSION,
            CONFIG_FEATURES_KEY: {},
        }
    }


def get_root_model(config: dict[str, Any]) -> dict[str, Any] | None:
    root = config.get(CONFIG_ROOT_KEY)
    return root if isinstance(root, dict) else None


def get_features_container(
    config: dict[str, Any],
    *,
    create: bool = False,
) -> dict[str, Any]:
    root = get_root_model(config)
    if root is None:
        if not create:
            return {}
        root = {
            CONFIG_SCHEMA_VERSION_KEY: CONFIG_SCHEMA_VERSION,
            CONFIG_FEATURES_KEY: {},
        }
        config[CONFIG_ROOT_KEY] = root

    features = root.get(CONFIG_FEATURES_KEY)
    if isinstance(features, dict):
        return features

    if not create:
        return {}

    features = {}
    root[CONFIG_FEATURES_KEY] = features
    return features


def get_feature_section(
    config: dict[str, Any],
    feature_id: str,
    *,
    create: bool = False,
) -> dict[str, Any]:
    features = get_features_container(config, create=create)
    section = features.get(feature_id)
    if isinstance(section, dict):
        return section

    if not create:
        return {}

    section = {}
    features[feature_id] = section
    return section


def set_feature_section(
    config: dict[str, Any], feature_id: str, section_data: dict[str, Any]
) -> dict[str, Any]:
    features = get_features_container(config, create=True)
    section = deepcopy(section_data)
    features[feature_id] = section
    return section


def get_device_section_mapping(section: dict[str, Any]) -> dict[str, Any]:
    for key in (CONFIG_FANS_KEY, CONFIG_DEVICES_KEY, "fans"):
        mapping = section.get(key)
        if isinstance(mapping, dict):
            return mapping
    return {}


def get_fan_ids(section: dict[str, Any]) -> list[str]:
    mapping = get_device_section_mapping(section)
    normalized_ids = {normalize_device_id(device_id) for device_id in mapping}
    return sorted(normalized_ids)


def get_sensor_control_device_section(
    section: dict[str, Any], device_id: str
) -> dict[str, Any]:
    normalized_device_id = normalize_device_id(device_id)
    canonical_devices = section.get(CONFIG_DEVICES_KEY)
    if isinstance(canonical_devices, dict):
        device_section = canonical_devices.get(normalized_device_id)
        if isinstance(device_section, dict):
            return deepcopy(device_section)

    legacy_key = legacy_device_key(normalized_device_id)
    device_config: dict[str, Any] = {}
    for config_key in SENSOR_CONTROL_SECTION_KEYS:
        config_group = section.get(config_key)
        if not isinstance(config_group, dict):
            continue
        value = config_group.get(legacy_key)
        if value is not None:
            device_config[config_key] = deepcopy(value)

    return device_config


def find_areas_for_zone(
    sensor_control_section: dict[str, Any],
    device_id: str,
    zone_id: str,
) -> list[dict[str, Any]]:
    device_section = get_sensor_control_device_section(
        sensor_control_section, device_id
    )
    area_sensors = device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY)
    if not isinstance(area_sensors, list):
        return []

    areas: list[dict[str, Any]] = []
    for area in area_sensors:
        if not isinstance(area, dict):
            continue
        if area.get(ZONE_ID_KEY) != zone_id:
            continue
        areas.append(deepcopy(area))

    return areas


def find_entities_for_zone(
    sensor_control_section: dict[str, Any],
    device_id: str,
    zone_id: str,
) -> list[str]:
    entities: list[str] = []
    for area in find_areas_for_zone(sensor_control_section, device_id, zone_id):
        for entity_key in ZONE_ENTITY_KEYS:
            entity_id = area.get(entity_key)
            if isinstance(entity_id, str) and entity_id and entity_id not in entities:
                entities.append(entity_id)

    return entities


__all__ = [
    "CONFIG_DEVICES_KEY",
    "CONFIG_FANS_KEY",
    "CONFIG_FEATURES_KEY",
    "CONFIG_REMS_KEY",
    "CONFIG_ROOT_KEY",
    "CONFIG_SCHEMA_VERSION",
    "CONFIG_SCHEMA_VERSION_KEY",
    "FEATURE_DEFAULT",
    "FEATURE_REMOTE_BINDING",
    "FEATURE_SENSOR_CONTROL",
    "FEATURE_ZONES",
    "REMOTE_BINDING_BINDINGS_KEY",
    "REMOTE_BINDING_REM_ID_KEY",
    "REMOTE_BINDING_REMOTE_ID_KEY",
    "SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY",
    "SENSOR_CONTROL_AREA_SENSORS_KEY",
    "SENSOR_CONTROL_SECTION_KEYS",
    "SENSOR_CONTROL_SOURCES_KEY",
    "ZONE_ID_KEY",
    "find_areas_for_zone",
    "find_entities_for_zone",
    "get_fan_ids",
    "get_feature_section",
    "get_features_container",
    "get_root_model",
    "get_sensor_control_device_section",
    "legacy_device_key",
    "make_empty_config_model",
    "normalize_device_id",
    "set_feature_section",
]
