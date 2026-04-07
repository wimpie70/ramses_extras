from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api

from ...const import DOMAIN
from .resolver import SensorControlResolver

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/sensor_control/get_device_config",
        vol.Required("device_id"): str,
        vol.Optional("device_type"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_sensor_control_device_config(
    hass: Any,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    device_id = str(msg.get("device_id") or "").strip()
    if not device_id:
        connection.send_error(msg["id"], "missing_device_id", "device_id is required")
        return

    device_type = msg.get("device_type")

    try:

        def _extract_device_id(raw: Any) -> str | None:
            if raw is None:
                return None
            if isinstance(raw, str):
                return raw
            for attr in ("id", "device_id", "_id", "name"):
                if hasattr(raw, attr):
                    value = getattr(raw, attr)
                    if value is not None:
                        return str(value)
            return str(raw)

        def _get_device_type(device_id: str) -> str | None:
            devices = hass.data.get(DOMAIN, {}).get("devices", [])
            target_colon = str(device_id).replace("_", ":")

            for device in devices:
                if isinstance(device, dict):
                    raw_id = device.get("device_id")
                    dev_type = device.get("type")
                else:
                    raw_id = device
                    dev_type = getattr(device, "type", None)

                dev_id = _extract_device_id(raw_id)
                if dev_id is None:
                    continue

                dev_id_str = dev_id.replace("_", ":")
                if dev_id_str == target_colon:
                    return str(dev_type) if dev_type is not None else None
            return None

        if not isinstance(device_type, str) or not device_type.strip():
            device_type = _get_device_type(device_id)

        if not device_type:
            connection.send_error(
                msg["id"],
                "unknown_device_type",
                f"Could not determine device_type for device_id {device_id}",
            )
            return

        resolver = SensorControlResolver(hass)
        result = await resolver.resolve_entity_mappings(device_id, str(device_type))

        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "device_type": str(device_type),
                "success": True,
                **result,
            },
        )

    except Exception as err:
        _LOGGER.error(
            "Failed to resolve sensor_control config for %s: %s",
            device_id,
            err,
            exc_info=True,
        )
        connection.send_error(msg["id"], "get_device_config_failed", str(err))


__all__ = ["ws_get_sensor_control_device_config"]
