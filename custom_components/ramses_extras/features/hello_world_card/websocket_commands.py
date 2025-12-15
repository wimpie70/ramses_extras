# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""WebSocket command handlers for Hello World Switch Card feature.

This module provides WebSocket command handlers for the Hello World feature,
including toggle switch and get switch state commands for frontend integration.

:platform: Home Assistant
:feature: Hello World WebSocket Commands
:components: WebSocket Handlers, Frontend Integration, Real-time Communication
:command_types: Toggle Switch, Get State, Error Handling
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers
from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
    SimpleEntityManager,
)

from .const import HELLO_WORLD_BINARY_SENSOR_CONFIGS, HELLO_WORLD_SWITCH_CONFIGS

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _get_entities_manager(hass: HomeAssistant) -> Any:
    """Get the shared entities manager from the Hello World feature.

    This function retrieves the SimpleEntityManager instance that is shared across
    the Hello World feature. The manager is used for entity coordination and state
    management.

    The function first tries to retrieve the manager from the Home Assistant data
    registry. If not found, it creates a new instance as a fallback.

    Args:
        hass: Home Assistant instance

    Returns:
        SimpleEntityManager instance or None if not available

    Note:
        This is an internal helper function used by WebSocket command handlers
        to access the shared entity management system.
    """
    try:
        # Try to get the global registry from Home Assistant data
        if hasattr(hass, "data") and "ramses_extras" in hass.data:
            registry = hass.data["ramses_extras"]
            if "hello_world_entities" in registry:
                return registry["hello_world_entities"]

        # If not found, create a new SimpleEntityManager instance
        return SimpleEntityManager(hass)

    except Exception as err:
        _LOGGER.error(f"Could not get shared entities manager: {err}")
        return None


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/hello_world/toggle_switch",
        vol.Required("device_id"): str,
        vol.Required("state"): vol.In([True, False]),
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
        # Generate entity ID using the template from const
        switch_entity_id = EntityHelpers.generate_entity_name_from_template(
            "switch",
            HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )

        # State must be explicitly provided to avoid synchronization issues
        if state is None:
            _LOGGER.error(
                "State parameter is required for toggle_switch WebSocket command"
            )
            connection.send_error(
                msg["id"], "state_required", "State parameter is required"
            )
            return

        # Check if entity exists before calling service
        entity_state = hass.states.get(switch_entity_id)
        if not entity_state:
            _LOGGER.error(
                f"Switch entity {switch_entity_id} does not exist in Home Assistant!"
            )
            connection.send_error(
                msg["id"],
                "entity_not_found",
                f"Switch entity {switch_entity_id} not found",
            )
            return

        _LOGGER.info(
            f"Entity {switch_entity_id} exists, calling service to set state to {state}"
        )

        # Use Home Assistant's switch service to control the entity
        # This will trigger the automation to handle binary sensor coordination
        if state:
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch_entity_id}
            )
        else:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": switch_entity_id}
            )

        _LOGGER.info(f"Set switch entity {switch_entity_id} to {state}")
        _LOGGER.info(
            f"Automation will handle binary sensor coordination for device {device_id}"
        )

        # Send success response
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "device_id": device_id,
                "state": state,
                "entity_id": switch_entity_id,
                "message": f"Hello World switch {'ON' if state else 'OFF'} "
                f"(automation handles coordination)",
                "framework_pattern": (
                    "switch -> HA Service -> Automation -> binary_sensor"
                ),
            },
        )

        _LOGGER.info(
            f"Successfully sent switch command for device {device_id} to {state}. "
            f"Automation will handle binary sensor coordination."
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
        # Generate entity IDs using the templates from const
        switch_entity_id = EntityHelpers.generate_entity_name_from_template(
            "switch",
            HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )
        binary_sensor_entity_id = EntityHelpers.generate_entity_name_from_template(
            "binary_sensor",
            HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )

        # Get current states directly from Home Assistant
        switch_state = hass.states.get(switch_entity_id)
        binary_sensor_state = hass.states.get(binary_sensor_entity_id)

        switch_is_on = switch_state.state == "on" if switch_state else False
        binary_sensor_is_on = (
            binary_sensor_state.state == "on" if binary_sensor_state else False
        )

        # Send response
        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "switch_state": switch_is_on,
                "binary_sensor_state": binary_sensor_is_on,
                "entity_ids": {
                    "switch": switch_entity_id,
                    "binary_sensor": binary_sensor_entity_id,
                },
                "framework_managed": True,
            },
        )

    except Exception as err:
        _LOGGER.error(
            f"Failed to get Hello World switch state for device {device_id}: {err}"
        )
        connection.send_error(msg["id"], "get_state_failed", str(err))
