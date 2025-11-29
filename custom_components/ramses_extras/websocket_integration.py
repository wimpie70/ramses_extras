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

    # Import commands dynamically for each feature to ensure decorators are executed
    for feature_name, commands in all_commands.items():
        try:
            # Dynamic import of websocket_commands module for this feature
            # This ensures the module is loaded and decorators are executed
            websocket_module_path = f"custom_components.ramses_extras.features.{feature_name}.websocket_commands"  # noqa: E501
            _LOGGER.info(f"🔌 Importing WebSocket module: {websocket_module_path}")
            websocket_module = __import__(websocket_module_path, fromlist=[""])
            _LOGGER.info(
                f"✅ Successfully imported WebSocket module: {websocket_module}"
            )

            # Check if the expected handler functions exist and register them
            expected_handlers = [f"ws_{cmd_name}" for cmd_name in commands.keys()]
            for handler_name in expected_handlers:
                handler_func = getattr(websocket_module, handler_name, None)
                if handler_func:
                    _LOGGER.info(f"✅ Found handler function: {handler_name}")
                    # Register the handler with Home Assistant's WebSocket API
                    try:
                        websocket_api.async_register_command(hass, handler_func)
                        _LOGGER.info(f"🔗 Registered WebSocket command: {handler_name}")
                    except Exception as register_error:
                        _LOGGER.error(
                            f"❌ Failed to register {handler_name}: {register_error}"
                        )
                else:
                    _LOGGER.warning(f"❌ Missing handler function: {handler_name}")

        except ImportError as error:
            # Check if this is a missing websocket_commands.py file
            if "websocket_commands" in str(error):
                _LOGGER.info(
                    f"Feature '{feature_name}' does not have a websocket_commands.py "
                    f"file - commands are registered via decorators in other modules"
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

    # Register the websocket_info function defined in this module
    try:
        websocket_api.async_register_command(hass, websocket_info)
        _LOGGER.info("🔗 Registered websocket_info command")
    except Exception as error:
        _LOGGER.error(f"❌ Failed to register websocket_info: {error}")

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
