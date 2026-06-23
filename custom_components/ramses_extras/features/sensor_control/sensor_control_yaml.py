"""Sensor Control YAML import/export and validation.

This module handles YAML export, import, and validation for the sensor_control feature.
Each feature is responsible for its own import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_schema,
    register_config_validator,
)

# Import schemas from const
from .const import (
    FEATURE_ID,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
)

# Sensor Control YAML Schemas
# These define the structure for sensor_control configuration in YAML

_AREA_SENSOR_SCHEMA_V2 = vol.Schema(
    {
        vol.Required("area_id"): str,
        vol.Optional("zone_id"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("temperature_entity"): str,
        vol.Optional("humidity_entity"): str,
        vol.Optional("co2_entity"): str,
        vol.Optional("co2_threshold"): vol.All(int, vol.Range(min=0)),
        vol.Optional("area_co2_enabled", default=False): bool,
        vol.Optional("spike_rise_percent"): vol.All(float, vol.Range(min=0)),
        vol.Optional("spike_window_minutes"): vol.All(int, vol.Range(min=1)),
        vol.Optional("trigger_on_high_humidity", default=False): bool,
        vol.Optional("co2_threshold_entity"): str,
        vol.Optional("comfort_temperature_entity"): str,
    }
)

_AREA_SENSOR_SCHEMA_LEGACY = vol.Schema(
    {
        vol.Optional("area_id"): str,
        vol.Optional("zone_id"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("temperature_entity"): str,
        vol.Optional("humidity_entity"): str,
        vol.Optional("co2_entity"): str,
        vol.Optional("co2_threshold"): vol.All(int, vol.Range(min=0)),
        vol.Optional("area_co2_enabled", default=False): bool,
        vol.Optional("spike_rise_percent"): vol.All(float, vol.Range(min=0)),
        vol.Optional("spike_window_minutes"): vol.All(int, vol.Range(min=1)),
        vol.Optional("trigger_on_high_humidity", default=False): bool,
        vol.Optional("co2_threshold_entity"): str,
        vol.Optional("comfort_temperature_entity"): str,
    }
)

AREA_SENSOR_SCHEMA = vol.Any(_AREA_SENSOR_SCHEMA_V2, _AREA_SENSOR_SCHEMA_LEGACY)

ABS_HUMIDITY_INPUT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): str,
        vol.Optional("temperature"): vol.Any(
            str,
            {
                vol.Required("kind"): str,
                vol.Optional("entity_id"): str,
            },
        ),
        vol.Optional("humidity"): vol.Any(
            str,
            {
                vol.Required("kind"): str,
                vol.Optional("entity_id"): str,
            },
        ),
        vol.Optional("indoor", default=True): bool,
    }
)

SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(["internal", "external", "calculated"]),
        vol.Optional("metric"): str,
        vol.Optional("entity_id"): str,
        vol.Optional("source_id"): str,
    }
)

FAN_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("sources"): {str: SOURCE_SCHEMA},
        vol.Optional(SENSOR_CONTROL_AREA_SENSORS_KEY): [AREA_SENSOR_SCHEMA],
        vol.Optional(SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY): {
            vol.Optional(str): ABS_HUMIDITY_INPUT_SCHEMA
        },
    }
)

SENSOR_CONTROL_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY): {
            vol.Optional(str): ABS_HUMIDITY_INPUT_SCHEMA
        },
        vol.Optional(SENSOR_CONTROL_AREA_SENSORS_KEY): {
            vol.Optional(str): [AREA_SENSOR_SCHEMA]
        },
        vol.Optional("devices"): {str: FAN_CONFIG_SCHEMA},
        vol.Optional("FANs"): {str: FAN_CONFIG_SCHEMA},
    }
)


def sensor_control_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate sensor_control configuration section.

    :param section: The sensor_control configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    for fan_id, fan_config in section.get("FANs", {}).items():
        if not isinstance(fan_config, dict):
            errors.append(f"FAN {fan_id}: configuration must be a dictionary")
            continue

        # Validate area_sensors if present
        area_sensors = fan_config.get(SENSOR_CONTROL_AREA_SENSORS_KEY, {})
        if not isinstance(area_sensors, dict):
            key = SENSOR_CONTROL_AREA_SENSORS_KEY
            errors.append(f"FAN {fan_id}: {key} must be a dictionary")

        # Validate abs_humidity_inputs if present
        abs_humidity_inputs = fan_config.get(SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY, {})
        if not isinstance(abs_humidity_inputs, dict):
            key = SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY
            errors.append(f"FAN {fan_id}: {key} must be a dictionary")

        # Validate sources if present
        sources = fan_config.get(SENSOR_CONTROL_SOURCES_KEY, [])
        if not isinstance(sources, list):
            errors.append(f"FAN {fan_id}: {SENSOR_CONTROL_SOURCES_KEY} must be a list")

    return errors


def export_sensor_control_to_yaml(config: dict) -> dict:
    """Export sensor_control configuration to YAML-compatible dict.

    :param config: The sensor_control configuration section
    :return: YAML-compatible dictionary
    """
    return config


def parse_sensor_control_yaml(yaml_data: dict) -> dict[str, Any]:
    """Parse sensor_control YAML data into canonical config format.

    :param yaml_data: Raw YAML data for sensor_control section
    :return: Canonical sensor_control configuration
    """
    # Validate against schema
    result = cast(dict[str, Any], SENSOR_CONTROL_CONFIG_SCHEMA(yaml_data))

    for fan_key in ("FANs", "devices"):
        fans = result.get(fan_key)
        if not isinstance(fans, dict):
            continue

        for device_id, fan_cfg in list(fans.items()):
            if not isinstance(fan_cfg, dict):
                continue

            area_sensors = fan_cfg.get(SENSOR_CONTROL_AREA_SENSORS_KEY)
            if not isinstance(area_sensors, list):
                continue

            normalized: list[dict[str, Any]] = []
            for item in area_sensors:
                if not isinstance(item, dict):
                    continue
                area_id = str(item.get("area_id") or "").strip()
                if not area_id:
                    continue
                cleaned = dict(item)
                cleaned["area_id"] = area_id
                normalized.append(cleaned)

            fan_cfg[SENSOR_CONTROL_AREA_SENSORS_KEY] = normalized

    return result


def merge_sensor_control_config(existing: dict, imported: dict) -> dict[str, Any]:
    """Merge imported sensor_control config with existing.

    :param existing: Existing sensor_control configuration
    :param imported: Imported sensor_control configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    if "FANs" in imported:
        if "FANs" not in merged:
            merged["FANs"] = {}
        merged["FANs"].update(imported["FANs"])
    return merged


def load_validator() -> None:
    """Register the sensor_control validator and schema with the framework."""
    register_config_validator(FEATURE_ID, sensor_control_validator)
    register_config_schema(FEATURE_ID, SENSOR_CONTROL_CONFIG_SCHEMA)
