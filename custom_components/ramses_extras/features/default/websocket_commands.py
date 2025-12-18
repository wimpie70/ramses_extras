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
from ...framework.helpers.ramses_commands import RamsesCommands
from ...framework.helpers.websocket_base import GetEntityMappingsCommand

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/default/get_enabled_features",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_enabled_features(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return enabled_features for the Ramses Extras config entry.

    This command is part of the default feature (always enabled), so cards can
    always query feature flags via WebSocket without depending on a generated
    JS file.
    """
    try:
        enabled_features = hass.data.get(DOMAIN, {}).get("enabled_features")
        if enabled_features is None:
            config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
            if config_entry is not None:
                enabled_features = (
                    config_entry.data.get("enabled_features")
                    or config_entry.options.get("enabled_features")
                    or {}
                )
            else:
                enabled_features = {}

        connection.send_result(msg["id"], {"enabled_features": enabled_features})

    except Exception as err:
        _LOGGER.error("Failed to get enabled features: %s", err)
        connection.send_error(msg["id"], "get_enabled_features_failed", str(err))


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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_available_devices",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_available_devices(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return available Ramses devices for card editors.

    This uses the device objects discovered and stored during integration setup.
    """

    def _extract_device_id(device: Any) -> str | None:
        if isinstance(device, str):
            return device
        for attr in ("id", "device_id", "_id", "name"):
            if hasattr(device, attr):
                value = getattr(device, attr)
                if value is not None:
                    return str(value)
        return None

    def _extract_device_type(device: Any) -> str | None:
        for attr in ("type", "_SLUG", "model", "__class__"):
            if attr == "__class__":
                if hasattr(device, "__class__"):
                    return str(device.__class__.__name__)
                continue
            if hasattr(device, attr):
                value = getattr(device, attr)
                if value is not None:
                    return str(value)
        return None

    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    results: list[dict[str, Any]] = []
    if isinstance(devices, list):
        for device in devices:
            device_id = _extract_device_id(device)
            if not device_id:
                continue
            results.append(
                {
                    "device_id": device_id,
                    "device_type": _extract_device_type(device) or "Unknown",
                }
            )

    connection.send_result(msg["id"], {"devices": results})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_bound_rem",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_bound_rem(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return the bound REM/DIS device for a FAN device, if any."""

    device_id = str(msg["device_id"])
    commands = RamsesCommands(hass)
    bound = await commands._get_bound_rem_device(device_id)
    connection.send_result(msg["id"], {"device_id": device_id, "bound_rem": bound})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_2411_schema",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_2411_schema(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return a lightweight 2411 parameter schema for a device.

    ramses_extras does not own the authoritative schema; ramses_cc does.
    For the frontend parameter editor we provide a pragmatic schema derived from
    existing HA number entities for the device (param_* entities).
    """

    device_id = str(msg["device_id"]).replace(":", "_").lower()
    prefix = f"number.{device_id}_param_"
    schema: dict[str, Any] = {}

    for st in hass.states.async_all():
        entity_id = st.entity_id
        if not entity_id.startswith(prefix):
            continue
        param_id = entity_id.removeprefix(prefix).upper()
        attrs = dict(st.attributes)
        schema[param_id] = {
            "name": attrs.get("friendly_name") or f"Parameter {param_id}",
            "description": attrs.get("friendly_name") or f"Parameter {param_id}",
            "min_value": attrs.get("min"),
            "max_value": attrs.get("max"),
            "precision": attrs.get("step"),
            "unit": attrs.get("unit_of_measurement"),
            "data_unit": attrs.get("unit_of_measurement"),
        }

    connection.send_result(msg["id"], schema)


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
