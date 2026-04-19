"""WebSocket commands for Device Simulator.

Provides real-time control and monitoring:
  - device_simulator/status: Get current state
  - device_simulator/devices: List available/loaded device types
  - device_simulator/active_devices: List currently active devices
  - device_simulator/activate: Start a device
  - device_simulator/silence: Stop a device
  - device_simulator/conversations: List conversation files
  - device_simulator/run_conversation: Execute conversation
  - device_simulator/messages: Get recent message log
"""

from __future__ import annotations

# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
import asyncio
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import (
    DOMAIN,
    LOGGER,
    SCENARIO_AUTO_ANSWER,
    SCENARIO_LOAD_PROFILE_YAML,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PARAM_SCHEMAS,
    SCENARIO_PROFILE_EMISSIONS,
    SCENARIO_REGISTRY,
)
from .scenario_engine import MESSAGE_EVENT, ScenarioEngine

try:  # pragma: no cover - legacy fallback for partially updated installs
    from .const import SCENARIO_DEVICE_UNAVAILABILITY
except ImportError:  # pragma: no cover - safety net when const is missing
    SCENARIO_DEVICE_UNAVAILABILITY = "device_unavailability"
except AttributeError:  # pragma: no cover - attribute missing in older builds
    SCENARIO_DEVICE_UNAVAILABILITY = "device_unavailability"

# Import ramses_cc storage constants
try:
    from custom_components.ramses_cc.const import (
        STORAGE_KEY as RAMSES_CC_STORAGE_KEY,
    )
    from custom_components.ramses_cc.const import (
        STORAGE_VERSION as RAMSES_CC_STORAGE_VERSION,
    )
    from custom_components.ramses_cc.const import (
        SZ_CLIENT_STATE,
        SZ_PACKETS,
    )
    from ramses_rf.schemas import SZ_SCHEMA
except ImportError:
    # Fallback for testing environments where ramses_cc may not be available
    RAMSES_CC_STORAGE_VERSION = 1
    RAMSES_CC_STORAGE_KEY = "ramses_cc"
    SZ_CLIENT_STATE = "client_state"
    SZ_PACKETS = "packets"
    SZ_SCHEMA = "schema"
from .profile_loader import (
    async_apply_profile,
    build_profile_from_yaml,
    profile_to_yaml,
)
from .system_config import SIM_DEVICE_ID, SystemConfigProfile

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection
    from homeassistant.core import HomeAssistant

    from .device_db import DeviceDatabase
    from .scenario_engine import MESSAGE_EVENT, ScenarioEngine
    from .system_config import ConfigProfileStore


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/clear_messages",
        vol.Optional("device_ids", default=[]): [str],
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_clear_device_messages(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear simulator message log (optionally per-device)."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    device_ids = msg.get("device_ids") or []
    engine.message_log.clear(device_ids or None)
    connection.send_result(msg["id"], {"status": "ok"})


@callback  # type: ignore[untyped-decorator]
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register Device Simulator WebSocket commands."""
    websocket_api.async_register_command(hass, ws_get_status)
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_get_active_devices)
    websocket_api.async_register_command(hass, ws_activate_device)
    websocket_api.async_register_command(hass, ws_silence_device)
    websocket_api.async_register_command(hass, ws_get_conversations)
    websocket_api.async_register_command(hass, ws_run_conversation)
    websocket_api.async_register_command(hass, ws_get_messages)
    # UI card handlers
    websocket_api.async_register_command(hass, ws_get_ui_status)
    websocket_api.async_register_command(hass, ws_load_profile)
    websocket_api.async_register_command(hass, ws_start_scenario)
    websocket_api.async_register_command(hass, ws_stop_scenario)
    websocket_api.async_register_command(hass, ws_set_device_enabled)
    websocket_api.async_register_command(hass, ws_set_device_excluded_codes)
    websocket_api.async_register_command(hass, ws_activate_profile_device)
    websocket_api.async_register_command(hass, ws_clear_ramses_cache)
    websocket_api.async_register_command(hass, ws_set_auto_answer)
    websocket_api.async_register_command(hass, ws_set_autonomous_speed)
    websocket_api.async_register_command(hass, ws_import_user_log)
    websocket_api.async_register_command(hass, ws_list_saved_playbacks)
    websocket_api.async_register_command(hass, ws_delete_saved_playback)
    websocket_api.async_register_command(hass, ws_pause_scenario)
    websocket_api.async_register_command(hass, ws_resume_scenario)
    websocket_api.async_register_command(hass, ws_subscribe_devices)
    websocket_api.async_register_command(hass, ws_subscribe_messages)
    websocket_api.async_register_command(hass, ws_delete_profile)
    websocket_api.async_register_command(hass, ws_get_device_messages)
    websocket_api.async_register_command(hass, ws_clear_device_messages)


def _get_engine(hass: HomeAssistant) -> ScenarioEngine | None:
    """Get scenario engine from hass data."""
    registry = hass.data.get("ramses_extras", {})
    return cast("ScenarioEngine | None", registry.get("device_simulator_engine"))


def _get_config_store(hass: HomeAssistant) -> ConfigProfileStore | None:
    """Return the configuration profile store if available."""

    registry = hass.data.get("ramses_extras", {})
    return cast(
        "ConfigProfileStore | None", registry.get("device_simulator_config_store")
    )


def _build_profile_zone_index(profile: SystemConfigProfile) -> list[dict[str, Any]]:
    """Create a lightweight summary of CTL zones for UI consumption."""

    schema = profile.device_configs.get("_schema") or {}
    known_list = profile.device_configs.get("_known_list") or {}
    zones: list[dict[str, Any]] = []

    for ctl_id, ctl_cfg in schema.items():
        if not isinstance(ctl_cfg, dict):
            continue
        ctl_zones = ctl_cfg.get("zones")
        if not isinstance(ctl_zones, dict):
            continue
        for zone_id, zone_cfg in ctl_zones.items():
            if not isinstance(zone_cfg, dict):
                continue
            zone_label = zone_cfg.get("label") or f"Zone {zone_id}"
            sensor_id = zone_cfg.get("sensor")
            raw_devices: list[tuple[str, str]] = []
            if sensor_id:
                raw_devices.append((str(sensor_id), "sensor"))
            for key in ("devices", "actuators", "children"):
                payload = zone_cfg.get(key)
                role = key[:-1] if key.endswith("s") else key
                if isinstance(payload, list):
                    raw_devices.extend((str(item), role) for item in payload if item)
                elif isinstance(payload, dict):
                    raw_devices.extend(
                        (str(value), role)
                        for value in payload.values()
                        if isinstance(value, str)
                    )

            # Preserve order while deduplicating but keep role metadata
            device_lookup: dict[str, dict[str, Any]] = {}
            for device_id, role in raw_devices:
                if not device_id:
                    continue
                info = known_list.get(device_id, {})
                entry = device_lookup.setdefault(
                    device_id,
                    {
                        "id": device_id,
                        "class": info.get("class"),
                        "roles": [],
                    },
                )
                if role and role not in entry["roles"]:
                    entry["roles"].append(role)
            device_entries = list(device_lookup.values())

            zones.append(
                {
                    "id": f"{ctl_id}|{zone_id}",
                    "zone_id": zone_id,
                    "controller": ctl_id,
                    "label": zone_label,
                    "sensor": sensor_id,
                    "devices": device_entries,
                }
            )

    return zones


def _build_zone_membership(
    zones: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Return per-device zone memberships for quick UI lookups."""

    membership: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for zone in zones:
        summary = {
            "id": zone.get("id"),
            "zone_id": zone.get("zone_id"),
            "label": zone.get("label"),
            "controller": zone.get("controller"),
            "sensor": zone.get("sensor"),
        }

        controller_id = zone.get("controller")
        if controller_id:
            membership[controller_id].append(
                {
                    **summary,
                    "roles": ["controller"],
                    "members": zone.get("devices", []),
                }
            )

        for member in zone.get("devices", []):
            device_id = member.get("id")
            if not device_id:
                continue
            membership[device_id].append(
                {
                    **summary,
                    "roles": member.get("roles", []),
                    "class": member.get("class"),
                }
            )

    return dict(membership)


def _resolve_zone_devices(profile: SystemConfigProfile, zone_key: str) -> list[str]:
    """Return device IDs for a given zone selector value."""

    zones = _build_profile_zone_index(profile)
    match = next((zone for zone in zones if zone["id"] == zone_key), None)
    if not match:
        return []
    return [device["id"] for device in match.get("devices", []) if device.get("id")]


async def _start_profile_emissions(
    engine: ScenarioEngine, profile_name: str, profile: SystemConfigProfile
) -> list[str]:
    """Activate all devices defined by the profile, respecting conflicts."""

    if engine.is_scenario_running(SCENARIO_PROFILE_EMISSIONS):
        raise RuntimeError("Profile device emissions are already running")

    conflicts = engine.check_scenario_conflicts(SCENARIO_PROFILE_EMISSIONS)
    if conflicts:
        raise RuntimeError("Conflicts with running scenarios: " + ", ".join(conflicts))

    profile_devices = engine.build_profile_devices(profile)
    if not profile_devices:
        raise RuntimeError("Active profile does not define any devices")

    started_ids: list[str] = []
    for device in profile_devices:
        await engine.async_activate_device(device)
        started_ids.append(device.device_id)

    engine.set_running_metadata(
        SCENARIO_PROFILE_EMISSIONS,
        {"profile": profile_name, "devices": started_ids},
    )
    return started_ids


async def _trigger_ramses_discovery(hass: HomeAssistant) -> None:
    """Poke the ramses_cc coordinator to run device discovery immediately.

    After a startup burst the coordinator's 60s scan interval would normally
    be the next chance for new devices to be registered as HA entities. Calling
    this after the burst skips that wait.
    """
    try:
        ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
        if not ramses_cc_entries:
            return
        entry_id = ramses_cc_entries[0].entry_id
        coordinator = (hass.data.get("ramses_cc") or {}).get(entry_id)
        if coordinator is None:
            return
        discover = getattr(coordinator, "_async_discovery_task", None)
        if callable(discover):
            LOGGER.debug("Triggering immediate ramses_cc discovery after burst")
            await discover()
    except Exception as err:  # noqa: BLE001
        LOGGER.warning("Could not trigger ramses_cc discovery: %s", err)


def _get_db(hass: HomeAssistant) -> DeviceDatabase | None:
    """Get device database from hass data."""
    registry = hass.data.get("ramses_extras", {})
    return cast("DeviceDatabase | None", registry.get("device_simulator_db"))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/status",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_status(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return simulator status."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    connection.send_result(
        msg["id"],
        {
            "state": engine.state,
            "connected": engine._endpoint.is_connected,
            "messages_sent": engine.messages_sent,
            "messages_received": engine.messages_received,
            "active_devices": len(engine.active_device_ids),
            "active_device_ids": engine.active_device_ids,
            "auto_answer": engine.auto_answer_enabled,
            "running_scenarios": engine.get_running_scenario_ids(),
            "scenario_registry": SCENARIO_REGISTRY,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/devices",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_devices(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return available device types."""
    db = _get_db(hass)
    if not db:
        connection.send_error(msg["id"], "not_ready", "Database not loaded")
        return

    result = []
    for slug, entry in db._device_types.items():
        variants = [v.id for v in entry.variants] if entry.variants else []
        result.append(
            {
                "slug": slug,
                "domain": entry.domain,
                "autonomous_count": len(entry.autonomous),
                "response_count": len(entry.responses),
                "variants": variants,
            }
        )

    connection.send_result(msg["id"], {"devices": result})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/active_devices",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_active_devices(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return currently active simulated devices."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    result = []
    for device_id, device in engine._active_devices.items():
        result.append(
            {
                "device_id": device.device_id,
                "slug": device.slug,
                "variant_id": device.variant_id,
                "enabled": device.enabled,
                "suppress_autonomous": device.suppress_autonomous,
                "suppress_responses": device.suppress_responses,
            }
        )

    connection.send_result(msg["id"], {"devices": result})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/activate",
        vol.Required("device_id"): str,
        vol.Required("slug"): str,
        vol.Optional("variant_id"): str,
    }
)
async def ws_activate_device(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Activate a device in the simulator."""
    from .scenario_engine import ActiveDevice

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    device = ActiveDevice(
        device_id=msg["device_id"],
        slug=msg["slug"],
        variant_id=msg.get("variant_id"),
    )
    await engine.async_activate_device(device)

    connection.send_result(
        msg["id"],
        {"success": True, "device_id": device.device_id},
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/silence",
        vol.Required("device_id"): str,
    }
)
async def ws_silence_device(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Silence a device."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    await engine.async_silence_device(msg["device_id"])
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/conversations",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_conversations(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return available conversation files."""
    db = _get_db(hass)
    if not db:
        connection.send_error(msg["id"], "not_ready", "Database not loaded")
        return

    result = []
    for ref, conv in db._conversations.items():
        result.append(
            {
                "ref": ref,
                "peers": conv.peers,
                "description": conv.description,
                "frame_count": len(conv.frames),
                "scheme": conv.scheme,
            }
        )

    connection.send_result(msg["id"], {"conversations": result})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/run_conversation",
        vol.Required("ref"): str,
        vol.Required("device_map"): dict,
        vol.Optional("speed", default=1.0): vol.Coerce(float),
    }
)
async def ws_run_conversation(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run a conversation."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    result = await engine.async_play_conversation(
        ref=msg["ref"],
        device_map=msg["device_map"],
        speed=msg.get("speed", 1.0),
    )

    connection.send_result(
        msg["id"],
        {
            "success": result.success,
            "messages_sent": result.messages_sent,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "device_simulator/messages",
        vol.Optional("limit", default=50): int,
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_messages(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return recent message log (legacy raw strings)."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    limit = msg.get("limit", 50)
    messages = engine._message_log[-limit:] if engine._message_log else []

    connection.send_result(msg["id"], {"messages": messages})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/get_messages",
        vol.Optional("limit", default=100): int,
        vol.Optional("device_id"): str,
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_device_messages(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return structured, parsed simulator message log."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    limit: int = msg.get("limit", 100)
    device_id: str | None = msg.get("device_id")
    entries = engine.message_log.get_recent(limit=limit, device_id=device_id)
    connection.send_result(
        msg["id"],
        {
            "messages": [engine.message_log.to_dict(e) for e in entries],
            "total": len(entries),
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/get_status",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_get_ui_status(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full simulator status for UI card."""
    ra = hass.data.setdefault("ramses_extras", {})

    # Get profiles from config store
    config_store = ra.get("device_simulator_config_store")
    profiles = []
    active_profile = None
    active_profile_yaml: str | None = None
    active_profile_scale: float | None = None
    active_profile_known_list: dict[str, Any] | None = None
    active_profile_schema: dict[str, Any] | None = None
    active_profile_zones: list[dict[str, Any]] = []
    zone_membership: dict[str, list[dict[str, Any]]] = {}
    filtered_known_list: dict[str, Any] | None = None
    if config_store:
        active_profile = config_store.get_active_profile()
        for name in config_store.list_profiles():
            p = config_store.get_profile(name)
            if not p:
                continue
            is_builtin = name in config_store.BUILTIN_PROFILES
            schema = p.device_configs.get("_schema") or {}
            profiles.append(
                {
                    "name": name,
                    "description": p.description,
                    "timeout_scale": p.timeout_scale,
                    "known_list": p.device_configs.get("_known_list", {}),
                    "is_builtin": is_builtin,
                    "can_delete": not is_builtin,
                    "is_active": name == active_profile,
                    "schema": schema or None,
                }
            )
            if name == active_profile:
                active_profile_yaml = profile_to_yaml(p)
                active_profile_scale = p.timeout_scale
                active_profile_known_list = p.device_configs.get("_known_list", {})
                active_profile_schema = schema or None
                active_profile_zones = _build_profile_zone_index(p)
                zone_membership = _build_zone_membership(active_profile_zones)
                filtered_known_list = {
                    device_id: meta
                    for device_id, meta in active_profile_known_list.items()
                    if (meta.get("class") or "").upper() != "HGI"
                }

    # Get active devices from scenario engine
    engine = ra.get("device_simulator_engine")
    devices = []
    if engine and hasattr(engine, "_active_devices"):
        devices = [
            {
                "id": device.device_id,
                "type": device.slug,
                "enabled": device.enabled,
                "suppress_autonomous": device.suppress_autonomous,
                "suppress_responses": device.suppress_responses,
                "excluded_codes": list(device.excluded_codes),
                "source": device.origin,
                "owned_by_profile": engine.is_profile_device(device.device_id),
                "zones": zone_membership.get(device.device_id, []),
            }
            for device in engine._active_devices.values()
        ]

    active_device_ids = {device["id"] for device in devices}

    profile_device_summary: list[dict[str, Any]] = []
    profile_device_counts = {"known": 0, "active": 0}
    if filtered_known_list:
        for device_id, meta in filtered_known_list.items():
            summary_entry = {
                "id": device_id,
                "class": meta.get("class"),
                "active": device_id in active_device_ids,
                "label": meta.get("name") or meta.get("label"),
            }
            profile_device_summary.append(summary_entry)
        profile_device_counts = {
            "known": len(profile_device_summary),
            "active": sum(1 for entry in profile_device_summary if entry["active"]),
        }

    # Stats from engine
    stats = {
        "rx": engine.messages_received if engine else 0,
        "tx": engine.messages_sent if engine else 0,
        "devices": len(devices),
        "active": sum(1 for d in devices if d["enabled"]),
    }

    ra_active_profile = ra.get("device_simulator_active_profile")
    if active_profile:
        if ra_active_profile != active_profile:
            ra["device_simulator_active_profile"] = active_profile
    elif ra_active_profile:
        active_profile = ra_active_profile
    auto_answer = engine.auto_answer_enabled if engine else True
    running_scenarios = engine.get_running_scenario_ids() if engine else []
    running_metadata = engine.get_running_metadata() if engine else {}
    emissions_active = engine.autonomous_emissions_active if engine else False
    autonomous_speed = (
        engine.get_autonomous_speed()
        if engine
        else (config_store.get_autonomous_speed() if config_store else 1.0)
    )

    device_message_previews: dict[str, list] = {}
    target_ids: list[str] = [d["id"] for d in devices]
    if not target_ids and profile_device_summary:
        target_ids = [
            entry["id"] for entry in profile_device_summary if entry.get("id")
        ]
    if engine and target_ids:
        device_message_previews = engine.message_log.get_for_devices(
            target_ids,
            per_device=20,
        )

    connection.send_result(
        msg["id"],
        {
            "profiles": profiles,
            "devices": devices,
            "stats": stats,
            "active_profile": active_profile,
            "active_profile_yaml": active_profile_yaml,
            "active_profile_timeout_scale": active_profile_scale,
            "active_profile_known_list": active_profile_known_list,
            "active_profile_schema": active_profile_schema,
            "active_profile_zones": active_profile_zones,
            "auto_answer": auto_answer,
            "autonomous_speed": autonomous_speed,
            "running_scenarios": running_scenarios,
            "running_metadata": running_metadata,
            "autonomous_emissions_active": emissions_active,
            "scenario_registry": SCENARIO_REGISTRY,
            "scenario_param_schemas": SCENARIO_PARAM_SCHEMAS,
            "profile_device_summary": profile_device_summary,
            "profile_device_counts": profile_device_counts,
            "profile_zone_membership": zone_membership,
            "device_message_previews": device_message_previews,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/activate_profile_device",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_activate_profile_device(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Activate a single configured device from the active profile."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    config_store = _get_config_store(hass)
    if not config_store:
        connection.send_error(msg["id"], "not_ready", "Config store not initialized")
        return

    active_profile_name = config_store.get_active_profile()
    if not active_profile_name:
        connection.send_error(msg["id"], "no_active_profile", "Load a profile first")
        return

    profile = config_store.get_profile(active_profile_name)
    if not profile:
        connection.send_error(
            msg["id"], "invalid_profile", "Active profile is missing or invalid"
        )
        return

    device_id = msg["device_id"].upper()
    if engine.is_device_active(device_id):
        connection.send_error(
            msg["id"], "already_active", f"Device {device_id} is already active"
        )
        return

    device = engine.build_profile_device(profile, device_id)
    if not device:
        connection.send_error(
            msg["id"], "not_found", f"Device {device_id} is not defined in profile"
        )
        return

    await engine.async_activate_device(device)
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "device_id": device_id,
            "message": f"Activated {device_id} from profile '{active_profile_name}'",
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/load_profile",
        vol.Required("profile"): str,
        vol.Optional("speed"): vol.Coerce(float),
        vol.Optional("reload_ramses_cc", default=True): bool,
        vol.Optional("preload_schema", default=True): bool,
        vol.Optional("reset_rf_cache", default=False): bool,
        vol.Optional("remove_database", default=False): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_load_profile(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Load a system configuration profile."""

    ra = hass.data.setdefault("ramses_extras", {})
    config_store = ra.get("device_simulator_config_store")
    if not config_store:
        connection.send_error(msg["id"], "not_ready", "Config store not initialized")
        return

    profile = config_store.get_profile(msg["profile"])
    if not profile:
        connection.send_error(
            msg["id"], "not_found", f"Profile '{msg['profile']}' not found"
        )
        return

    try:
        # Use profile's remove_database setting, but allow override from UI
        remove_database = msg.get("remove_database")
        if remove_database is None:
            remove_database = getattr(profile, "remove_database", False)

        result = await async_apply_profile(
            hass,
            profile_name=profile.name,
            profile=profile,
            reload_ramses_cc=msg.get("reload_ramses_cc", True),
            speed=msg.get("speed"),
            preload_schema=msg.get("preload_schema", True),
            reset_rf_cache=msg.get("reset_rf_cache", False),
            skip_rf_hydrate=remove_database,
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "error", str(err))
        return

    ra["device_simulator_active_profile"] = profile.name
    config_store.set_active_profile(profile.name)
    await config_store.async_save_state()

    result["started_devices"] = 0
    result["message"] = (
        "Profile applied. Use the profile emissions scenario to start devices."
    )

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/delete_profile",
        vol.Required("profile"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_delete_profile(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a user-defined profile."""

    config_store = _get_config_store(hass)
    if not config_store:
        connection.send_error(msg["id"], "not_ready", "Config store not initialized")
        return

    profile_name = msg["profile"]
    if profile_name in config_store.BUILTIN_PROFILES:
        connection.send_error(
            msg["id"],
            "cannot_delete_builtin",
            f"Profile '{profile_name}' is built-in and cannot be deleted",
        )
        return

    if not config_store.delete_profile(profile_name):
        connection.send_error(
            msg["id"],
            "not_found",
            f"Profile '{profile_name}' not found or already removed",
        )
        return

    ra = hass.data.setdefault("ramses_extras", {})
    if ra.get("device_simulator_active_profile") == profile_name:
        ra["device_simulator_active_profile"] = None
        config_store.set_active_profile(None)
        await config_store.async_save_state()

    connection.send_result(msg["id"], {"success": True, "profile": profile_name})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/import_user_log",
        vol.Optional("path"): str,
        vol.Required("name"): str,
        vol.Optional("content"): str,
        vol.Optional("save_yaml", default=False): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_import_user_log(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Import a user's ramses.log file as a conversation for playback."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    db = engine.device_db
    if not db:
        connection.send_error(msg["id"], "not_ready", "Device database not available")
        return

    # Import the log file (from path or content)
    path = msg.get("path")
    name = msg["name"]
    content = msg.get("content")
    save_yaml = msg.get("save_yaml", False)

    success = db.import_user_log(path, name, content, save_yaml=save_yaml)
    if success:
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "conversation_name": name,
                "message": f"Imported log as conversation '{name}'",
            },
        )
    else:
        connection.send_error(msg["id"], "import_failed", "Failed to import log")


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {vol.Required("type"): "ramses_extras/device_simulator/list_saved_playbacks"}
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_list_saved_playbacks(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all saved (imported) playback conversations."""
    engine = _get_engine(hass)
    if not engine or not engine.device_db:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return
    playbacks = engine.device_db.list_saved_playbacks()
    connection.send_result(msg["id"], {"success": True, "playbacks": playbacks})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/delete_saved_playback",
        vol.Required("identifier"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_delete_saved_playback(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a saved playback by conversation id or filename."""
    engine = _get_engine(hass)
    if not engine or not engine.device_db:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return
    ok = engine.device_db.delete_saved_playback(msg["identifier"])
    if ok:
        connection.send_result(msg["id"], {"success": True})
    else:
        connection.send_error(
            msg["id"], "not_found", f"Saved playback '{msg['identifier']}' not found"
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/pause_scenario",
        vol.Required("scenario"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_pause_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Pause a cooperating running scenario (e.g. conversation playback)."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return
    ok = engine.pause_scenario(msg["scenario"])
    if ok:
        connection.send_result(msg["id"], {"success": True, "paused": True})
    else:
        connection.send_error(
            msg["id"], "not_running", f"Scenario '{msg['scenario']}' not running"
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/resume_scenario",
        vol.Required("scenario"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_resume_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Resume a paused scenario."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return
    ok = engine.resume_scenario(msg["scenario"])
    if ok:
        connection.send_result(msg["id"], {"success": True, "paused": False})
    else:
        connection.send_error(
            msg["id"], "not_running", f"Scenario '{msg['scenario']}' not paused"
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/start_scenario",
        vol.Required("scenario"): str,
        vol.Optional("params", default={}): dict,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_start_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Start a simulator scenario from the UI."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    scenario_id = msg["scenario"]
    params = msg.get("params", {})

    if scenario_id == SCENARIO_AUTO_ANSWER:
        connection.send_error(
            msg["id"],
            "unsupported",
            "Use set_auto_answer to toggle the auto-answer scenario",
        )
        return

    try:
        if scenario_id == SCENARIO_MANUAL_DEVICE_INJECTION:
            response = await _start_autonomous_emissions(engine, params)
        elif scenario_id == SCENARIO_LOAD_PROFILE_YAML:
            response = await _start_load_profile_yaml(hass, params)
        elif scenario_id == SCENARIO_PROFILE_EMISSIONS:
            config_store = _get_config_store(hass)
            if not config_store:
                connection.send_error(
                    msg["id"], "not_ready", "Config profile store not initialized"
                )
                return
            active_profile_name = config_store.get_active_profile()
            if not active_profile_name:
                connection.send_error(
                    msg["id"],
                    "no_active_profile",
                    "Load a simulator profile before starting profile emissions",
                )
                return
            profile = config_store.get_profile(active_profile_name)
            if not profile:
                connection.send_error(
                    msg["id"],
                    "no_active_profile",
                    "Active profile is missing or invalid",
                )
                return
            if engine.is_scenario_running(SCENARIO_PROFILE_EMISSIONS):
                connection.send_error(
                    msg["id"],
                    "already_running",
                    "Profile device emissions are already running",
                )
                return
            conflicts = engine.check_scenario_conflicts(SCENARIO_PROFILE_EMISSIONS)
            if conflicts:
                connection.send_error(
                    msg["id"],
                    "conflict",
                    "Conflicts with running scenarios: " + ", ".join(conflicts),
                )
                return
            try:
                started_ids = await _start_profile_emissions(
                    engine, active_profile_name, profile
                )
            except RuntimeError as err:
                connection.send_error(msg["id"], "error", str(err))
                return
            response = {
                "success": True,
                "scenario_id": SCENARIO_PROFILE_EMISSIONS,
                "message": f"Started profile devices ({len(started_ids)})",
            }
        elif engine.has_scenario_definition(scenario_id):
            if scenario_id == SCENARIO_DEVICE_UNAVAILABILITY and params.get("zone_id"):
                config_store = _get_config_store(hass)
                active_name = (
                    config_store.get_active_profile() if config_store else None
                )
                if not config_store or not active_name:
                    connection.send_error(
                        msg["id"],
                        "no_active_profile",
                        "Load a simulator profile before selecting a zone",
                    )
                    return
                profile = config_store.get_profile(active_name)
                if not profile:
                    connection.send_error(
                        msg["id"],
                        "no_active_profile",
                        "Active profile is missing or invalid",
                    )
                    return
                zone_devices = _resolve_zone_devices(profile, params["zone_id"])
                if not zone_devices:
                    connection.send_error(
                        msg["id"],
                        "invalid_zone",
                        "Selected zone has no devices",
                    )
                    return
                params = {**params, "targets": zone_devices}
            conflicts = engine.check_scenario_conflicts(scenario_id)
            if conflicts:
                connection.send_error(
                    msg["id"],
                    "conflict",
                    "Conflicts with running scenarios: " + ", ".join(conflicts),
                )
                return
            response = await engine.async_run_registered_scenario(scenario_id, params)
        else:
            connection.send_error(
                msg["id"], "unknown_scenario", f"Scenario '{scenario_id}' not found"
            )
            return
    except Exception as err:  # noqa: BLE001
        LOGGER.exception("Scenario %s failed: %s", scenario_id, err)
        connection.send_error(msg["id"], "error", str(err))
        return

    connection.send_result(msg["id"], response)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/stop_scenario",
        vol.Optional("scenario"): str,
        vol.Optional("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_stop_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stop a running simulator scenario."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    scenario_id = msg.get("scenario")
    device_id = msg.get("device_id")

    if scenario_id == SCENARIO_AUTO_ANSWER:
        connection.send_error(
            msg["id"], "unsupported", "Use set_auto_answer to toggle auto-answer"
        )
        return

    if scenario_id == SCENARIO_MANUAL_DEVICE_INJECTION or device_id:
        target_id = device_id
        if target_id and not engine.is_manual_device(target_id):
            connection.send_error(
                msg["id"],
                "not_manual",
                f"Device '{target_id}' is not a manual injection",
            )
            return
        if target_id:
            await engine.async_stop_manual_devices(target_id)
            connection.send_result(
                msg["id"],
                {
                    "success": True,
                    "message": f"Manual device injection stopped for {target_id}",
                },
            )
            return
        await engine.async_stop_manual_devices()
        connection.send_result(
            msg["id"],
            {"success": True, "message": "Manual device injections stopped"},
        )
        return

    if scenario_id == SCENARIO_PROFILE_EMISSIONS:
        await engine.async_stop_profile_devices()
        engine.clear_running_metadata(SCENARIO_PROFILE_EMISSIONS)
        connection.send_result(
            msg["id"],
            {"success": True, "message": "Profile device emissions stopped"},
        )
        return

    if scenario_id:
        await engine.async_cancel_scenario(scenario_id)
        connection.send_result(
            msg["id"],
            {"success": True, "message": f"Scenario '{scenario_id}' cancelled"},
        )
        return

    connection.send_result(msg["id"], {"success": True})


async def _start_autonomous_emissions(
    engine: ScenarioEngine, params: dict[str, Any]
) -> dict[str, Any]:
    from .scenario_engine import ActiveDevice

    device_id = params.get("device_id", SIM_DEVICE_ID["FAN"])
    device_type = params.get("device_type", "FAN")
    variant_id = params.get("variant_id", "default")
    excluded_codes = params.get("excluded_codes")
    if excluded_codes is None:
        excluded_codes = ["1FC9"]

    device = ActiveDevice(
        device_id=device_id,
        slug=device_type,
        variant_id=variant_id,
        excluded_codes=excluded_codes,
        suppress_autonomous=False,
        suppress_responses=False,
        enabled=True,
        origin="manual",
    )
    await engine.async_activate_device(device)
    return {
        "success": True,
        "scenario_id": SCENARIO_MANUAL_DEVICE_INJECTION,
        "device_id": device_id,
        "message": f"Manual device injection started for {device_id}",
    }


async def _start_load_profile_yaml(
    hass: HomeAssistant, params: dict[str, Any]
) -> dict[str, Any]:
    config_store = _get_config_store(hass)
    if not config_store:
        raise RuntimeError("Profile store not available")

    yaml_blob = params.get("profile_yaml")
    if not isinstance(yaml_blob, str) or not yaml_blob.strip():
        raise ValueError("profile_yaml param is required")

    profile_name = (params.get("profile_name") or "").strip()
    if not profile_name:
        profile_name = f"imported_profile_{int(time.time())}"

    profile = build_profile_from_yaml(profile_name, yaml_blob)
    config_store.save_profile(profile)
    config_store.set_active_profile(profile.name)
    await config_store.async_save_state()

    ra = hass.data.setdefault("ramses_extras", {})
    ra["device_simulator_active_profile"] = profile.name

    result: dict[str, Any] = await async_apply_profile(
        hass,
        profile_name=profile.name,
        profile=profile,
        reload_ramses_cc=params.get("reload_ramses", True),
        speed=params.get("speed"),
        preload_schema=params.get("preload_schema", True),
        reset_rf_cache=params.get("reset_rf_cache", False),
        skip_rf_hydrate=params.get("remove_database"),
    )
    result.setdefault("scenario_id", SCENARIO_LOAD_PROFILE_YAML)
    result.setdefault(
        "message",
        "Profile applied from YAML. Use the profile emissions scenario to "
        "start devices.",
    )
    result.setdefault("started_devices", 0)
    return result


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/set_device_enabled",
        vol.Required("device_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_set_device_enabled(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Enable or disable a simulated device."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    device = engine._active_devices.get(msg["device_id"])
    if not device:
        connection.send_error(
            msg["id"], "not_found", f"Device '{msg['device_id']}' not active"
        )
        return

    was_enabled = device.enabled
    device.enabled = msg["enabled"]
    LOGGER.info("Device %s enabled=%s", msg["device_id"], msg["enabled"])

    # Fire event to notify UI that device state has changed
    hass.bus.async_fire(
        "ramses_extras_simulator_devices_changed",
        {"device_id": msg["device_id"], "action": "updated", "enabled": msg["enabled"]},
    )

    # Re-activate to restart the emitter with a fresh burst when enabling a
    # previously disabled device, so traffic starts immediately.
    if msg["enabled"] and not was_enabled:
        await engine.async_activate_device(device)

    connection.send_result(
        msg["id"],
        {"success": True, "enabled": bool(engine and engine.auto_answer_enabled)},
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/set_autonomous_speed",
        vol.Required("speed"): vol.All(
            vol.Coerce(float), vol.Clamp(min=0.01, max=100.0)
        ),
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_set_autonomous_speed(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the global autonomous emission speed multiplier."""

    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    speed = msg["speed"]
    engine.set_autonomous_speed(speed)

    config_store = _get_config_store(hass)
    if config_store is not None:
        config_store.set_autonomous_speed(speed)
        hass.async_create_background_task(
            config_store.async_save_state(),
            "ramses_extras.device_simulator.save_state",
        )

    connection.send_result(
        msg["id"],
        {"success": True, "speed": engine.get_autonomous_speed()},
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/clear_ramses_cache",
        vol.Optional("clear_schema", default=True): bool,
        vol.Optional("clear_packets", default=False): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_clear_ramses_cache(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear ramses_cc stored client state (schema and/or packets)."""
    from homeassistant.helpers.storage import Store

    clear_schema = msg.get("clear_schema", True)
    clear_packets = msg.get("clear_packets", False)
    actions: list[str] = []

    try:
        store: Store = Store(hass, RAMSES_CC_STORAGE_VERSION, RAMSES_CC_STORAGE_KEY)
        stored_data: dict[str, Any] = await store.async_load() or {}

        if SZ_CLIENT_STATE in stored_data:
            if clear_schema:
                stored_data[SZ_CLIENT_STATE].pop(SZ_SCHEMA, None)
                msg_code_filter = {"0004", "0005", "000C"}
                packets = stored_data[SZ_CLIENT_STATE].get(SZ_PACKETS, {})
                stored_data[SZ_CLIENT_STATE][SZ_PACKETS] = {
                    dtm: pkt
                    for dtm, pkt in packets.items()
                    if (
                        isinstance(pkt, dict) and pkt.get("code") not in msg_code_filter
                    )
                    or (
                        isinstance(pkt, str)
                        and not any(f" {c} " in pkt for c in msg_code_filter)
                    )
                }
                actions.append("cleared_schema")

            if clear_packets:
                stored_data[SZ_CLIENT_STATE].pop(SZ_PACKETS, None)
                actions.append("cleared_ha_packets")

            await store.async_save(stored_data)

        # Also delete ramses.db SQLite file when clearing all packets
        if clear_packets:
            db_path = Path(hass.config.config_dir) / "ramses.db"
            if db_path.exists():
                await asyncio.get_event_loop().run_in_executor(None, db_path.unlink)
                actions.append("deleted_ramses_db")
                LOGGER.info("Cleared ramses.db at %s", db_path)

        LOGGER.info("Cleared ramses_cc cache: %s", actions)
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "clear_schema": clear_schema,
                "clear_packets": clear_packets,
                "message": "Cache cleared. Restart ramses_cc to apply.",
            },
        )
    except Exception as err:  # noqa: BLE001
        LOGGER.error("Failed to clear ramses_cc cache: %s", err)
        connection.send_error(msg["id"], "error", str(err))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required(
            "type"
        ): "ramses_extras/device_simulator/set_device_excluded_codes",
        vol.Required("device_id"): str,
        vol.Required("excluded_codes"): [str],
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_set_device_excluded_codes(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update the excluded codes for a simulated device."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    device = engine._active_devices.get(msg["device_id"])
    if not device:
        connection.send_error(
            msg["id"], "not_found", f"Device '{msg['device_id']}' not active"
        )
        return

    device.excluded_codes = list(msg["excluded_codes"])
    LOGGER.info("Device %s excluded_codes=%s", msg["device_id"], device.excluded_codes)

    # Fire event to notify UI that device state has changed
    hass.bus.async_fire(
        "ramses_extras_simulator_devices_changed",
        {
            "device_id": msg["device_id"],
            "action": "updated",
            "excluded_codes": list(device.excluded_codes),
        },
    )

    connection.send_result(
        msg["id"],
        {
            "success": True,
            "device_id": msg["device_id"],
            "excluded_codes": device.excluded_codes,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/set_auto_answer",
        vol.Required("enabled"): bool,
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_set_auto_answer(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Enable or disable global RQ\u2192RP auto-answering.

    When disabled the simulator receives RQ frames but never replies,
    simulating a device/ESP that is powered off or unreachable.
    Conflicts with other running scenarios are reported as warnings only
    (the caller decides whether to proceed).
    """
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    from .const import SCENARIO_AUTO_ANSWER

    enabled: bool = msg["enabled"]
    conflicts = (
        engine.check_scenario_conflicts(SCENARIO_AUTO_ANSWER) if not enabled else []
    )
    engine.set_auto_answer(enabled)

    ra = hass.data.get("ramses_extras", {})
    config_store = ra.get("device_simulator_config_store")
    if config_store is not None:
        config_store.set_auto_answer(enabled)
        hass.async_create_background_task(
            config_store.async_save_state(),
            "ramses_extras.device_simulator.save_state",
        )

    connection.send_result(
        msg["id"],
        {
            "success": True,
            "auto_answer": enabled,
            "conflicts": conflicts,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/subscribe_devices",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_subscribe_devices(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe to device simulator device changes.

    Pushes updates to the client whenever devices are activated, silenced,
    or their properties change.
    """

    @callback  # type: ignore[untyped-decorator]
    def _on_device_changed(event: dict[str, Any]) -> None:
        """Push device change event to client."""
        payload = getattr(event, "data", {}) or {}
        data = {
            "action": payload.get("action", "updated"),
            "device_id": payload.get("device_id"),
            "count": payload.get("count"),
            "enabled": payload.get("enabled"),
            "excluded_codes": payload.get("excluded_codes"),
        }
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                {
                    "event_type": "devices_changed",
                    "data": data,
                },
            )
        )

    # Subscribe to device change events
    unsubscribe = hass.bus.async_listen(
        "ramses_extras_simulator_devices_changed",
        _on_device_changed,
    )

    # Send initial device list
    engine = _get_engine(hass)
    devices = []
    if engine and hasattr(engine, "_active_devices"):
        devices = [
            {
                "id": device.device_id,
                "type": device.slug,
                "enabled": device.enabled,
                "suppress_autonomous": device.suppress_autonomous,
                "suppress_responses": device.suppress_responses,
                "excluded_codes": list(device.excluded_codes),
            }
            for device in engine._active_devices.values()
        ]

    connection.send_result(
        msg["id"],
        {
            "success": True,
            "devices": devices,
        },
    )

    # Store unsubscribe function to clean up when connection closes
    connection.subscriptions[msg["id"]] = unsubscribe


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/subscribe_messages",
        vol.Optional("device_ids", default=[]): [str],
        vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=200)),
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_subscribe_messages(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe to simulator message log updates."""

    engine = _get_engine(hass)
    device_ids = msg.get("device_ids") or []
    target_ids = {device_id for device_id in device_ids if device_id}
    limit: int = msg.get("limit", 50)
    limit = max(1, min(limit, 200))

    def _send_messages(messages: list[dict]) -> None:
        if not messages:
            return
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                {
                    "event_type": "device_messages",
                    "data": {"messages": messages},
                },
            )
        )

    initial: list[dict[str, Any]] = []
    if engine:
        if target_ids:
            snapshots = engine.message_log.get_for_devices(
                list(target_ids),
                per_device=limit,
            )
            for entries in snapshots.values():
                initial.extend(entries)
        else:
            initial = [
                engine.message_log.to_dict(entry)
                for entry in engine.message_log.get_recent(limit=limit)
            ]

    @callback  # type: ignore[untyped-decorator]
    def _on_message_event(event: dict[str, Any]) -> None:
        payload = getattr(event, "data", {}) or {}
        messages: list[dict[str, Any]] = payload.get("messages") or []
        if not messages:
            return
        if target_ids:
            filtered = []
            for message in messages:
                ids = message.get("device_ids") or []
                if not ids and message.get("device_id"):
                    ids = [message["device_id"]]
                if not ids:
                    continue
                if target_ids.isdisjoint(ids):
                    continue
                filtered.append(message)
            _send_messages(filtered)
        else:
            _send_messages(messages)

    unsubscribe = hass.bus.async_listen(MESSAGE_EVENT, _on_message_event)
    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"], {"success": True})
    if initial:
        _send_messages(initial)
