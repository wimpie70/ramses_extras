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


def _get_entities_manager(hass: HomeAssistant) -> Any:
    """Get the shared entities manager from the Hello World feature.

    Args:
        hass: Home Assistant instance

    Returns:
        HelloWorldEntities instance or None if not available
    """
    try:
        # Try to get the global registry from Home Assistant data
        if hasattr(hass, "data") and "ramses_extras" in hass.data:
            registry = hass.data["ramses_extras"]
            if "hello_world_entities" in registry:
                return registry["hello_world_entities"]

        # If not found, this is an error - the feature should have been initialized
        _LOGGER.error(
            "Shared entities manager not found - feature may not be properly "
            "initialized"
        )
        return None

    except Exception as err:
        _LOGGER.error(f"Could not get shared entities manager: {err}")
        return None


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
    _LOGGER.info(f"WebSocket command received: {msg}")
    device_id = msg["device_id"]
    state = msg.get("state")

    _LOGGER.info(f"Processing toggle_switch for device {device_id} with state {state}")

    try:
        # Import the global entities manager class
        from .entities import HelloWorldEntities

        # Get the global entities manager from the feature
        entities_manager = _get_entities_manager(hass)

        if not entities_manager:
            raise Exception(
                "Hello World entities manager not available - feature not properly "
                "initialized"
            )

        # If state is not specified, toggle current state
        if state is None:
            current_state = entities_manager.get_entity_state(
                device_id, "switch", "hello_world_switch"
            )
            state = not current_state
            _LOGGER.info(f"Toggling from current state {current_state} to {state}")

        # Update entity state (this will trigger all necessary events and callbacks)
        _LOGGER.info(f"Setting entity state for {device_id} switch to {state}")
        entities_manager.set_entity_state(
            device_id, "switch", "hello_world_switch", state
        )

        # Also update the switch entity's HA state
        switch_entity_id = f"switch.hello_world_switch_{device_id.replace(':', '_')}"
        switch_entity = (
            hass.data.get("ramses_extras", {}).get("entities", {}).get(switch_entity_id)
        )
        if switch_entity:
            if state:
                await switch_entity.async_turn_on()
            else:
                await switch_entity.async_turn_off()
            _LOGGER.info(f"Updated switch entity HA state to {state}")
        else:
            _LOGGER.warning(
                f"Switch entity {switch_entity_id} not found for HA state update"
            )

        # Send success response
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "device_id": device_id,
                "state": state,
                "message": f"Hello World switch {'ON' if state else 'OFF'} "
                f"(automation will update binary sensor)",
                "automation_pattern": "switch -> automation -> binary_sensor",
            },
        )

        _LOGGER.info(
            f"Successfully toggled switch for device {device_id} to {state}. "
            f"Automation will handle binary sensor update."
        )

    except Exception as err:
        _LOGGER.error(
            f"Failed to toggle Hello World switch for device {device_id}: {err}"
        )
        import traceback

        _LOGGER.error(f"Traceback: {traceback.format_exc()}")
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
        # Import the global entities manager class
        from .entities import HelloWorldEntities

        # Get the global entities manager from the feature
        entities_manager = _get_entities_manager(hass)

        if not entities_manager:
            raise Exception(
                "Hello World entities manager not available - feature not properly "
                "initialized"
            )

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
