"""WebSocket commands for the default feature.

This module contains WebSocket command handlers for the default feature,
including utility commands that can be used by any feature.
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...extras_registry import extras_registry
from ...framework.helpers.device.filter import DeviceFilter
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

        options_payload: dict[str, Any] = {}
        config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
        if config_entry is not None:
            default_poll_ms = getattr(config_entry, "options", {}).get(
                "ramses_debugger_default_poll_ms"
            )
            if isinstance(default_poll_ms, int):
                options_payload["ramses_debugger_default_poll_ms"] = int(
                    default_poll_ms
                )

        connection.send_result(
            msg["id"],
            {
                "enabled_features": enabled_features,
                "options": options_payload,
            },
        )

    except Exception as err:
        _LOGGER.error("Failed to get enabled features: %s", err)
        connection.send_error(msg["id"], "get_enabled_features_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/default/get_cards_enabled",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_cards_enabled(
    hass: "HomeAssistant", connection: "WebSocket", msg: dict[str, Any]
) -> None:
    try:
        cards_enabled = hass.data.get(DOMAIN, {}).get("cards_enabled") is True
        connection.send_result(msg["id"], {"cards_enabled": cards_enabled})
    except Exception as err:
        _LOGGER.error("Failed to get cards_enabled: %s", err)
        connection.send_error(msg["id"], "get_cards_enabled_failed", str(err))


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
    all_commands = extras_registry.get_all_websocket_commands()
    features_with_commands = extras_registry.get_features_with_websocket_commands()

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

    _LOGGER.debug(
        "ws_get_entity_mappings called with: feature_id=%s, const_module=%s, "
        "device_id=%s",
        feature_id,
        const_module,
        device_id,
    )

    try:

        def _extract_device_id(raw: Any) -> str | None:
            if raw is None:
                return None
            if isinstance(raw, str):
                return raw
            for attr in ("id", "device_id", "_id", "name"):
                if hasattr(raw, attr):
                    value = getattr(raw, attr)
                    if value is not None:
                        return str(value)
            return str(raw)

        def _get_device_type(device_id: str) -> str | None:
            devices = hass.data.get(DOMAIN, {}).get("devices", [])
            target_colon = str(device_id).replace("_", ":")

            for device in devices:
                if isinstance(device, dict):
                    raw_id = device.get("device_id")
                    dev_type = device.get("type")
                else:
                    raw_id = device
                    dev_type = getattr(device, "type", None)

                dev_id = _extract_device_id(raw_id)
                if dev_id is None:
                    continue

                dev_id_str = dev_id.replace("_", ":")
                if dev_id_str == target_colon:
                    return dev_type
            return None

        def _is_feature_enabled(feature_name: str) -> bool:
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

            if isinstance(enabled_features, dict):
                return enabled_features.get(feature_name) is True
            if isinstance(enabled_features, list):
                return feature_name in enabled_features
            return False

        async def _overlay_provider(
            device_id: str,
            base_mappings: dict[str, str],
        ) -> dict[str, Any]:
            if not _is_feature_enabled("sensor_control"):
                return {}

            try:
                from ...features.sensor_control.resolver import SensorControlResolver

                device_type = _get_device_type(device_id)
                if not device_type:
                    return {}

                resolver = SensorControlResolver(hass)
                sensor_result = await resolver.resolve_entity_mappings(
                    device_id,
                    device_type,
                )

                merged_mappings = base_mappings.copy()
                merged_mappings.update(sensor_result["mappings"])

                return {
                    "mappings": merged_mappings,
                    "sources": sensor_result["sources"],
                    "raw_internal": sensor_result.get("raw_internal"),
                    "abs_humidity_inputs": sensor_result.get("abs_humidity_inputs", {}),
                }
            except Exception as err:
                _LOGGER.error(
                    "Failed to apply sensor_control overlays: %s",
                    err,
                    exc_info=True,
                )
                return {}

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

        _LOGGER.debug("Using feature_identifier: %s", feature_identifier)

        # Create and execute the command
        cmd = GetEntityMappingsCommand(
            hass,
            feature_identifier,
            overlay_provider=_overlay_provider,
        )
        await cmd.execute(connection, msg)

    except Exception as err:
        _LOGGER.error("Failed to get entity mappings: %s", err, exc_info=True)
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
        _LOGGER.error("Failed to get all feature entities: %s", err, exc_info=True)
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

    def _extract_device_slugs(device: Any) -> list[str]:
        try:
            slugs = DeviceFilter._get_device_slugs(device)
            return [str(slug) for slug in slugs if str(slug)]
        except Exception:  # pragma: no cover - defensive
            return []

    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    results: list[dict[str, Any]] = []
    if isinstance(devices, list):
        for device in devices:
            device_id = _extract_device_id(device)
            if not device_id:
                continue
            slugs = _extract_device_slugs(device)
            slug_label = ", ".join(dict.fromkeys(slugs)) if slugs else None
            results.append(
                {
                    "device_id": device_id,
                    "device_type": _extract_device_type(device) or "Unknown",
                    "slugs": slugs,
                    "slug_label": slug_label,
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
    from .const import DEFAULT_WEBSOCKET_COMMANDS

    return {
        **DEFAULT_WEBSOCKET_COMMANDS,
        "websocket_info": "ramses_extras/websocket_info",  # Utility for cmd discovery
    }
