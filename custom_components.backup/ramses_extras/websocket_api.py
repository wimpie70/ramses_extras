import logging
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import WS_CMD_GET_BOUND_REM

_LOGGER = logging.getLogger(__name__)

@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_CMD_GET_BOUND_REM,
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_bound_rem(hass: HomeAssistant, connection, msg):
    """Return bound REM info for a Ramses device."""
    device_id = msg["device_id"]

    ramses_data = hass.data.get("ramses_rf")
    if not ramses_data:
        connection.send_error(msg["id"], "ramses_rf_not_found", "Ramses RF integration not loaded")
        return

    result = None
    for entry_id, data in ramses_data.items():
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


def register_ws_commands(hass: HomeAssistant):
    """Register all websocket commands for Ramses Extras."""
    hass.components.websocket_api.async_register_command(ws_get_bound_rem)
