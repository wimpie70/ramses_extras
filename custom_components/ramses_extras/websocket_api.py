import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import WS_CMD_GET_BOUND_REM

WS_CMD_GET_2411_SCHEMA = "ramses_extras/get_2411_schema"

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[misc]
    {
        vol.Required("type"): WS_CMD_GET_BOUND_REM,
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_bound_rem(
    hass: HomeAssistant, connection: "ActiveConnection", msg: dict[str, Any]
) -> None:
    """Return bound REM info for a Ramses device."""
    device_id = msg["device_id"]

    ramses_data = hass.data.get("ramses_rf")
    if not ramses_data:
        connection.send_error(
            msg["id"], "ramses_rf_not_found", "Ramses RF integration not loaded"
        )
        return

    result = None
    for _entry_id, data in ramses_data.items():
        broker = data.get("broker")
        if not broker:
            continue
        # Each broker has devices
        devices = getattr(broker, "devices", {})
        device = devices.get(device_id)
        if device:
            if hasattr(device, "get_bound_rem"):
                bound = device.get_bound_rem()
                result = bound.id if bound else None
            else:
                result = None
            break

    if result is None:
        connection.send_result(msg["id"], {"device_id": device_id, "bound_rem": None})
    else:
        connection.send_result(msg["id"], {"device_id": device_id, "bound_rem": result})


@websocket_api.websocket_command(  # type: ignore[misc]
    {
        vol.Required("type"): WS_CMD_GET_2411_SCHEMA,
    }
)
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_2411_schema(
    hass: HomeAssistant, connection: "ActiveConnection", msg: dict[str, Any]
) -> None:
    """Return 2411 parameter schema with descriptions, min/max, units."""
    try:
        # Try different import paths for the schema
        try:
            from ramses_rf.src.ramses_tx.ramses import _2411_PARAMS_SCHEMA
        except ImportError:
            try:
                from ramses_rf.ramses_tx.ramses import _2411_PARAMS_SCHEMA
            except ImportError:
                from ramses_tx.ramses import _2411_PARAMS_SCHEMA

        connection.send_result(msg["id"], _2411_PARAMS_SCHEMA)
        _LOGGER.info("Successfully retrieved 2411 parameter schema from ramses_rf")
    except ImportError as e:
        _LOGGER.error("Failed to import 2411 parameter schema: %s", e)
        # Return a basic fallback schema for testing
        fallback_schema = {
            "75": {
                "name": "Comfort Temperature",
                "description": "Target comfort temperature",
                "data_type": "92",
                "precision": 0.01,
                "min_value": 0.0,
                "max_value": 30.0,
                "unit": "°C",
                "default_value": 21.0,
            }
        }
        connection.send_result(msg["id"], fallback_schema)
        _LOGGER.warning("Using fallback schema due to import error")
    except Exception as e:
        _LOGGER.error("Error getting 2411 schema: %s", e)
        connection.send_error(
            msg["id"], "schema_error", "Failed to retrieve parameter schema"
        )


def register_ws_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands for Ramses Extras."""
    from homeassistant.components import websocket_api

    websocket_api.async_register_command(hass, ws_get_bound_rem)
    websocket_api.async_register_command(hass, ws_get_2411_schema)
