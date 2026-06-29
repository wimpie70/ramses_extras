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
