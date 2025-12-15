"""WebSocket commands for the default feature.

This module contains WebSocket command handlers for the default feature,
including utility commands that can be used by any feature.
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api

from ...const import (
    AVAILABLE_FEATURES,
    DOMAIN,
    discover_ws_commands,
    get_all_ws_commands,
)
from ...framework.helpers.websocket_base import GetEntityMappingsCommand

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/websocket_info",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_websocket_info(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return information about available WebSocket commands.

    This utility command provides discovery functionality for all available
    WebSocket commands across all features. Moved to default feature for
    architectural consistency.
    """
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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_entity_mappings",
        vol.Optional("feature_id"): str,  # Feature identifier
        vol.Optional("const_module"): str,  # Full const module path
        vol.Optional("device_id"): str,  # Device ID for template parsing
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_entity_mappings(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Default feature WebSocket command to get entity mappings.

    This command is available through the default feature and can be used
    by any other feature to retrieve entity mappings. It supports both
    feature_id and const_module parameters for flexibility.
    """
    feature_id = msg.get("feature_id")
    const_module = msg.get("const_module")
    device_id = msg.get("device_id")

    _LOGGER.info(
        f"ws_get_entity_mappings called with: feature_id={feature_id}, "
        f"const_module={const_module}, device_id={device_id}"
    )

    try:
        # Determine feature identifier
        if const_module:
            feature_identifier = const_module
        elif feature_id:
            feature_identifier = feature_id
        else:
            connection.send_error(
                msg["id"],
                "missing_feature_identifier",
                "Either feature_id or const_module must be provided",
            )
            return

        _LOGGER.info(f"Using feature_identifier: {feature_identifier}")

        # Create and execute the command
        cmd = GetEntityMappingsCommand(hass, feature_identifier)
        await cmd.execute(connection, msg)

    except Exception as err:
        _LOGGER.error(f"Failed to get entity mappings: {err}")
        _LOGGER.error(f"Exception details: {repr(err)}")
        connection.send_error(msg["id"], "get_entity_mappings_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_all_feature_entities",
        vol.Required("feature_id"): str,  # Feature identifier
        vol.Required("device_id"): str,  # Device ID for template parsing
        vol.Optional("const_module"): str,  # Full const module path (alternative)
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_all_feature_entities(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """WebSocket command to retrieve all entities from a feature with device_id support.

    This command retrieves all entity configurations from a feature and returns them
    as parsed entity mappings that can be used from anywhere in the frontend.
    It keeps the frontend and feature clean by providing a centralized way to
    access entity information.

    Part of the default feature, so it's always available to all other features.
    """
    from custom_components.ramses_extras.framework.helpers.websocket_base import (
        GetAllFeatureEntitiesCommand,
    )

    feature_id = msg.get("feature_id")
    const_module = msg.get("const_module")

    try:
        # Determine feature identifier
        if const_module:
            feature_identifier = const_module
        elif feature_id:
            feature_identifier = feature_id
        else:
            connection.send_error(
                msg["id"],
                "missing_feature_identifier",
                "Either feature_id or const_module must be provided",
            )
            return

        # Create and execute the command
        cmd = GetAllFeatureEntitiesCommand(hass, feature_identifier)
        await cmd.execute(connection, msg)

    except Exception as err:
        _LOGGER.error(f"Failed to get all feature entities: {err}")
        connection.send_error(msg["id"], "get_all_feature_entities_failed", str(err))


def register_default_websocket_commands() -> dict[str, str]:
    """Register WebSocket commands for the default feature.

    Returns:
        Dictionary mapping command names to their WebSocket command types
    """
    return {
        "websocket_info": "ramses_extras/websocket_info",  # Utility for cmd discovery
        "get_entity_mappings": "ramses_extras/get_entity_mappings",
        "get_all_feature_entities": "ramses_extras/get_all_feature_entities",
    }
