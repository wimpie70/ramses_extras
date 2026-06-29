"""WebSocket commands for the temp_control feature."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api

from ...const import DOMAIN
from ...framework.helpers.config.migration import get_migrated_feature_section
from .const import TEMP_CONTROL_DEFAULTS

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/temp_control/get_device_config",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_temp_control_device_config(
    hass: Any,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return temp_control settings for a device."""
    device_id = str(msg.get("device_id") or "").strip()
    if not device_id:
        connection.send_error(msg["id"], "missing_device_id", "device_id is required")
        return

    try:
        config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
        if config_entry is None:
            connection.send_error(
                msg["id"], "no_config_entry", "Config entry not found"
            )
            return

        merged: dict[str, Any] = dict(config_entry.data or {})
        merged.update(config_entry.options or {})
        section = get_migrated_feature_section(merged, "temp_control")

        settings: dict[str, Any] = {}
        for key, default in TEMP_CONTROL_DEFAULTS.items():
            if key == "enabled":
                continue
            settings[key] = section.get(key, default)

        # Also include the comfort_temp_entity from sensor_control if
        # configured, so the card can display the actual source.
        sc_section = get_migrated_feature_section(merged, "sensor_control")
        devices = sc_section.get("devices", {})
        if isinstance(devices, dict):
            from ...framework.helpers.config.model import normalize_device_id

            norm_id = normalize_device_id(device_id)
            dev_cfg = devices.get(norm_id) or devices.get(device_id)
            if isinstance(dev_cfg, dict):
                cte = str(dev_cfg.get("comfort_temp_entity") or "").strip()
                if cte:
                    settings["comfort_temp_entity"] = cte

        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "success": True,
                "settings": settings,
            },
        )

    except Exception as err:
        _LOGGER.error(
            "Failed to get temp_control config for %s: %s",
            device_id,
            err,
            exc_info=True,
        )
        connection.send_error(msg["id"], "get_device_config_failed", str(err))


# Keys that can be updated via the card, with their type coercion.
_SETTING_COERCIONS: dict[str, Any] = {
    "comfort_delta_activate": float,
    "comfort_delta_deactivate": float,
    "cooling_delta_activate": float,
    "cooling_delta_deactivate": float,
    "min_outdoor_temp": float,
    "min_bypass_mode_interval_seconds": int,
    "default_desired_speed": str,
    "dewpoint_guard_enabled": bool,
    "dewpoint_margin_c": float,
    "supply_cooler_delta_activate": float,
    "supply_cooler_delta_deactivate": float,
    "min_supply_temp": float,
}


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/temp_control/set_device_config",
        vol.Required("device_id"): str,
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_set_temp_control_device_config(
    hass: Any,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist temp_control settings from the card edit window."""
    device_id = str(msg.get("device_id") or "").strip()
    if not device_id:
        connection.send_error(msg["id"], "missing_device_id", "device_id is required")
        return

    raw_settings = msg.get("settings") or {}
    if not isinstance(raw_settings, dict):
        connection.send_error(msg["id"], "invalid_settings", "settings must be a dict")
        return

    try:
        # Coerce and validate settings
        settings: dict[str, Any] = {}
        for key, coerce in _SETTING_COERCIONS.items():
            if key not in raw_settings:
                continue
            raw_val = raw_settings[key]
            try:
                if coerce is bool:
                    settings[key] = (
                        raw_val
                        if isinstance(raw_val, bool)
                        else str(raw_val).strip().lower() in {"1", "true", "yes", "on"}
                    )
                else:
                    settings[key] = coerce(raw_val)
            except TypeError, ValueError:
                connection.send_error(
                    msg["id"],
                    "invalid_value",
                    f"Invalid value for {key}: {raw_val}",
                )
                return

        if not settings:
            connection.send_error(
                msg["id"], "no_settings", "No valid settings provided"
            )
            return

        config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
        if config_entry is None:
            connection.send_error(
                msg["id"], "no_config_entry", "Config entry not found"
            )
            return

        from .config_flow import _persist_temp_control_settings

        class _FlowShim:
            def __init__(self, hass: Any, entry: Any) -> None:
                self.hass = hass
                self._config_entry = entry

        flow = _FlowShim(hass, config_entry)
        _persist_temp_control_settings(flow, settings)

        _LOGGER.info(
            "Updated temp_control settings for device %s: %s",
            device_id,
            list(settings.keys()),
        )

        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "success": True,
                "settings": settings,
            },
        )

    except Exception as err:
        _LOGGER.error(
            "Failed to set temp_control config for %s: %s",
            device_id,
            err,
            exc_info=True,
        )
        connection.send_error(msg["id"], "set_device_config_failed", str(err))
