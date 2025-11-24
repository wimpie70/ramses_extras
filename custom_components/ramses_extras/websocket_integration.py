"""WebSocket Integration for Ramses Extras.

This module handles WebSocket command registration and integration with Home Assistant.
Uses the exact same pattern as the old working implementation.
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command({vol.Required("type"): str})  # type: ignore[misc]
async def websocket_info(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return information about available WebSocket commands."""
    commands_info = [
        {
            "type": "ramses_extras/get_bound_rem",
            "description": "Get bound REM device for a device",
            "feature": "default",
        },
        {
            "type": "ramses_extras/get_2411_schema",
            "description": "Get 2411 parameter schema for a device",
            "feature": "default",
        },
    ]

    connection.send_result(
        msg["id"],
        {
            "commands": commands_info,
            "domain": DOMAIN,
            "total_commands": len(commands_info),
            "features": ["default"],
        },
    )


async def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all WebSocket commands for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    _LOGGER.info("Registering Ramses Extras WebSocket commands")

    # Import and register commands directly (same as old working implementation)
    try:
        from .features.default.websocket_commands import (
            ws_get_2411_schema,
            ws_get_bound_rem,
        )

        # Register each command with HA (same pattern as old implementation)
        websocket_api.async_register_command(hass, ws_get_bound_rem)
        websocket_api.async_register_command(hass, ws_get_2411_schema)

        _LOGGER.info(
            "Registered Ramses Extras WebSocket commands: "
            "get_bound_rem, get_2411_schema"
        )

    except Exception as error:
        _LOGGER.error(f"Failed to register WebSocket commands: {error}")
        raise


def get_websocket_commands_info() -> dict[str, Any]:
    """Get information about registered WebSocket commands.

    Returns:
        Dictionary containing WebSocket commands information
    """
    return {
        "total_features": 1,
        "total_commands": 2,
        "commands_by_feature": {
            "default": {
                "command_count": 2,
                "commands": ["get_bound_rem", "get_2411_schema"],
            }
        },
        "commands": [
            {
                "type": "ramses_extras/get_bound_rem",
                "name": "get_bound_rem",
                "description": "Get bound REM device for a device",
                "parameters": {"device_id": "Device ID to query"},
            },
            {
                "type": "ramses_extras/get_2411_schema",
                "name": "get_2411_schema",
                "description": "Get 2411 parameter schema for a device",
                "parameters": {"device_id": "Device ID to query"},
            },
        ],
    }


async def async_setup_websocket_integration(hass: HomeAssistant) -> bool:
    """Set up WebSocket integration for Ramses Extras.

    Args:
        hass: Home Assistant instance

    Returns:
        True if setup successful, False otherwise
    """
    try:
        # Register WebSocket commands
        await async_register_websocket_commands(hass)

        # Log registration info
        info = get_websocket_commands_info()
        _LOGGER.info(
            f"WebSocket integration setup complete: {info['total_commands']} commands"
        )

        # Store integration state in hass.data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["websocket_integration"] = {
            "registered": True,
            "commands_info": info,
        }

        return True

    except Exception as error:
        _LOGGER.error(f"Failed to set up WebSocket integration: {error}")
        return False


async def async_cleanup_websocket_integration(hass: HomeAssistant) -> None:
    """Clean up WebSocket integration.

    Args:
        hass: Home Assistant instance
    """
    try:
        # Clean up integration state
        if DOMAIN in hass.data and "websocket_integration" in hass.data[DOMAIN]:
            del hass.data[DOMAIN]["websocket_integration"]

        _LOGGER.info("WebSocket integration cleanup complete")

    except Exception as error:
        _LOGGER.error(f"Error during WebSocket integration cleanup: {error}")


def is_websocket_enabled(hass: HomeAssistant) -> bool:
    """Check if WebSocket integration is enabled.

    Args:
        hass: Home Assistant instance

    Returns:
        True if WebSocket integration is enabled
    """
    websocket_data = hass.data.get(DOMAIN, {}).get("websocket_integration", {})
    return bool(websocket_data.get("registered", False))


def get_enabled_websocket_commands(
    hass: HomeAssistant, feature_name: str
) -> dict[str, str]:
    """Get WebSocket commands enabled for a specific feature.

    Args:
        hass: Home Assistant instance
        feature_name: Name of the feature

    Returns:
        Dictionary of enabled command names to command types
    """
    if not is_websocket_enabled(hass):
        return {}

    # For the simplified approach, all commands belong to the main domain
    if feature_name == DOMAIN or feature_name == "default":
        return {
            "get_bound_rem": "ramses_extras/get_bound_rem",
            "get_2411_schema": "ramses_extras/get_2411_schema",
        }

    return {}
