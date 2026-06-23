"""Feature-specific config flow for temp_control.

Provides a combined device-selection + basic settings form.

Called by the root options flow via:
- custom_components.ramses_extras.config_flow.RamsesExtrasOptionsFlowHandler
  -> async_step_feature_config()
  -> imports this module and calls async_step_temp_control_config(flow, user_input)
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import FlowResult
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES
from ...framework.helpers.config.migration import get_migrated_feature_section

_LOGGER = logging.getLogger(__name__)


def _get_section_defaults(flow: Any) -> dict[str, Any]:
    options = dict(flow._config_entry.options or {})
    merged = dict(flow._config_entry.data or {})
    merged.update(options)

    section = get_migrated_feature_section(merged, "temp_control")

    return {
        "comfort_delta_activate": float(section.get("comfort_delta_activate", 1.0)),
        "comfort_delta_deactivate": float(section.get("comfort_delta_deactivate", 0.5)),
        "cooling_delta_activate": float(section.get("cooling_delta_activate", 1.0)),
        "cooling_delta_deactivate": float(section.get("cooling_delta_deactivate", 0.5)),
        "min_outdoor_temp": float(section.get("min_outdoor_temp", 10.0)),
        "min_bypass_mode_interval_seconds": int(
            section.get("min_bypass_mode_interval_seconds", 180)
        ),
    }


def _persist_temp_control_settings(flow: Any, settings: dict[str, Any]) -> None:
    config_entry = flow._config_entry
    options = dict(config_entry.options)

    # Legacy store
    legacy_section = options.get("temp_control")
    legacy_section = legacy_section if isinstance(legacy_section, dict) else {}
    legacy_section = dict(legacy_section)
    legacy_section.update(settings)
    options["temp_control"] = legacy_section

    # Canonical store
    root = options.get("ramses_extras")
    root = root if isinstance(root, dict) else {}
    root = dict(root)
    features = root.get("features")
    features = features if isinstance(features, dict) else {}
    features = dict(features)
    canonical = features.get("temp_control")
    canonical = canonical if isinstance(canonical, dict) else {}
    canonical = dict(canonical)
    canonical.update(settings)
    features["temp_control"] = canonical
    root["features"] = features
    options["ramses_extras"] = root

    flow.hass.config_entries.async_update_entry(config_entry, options=options)

    refresh = getattr(flow, "_refresh_config_entry", None)
    if callable(refresh):
        refresh(flow.hass)


async def async_step_temp_control_config(
    flow: Any, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Handle temp_control configuration."""

    feature_id = "temp_control"

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
            "comfort_delta_activate": float(user_input["comfort_delta_activate"]),
            "comfort_delta_deactivate": float(user_input["comfort_delta_deactivate"]),
            "cooling_delta_activate": float(user_input["cooling_delta_activate"]),
            "cooling_delta_deactivate": float(user_input["cooling_delta_deactivate"]),
            "min_outdoor_temp": float(user_input["min_outdoor_temp"]),
            "min_bypass_mode_interval_seconds": int(
                user_input["min_bypass_mode_interval_seconds"]
            ),
        }
        _persist_temp_control_settings(flow, settings)

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
                "comfort_delta_activate", default=defaults["comfort_delta_activate"]
            ): vol.Coerce(float),
            vol.Required(
                "comfort_delta_deactivate", default=defaults["comfort_delta_deactivate"]
            ): vol.Coerce(float),
            vol.Required(
                "cooling_delta_activate",
                default=defaults["cooling_delta_activate"],
            ): vol.Coerce(float),
            vol.Required(
                "cooling_delta_deactivate",
                default=defaults["cooling_delta_deactivate"],
            ): vol.Coerce(float),
            vol.Required(
                "min_outdoor_temp", default=defaults["min_outdoor_temp"]
            ): vol.Coerce(float),
            vol.Required(
                "min_bypass_mode_interval_seconds",
                default=defaults["min_bypass_mode_interval_seconds"],
            ): vol.Coerce(int),
        }
    )

    info_text = f"🌡️ **{feature_name}**\n\n"
    info_text += "Controls bypass to keep indoor temperature near comfort temp.\n\n"
    info_text += "Defaults: desired speed = high (config entity).\n"

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )
