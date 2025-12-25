"""WebSocket Integration for Ramses Extras.

This module handles WebSocket command registration and integration with Home Assistant.
Uses the exact same pattern as the old working implementation.
"""

import asyncio
import importlib
import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, discover_ws_commands, get_all_ws_commands


def _import_websocket_module(feature_name: str) -> Any:
    """Import the WebSocket commands module for a feature.

    Importing executes the `@websocket_api.websocket_command` decorators.

    Raises:
        ImportError: If import fails.
    """

    websocket_module_path = (
        f"custom_components.ramses_extras.features.{feature_name}.websocket_commands"
    )
    return importlib.import_module(websocket_module_path)


def _register_commands_from_module(hass: HomeAssistant, module: Any) -> int:
    """Register all websocket commands found in a module.

    Home Assistant's `@websocket_api.websocket_command` decorator only tags
    a handler. Registration happens via `websocket_api.async_register_command`.

    Returns:
        Number of commands registered.
    """

    registered = 0

    for attr_name in dir(module):
        handler = getattr(module, attr_name, None)
        if not callable(handler):
            continue

        command = getattr(handler, "_ws_command", None)
        if not isinstance(command, str):
            continue

        websocket_api.async_register_command(hass, handler)
        registered += 1

    return registered


_LOGGER = logging.getLogger(__name__)


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

    # Import modules, then register handlers with HA.
    for feature_name in all_commands:
        try:
            websocket_module = await asyncio.to_thread(
                _import_websocket_module,
                feature_name,
            )
            registered = _register_commands_from_module(hass, websocket_module)
            _LOGGER.debug(
                "Imported websocket_commands module for feature '%s' (%d handlers)",
                feature_name,
                registered,
            )

        except ImportError as error:
            # Check if this is a missing websocket_commands.py file
            if "websocket_commands" in str(error):
                _LOGGER.debug(
                    "Feature '%s' has no websocket_commands module",
                    feature_name,
                )
            else:
                _LOGGER.warning(
                    f"Could not import WebSocket commands for feature '"
                    f"{feature_name}': "
                    f"{error}"
                )
        except Exception as error:
            _LOGGER.error(
                f"Error importing commands for feature '{feature_name}': {error}"
            )

    # Log summary
    total_commands = sum(len(commands) for commands in all_commands.values())
    _LOGGER.info(
        f"Imported WebSocket command modules for "
        f"{len(features_with_commands)} features: "
        f"{', '.join(features_with_commands)} "
        f"({total_commands} commands available)"
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


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup entry for websocket integration."""
    return await async_setup_websocket_integration(hass)


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

    # Get all registered commands from registry
    all_commands = get_all_ws_commands()

    # Check if feature has commands registered in the registry
    feature_commands = all_commands.get(feature_name, {})

    if not feature_commands:
        _LOGGER.debug(f"No WebSocket commands registered for feature: {feature_name}")
        return {}

    # Check if the feature is enabled based on configuration
    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")

    # Default feature is always considered enabled
    if feature_name == "default":
        _LOGGER.debug(
            f"Default feature always enabled, returning "
            f"{len(feature_commands)} commands"
        )
        return feature_commands

    # For other features, check if explicitly enabled in config
    if config_entry and hasattr(config_entry, "options"):
        enabled_features = config_entry.options.get("enabled_features", [])

        if feature_name in enabled_features:
            _LOGGER.debug(
                f"Feature {feature_name} enabled in config, returning "
                f"{len(feature_commands)} commands"
            )
            return feature_commands

        _LOGGER.debug(f"Feature {feature_name} not enabled in config")
        return {}

    # Fallback: if no config entry, deny non-default features
    _LOGGER.debug("No config entry found, only allowing default feature")
    return {}
