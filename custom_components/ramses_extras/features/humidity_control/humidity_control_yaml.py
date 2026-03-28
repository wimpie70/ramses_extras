"""Humidity control YAML import/export and validation.

This module handles YAML export, import, and validation for the
humidity_control feature. Each feature is responsible for its own
import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_schema,
    register_config_validator,
)
from .const import FEATURE_ID

# Humidity Control YAML Schemas

HUMIDITY_FAN_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): bool,
        vol.Optional("automation_enabled", default=False): bool,
        vol.Optional("default_min_humidity", default=40.0): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
        vol.Optional("default_max_humidity", default=60.0): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
        vol.Optional("indoor_sensor_entity"): str,
        vol.Optional("outdoor_sensor_entity"): str,
        vol.Optional("max_runtime_minutes", default=120): vol.All(
            int, vol.Range(min=10, max=480)
        ),
        vol.Optional("cooldown_period_minutes", default=15): int,
    }
)

HUMIDITY_CONTROL_CONFIG_SCHEMA = vol.Schema(
    {vol.Required("FANs"): {str: HUMIDITY_FAN_CONFIG_SCHEMA}}
)


def humidity_control_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate humidity_control configuration section."""
    errors: list[str] = []

    for fan_id, fan_config in section.get("FANs", {}).items():
        if not isinstance(fan_config, dict):
            errors.append(f"FAN {fan_id}: configuration must be a dictionary")
            continue

        # Validate min/max humidity ranges
        min_hum = fan_config.get("default_min_humidity")
        max_hum = fan_config.get("default_max_humidity")

        if min_hum is not None and max_hum is not None:
            if min_hum >= max_hum:
                msg = f"FAN {fan_id}: min ({min_hum}) must be less than max ({max_hum})"
                errors.append(msg)

    return errors


def export_humidity_control_to_yaml(config: dict) -> dict:
    """Export humidity_control configuration to YAML-compatible dict."""
    return config


def parse_humidity_control_yaml(yaml_data: dict) -> dict[Any, Any]:
    """Parse humidity_control YAML data into canonical config format."""
    result = HUMIDITY_CONTROL_CONFIG_SCHEMA(yaml_data)
    return cast(dict[Any, Any], result)


def merge_humidity_control_config(existing: dict, imported: dict) -> dict:
    """Merge imported humidity_control config with existing."""
    merged = dict(existing)
    if "FANs" in imported:
        if "FANs" not in merged:
            merged["FANs"] = {}
        merged["FANs"].update(imported["FANs"])
    return merged


def load_validator() -> None:
    """Register the humidity_control validator and schema with the framework."""
    register_config_validator(FEATURE_ID, humidity_control_validator)
    register_config_schema(FEATURE_ID, HUMIDITY_CONTROL_CONFIG_SCHEMA)
