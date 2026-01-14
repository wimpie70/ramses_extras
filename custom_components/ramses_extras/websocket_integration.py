"""WebSocket Integration for Ramses Extras.

This module ONLY handles WebSocket command registration and integration
with Home Assistant. It does NOT host command handlers themselves—those
live in per-feature websocket_commands.py modules. This keeps the
integration minimal and feature-centric.
"""

import asyncio
import importlib
import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .extras_registry import extras_registry
from .feature_utils import get_enabled_feature_names


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

    enabled_feature_names = get_enabled_feature_names(hass)

    all_commands = extras_registry.get_all_websocket_commands()
    enabled_features_with_commands = [
        feature_name
        for feature_name in enabled_feature_names
        if all_commands.get(feature_name)
    ]

    if not enabled_features_with_commands:
        _LOGGER.warning("No WebSocket commands registered for any features")
        return

    # Import modules, then register handlers with HA.
    for feature_name in enabled_features_with_commands:
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
    total_commands = sum(
        len(all_commands.get(feature_name, {}))
        for feature_name in enabled_features_with_commands
    )
    _LOGGER.info(
        "Imported WebSocket command modules for %d features: %s "
        "(%d commands available)",
        len(enabled_features_with_commands),
        ", ".join(enabled_features_with_commands),
        total_commands,
    )


def get_websocket_commands_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get information about registered WebSocket commands.

    Returns:
        Dictionary containing WebSocket commands information
    """
    all_commands = extras_registry.get_all_websocket_commands()

    enabled_feature_names = get_enabled_feature_names(hass)

    # Build commands by feature
    commands_by_feature = {}
    commands_list = []

    for feature_name in enabled_feature_names:
        commands = all_commands.get(feature_name, {})
        if not commands:
            continue
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
        "total_features": len(
            [f for f in enabled_feature_names if all_commands.get(f)]
        ),
        "total_commands": sum(
            len(all_commands.get(f, {})) for f in enabled_feature_names
        ),
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

        info = get_websocket_commands_info(hass)
        _LOGGER.info(
            "WebSocket integration setup complete: %s commands",
            info["total_commands"],
        )

        # Store integration state in hass.data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["websocket_integration"] = {
            "registered": True,
            "commands_info": info,
        }

        return True

    except Exception as error:
        _LOGGER.error("Failed to set up WebSocket integration: %s", error)
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
        _LOGGER.error("Error during WebSocket integration cleanup: %s", error)


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
    all_commands = extras_registry.get_all_websocket_commands()

    # Check if feature has commands registered in the registry
    feature_commands = all_commands.get(feature_name, {})

    if not feature_commands:
        _LOGGER.debug("No WebSocket commands registered for feature: %s", feature_name)
        return {}

    # Check if the feature is enabled based on configuration
    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")

    # Default feature is always considered enabled
    if feature_name == "default":
        _LOGGER.debug(
            "Default feature always enabled, returning %d commands",
            len(feature_commands),
        )
        return feature_commands

    if config_entry and hasattr(config_entry, "options"):
        enabled_features_raw = (
            config_entry.data.get("enabled_features")
            or config_entry.options.get("enabled_features")
            or {}
        )

        if isinstance(enabled_features_raw, dict):
            is_enabled = bool(enabled_features_raw.get(feature_name, False))
        elif isinstance(enabled_features_raw, list):
            is_enabled = feature_name in enabled_features_raw
        else:
            is_enabled = False

        if is_enabled:
            _LOGGER.debug(
                "Feature %s enabled in config, returning %d commands",
                feature_name,
                len(feature_commands),
            )
            return feature_commands

    # Fallback: if no config entry, deny non-default features
    return {}
