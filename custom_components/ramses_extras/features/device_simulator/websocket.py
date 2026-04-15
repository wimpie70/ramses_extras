# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
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

import asyncio
import time
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
from .system_config import SIM_DEVICE_ID

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection
    from homeassistant.core import HomeAssistant

    from .device_db import DeviceDatabase
    from .scenario_engine import ScenarioEngine
    from .system_config import ConfigProfileStore


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
    websocket_api.async_register_command(hass, ws_clear_ramses_cache)
    websocket_api.async_register_command(hass, ws_set_auto_answer)
    websocket_api.async_register_command(hass, ws_subscribe_devices)
    websocket_api.async_register_command(hass, ws_delete_profile)


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
    """Return recent message log."""
    engine = _get_engine(hass)
    if not engine:
        connection.send_error(msg["id"], "not_ready", "Simulator not initialized")
        return

    # Get last N messages
    limit = msg.get("limit", 50)
    messages = engine._message_log[-limit:] if engine._message_log else []

    connection.send_result(msg["id"], {"messages": messages})


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
    ra = hass.data.get("ramses_extras", {})

    # Get profiles from config store
    config_store = ra.get("device_simulator_config_store")
    profiles = []
    active_profile = None
    active_profile_yaml: str | None = None
    active_profile_scale: float | None = None
    if config_store:
        active_profile = config_store.get_active_profile()
        for name in config_store.list_profiles():
            p = config_store.get_profile(name)
            if not p:
                continue
            is_builtin = name in config_store.BUILTIN_PROFILES
            profiles.append(
                {
                    "name": name,
                    "description": p.description,
                    "timeout_scale": p.timeout_scale,
                    "speed_options": p.speed_options,
                    "known_list": p.device_configs.get("_known_list", {}),
                    "is_builtin": is_builtin,
                    "can_delete": not is_builtin,
                    "is_active": name == active_profile,
                }
            )
            if name == active_profile:
                active_profile_yaml = profile_to_yaml(p)
                active_profile_scale = p.timeout_scale

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
            }
            for device in engine._active_devices.values()
        ]

    # Stats from engine
    stats = {
        "rx": engine.messages_received if engine else 0,
        "tx": engine.messages_sent if engine else 0,
        "devices": len(devices),
        "active": sum(1 for d in devices if d["enabled"]),
    }

    active_profile = ra.get("device_simulator_active_profile")
    auto_answer = engine.auto_answer_enabled if engine else True
    running_scenarios = engine.get_running_scenario_ids() if engine else []
    emissions_active = engine.autonomous_emissions_active if engine else False

    connection.send_result(
        msg["id"],
        {
            "profiles": profiles,
            "devices": devices,
            "stats": stats,
            "active_profile": active_profile,
            "active_profile_yaml": active_profile_yaml,
            "active_profile_timeout_scale": active_profile_scale,
            "auto_answer": auto_answer,
            "running_scenarios": running_scenarios,
            "autonomous_emissions_active": emissions_active,
            "scenario_registry": SCENARIO_REGISTRY,
            "scenario_param_schemas": SCENARIO_PARAM_SCHEMAS,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/load_profile",
        vol.Required("profile"): str,
        vol.Optional("speed"): vol.Coerce(float),
        vol.Optional("reload_ramses_cc", default=True): bool,
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
        result = await async_apply_profile(
            hass,
            profile_name=profile.name,
            profile=profile,
            reload_ramses_cc=msg.get("reload_ramses_cc", True),
            speed=msg.get("speed"),
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "error", str(err))
        return

    ra["device_simulator_active_profile"] = profile.name
    config_store.set_active_profile(profile.name)
    await config_store.async_save_state()

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
            profile_devices = engine.build_profile_devices(profile)
            if not profile_devices:
                connection.send_error(
                    msg["id"],
                    "no_devices",
                    "Active profile does not define any devices to emit",
                )
                return
            started_ids: list[str] = []
            for device in profile_devices:
                await engine.async_activate_device(device)
                started_ids.append(device.device_id)
            engine.set_running_metadata(
                SCENARIO_PROFILE_EMISSIONS,
                {"profile": active_profile_name, "devices": started_ids},
            )
            response = {
                "success": True,
                "scenario_id": SCENARIO_PROFILE_EMISSIONS,
                "message": f"Started profile devices ({len(started_ids)})",
            }
        elif engine.has_scenario_definition(scenario_id):
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

    result = await async_apply_profile(
        hass,
        profile_name=profile.name,
        profile=profile,
        reload_ramses_cc=params.get("reload_ramses", True),
        speed=params.get("speed"),
    )
    result.setdefault("scenario_id", SCENARIO_LOAD_PROFILE_YAML)
    result.setdefault(
        "message",
        f"Loaded profile '{profile.name}' from YAML",
    )
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
        {"success": True, "device_id": msg["device_id"], "enabled": msg["enabled"]},
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
