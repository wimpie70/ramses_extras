# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""WebSocket command handlers for Hello World Switch Card feature."""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/hello_world/toggle_switch",
        vol.Required("device_id"): str,
        vol.Optional("state"): vol.In([True, False]),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_toggle_switch(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Toggle Hello World switch state via WebSocket."""
    device_id = msg["device_id"]
    state = msg.get("state")

    try:
        # Get the feature entities manager
        from .entities import HelloWorldEntities

        # Create entities manager instance
        entities_manager = HelloWorldEntities(hass, None)

        # If state is not specified, toggle current state
        if state is None:
            current_state = entities_manager.get_entity_state(
                device_id, "switch", "hello_world_switch"
            )
            state = not current_state

        # Update entity state
        entities_manager.set_entity_state(
            device_id, "switch", "hello_world_switch", state
        )

        # Send success response
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "device_id": device_id,
                "state": state,
                "message": f"Hello World switch {'ON' if state else 'OFF'}",
            },
        )

        # Broadcast state change event for real-time updates
        hass.bus.async_fire(
            "hello_world_switch_state_changed",
            {
                "device_id": device_id,
                "state": state,
                "entity_id": f"switch.hello_world_switch_{device_id.replace(':', '_')}",
            },
        )

    except Exception as err:
        _LOGGER.error(
            f"Failed to toggle Hello World switch for device {device_id}: {err}"
        )
        connection.send_error(msg["id"], "toggle_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/hello_world/get_switch_state",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_switch_state(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Get Hello World switch state via WebSocket."""
    device_id = msg["device_id"]

    try:
        # Get the feature entities manager
        from .entities import HelloWorldEntities

        # Create entities manager instance
        entities_manager = HelloWorldEntities(hass, None)

        # Get current state
        switch_state = entities_manager.get_entity_state(
            device_id, "switch", "hello_world_switch"
        )
        binary_sensor_state = entities_manager.get_entity_state(
            device_id, "binary_sensor", "hello_world_status"
        )

        # Send response
        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "switch_state": switch_state,
                "binary_sensor_state": binary_sensor_state,
                "entity_ids": {
                    "switch": f"switch.hello_world_switch_"
                    f"{device_id.replace(':', '_')}",
                    "binary_sensor": f"binary_sensor.hello_world_status_"
                    f"{device_id.replace(':', '_')}",
                },
            },
        )

    except Exception as err:
        _LOGGER.error(
            f"Failed to get Hello World switch state for device {device_id}: {err}"
        )
        connection.send_error(msg["id"], "get_state_failed", str(err))
