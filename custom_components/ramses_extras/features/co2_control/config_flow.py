"""CO2 Control Config Flow Helper.

This module provides config flow helpers for CO2 control feature configuration.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def get_co2_control_schema(hass: HomeAssistant, device_id: str) -> vol.Schema:
    """Get CO2 control configuration schema.

    :param hass: Home Assistant instance
    :param device_id: Device identifier
    :return: Configuration schema
    """
    return vol.Schema(
        {
            vol.Optional("enabled", default=False): bool,
            vol.Optional("automation_enabled", default=False): bool,
            vol.Optional("default_threshold", default=1000): vol.All(
                vol.Coerce(int), vol.Range(min=400, max=2000)
            ),
            vol.Optional("activation_hysteresis", default=100): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=500)
            ),
            vol.Optional("deactivation_hysteresis", default=-100): vol.All(
                vol.Coerce(int), vol.Range(min=-500, max=0)
            ),
        }
    )


def get_zone_config_schema(hass: HomeAssistant) -> vol.Schema:
    """Get zone configuration schema.

    :param hass: Home Assistant instance
    :return: Zone configuration schema
    """
    return vol.Schema(
        {
            vol.Required("zone_id"): str,
            vol.Required("zone_name"): str,
            vol.Required("sensor_entity"): str,
            vol.Optional("threshold", default=1000): vol.All(
                vol.Coerce(int), vol.Range(min=400, max=2000)
            ),
            vol.Optional("enabled", default=True): bool,
        }
    )


async def async_validate_co2_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, str]:
    """Validate CO2 control configuration.

    :param hass: Home Assistant instance
    :param config: Configuration to validate
    :return: Dictionary of validation errors (empty if valid)
    """
    errors = {}

    # Validate threshold range
    threshold = config.get("default_threshold", 1000)
    if not 400 <= threshold <= 2000:
        errors["default_threshold"] = "threshold_out_of_range"

    # Validate hysteresis
    activation = config.get("activation_hysteresis", 100)
    if activation < 0:
        errors["activation_hysteresis"] = "must_be_positive"

    deactivation = config.get("deactivation_hysteresis", -100)
    if deactivation > 0:
        errors["deactivation_hysteresis"] = "must_be_negative"

    # Validate zones if present
    zones = config.get("zones", [])
    for idx, zone in enumerate(zones):
        sensor_entity = zone.get("sensor_entity")
        if sensor_entity:
            state = hass.states.get(sensor_entity)
            if not state:
                errors[f"zone_{idx}_sensor"] = "entity_not_found"

    return errors


__all__ = [
    "get_co2_control_schema",
    "get_zone_config_schema",
    "async_validate_co2_config",
]
