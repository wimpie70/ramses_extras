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
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import DOMAIN, LOGGER

RAMSES_CC_STORAGE_KEY = "ramses_cc"
RAMSES_CC_STORAGE_VERSION = 1
SZ_CLIENT_STATE = "client_state"
SZ_SCHEMA = "schema"
SZ_PACKETS = "packets"

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection
    from homeassistant.core import HomeAssistant

    from .device_db import DeviceDatabase
    from .scenario_engine import ScenarioEngine


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


def _get_engine(hass: HomeAssistant) -> ScenarioEngine | None:
    """Get scenario engine from hass data."""
    registry = hass.data.get("ramses_extras", {})
    return cast(ScenarioEngine | None, registry.get("device_simulator_engine"))


def _get_db(hass: HomeAssistant) -> DeviceDatabase | None:
    """Get device database from hass data."""
    registry = hass.data.get("ramses_extras", {})
    return cast(DeviceDatabase | None, registry.get("device_simulator_db"))


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
            "active_devices": len(engine.active_device_ids),
            "active_device_ids": engine.active_device_ids,
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
    if config_store:
        for name in config_store.list_profiles():
            p = config_store.get_profile(name)
            if p:
                profiles.append(
                    {
                        "name": name,
                        "description": p.description,
                        "timeout_scale": p.timeout_scale,
                        "speed_options": p.speed_options,
                    }
                )

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
                "excluded_codes": list(device.excluded_codes),
            }
            for device in engine._active_devices.values()
        ]

    # Stats from engine
    stats = {
        "rx": 0,
        "tx": engine.messages_sent if engine else 0,
        "devices": len(devices),
        "active": sum(1 for d in devices if d["enabled"]),
    }

    # Scenarios with their HA service scenario_type values
    scenarios = [
        {
            "id": "autonomous_emissions",
            "name": "Autonomous Emissions",
            "description": "Start periodic I frame emissions for a device",
            "scenario_type": "autonomous_emissions",
            "params": {"device_id": "37:168270", "device_type": "FAN"},
        },
        {
            "id": "discovery",
            "name": "Discovery Test",
            "description": "Emit 10E0 + initial I messages (stub)",
            "scenario_type": "discovery_test",
            "params": {},
        },
        {
            "id": "device_unavailability",
            "name": "Device Unavailability",
            "description": (
                "Silence all active devices after N seconds, resume after M seconds"
            ),
            "scenario_type": "device_unavailability",
            "params": {"silence_after": 30, "resume_after": 60},
        },
        {
            "id": "hvac_device_loss",
            "name": "HVAC Device Loss",
            "description": "Silence a specific device mid-run (optional restore)",
            "scenario_type": "hvac_device_loss",
            "params": {
                "device_id": "37:168270",
                "loss_after": 30,
                "restore_after": 60,
            },
        },
    ]

    connection.send_result(
        msg["id"],
        {
            "profiles": profiles,
            "devices": devices,
            "scenarios": scenarios,
            "stats": stats,
            "active_profile": None,
            "scenario_state": "idle",
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/load_profile",
        vol.Required("profile"): str,
        vol.Optional("speed"): vol.Coerce(float),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_load_profile(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Load a system configuration profile."""
    from .system_config import apply_timeout_scale

    ra = hass.data.get("ramses_extras", {})
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

    actions: list[str] = []

    # 1. Stop all active devices in the engine
    engine = ra.get("device_simulator_engine")
    if engine:
        await engine.async_stop_all()
        actions.append("stopped_devices")

    # 2. (Cache clearing is handled post-unload in _reload_ramses_cc below)

    # 3. Update ramses_cc known_list options if profile defines one
    known_list = profile.device_configs.get("_known_list")
    if known_list is not None:
        try:
            ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
            if ramses_cc_entries:
                entry = ramses_cc_entries[0]
                new_options = dict(entry.options)
                new_options["known_list"] = known_list
                hass.config_entries.async_update_entry(entry, options=new_options)
                actions.append("updated_known_list")
                LOGGER.info(
                    "Profile load: updated ramses_cc known_list: %s", known_list
                )

                clear_db = bool(profile.device_configs.get("_clear_cache_on_load"))

                async def _reload_ramses_cc(entry_id: str, wipe_db: bool) -> None:
                    """Unload ramses_cc, wipe caches, then set up again."""
                    from homeassistant.helpers import device_registry as dr
                    from homeassistant.helpers.storage import Store as HaStore

                    await hass.config_entries.async_unload(entry_id)

                    if wipe_db:
                        # Remove all HA device registry entries for this config entry
                        # so stale devices don't linger in the UI after a fresh start
                        dev_reg = dr.async_get(hass)
                        stale_devices = dr.async_entries_for_config_entry(
                            dev_reg, entry_id
                        )
                        for device in stale_devices:
                            dev_reg.async_remove_device(device.id)
                        if stale_devices:
                            LOGGER.info(
                                "Profile load: removed %d stale HA devices",
                                len(stale_devices),
                            )

                    if wipe_db:
                        # Clear HA store AFTER unload so save-on-unload is overwritten
                        try:
                            ha_store: HaStore = HaStore(
                                hass, RAMSES_CC_STORAGE_VERSION, RAMSES_CC_STORAGE_KEY
                            )
                            stored: dict[str, Any] = await ha_store.async_load() or {}
                            if SZ_CLIENT_STATE in stored:
                                stored[SZ_CLIENT_STATE].pop(SZ_SCHEMA, None)
                                stored[SZ_CLIENT_STATE].pop(SZ_PACKETS, None)
                                await ha_store.async_save(stored)
                                LOGGER.info(
                                    "Profile load: cleared HA store after unload"
                                )
                        except Exception as err:  # noqa: BLE001
                            LOGGER.warning(
                                "Profile load: could not clear HA store: %s", err
                            )

                        # Delete ramses.db after unload
                        # (final SQLite snapshot already written)
                        db_path = Path(hass.config.config_dir) / "ramses.db"
                        try:
                            if db_path.exists():
                                db_path.unlink()
                                LOGGER.info(
                                    "Profile load: deleted %s after unload", db_path
                                )
                        except Exception as err:  # noqa: BLE001
                            LOGGER.warning(
                                "Profile load: could not delete ramses.db: %s", err
                            )

                    await hass.config_entries.async_setup(entry_id)

                hass.async_create_task(_reload_ramses_cc(entry.entry_id, clear_db))
                actions.append("reloading_ramses_cc")
            else:
                LOGGER.warning("Profile load: no ramses_cc config entry found")
        except Exception as err:  # noqa: BLE001
            LOGGER.warning(
                "Profile load: could not update ramses_cc known_list: %s", err
            )

    # 4. Apply timeout scale (msg speed override takes precedence)
    scale = msg.get("speed", profile.timeout_scale)
    apply_timeout_scale(scale)
    actions.append(f"timeout_scale={scale}")

    LOGGER.info("Loaded simulator profile: %s (actions: %s)", msg["profile"], actions)
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "profile": msg["profile"],
            "actions": actions,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/start_scenario",
        vol.Required("scenario"): str,
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_start_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Start a test scenario."""
    # TODO: Implement scenario runner
    LOGGER.info("Starting scenario: %s", msg["scenario"])
    connection.send_result(msg["id"], {"success": True, "scenario": msg["scenario"]})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/stop_scenario",
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_stop_scenario(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stop the current scenario."""
    # TODO: Implement scenario stop
    LOGGER.info("Stopping scenario")
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/device_simulator/set_device_enabled",
        vol.Required("device_id"): str,
        vol.Required("enabled"): bool,
    }
)
@callback  # type: ignore[untyped-decorator]
def ws_set_device_enabled(
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

    device.enabled = msg["enabled"]
    LOGGER.info("Device %s enabled=%s", msg["device_id"], msg["enabled"])
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
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "device_id": msg["device_id"],
            "excluded_codes": device.excluded_codes,
        },
    )
