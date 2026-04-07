"""CO2 control YAML import/export and validation.

This module handles YAML export, import, and validation for the
co2_control feature. Each feature is responsible for its own
import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_schema,
    register_config_validator,
)
from .const import (
    CO2_CONTROL_DEFAULTS,
    CO2_CONTROL_VALIDATION_RULES,
    FEATURE_ID,
)

# CO2 Control YAML Schemas

CO2_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): str,
        vol.Optional("name"): str,
        vol.Optional("threshold", default=1000): vol.All(
            int, vol.Range(min=400, max=2000)
        ),
        vol.Optional("activation_hysteresis", default=100): vol.All(
            int, vol.Range(min=0, max=500)
        ),
        vol.Optional("deactivation_hysteresis", default=-100): vol.All(
            int, vol.Range(min=-500, max=0)
        ),
    }
)

CO2_FAN_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): bool,
        vol.Optional("automation_enabled", default=False): bool,
        vol.Optional("threshold", default=1000): vol.All(
            int, vol.Range(min=400, max=2000)
        ),
        vol.Optional("activation_hysteresis", default=100): vol.All(
            int, vol.Range(min=0, max=500)
        ),
        vol.Optional("deactivation_hysteresis", default=-100): vol.All(
            int, vol.Range(min=-500, max=0)
        ),
        vol.Optional("max_runtime_minutes", default=120): vol.All(
            int, vol.Range(min=10, max=480)
        ),
        vol.Optional("cooldown_period_minutes", default=15): int,
        vol.Optional("priority_over_humidity", default=True): bool,
        vol.Optional("zones"): [CO2_ZONE_SCHEMA],
    }
)

CO2_CONTROL_CONFIG_SCHEMA = vol.Schema(
    {vol.Required("FANs"): {str: CO2_FAN_CONFIG_SCHEMA}}
)


def co2_control_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate co2_control configuration section.

    :param section: The co2_control configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    for fan_id, fan_config in section.get("FANs", {}).items():
        if not isinstance(fan_config, dict):
            errors.append(f"FAN {fan_id}: configuration must be a dictionary")
            continue

        # Validate threshold range
        threshold = fan_config.get("threshold")
        if threshold is not None:
            if not isinstance(threshold, (int, float)):
                errors.append(f"FAN {fan_id}: threshold must be numeric")
            elif threshold < 400 or threshold > 2000:
                rng = "(400-2000)"
                errors.append(f"FAN {fan_id}: threshold {threshold} out of range {rng}")

        # Validate hysteresis ranges
        activation = fan_config.get("activation_hysteresis")
        if activation is not None:
            if not isinstance(activation, (int, float)):
                errors.append(f"FAN {fan_id}: activation_hysteresis must be numeric")
            elif activation < 0 or activation > 500:
                act = activation
                msg = f"FAN {fan_id}: activation_hysteresis {act} out of range"
                errors.append(msg)

        deactivation = fan_config.get("deactivation_hysteresis")
        if deactivation is not None:
            if not isinstance(deactivation, (int, float)):
                errors.append(f"FAN {fan_id}: deactivation_hysteresis must be numeric")
            elif deactivation < -500 or deactivation > 0:
                deact = deactivation
                msg = f"FAN {fan_id}: deactivation_hysteresis {deact} out of range"
                errors.append(msg)

        # Validate zones if present
        zones = fan_config.get("zones", [])
        if zones and not isinstance(zones, list):
            errors.append(f"FAN {fan_id}: zones must be a list")

    return errors


def export_co2_control_to_yaml(config: dict) -> dict:
    """Export co2_control configuration to YAML-compatible dict.

    :param config: The co2_control configuration section
    :return: YAML-compatible dictionary
    """
    return config


def parse_co2_control_yaml(yaml_data: dict) -> dict[str, Any]:
    """Parse co2_control YAML data into canonical config format.

    :param yaml_data: Raw YAML data for co2_control section
    :return: Canonical co2_control configuration
    """
    # Validate against schema
    result = CO2_CONTROL_CONFIG_SCHEMA(yaml_data)
    return cast(dict[str, Any], result)


def merge_co2_control_config(existing: dict, imported: dict) -> dict[str, Any]:
    """Merge imported co2_control config with existing.

    :param existing: Existing co2_control configuration
    :param imported: Imported co2_control configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    if "FANs" in imported:
        if "FANs" not in merged:
            merged["FANs"] = {}
        merged["FANs"].update(imported["FANs"])
    return merged


def load_validator() -> None:
    """Register the co2_control validator and schema with the framework."""
    register_config_validator(FEATURE_ID, co2_control_validator)
    register_config_schema(FEATURE_ID, CO2_CONTROL_CONFIG_SCHEMA)
