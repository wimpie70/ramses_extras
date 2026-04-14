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

from .const import (
    DOMAIN,
    LOGGER,
    SCENARIO_AUTO_ANSWER,
    SCENARIO_AUTONOMOUS_EMISSIONS,
    SCENARIO_PARAM_SCHEMAS,
    SCENARIO_REGISTRY,
)
from .system_config import SIM_DEVICE_ID

# Used by ws_clear_ramses_cache
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
    websocket_api.async_register_command(hass, ws_set_auto_answer)
    websocket_api.async_register_command(hass, ws_subscribe_devices)


def _get_engine(hass: HomeAssistant) -> ScenarioEngine | None:
    """Get scenario engine from hass data."""
    registry = hass.data.get("ramses_extras", {})
    return cast("ScenarioEngine | None", registry.get("device_simulator_engine"))


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
                        "known_list": p.device_configs.get("_known_list", {}),
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
                "suppress_responses": device.suppress_responses,
                "excluded_codes": list(device.excluded_codes),
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

    # 2. Update ramses_cc known_list + enforce_known_list from profile.
    # enforce_known_list=True causes ramses_cc's _get_saved_packets to
    # automatically filter out any cached packets whose devices are not in the
    # known_list — no manual HA store or ramses.db wipe needed.
    known_list = profile.device_configs.get("_known_list")
    if known_list is not None:
        try:
            ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
            if ramses_cc_entries:
                entry = ramses_cc_entries[0]
                new_options = dict(entry.options)
                new_options["known_list"] = known_list

                # Apply _enforce_known_list from profile into the nested ramses_rf dict
                _ekl = profile.device_configs.get("_enforce_known_list", False)
                enforce = (
                    bool(_ekl.get("enabled", False))
                    if isinstance(_ekl, dict)
                    else bool(_ekl)
                )
                ramses_rf_opts = dict(new_options.get("ramses_rf", {}))
                ramses_rf_opts["enforce_known_list"] = enforce
                new_options["ramses_rf"] = ramses_rf_opts

                # Update options in-memory without firing update_listeners.
                # async_update_entry triggers async_update_listener in ramses_cc
                # which starts its own reload before our controlled one.
                from types import MappingProxyType

                object.__setattr__(entry, "options", MappingProxyType(new_options))

                # Also persist to HA store so the options survive a restart.
                # We write directly to the core.config_entries store to avoid
                # triggering the update listener.
                try:
                    from homeassistant.helpers.storage import Store as HaStore

                    ce_store: HaStore = HaStore(hass, 1, "core.config_entries")
                    ce_data: dict = await ce_store.async_load() or {}
                    for stored_entry in ce_data.get("entries", []):
                        if stored_entry.get("entry_id") == entry.entry_id:
                            stored_entry["options"] = dict(new_options)
                            break
                    await ce_store.async_save(ce_data)
                    LOGGER.debug("Profile load: persisted ramses_cc options to store")
                except Exception as err:  # noqa: BLE001
                    LOGGER.warning(
                        "Profile load: could not persist ramses_cc options: %s", err
                    )

                actions.append("updated_known_list")
                LOGGER.info(
                    "Profile load: known_list=%s enforce_known_list=%s",
                    list(known_list.keys()),
                    enforce,
                )

                async def _reload_ramses_cc(
                    entry_id: str,
                    wipe_schema: bool,
                    auto_start_devices: dict[str, dict],
                ) -> None:
                    """Unload ramses_cc, set up again, auto-start new devices."""
                    import asyncio

                    from homeassistant.helpers import device_registry as dr
                    from homeassistant.helpers.storage import Store as HaStore

                    await hass.config_entries.async_unload(entry_id)

                    if wipe_schema:
                        # Remove stale HA device registry entries so old sim
                        # devices don't linger in the UI after a profile switch.
                        dev_reg = dr.async_get(hass)
                        stale = dr.async_entries_for_config_entry(dev_reg, entry_id)
                        for dev in stale:
                            dev_reg.async_remove_device(dev.id)
                        if stale:
                            LOGGER.info(
                                "Profile load: removed %d stale HA devices",
                                len(stale),
                            )

                        # Unload triggers async_save_client_state which writes sim
                        # device IDs into the schema. Clear them now so setup doesn't
                        # fail with "device is in schema but not in known_list".
                        try:
                            ha_store: HaStore = HaStore(
                                hass,
                                RAMSES_CC_STORAGE_VERSION,
                                RAMSES_CC_STORAGE_KEY,
                            )
                            stored: dict[str, Any] = await ha_store.async_load() or {}
                            client_state = stored.get(SZ_CLIENT_STATE, {})
                            changed = False
                            if SZ_SCHEMA in client_state:
                                client_state.pop(SZ_SCHEMA)
                                changed = True
                            if SZ_PACKETS in client_state:
                                client_state.pop(SZ_PACKETS)
                                changed = True
                            if changed:
                                await ha_store.async_save(stored)
                                LOGGER.info(
                                    "Profile load: cleared HA store schema+packets"
                                )
                        except Exception as err:  # noqa: BLE001
                            LOGGER.warning(
                                "Profile load: could not clear HA store schema: %s",
                                err,
                            )

                    await hass.config_entries.async_setup(entry_id)

                    # Auto-start autonomous emissions for new known-list devices.
                    # Brief delay lets ramses_cc finish MQTT reconnect so the
                    # first emitted packets are actually processed.
                    if auto_start_devices:
                        _engine = ra.get("device_simulator_engine")
                        if _engine:
                            await asyncio.sleep(3)
                            from .scenario_engine import ActiveDevice

                            for dev_id, dev_cfg in auto_start_devices.items():
                                slug = dev_cfg.get("class", "FAN")
                                device = ActiveDevice(
                                    device_id=dev_id,
                                    slug=slug,
                                    variant_id="default",
                                    excluded_codes=["1FC9"],
                                    suppress_autonomous=False,
                                    suppress_responses=False,
                                    enabled=True,
                                )
                                await _engine.async_activate_device(
                                    device,
                                    start_emitter=False,
                                )
                                LOGGER.info(
                                    "Profile load: auto-started %s (%s)",
                                    dev_id,
                                    slug,
                                )
                            # Wait briefly for ramses_rf to process the burst
                            # frames, then poke the coordinator so new devices
                            # are registered as HA entities immediately rather
                            # than waiting up to 60s for the scan interval.
                            await asyncio.sleep(1)
                            await _trigger_ramses_discovery(hass)

                # Auto-start all non-HGI devices from the new profile.
                auto_start = {
                    dev_id: cfg
                    for dev_id, cfg in known_list.items()
                    if cfg.get("class") != "HGI"
                }
                if msg.get("reload_ramses_cc", True):
                    hass.async_create_task(
                        _reload_ramses_cc(entry.entry_id, enforce, auto_start)
                    )
                    actions.append("reloading_ramses_cc")
                else:
                    actions.append("skipped_reload")
            else:
                LOGGER.warning("Profile load: no ramses_cc config entry found")
        except Exception as err:  # noqa: BLE001
            LOGGER.warning(
                "Profile load: could not update ramses_cc known_list: %s", err
            )

    # 4. Track active profile (in-memory and persisted to disk)
    ra = hass.data.setdefault("ramses_extras", {})
    ra["device_simulator_active_profile"] = profile.name
    config_store = ra.get("device_simulator_config_store")
    if config_store is not None:
        config_store.set_active_profile(profile.name)
        await config_store.async_save_state()

    # 5. Apply timeout scale (msg speed override takes precedence)
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
        if scenario_id == SCENARIO_AUTONOMOUS_EMISSIONS:
            response = await _start_autonomous_emissions(engine, params)
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

    if scenario_id == SCENARIO_AUTONOMOUS_EMISSIONS or device_id:
        if device_id:
            await engine.async_silence_device(device_id)
            connection.send_result(
                msg["id"],
                {
                    "success": True,
                    "message": f"Autonomous emissions stopped for {device_id}",
                },
            )
            return
        await engine.async_stop_all()
        connection.send_result(
            msg["id"],
            {"success": True, "message": "Autonomous emissions stopped (all)"},
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
    )
    await engine.async_activate_device(device)
    return {
        "success": True,
        "scenario_id": SCENARIO_AUTONOMOUS_EMISSIONS,
        "device_id": device_id,
        "message": f"Autonomous emissions started for {device_id}",
    }


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
