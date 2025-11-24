"""WebSocket Integration for Ramses Extras.

This module handles WebSocket command registration and integration with Home Assistant.
Uses the exact same pattern as the old working implementation.
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import AVAILABLE_FEATURES, DOMAIN, discover_ws_commands, get_all_ws_commands

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command({vol.Required("type"): str})  # type: ignore[misc]
async def websocket_info(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return information about available WebSocket commands."""
    # Get all registered WebSocket commands
    all_commands = get_all_ws_commands()
    features_with_commands = discover_ws_commands()

    # Build commands info dynamically from registry
    commands_info = []
    for feature_name, commands in all_commands.items():
        feature_config = AVAILABLE_FEATURES.get(feature_name, {})
        feature_description = feature_config.get(
            "description", f"Feature: {feature_name}"
        )

        for command_name, command_type in commands.items():
            commands_info.append(
                {
                    "type": command_type,
                    "description": f"{command_name.replace('_', ' ').title()} - "
                    f"{feature_description}",
                    "feature": feature_name,
                }
            )

    connection.send_result(
        msg["id"],
        {
            "commands": commands_info,
            "domain": DOMAIN,
            "total_commands": len(commands_info),
            "features": features_with_commands,
        },
    )


async def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all WebSocket commands for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    _LOGGER.info("Registering Ramses Extras WebSocket commands")

    # Get all registered WebSocket commands from the registry
    all_commands = get_all_ws_commands()
    features_with_commands = discover_ws_commands()

    if not features_with_commands:
        _LOGGER.warning("No WebSocket commands registered for any features")
        return

    # Import commands dynamically for each feature
    for feature_name, commands in all_commands.items():
        try:
            # Dynamic import based on feature name (correct relative import path)
            if feature_name == "default":
                from .features.default.websocket_commands import (
                    ws_get_2411_schema,
                    ws_get_bound_rem,
                )

                # Register commands if they exist in the commands dict
                if "get_bound_rem" in commands:
                    websocket_api.async_register_command(hass, ws_get_bound_rem)
                    _LOGGER.debug(
                        f"Registered WebSocket command: get_bound_rem for feature: "
                        f"{feature_name}"
                    )
                if "get_2411_schema" in commands:
                    websocket_api.async_register_command(hass, ws_get_2411_schema)
                    _LOGGER.debug(
                        f"Registered WebSocket command: get_2411_schema for feature: "
                        f"{feature_name}"
                    )
            else:
                # For future features, use the pattern
                # This will be expanded when new features are added
                _LOGGER.debug(
                    f"No import logic implemented yet for feature: {feature_name}"
                )

        except ImportError as error:
            _LOGGER.warning(
                f"Could not import WebSocket commands for feature '{feature_name}': "
                f"{error}"
            )
        except Exception as error:
            _LOGGER.error(
                f"Error registering commands for feature '{feature_name}': {error}"
            )

    # Log summary
    total_commands = sum(len(commands) for commands in all_commands.values())
    _LOGGER.info(
        f"Registered {total_commands} WebSocket commands for "
        f"{len(features_with_commands)} features: "
        f"{', '.join(features_with_commands)}"
    )


def get_websocket_commands_info() -> dict[str, Any]:
    """Get information about registered WebSocket commands.

    Returns:
        Dictionary containing WebSocket commands information
    """
    # Get all registered WebSocket commands from the registry
    all_commands = get_all_ws_commands()
    features_with_commands = discover_ws_commands()

    # Build commands by feature
    commands_by_feature = {}
    commands_list = []

    for feature_name, commands in all_commands.items():
        command_names = list(commands.keys())
        commands_by_feature[feature_name] = {
            "command_count": len(command_names),
            "commands": command_names,
        }

        # Add to commands list with detailed info
        for command_name, command_type in commands.items():
            commands_list.append(
                {
                    "type": command_type,
                    "name": command_name,
                    "description": f"{command_name.replace('_', ' ').title()} command",
                    "parameters": {"device_id": "Device ID to query"},
                    "feature": feature_name,
                }
            )

    return {
        "total_features": len(features_with_commands),
        "total_commands": sum(len(commands) for commands in all_commands.values()),
        "commands_by_feature": commands_by_feature,
        "commands": commands_list,
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

    # Get all registered commands
    all_commands = get_all_ws_commands()

    # Check if feature has commands registered
    feature_commands = all_commands.get(feature_name, {})

    if not feature_commands:
        return {}

    # Check if the feature is enabled
    # Default feature is always considered enabled
    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
    if config_entry and hasattr(config_entry, "options"):
        enabled_features = config_entry.options.get("enabled_features", [])

        # Default feature is always available
        if feature_name == "default":
            return feature_commands

        # Other features must be explicitly enabled
        if feature_name in enabled_features:
            return feature_commands

        return {}

    # Fallback: if no config entry, only allow default feature
    return feature_commands if feature_name == "default" else {}
