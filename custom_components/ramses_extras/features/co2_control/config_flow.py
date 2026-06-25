"""CO2 Control Config Flow Helper.

This module provides config flow helpers for CO2 control feature configuration.

Called by the root options flow via:
- custom_components.ramses_extras.config_flow.RamsesExtrasOptionsFlowHandler
  -> async_step_feature_config()
  -> imports this module and calls async_step_co2_control_config(flow, user_input)
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import FlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...framework.helpers.config.migration import get_migrated_feature_section

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
    errors: dict[str, str] = {}

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


def _get_section_defaults(flow: Any) -> dict[str, Any]:
    """Read current CO2 control settings from config entry."""
    options = dict(flow._config_entry.options or {})  # noqa: SLF001
    merged = dict(flow._config_entry.data or {})  # noqa: SLF001
    merged.update(options)

    section = get_migrated_feature_section(merged, "co2_control")

    return {
        "default_threshold": int(section.get("default_threshold", 1000)),
        "activation_hysteresis": int(section.get("activation_hysteresis", 100)),
        "deactivation_hysteresis": int(section.get("deactivation_hysteresis", -100)),
        "priority_over_humidity": bool(section.get("priority_over_humidity", True)),
        "max_runtime_minutes": int(section.get("max_runtime_minutes", 120)),
        "cooldown_period_minutes": int(section.get("cooldown_period_minutes", 15)),
    }


def _persist_co2_control_settings(flow: Any, settings: dict[str, Any]) -> None:
    """Persist CO2 control settings to config entry options."""
    config_entry = flow._config_entry  # noqa: SLF001
    options = dict(config_entry.options)

    # Legacy store
    legacy_section = options.get("co2_control")
    legacy_section = legacy_section if isinstance(legacy_section, dict) else {}
    legacy_section = dict(legacy_section)
    legacy_section.update(settings)
    options["co2_control"] = legacy_section

    # Canonical store
    root = options.get("ramses_extras")
    root = root if isinstance(root, dict) else {}
    root = dict(root)
    features = root.get("features")
    features = features if isinstance(features, dict) else {}
    features = dict(features)
    canonical = features.get("co2_control")
    canonical = canonical if isinstance(canonical, dict) else {}
    canonical = dict(canonical)
    canonical.update(settings)
    features["co2_control"] = canonical
    root["features"] = features
    options["ramses_extras"] = root

    flow.hass.config_entries.async_update_entry(config_entry, options=options)  # noqa: SLF001

    # Sync saved settings to existing number entities so they take
    # effect immediately without requiring a reload.
    _sync_settings_to_number_entities(flow.hass, settings)

    refresh = getattr(flow, "_refresh_config_entry", None)  # noqa: SLF001
    if callable(refresh):
        refresh(flow.hass)  # noqa: SLF001


def _sync_settings_to_number_entities(hass: Any, settings: dict[str, Any]) -> None:
    """Update existing CO2 number entities with new config flow values."""
    from .const import CO2_NUMBER_CONFIGS

    # Map config flow keys → number_type
    key_to_number_type = {
        "default_threshold": "co2_threshold",
        "activation_hysteresis": "co2_activation_hysteresis",
        "deactivation_hysteresis": "co2_deactivation_hysteresis",
    }

    entities = hass.data.get(DOMAIN, {}).get("entities", {})
    for config_key, value in settings.items():
        number_type = key_to_number_type.get(config_key)
        if not number_type:
            continue
        entity_template = CO2_NUMBER_CONFIGS.get(number_type, {}).get(
            "entity_template", ""
        )
        if not entity_template:
            continue
        # Update all CO2 number entities of this type
        for entity_id, entity in list(entities.items()):
            if number_type in entity_id and hasattr(entity, "async_set_native_value"):
                try:
                    hass.loop.call_soon_threadsafe(
                        lambda e=entity, v=value: hass.async_create_task(
                            e.async_set_native_value(float(v))
                        )
                    )
                except Exception:
                    pass


async def async_step_co2_control_config(
    flow: Any, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle co2_control configuration.

    Combined device-selection + threshold/hysteresis settings form.
    """
    feature_id = "co2_control"

    flow._refresh_config_entry(flow.hass)  # noqa: SLF001

    feature_config = AVAILABLE_FEATURES.get(feature_id, {})
    feature_name = feature_config.get("name", feature_id)

    helper = flow._get_config_flow_helper()  # noqa: SLF001

    matrix_state = flow._get_persisted_matrix_state()  # noqa: SLF001
    if matrix_state:
        helper.restore_matrix_state(matrix_state)

    flow._old_matrix_state = deepcopy(matrix_state)  # noqa: SLF001

    devices = flow._get_all_devices()  # noqa: SLF001
    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)
    current_enabled = helper.get_enabled_devices_for_feature(feature_id)

    device_options = [
        selector.SelectOptionDict(
            value=dev_id,
            label=flow._get_device_label(dev),  # noqa: SLF001
        )
        for dev in filtered_devices
        if (dev_id := flow._extract_device_id(dev))  # noqa: SLF001
    ]

    option_values = {opt["value"] for opt in device_options}
    current_enabled = [d for d in current_enabled if d in option_values]

    defaults = _get_section_defaults(flow)

    if user_input is not None:
        selected_device_ids = user_input.get("enabled_devices", [])
        helper.set_enabled_devices_for_feature(feature_id, selected_device_ids)

        settings = {
            "default_threshold": int(user_input["default_threshold"]),
            "activation_hysteresis": int(user_input["activation_hysteresis"]),
            "deactivation_hysteresis": int(user_input["deactivation_hysteresis"]),
            "priority_over_humidity": bool(
                user_input.get(
                    "priority_over_humidity", defaults["priority_over_humidity"]
                )
            ),
            "max_runtime_minutes": int(
                user_input.get("max_runtime_minutes", defaults["max_runtime_minutes"])
            ),
            "cooldown_period_minutes": int(
                user_input.get(
                    "cooldown_period_minutes", defaults["cooldown_period_minutes"]
                )
            ),
        }
        _persist_co2_control_settings(flow, settings)

        flow._selected_feature = feature_id  # noqa: SLF001
        flow._temp_matrix_state = helper.get_feature_device_matrix_state()  # noqa: SLF001

        return await flow._show_matrix_based_confirmation()  # noqa: SLF001

    schema = vol.Schema(
        {
            vol.Required(
                "enabled_devices", default=current_enabled
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=device_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                "default_threshold",
                default=defaults["default_threshold"],
            ): vol.All(vol.Coerce(int), vol.Range(min=400, max=2000)),
            vol.Required(
                "activation_hysteresis",
                default=defaults["activation_hysteresis"],
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=500)),
            vol.Required(
                "deactivation_hysteresis",
                default=defaults["deactivation_hysteresis"],
            ): vol.All(vol.Coerce(int), vol.Range(min=-500, max=0)),
            vol.Required(
                "priority_over_humidity",
                default=defaults["priority_over_humidity"],
            ): bool,
            vol.Required(
                "max_runtime_minutes",
                default=defaults["max_runtime_minutes"],
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=480)),
            vol.Required(
                "cooldown_period_minutes",
                default=defaults["cooldown_period_minutes"],
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=360)),
        }
    )

    info_text = f"🌫️ **{feature_name}**\n\n"
    info_text += "CO2-based ventilation control with priority over humidity.\n"
    info_text += "Set the threshold and hysteresis values (ppm).\n"

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = [
    "get_co2_control_schema",
    "get_zone_config_schema",
    "async_validate_co2_config",
    "async_step_co2_control_config",
]
