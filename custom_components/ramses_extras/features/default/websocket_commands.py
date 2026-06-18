"""WebSocket commands for the default feature.

This module contains WebSocket command handlers for the default feature,
including utility commands that can be used by any feature.
"""

import logging
from datetime import datetime
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    try:
        cards_enabled = hass.data.get(DOMAIN, {}).get("cards_enabled") is True
        # Inject backend version for version mismatch detection
        result = {"cards_enabled": cards_enabled}
        version = hass.data.get(DOMAIN, {}).get("_integration_version", "0.0.0")
        result["_backend_version"] = version
        connection.send_result(msg["id"], result)
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
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
                    "area_sensors": sensor_result.get("area_sensors", []),
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
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
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return the bound REM/DIS device for a FAN device, if any.

    Provides both device-reported binding (from ramses_cc) and
    Extras-configured binding (from remote_binding registry).
    """
    from ...framework.helpers.remote_binding import get_remote_binding_registry

    device_id = str(msg["device_id"])
    commands = RamsesCommands(hass)

    # Get device-reported binding
    bound = await commands._get_bound_rem_device(device_id)

    # Get Extras registry binding
    registry = get_remote_binding_registry(hass)
    extras_binding = registry.get_binding_for_fan(device_id)
    extras_rem_id = registry.get_rem_id_for_fan(device_id)

    connection.send_result(
        msg["id"],
        {
            "device_id": device_id,
            "bound_rem": bound,
            "extras_binding": extras_binding,
            "extras_rem_id": extras_rem_id,
            "source": "extras" if extras_rem_id else ("device" if bound else None),
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_fan_config_associations",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_fan_config_associations(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return config-based zone and REM associations for a FAN device.

    Uses the shared FAN-oriented config helpers for normalized lookups.
    This provides the configuration perspective (as opposed to runtime binding).
    """
    from ...framework.helpers.config.migration import migrate_to_canonical_config
    from ...framework.helpers.config.model import (
        get_feature_section,
        get_remote_binding_rem_ids,
        get_remote_binding_rems,
        get_zone_ids_for_fan,
        get_zones_for_fan,
    )

    # Feature IDs used locally
    feature_remote_binding = "remote_binding"
    feature_zones = "zones"

    device_id = str(msg["device_id"])

    try:
        config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
        if config_entry is None:
            connection.send_result(
                msg["id"],
                {
                    "device_id": device_id,
                    "zones": [],
                    "zone_ids": [],
                    "remote_bindings": [],
                    "remote_binding_ids": [],
                    "source": "config",
                },
            )
            return

        # Get raw config from config entry and migrate to canonical form
        raw_config: dict[str, Any] = {}
        if getattr(config_entry, "data", None):
            raw_config.update(dict(config_entry.data))
        if getattr(config_entry, "options", None):
            raw_config.update(dict(config_entry.options))

        canonical_config = migrate_to_canonical_config(raw_config)

        zones_section = get_feature_section(canonical_config, feature_zones)
        remote_binding_section = get_feature_section(
            canonical_config, feature_remote_binding
        )

        zones = get_zones_for_fan(zones_section, device_id)
        zone_ids = get_zone_ids_for_fan(zones_section, device_id)
        remote_bindings = get_remote_binding_rems(remote_binding_section, device_id)
        remote_binding_ids = get_remote_binding_rem_ids(
            remote_binding_section, device_id
        )

        rems_by_zone: dict[str, list[dict[str, Any]]] = {}
        for rem in remote_bindings:
            zone_id = str(rem.get("zone_id") or "").strip()
            if not zone_id:
                continue
            rems_by_zone.setdefault(zone_id, []).append(dict(rem))

        projected_zones: list[dict[str, Any]] = []
        for zone in zones:
            zone_id = str(zone.get("zone_id") or "").strip()
            zone_copy = dict(zone)
            if zone_id:
                zone_copy["rems"] = [
                    dict(item) for item in rems_by_zone.get(zone_id, [])
                ]
            projected_zones.append(zone_copy)

        from ...framework.helpers.fan_speed_arbiter import get_fan_speed_arbiter
        from ...framework.helpers.remote_binding import get_remote_binding_registry

        arbiter = get_fan_speed_arbiter(hass)
        resolved = arbiter.resolve(device_id)
        winning = resolved.winning_demand

        registry = get_remote_binding_registry(hass)
        remote_activity = registry.get_last_activity_for_fan(device_id)
        remote_activity_active = False
        if remote_activity and winning is not None:
            remote_activity_active = (
                winning.feature_id == "manual_override"
                and winning.metadata.get("origin") == "remote"
                and winning.source_id == remote_activity.get("rem_id")
                and winning.requested_speed == remote_activity.get("command")
            )

        connection.send_result(
            msg["id"],
            {
                "device_id": device_id,
                "zones": projected_zones,
                "zone_ids": zone_ids,
                "remote_bindings": remote_bindings,
                "remote_binding_ids": remote_binding_ids,
                "remote_activity": remote_activity,
                "remote_activity_active": remote_activity_active,
                "resolved_command": resolved.command_name,
                "winning_demand": (
                    {
                        "feature_id": winning.feature_id,
                        "source_id": winning.source_id,
                        "requested_speed": winning.requested_speed,
                        "priority": winning.priority,
                        "reason": winning.reason,
                        "metadata": winning.metadata,
                        "updated_at": winning.updated_at.isoformat(),
                    }
                    if winning is not None
                    else None
                ),
                "source": "config",
            },
        )
    except Exception as err:
        _LOGGER.error("Failed to get FAN config associations: %s", err)
        connection.send_error(msg["id"], "get_fan_config_associations_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_remote_bindings",
        vol.Optional("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_remote_bindings(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return remote binding registry state.

    If device_id is provided, returns binding for that specific FAN.
    Otherwise returns all bindings.
    """
    from ...framework.helpers.remote_binding import get_remote_binding_registry

    try:
        registry = get_remote_binding_registry(hass)
        device_id = msg.get("device_id")

        if device_id:
            # Return binding for specific FAN
            binding = registry.get_binding_for_fan(str(device_id))
            result = {
                "device_id": device_id,
                "binding": binding,
                "rem_id": registry.get_rem_id_for_fan(str(device_id)),
            }
        else:
            # Return all bindings
            all_bindings = registry.list_bindings()
            result = {
                "bindings": all_bindings,
                "count": len(all_bindings),
            }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get remote bindings: %s", err)
        connection.send_error(msg["id"], "get_remote_bindings_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_binding_diagnostics",
        vol.Optional("rem_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_binding_diagnostics(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return binding diagnostics including last-seen timestamps and unmatched."""
    from ...framework.helpers.remote_binding import get_remote_binding_registry

    try:
        registry = get_remote_binding_registry(hass)
        rem_id = msg.get("rem_id")

        result: dict[str, Any] = {
            "diagnostics": registry.get_diagnostics(),
            "conflicts": registry.detect_conflicts(),
        }

        if rem_id:
            # Return specific REM info
            from datetime import datetime

            last_seen = registry.get_last_seen(str(rem_id))
            result["rem_id"] = rem_id
            result["last_seen"] = last_seen.isoformat() if last_seen else None
            result["bound_fan"] = registry.find_fan_for_rem(str(rem_id))
        else:
            # Return unmatched traffic
            result["unmatched_traffic"] = registry.get_unmatched_traffic(limit=50)

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get binding diagnostics: %s", err)
        connection.send_error(msg["id"], "get_binding_diagnostics_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/export_bindings",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_export_bindings(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Export bindings as strict YAML for support/debugging."""
    from ...framework.helpers.remote_binding import get_remote_binding_registry

    try:
        registry = get_remote_binding_registry(hass)

        result: dict[str, Any] = {
            "yaml": registry.export_bindings_yaml(),
            "conflicts": registry.detect_conflicts(),
        }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to export bindings: %s", err)
        connection.send_error(msg["id"], "export_bindings_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_2411_schema",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_2411_schema(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return a lightweight 2411 parameter schema for a device.

    ramses_extras does not own the authoritative schema; ramses_cc does.
    For the frontend parameter editor we provide a pragmatic schema derived from
    existing HA number entities for the device (param_* entities).
    """

    device_id = str(msg["device_id"]).replace(":", "_").lower()
    prefixes = (
        f"number.{device_id}_param_",
        f"number.fan_{device_id}_param_",
    )
    schema: dict[str, Any] = {}

    for st in hass.states.async_all():
        entity_id = st.entity_id
        prefix = next((p for p in prefixes if entity_id.startswith(p)), None)
        if prefix is None:
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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_binding_suggestions",
        vol.Optional("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_binding_suggestions(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return binding suggestions from observed unmatched traffic."""
    from ...framework.helpers.remote_binding import get_remote_binding_registry

    try:
        registry = get_remote_binding_registry(hass)
        device_id = msg.get("device_id")

        result = registry.get_binding_suggestions(device_id)

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get binding suggestions: %s", err)
        connection.send_error(msg["id"], "get_binding_suggestions_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_zones",
        vol.Optional("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_zones(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return zone configuration for FAN devices."""
    from ...framework.helpers.zones import get_zone_registry

    try:
        registry = get_zone_registry(hass)
        device_id = msg.get("device_id")

        if device_id:
            result = {
                "device_id": device_id,
                "zones": registry.get_zones_for_fan(device_id),
            }
        else:
            result = {
                "zones_by_fan": registry.list_all_zones(),
            }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get zones: %s", err)
        connection.send_error(msg["id"], "get_zones_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/export_zones",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_export_zones(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Export zones as strict YAML for support/debugging."""
    from ...framework.helpers.zones import get_zone_registry

    try:
        registry = get_zone_registry(hass)

        result: dict[str, Any] = {
            "yaml": registry.export_zones_yaml(),
        }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to export zones: %s", err)
        connection.send_error(msg["id"], "export_zones_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_zone_position",
        vol.Required("fan_id"): str,
        vol.Required("zone_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_zone_position(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return current zone position from its adapter."""
    from ...framework.helpers.zone_adapters import get_zone_adapter_registry

    try:
        registry = get_zone_adapter_registry(hass)
        fan_id = msg["fan_id"]
        zone_id = msg["zone_id"]

        adapter = registry.get_or_create_adapter(fan_id, zone_id)

        if adapter is None:
            connection.send_result(
                msg["id"],
                {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "error": "Zone not found or no adapter available",
                },
            )
            return

        position = await adapter.async_get_position()

        result: dict[str, Any] = {
            "fan_id": fan_id,
            "zone_id": zone_id,
            "position": position.position,
            "target_position": position.target_position,
            "is_available": position.is_available,
            "source": position.source,
            "adapter_available": adapter.is_available,
        }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get zone position: %s", err)
        connection.send_error(msg["id"], "get_zone_position_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_zone_adapter_diagnostics",
        vol.Optional("fan_id"): str,
        vol.Optional("zone_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_zone_adapter_diagnostics(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return zone adapter diagnostics."""
    from ...framework.helpers.zone_adapters import get_zone_adapter_registry

    try:
        registry = get_zone_adapter_registry(hass)
        fan_id = msg.get("fan_id")
        zone_id = msg.get("zone_id")

        if fan_id and zone_id:
            # Single adapter diagnostics
            adapter = registry.get_adapter(fan_id, zone_id)
            if adapter:
                result = {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "adapter": adapter.get_diagnostics(),
                }
            else:
                result = {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "error": "Adapter not found",
                }
        elif fan_id:
            # All adapters for a FAN
            adapters = registry.get_all_adapters_for_fan(fan_id)
            result = {
                "fan_id": fan_id,
                "adapters": [a.get_diagnostics() for a in adapters],
            }
        else:
            # Global diagnostics
            result = registry.get_diagnostics()

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get zone adapter diagnostics: %s", err)
        connection.send_error(
            msg["id"], "get_zone_adapter_diagnostics_failed", str(err)
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_zone_coordinator_state",
        vol.Required("fan_id"): str,
        vol.Optional("zone_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_zone_coordinator_state(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Return zone coordinator state for a FAN."""
    from ...framework.helpers.zone_coordinator import (
        get_zone_coordinator,
    )

    try:
        fan_id = msg["fan_id"]
        zone_id = msg.get("zone_id")

        coordinator = get_zone_coordinator(hass, fan_id)

        if zone_id:
            # Single zone state
            state = coordinator.get_zone_states().get(zone_id)
            if state:
                result: dict[str, Any] = {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "state": {
                        "position": state.position,
                        "available": state.is_available,
                        "controllable": state.is_controllable,
                        "source": state.demand_source.value,
                        "reason": state.demand_reason,
                    },
                }
            else:
                result = {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "error": "Zone state not found",
                }
        else:
            # Full coordinator state
            result = {
                "fan_id": fan_id,
                "enabled": coordinator.is_enabled,
                "states": {
                    zid: {
                        "position": s.position,
                        "available": s.is_available,
                        "source": s.demand_source.value,
                        "reason": s.demand_reason,
                    }
                    for zid, s in coordinator.get_zone_states().items()
                },
                "diagnostics": coordinator.get_diagnostics(),
            }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to get zone coordinator state: %s", err)
        connection.send_error(msg["id"], "get_zone_coordinator_state_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/set_zone_demand",
        vol.Required("fan_id"): str,
        vol.Required("zone_id"): str,
        vol.Required("fan_speed"): str,
        vol.Optional("reason"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_set_zone_demand(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Set a manual zone demand."""
    from ...framework.helpers.zone_coordinator import (
        get_zone_coordinator,
    )

    try:
        fan_id = msg["fan_id"]
        zone_id = msg["zone_id"]
        fan_speed = msg["fan_speed"]
        reason = msg.get("reason", "Manual WebSocket demand")

        coordinator = get_zone_coordinator(hass, fan_id)

        # Ensure zone is configured
        if zone_id not in coordinator.get_zone_states():
            coordinator.configure_zone(zone_id)

        success = await coordinator.async_set_manual_zone_demand(
            zone_id=zone_id,
            fan_speed=fan_speed,
            reason=reason,
        )

        result: dict[str, Any] = {
            "fan_id": fan_id,
            "zone_id": zone_id,
            "fan_speed": fan_speed,
            "applied": success,
        }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to set zone demand: %s", err)
        connection.send_error(msg["id"], "set_zone_demand_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/run_zone_actuation",
        vol.Required("fan_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_run_zone_actuation(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Trigger zone actuation cycle for a FAN.

    This runs the demand-driven min/max actuation for all zones
    associated with the specified FAN device.
    """
    from ...framework.helpers.zone_coordinator import get_zone_coordinator

    try:
        fan_id = msg["fan_id"]

        coordinator = get_zone_coordinator(hass, fan_id)

        # Run the actuation cycle
        results = await coordinator.async_run_zone_actuation_cycle()

        connection.send_result(
            msg["id"],
            {
                "fan_id": fan_id,
                "results": results,
                "timestamp": datetime.now().isoformat(),
            },
        )
    except Exception as err:
        _LOGGER.error("Failed to run zone actuation: %s", err)
        connection.send_error(msg["id"], "run_zone_actuation_failed", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/clear_zone_demand",
        vol.Required("fan_id"): str,
        vol.Required("zone_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_clear_zone_demand(
    hass: HomeAssistant, connection: WebSocket, msg: dict[str, Any]
) -> None:
    """Clear a manual zone demand."""
    from ...framework.helpers.zone_coordinator import (
        get_zone_coordinator,
    )

    try:
        fan_id = msg["fan_id"]
        zone_id = msg["zone_id"]

        coordinator = get_zone_coordinator(hass, fan_id)
        success = await coordinator.async_clear_manual_zone_demand(zone_id)

        result: dict[str, Any] = {
            "fan_id": fan_id,
            "zone_id": zone_id,
            "cleared": success,
        }

        connection.send_result(msg["id"], result)
    except Exception as err:
        _LOGGER.error("Failed to clear zone demand: %s", err)
        connection.send_error(msg["id"], "clear_zone_demand_failed", str(err))


def register_default_websocket_commands() -> dict[str, str]:
    """Register WebSocket commands for the default feature.

    :return: Dictionary mapping command names to their WebSocket command types
    """
    from .const import DEFAULT_WEBSOCKET_COMMANDS

    return {
        **DEFAULT_WEBSOCKET_COMMANDS,
        "websocket_info": "ramses_extras/websocket_info",  # Utility for cmd discovery
    }
