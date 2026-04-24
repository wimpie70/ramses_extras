# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Device Simulator feature.

Simulates RAMSES devices at the communication endpoint (MQTT or serial),
allowing testing without physical RF hardware."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
import logging
from pathlib import Path

from homeassistant.helpers.storage import Store as HaStore

from ...framework.helpers.ramses_message_stream import get_ramses_message_stream
from .comm_endpoint import MqttEndpoint
from .const import (
    DOMAIN,
    FEATURE_DEFINITION,
    LOGGER,
    SIMULATOR_HGI_ID,
    SIMULATOR_TOPIC_NS,
)
from .scenarios import async_discover_scenarios, discover_scenarios

_LOGGER = logging.getLogger(__name__)

_RAMSES_CC_STORAGE_VERSION = 1
_RAMSES_CC_STORAGE_KEY = "ramses_cc"
_SZ_CLIENT_STATE = "client_state"
_SZ_SCHEMA = "schema"
_SZ_PACKETS = "packets"

_SIM_ISOLATION_STORAGE_VERSION = 1
_SIM_ISOLATION_STORAGE_KEY = "ramses_extras_device_sim_isolation"
_SZ_ORIGINAL_PORT = "original_port_name"
_SZ_ORIGINAL_SCHEMA = "original_schema"
_SZ_ORIGINAL_KNOWN_LIST = "original_known_list"
_SZ_ORIGINAL_ENFORCE_KNOWN_LIST = "original_enforce_known_list"
_SZ_ORIGINAL_ENABLE_EAVESDROP = "original_enable_eavesdrop"
_SZ_STATE_SAVED = "state_saved"
_DEFAULT_GATEWAY_TOPIC_NS = "RAMSES/GATEWAY"


def _make_isolation_store(hass: HomeAssistant) -> HaStore:
    from homeassistant.helpers.storage import (
        Store,  # local import to avoid HA dependency at import time
    )

    return Store(hass, _SIM_ISOLATION_STORAGE_VERSION, _SIM_ISOLATION_STORAGE_KEY)


async def _load_isolation_state(hass: HomeAssistant) -> tuple[Any, dict[str, Any]]:
    store = _make_isolation_store(hass)
    state = await store.async_load()
    if not isinstance(state, dict):
        state = {}
    return store, state


def _parse_mqtt_port(port_name: str) -> tuple[str, str, str]:
    if not isinstance(port_name, str) or not port_name.startswith("mqtt://"):
        raise ValueError("serial_port.port_name must be an mqtt:// URL")
    url_body = port_name[7:]
    auth_section = ""
    remainder = url_body
    if "@" in remainder:
        auth_section, remainder = remainder.split("@", 1)
        auth_section = f"{auth_section}@"
    if "/" in remainder:
        host_port, path = remainder.split("/", 1)
    else:
        host_port = remainder
        path = ""
    return auth_section, host_port, path


def _split_topic_and_gateway(path: str) -> tuple[str, str | None]:
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return "", None
    if len(segments) == 1:
        return segments[0], None
    topic = "/".join(segments[:-1])
    gateway = segments[-1]
    return topic, gateway


def _compose_mqtt_port(
    auth: str, host_port: str, topic: str, gateway: str | None
) -> str:
    topic = topic.strip("/") if topic else ""
    path_parts = [part for part in (topic, gateway) if part]
    if path_parts:
        return f"mqtt://{auth}{host_port}/{'/'.join(path_parts)}"
    return f"mqtt://{auth}{host_port}"


def _build_default_gateway_port(port_name: str) -> str:
    auth, host_port, path = _parse_mqtt_port(port_name)
    _, gateway = _split_topic_and_gateway(path)
    return _compose_mqtt_port(auth, host_port, _DEFAULT_GATEWAY_TOPIC_NS, gateway)


async def _remember_original_ramses_cc_state(
    hass: HomeAssistant,
    port_name: str | None,
    schema: Any,
    known_list: Any,
    enforce_known_list: Any,
    enable_eavesdrop: Any,
) -> None:
    """Save original ramses_cc options before simulator isolation overwrites them.

    Idempotent: if state was already saved (sim already enabled previously),
    this is a no-op so we don't overwrite the true original with sim values.
    """
    from copy import deepcopy

    if not isinstance(port_name, str) or not port_name:
        return
    if SIMULATOR_TOPIC_NS in port_name:
        # Already in isolation mode - do NOT save current (sim) state as "original"
        return
    store, state = await _load_isolation_state(hass)
    if state.get(_SZ_STATE_SAVED):
        return
    state[_SZ_ORIGINAL_PORT] = port_name
    state[_SZ_ORIGINAL_SCHEMA] = deepcopy(schema) if schema is not None else None
    state[_SZ_ORIGINAL_KNOWN_LIST] = (
        deepcopy(known_list) if known_list is not None else None
    )
    state[_SZ_ORIGINAL_ENFORCE_KNOWN_LIST] = enforce_known_list
    state[_SZ_ORIGINAL_ENABLE_EAVESDROP] = enable_eavesdrop
    state[_SZ_STATE_SAVED] = True
    await store.async_save(state)
    _LOGGER.info(
        "Saved original ramses_cc state for simulator cleanup "
        "(port=%s schema_keys=%s known_list_count=%s enforce=%s eavesdrop=%s)",
        port_name,
        list(schema.keys()) if isinstance(schema, dict) else None,
        len(known_list) if isinstance(known_list, dict) else None,
        enforce_known_list,
        enable_eavesdrop,
    )


# Backwards-compat shim for any legacy callers.
async def _remember_original_port_name(
    hass: HomeAssistant, port_name: str | None
) -> None:
    await _remember_original_ramses_cc_state(hass, port_name, None, None, None, None)


async def async_restore_ramses_cc_gateway_topic(hass: HomeAssistant) -> bool:
    """Restore full ramses_cc state if simulator isolation modified it.

    Restores serial_port.port_name, schema, known_list, ramses_rf.enforce_known_list,
    and ramses_rf.enable_eavesdrop from the values saved when isolation was enabled.
    If only port_name was saved (legacy), only port_name is restored.

    Returns True if any state was restored and ramses_cc was reloaded.
    """

    entries = hass.config_entries.async_entries("ramses_cc")
    if not entries:
        _LOGGER.warning("No ramses_cc config entry found - cannot restore state")
        return False

    cc_entry = entries[0]
    cc_options = dict(cc_entry.options) if cc_entry.options else {}
    serial_port = dict(cc_options.get("serial_port", {}))
    current_port = serial_port.get("port_name")

    store, state = await _load_isolation_state(hass)
    stored_port = state.get(_SZ_ORIGINAL_PORT)
    state_saved = state.get(_SZ_STATE_SAVED, False)
    isolation_active = isinstance(current_port, str) and (
        SIMULATOR_TOPIC_NS in current_port or SIMULATOR_HGI_ID in current_port
    )

    if not stored_port and not isolation_active:
        _LOGGER.debug("Simulator isolation already cleared - nothing to restore")
        if state:
            await store.async_save({})
        return False

    # Resolve target port (stored or fallback)
    target_port = stored_port
    used_fallback = False
    if not target_port:
        if not isinstance(current_port, str):
            _LOGGER.warning(
                "Simulator isolation fallback failed: current ramses_cc port missing",
            )
            return False
        try:
            target_port = _build_default_gateway_port(current_port)
            used_fallback = True
        except ValueError as err:
            _LOGGER.warning(
                "Simulator isolation fallback failed for '%s': %s",
                current_port,
                err,
            )
            return False

    # Build restored options
    changed = False

    if target_port != current_port:
        serial_port["port_name"] = target_port
        cc_options["serial_port"] = serial_port
        changed = True

    if state_saved:
        # Restore schema
        original_schema = state.get(_SZ_ORIGINAL_SCHEMA)
        if original_schema is not None:
            cc_options["schema"] = original_schema
        else:
            cc_options.pop("schema", None)

        # Restore known_list
        original_known_list = state.get(_SZ_ORIGINAL_KNOWN_LIST)
        if original_known_list is not None:
            cc_options["known_list"] = original_known_list
        else:
            cc_options.pop("known_list", None)

        # Restore ramses_rf options
        ramses_rf_opts = dict(cc_options.get("ramses_rf", {}))
        original_enforce = state.get(_SZ_ORIGINAL_ENFORCE_KNOWN_LIST)
        original_eavesdrop = state.get(_SZ_ORIGINAL_ENABLE_EAVESDROP)
        if original_enforce is not None:
            ramses_rf_opts["enforce_known_list"] = original_enforce
        else:
            ramses_rf_opts.pop("enforce_known_list", None)
        if original_eavesdrop is not None:
            ramses_rf_opts["enable_eavesdrop"] = original_eavesdrop
        else:
            ramses_rf_opts.pop("enable_eavesdrop", None)
        cc_options["ramses_rf"] = ramses_rf_opts

        changed = True
        _LOGGER.info(
            "Restored ramses_cc schema/known_list/ramses_rf to pre-simulator state"
        )

    if not changed:
        _LOGGER.debug("ramses_cc already in desired state - no reload needed")
        if state:
            await store.async_save({})
        return False

    hass.config_entries.async_update_entry(cc_entry, options=cc_options)
    await hass.config_entries.async_reload(cc_entry.entry_id)

    # Clear saved state so a subsequent sim-enable will re-capture
    await store.async_save({})

    _LOGGER.info("Restored ramses_cc MQTT serial_port to %s", target_port)
    if used_fallback:
        _LOGGER.warning(
            "Simulator restore used fallback topic %s - please verify gateway ID",
            target_port,
        )

    return True


# Expose as async_restore_ramses_cc_state for clarity; keep old name as alias.
async_restore_ramses_cc_state = async_restore_ramses_cc_gateway_topic


async def _pre_clear_ramses_cc_schema(hass: HomeAssistant, profile_name: str) -> None:
    """Clear the ramses_cc HA store schema at startup.

    Called when the last active profile enforced known_list, so the stale
    schema (from a previous session) does not cause HA to boot with hundreds
    of old sim devices before our profile reload kicks in.
    """
    from homeassistant.helpers.storage import Store as HaStore

    try:
        ha_store: HaStore = HaStore(
            hass, _RAMSES_CC_STORAGE_VERSION, _RAMSES_CC_STORAGE_KEY
        )
        stored: dict = await ha_store.async_load() or {}
        client_state = stored.get(_SZ_CLIENT_STATE, {})
        changed = False
        for key in (_SZ_SCHEMA, _SZ_PACKETS):
            if key in client_state:
                client_state.pop(key)
                changed = True
        if changed:
            await ha_store.async_save(stored)
            _LOGGER.info(
                "Startup: pre-cleared ramses_cc store schema+packets (last profile=%s)",
                profile_name,
            )
        else:
            _LOGGER.debug(
                "Startup: ramses_cc store already clean (last profile=%s)",
                profile_name,
            )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Startup: could not pre-clear ramses_cc store schema: %s", err)


# SIMULATOR_TOPIC_NS is imported from const
# ramses_rf requires RAMSES/GATEWAY prefix, but RAMSES/GATEWAY_SIM is valid
# This provides complete topic isolation from production traffic


async def _enforce_simulator_isolation(hass: HomeAssistant) -> bool:
    """Enforce that ramses_cc uses isolated topics for simulation.

    When device_simulator is enabled, ramses_cc MUST use a different HGI ID
    and topic namespace to avoid interfering with real devices.

    This function automatically reconfigures ramses_cc if needed and triggers
    a reload so the isolation takes effect.

    :param hass: Home Assistant instance
    :return: True if isolation is enforced (may require reload)
    :raises RuntimeError: If reconfiguration fails
    """
    entries = hass.config_entries.async_entries("ramses_cc")
    if not entries:
        _LOGGER.warning("No ramses_cc config entry found - cannot enforce isolation")
        return False

    cc_entry = entries[0]
    cc_options = dict(cc_entry.options) if cc_entry.options else {}
    serial_port = dict(cc_options.get("serial_port", {}))
    port_name = serial_port.get("port_name", "")

    # Capture current ramses_cc state before any modification so we can
    # restore the user's real-device configuration on disable/remove.
    current_schema = cc_options.get("schema")
    current_known_list = cc_options.get("known_list")
    ramses_rf_opts = cc_options.get("ramses_rf", {})
    current_enforce = (
        ramses_rf_opts.get("enforce_known_list")
        if isinstance(ramses_rf_opts, dict)
        else None
    )
    current_eavesdrop = (
        ramses_rf_opts.get("enable_eavesdrop")
        if isinstance(ramses_rf_opts, dict)
        else None
    )

    _LOGGER.debug("Checking ramses_cc config: port_name=%s", port_name)

    # Check if using MQTT (device_simulator only makes sense with MQTT)
    if not port_name.startswith("mqtt://"):
        _LOGGER.info("ramses_cc not using MQTT - simulator isolation not applicable")
        return True

    # Check if already using simulator isolation
    if SIMULATOR_HGI_ID in port_name and SIMULATOR_TOPIC_NS in port_name:
        _LOGGER.info("ramses_cc already configured for simulator isolation")
        return True

    # Need to reconfigure - parse the MQTT URL and rebuild with isolation
    _LOGGER.warning(
        "Reconfiguring ramses_cc for simulator isolation: HGI=%s, topic=%s",
        SIMULATOR_HGI_ID,
        SIMULATOR_TOPIC_NS,
    )

    # Parse mqtt://[user:pass@]host:port/topic/gwid format
    # or mqtt://[user:pass@]host:port (uses defaults)
    try:
        await _remember_original_ramses_cc_state(
            hass,
            port_name,
            current_schema,
            current_known_list,
            current_enforce,
            current_eavesdrop,
        )

        auth, host_port, _ = _parse_mqtt_port(port_name)

        # ramses_rf requires RAMSES/GATEWAY* prefix, SIMULATOR_TOPIC_NS is valid
        new_port_name = _compose_mqtt_port(
            auth,
            host_port,
            SIMULATOR_TOPIC_NS,
            SIMULATOR_HGI_ID,
        )

        _LOGGER.info(
            "Updating ramses_cc serial_port from '%s' to '%s'", port_name, new_port_name
        )
        _LOGGER.info(
            "Simulator will use HGI %s - completely isolated from production HGI",
            SIMULATOR_HGI_ID,
        )

        # Update config entry
        serial_port["port_name"] = new_port_name
        cc_options["serial_port"] = serial_port

        hass.config_entries.async_update_entry(cc_entry, options=cc_options)

        # Schedule reload of ramses_cc to apply changes
        _LOGGER.info("Scheduling ramses_cc reload to apply simulator isolation")
        await hass.config_entries.async_reload(cc_entry.entry_id)

        return True

    except Exception as err:
        error_msg = (
            f"Failed to enforce simulator isolation: {err}. "
            f"Please manually reconfigure ramses_cc to use: "
            f"mqtt://[host]:[port]/{SIMULATOR_TOPIC_NS}/{SIMULATOR_HGI_ID}"
        )
        _LOGGER.error(error_msg)
        raise RuntimeError(error_msg) from err


async def create_device_simulator_feature(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Factory function to create the Device Simulator feature.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry
    :return: Feature descriptor dict
    """
    _LOGGER.info("Device Simulator: create_device_simulator_feature starting")

    from .device_db import DeviceDatabase
    from .periodic_emitter import PeriodicEmitter
    from .response_engine import ResponseEngine
    from .scenario_engine import ScenarioEngine
    from .services import async_setup_services
    from .system_config import ConfigProfileStore, apply_timeout_scale
    from .websocket import async_register_websocket_commands

    hass.data.setdefault("ramses_extras", {})

    # Initialize system configuration profiles first so we can read the last
    # active profile before ramses_cc gets a chance to reload.
    if "device_simulator_config_store" not in hass.data["ramses_extras"]:
        config_store = ConfigProfileStore()
        await config_store.async_initialize(hass)
        hass.data["ramses_extras"]["device_simulator_config_store"] = config_store
        _LOGGER.debug("Device Simulator: initialized config profile store")

        # Apply default timeout scaling (can be overridden by loaded profile)
        apply_timeout_scale(1.0)

        # Clean restart: when preserve_state is False, force-switch to
        # fresh_start_allow_unknown_devices so we boot with a clean known_list
        # and schema (any device that appears is eavesdropped, not pre-known).
        if not config_store.get_preserve_state():
            clean_profile_name = "fresh_start_allow_unknown_devices"
            clean_profile = config_store.get_profile(clean_profile_name)
            if clean_profile is not None:
                _LOGGER.info(
                    "Device Simulator: preserve_state=False, switching active "
                    "profile to '%s' for clean restart",
                    clean_profile_name,
                )
                config_store.set_active_profile(clean_profile_name)
                await config_store.async_save_state()

                # Clear RF cache and database before profile loading for clean slate
                from .profile_loader import (
                    _clear_ramses_rf_cache,
                    _reload_ramses_cc,
                    _update_known_list_and_reload,
                )

                try:
                    await _clear_ramses_rf_cache(hass)
                    _LOGGER.info("Device Simulator: cleared RF cache for clean restart")
                except Exception as e:
                    _LOGGER.warning("Device Simulator: failed to clear RF cache: %s", e)

                try:
                    await _remove_ramses_database(hass)
                    _LOGGER.info("Device Simulator: removed database for clean restart")
                except Exception as e:
                    _LOGGER.warning(
                        "Device Simulator: failed to remove database: %s", e
                    )
                await _pre_clear_ramses_cc_schema(hass, clean_profile_name)

                # Write the clean profile's known_list/schema to the ramses_cc
                # config entry so the reload below picks up the fresh options.
                known_list = clean_profile.device_configs.get("_known_list")
                schema = clean_profile.device_configs.get("_schema")
                if known_list is not None:
                    schema_payload = dict(schema) if isinstance(schema, dict) else None
                    await _update_known_list_and_reload(
                        hass,
                        dict(known_list),
                        clean_profile.device_configs.get("_enforce_known_list", False),
                        reload_ramses_cc=False,
                        schema=schema_payload,
                    )

                # Reload ramses_cc to ensure it starts with clean state.
                #
                # This fixes the load order issue during container restart:
                # - When HA restarts, ramses_cc loads BEFORE ramses_extras
                # - ramses_cc hydrates from stale disk state (schema, known_list, db)
                # - Then ramses_extras starts and cleans the state, but it's too late
                # - Devices are already announced from the stale state
                #
                # Use _reload_ramses_cc (same helper as the manual fresh_start
                # profile load) so the HA device registry is also wiped.
                # A plain hass.config_entries.async_reload() keeps stale HA
                # devices around, which then re-hydrate through ramses_cc.
                ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
                if ramses_cc_entries:
                    try:
                        await _reload_ramses_cc(
                            hass,
                            ramses_cc_entries[0].entry_id,
                            wipe_schema=True,
                            auto_start_on_reload=False,
                            profile_devices={},
                        )
                        _LOGGER.info(
                            "Device Simulator: reloaded ramses_cc for clean restart"
                        )
                    except Exception as e:
                        _LOGGER.warning(
                            "Device Simulator: failed to reload ramses_cc: %s", e
                        )

    registry = hass.data["ramses_extras"]

    # Enforce simulator isolation: reconfigure ramses_cc if needed.
    # If isolation was already configured this returns immediately, but
    # the schema was already cleared above so the next profile load will
    # still reload ramses_cc with a clean store.
    _LOGGER.info("Device Simulator: calling _enforce_simulator_isolation")
    await _enforce_simulator_isolation(hass)

    if "device_simulator_db" not in registry:
        user_conversations_dir = Path(
            hass.config.path("ramses_extras", "device_simulator", "conversations")
        )
        registry["device_simulator_db"] = DeviceDatabase(
            user_conversations_dir=user_conversations_dir
        )
        await hass.async_add_executor_job(registry["device_simulator_db"].load_all)

    # Create endpoint first (don't connect yet)
    # If there's an old endpoint, disconnect it to clean up MQTT subscription
    if "device_simulator_endpoint" in registry:
        old_endpoint = registry["device_simulator_endpoint"]
        if old_endpoint.is_connected:
            _LOGGER.info("Disconnecting old endpoint...")
            await old_endpoint.async_disconnect()
        _LOGGER.info("Removing old endpoint from registry")
        del registry["device_simulator_endpoint"]

    _LOGGER.info("Creating new MqttEndpoint...")
    registry["device_simulator_endpoint"] = MqttEndpoint(
        hass, topic_base=SIMULATOR_TOPIC_NS
    )
    _LOGGER.info(
        "Created MqttEndpoint instance: %s", id(registry["device_simulator_endpoint"])
    )

    # Create and wire up ResponseEngine BEFORE connecting endpoint
    # This ensures no messages are lost during initialization
    # Always create fresh to avoid stale handler issues
    if "device_simulator_response_engine" in registry:
        _LOGGER.info("Removing stale ResponseEngine...")
        del registry["device_simulator_response_engine"]

    _LOGGER.info("Creating ResponseEngine...")
    registry["device_simulator_response_engine"] = ResponseEngine(
        registry["device_simulator_db"],
        registry["device_simulator_endpoint"],
        config_store=registry["device_simulator_config_store"],
    )
    _LOGGER.info("ResponseEngine created")

    # ALWAYS wire up handlers fresh to the new endpoint.
    # Both ResponseEngine and ScenarioEngine need to be re-registered because
    # a new MqttEndpoint is created on every reload — the old handlers would
    # reference the disconnected old endpoint.
    _LOGGER.info("Wiring up handlers to new endpoint...")
    endpoint = registry["device_simulator_endpoint"]
    endpoint.clear_inbound_handlers()

    # ResponseEngine — handles legacy RQ→RP path
    handler = registry["device_simulator_response_engine"].handle_inbound_frame
    endpoint.add_inbound_handler(handler)

    # ScenarioEngine — handles auto-answer and inbound frame logic.
    # Also update its endpoint reference so emitter tasks send to the new one.
    if "device_simulator_engine" in registry:
        eng = registry["device_simulator_engine"]
        # Stop active emitters so they don't keep sending to the old endpoint
        await eng.async_stop_all()
        eng._endpoint = endpoint
        endpoint.add_inbound_handler(eng._handle_inbound_frame)
        _LOGGER.info(
            "ScenarioEngine re-wired to new endpoint (endpoint_id=%s)",
            id(endpoint),
        )

    _LOGGER.info(
        "ResponseEngine wired up to endpoint (endpoint_id=%s handler_id=%s)",
        id(endpoint),
        id(handler),
    )

    # Always reconnect endpoint to ensure MQTT callback is bound to fresh instance
    if registry["device_simulator_endpoint"].is_connected:
        _LOGGER.info("Disconnecting endpoint to rebind with new handler...")
        await registry["device_simulator_endpoint"].async_disconnect()

    _LOGGER.info("Connecting endpoint with new handler...")
    await registry["device_simulator_endpoint"].async_connect()

    def _profile_has_hvac_devices(store: Any | None) -> bool:
        if not store:
            return False
        active = store.get_active_profile()
        if not active:
            return False
        profile = store.get_profile(active)
        if not profile:
            return False
        known = profile.device_configs.get("_known_list", {})
        for dev_cfg in known.values():
            slug = (dev_cfg or {}).get("class")
            if slug in {"FAN", "CO2", "REM", "HUM", "DIS"}:
                return True
        return False

    send_hvac_presence = _profile_has_hvac_devices(
        registry.get("device_simulator_config_store")
    )

    if send_hvac_presence:
        # Send an initial HGI presence packet to announce the gateway
        # The retained online status (published by MqttEndpoint) triggers ramses_cc
        # binding
        hgi_device_id = SIMULATOR_HGI_ID  # 18:001234
        dst = "--:------"  # Broadcast
        code = "0005"  # HGI presence announcement packet
        payload = "0005DC0101F40205DC"  # HGI presence payload
        payload_len = len(payload) // 2  # 9 bytes
        # Format: RSSI VERB --- SRC DST BROADCAST CODE LEN PAYLOAD
        # For HGI I frames: BROADCAST = SRC (the HGI itself)
        initial_frame = (
            f"040  I --- {hgi_device_id} {dst} {hgi_device_id} {code} "
            f"{payload_len:03d} {payload}"
        )

        try:
            await registry["device_simulator_endpoint"].send_packet(initial_frame)
            _LOGGER.info("Sent initial HGI presence packet: %s", initial_frame)
        except Exception as err:
            _LOGGER.error("Failed to send initial HGI packet: %s", err)

    # Create periodic emitter but don't auto-start it
    # Autonomous emissions are now scenario-controlled only
    if "device_simulator_periodic_emitter" not in registry:
        registry["device_simulator_periodic_emitter"] = PeriodicEmitter(
            registry["device_simulator_db"],
            registry["device_simulator_endpoint"],
        )
        # Note: Not starting here - scenarios control emissions
        _LOGGER.info(
            "Periodic emitter created (not auto-started - scenario controlled)"
        )

    await async_discover_scenarios(hass)

    if "device_simulator_engine" not in registry:
        registry["device_simulator_engine"] = ScenarioEngine(
            hass,
            registry["device_simulator_endpoint"],
            registry["device_simulator_db"],
            scenario_definitions=discover_scenarios(),
        )

    registry["device_simulator_response_engine"].set_engine(
        registry["device_simulator_engine"]
    )

    existing_stream_unsub = registry.get("device_simulator_message_stream_unsub")
    if callable(existing_stream_unsub):
        existing_stream_unsub()

    stream = get_ramses_message_stream(hass)
    stream.start()

    def _handle_processed_message(data: dict[str, Any]) -> None:
        frame = data.get("frame")
        verb = data.get("verb")
        if not isinstance(frame, str) or not frame.strip():
            return
        if verb not in {"RP", "I"}:
            return
        dtm = data.get("dtm")
        timestamp = None
        if isinstance(dtm, str):
            try:
                timestamp = datetime.fromisoformat(dtm).timestamp()
            except Exception:
                pass
        registry["device_simulator_engine"].log_processed_frame(frame, timestamp)

    registry["device_simulator_message_stream_unsub"] = stream.subscribe(
        _handle_processed_message
    )

    # Restore persisted auto_answer and answer_unknown_devices settings into the
    # freshly-created engine.
    _engine_now = registry["device_simulator_engine"]
    _cs = registry.get("device_simulator_config_store")
    if _cs is not None:
        _engine_now.set_auto_answer(_cs.get_auto_answer())
        _engine_now.set_autonomous_speed(_cs.get_autonomous_speed())
        _engine_now.set_answer_unknown_devices(_cs.get_answer_unknown_devices())
        _LOGGER.info(
            "Startup: restored auto_answer=%s answer_unknown=%s from persisted state",
            _cs.get_auto_answer(),
            _cs.get_answer_unknown_devices(),
        )

    # On restart we no longer auto-start profile devices. Users should trigger the
    # "Profile Emissions" scenario after selecting a profile to mimic real RF
    # behaviour and avoid unsolicited bursts during HA startup.
    config_store = registry.get("device_simulator_config_store")
    if config_store and config_store.get_active_profile():
        _LOGGER.info(
            "Device Simulator: profile '%s' loaded. Use the profile emissions scenario "
            "to start simulated devices when needed.",
            config_store.get_active_profile(),
        )

    # Handle database removal if requested
    config_store = registry.get("device_simulator_config_store")
    if config_store and config_store.get_remove_database():
        await _remove_ramses_database(hass)
        config_store.set_remove_database(False)  # Clear flag after use
        _LOGGER.info("Database removal completed and flag cleared")

    # Set up services
    await async_setup_services(hass)

    # Register websocket commands
    async_register_websocket_commands(hass)

    _LOGGER.debug("Device Simulator feature created")

    return {
        "db": registry["device_simulator_db"],
        "endpoint": registry["device_simulator_endpoint"],
        "response_engine": registry["device_simulator_response_engine"],
        "periodic_emitter": registry["device_simulator_periodic_emitter"],
        "engine": registry["device_simulator_engine"],
        "config_store": hass.data["ramses_extras"]["device_simulator_config_store"],
        "feature_name": "device_simulator",
    }


async def _remove_ramses_database(hass: HomeAssistant) -> None:
    """Remove the ramses database file."""
    try:
        # Get ramses_cc config to find database path
        entries = hass.config_entries.async_entries("ramses_cc")
        if not entries:
            _LOGGER.warning("No ramses_cc entry found - cannot determine database path")
            return

        cc_entry = entries[0]
        cc_options = dict(cc_entry.options) if cc_entry.options else {}
        ramses_rf_config = cc_options.get("ramses_rf", {})
        database_path = ramses_rf_config.get("database_path", "ramses.db")

        if database_path:
            db_path = Path(database_path)
            if db_path.exists():
                db_path.unlink()
                _LOGGER.info("Removed ramses database file: %s", db_path)
            else:
                _LOGGER.info("Database file not found: %s", db_path)
        else:
            _LOGGER.warning("No database path configured")

    except Exception as err:
        _LOGGER.error("Failed to remove database file: %s", err)


# Framework entry point: synchronous wrapper for async feature creation
def load_feature(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
    """Load the Device Simulator feature.

    This is the synchronous entry point called by the framework.
    It schedules the async creation via hass.async_create_task.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry for ramses_extras
    :return: Feature descriptor with minimal info; actual setup is async
    """
    from custom_components.ramses_extras.extras_registry import extras_registry

    from .const import DEVICE_SIMULATOR_CARD_CONFIGS

    # Register each card configuration for feature-centric card management
    for card_config in DEVICE_SIMULATOR_CARD_CONFIGS:
        extras_registry.register_card_config("device_simulator", card_config)

    # Schedule async setup and return immediately
    # The async task will handle the actual feature creation
    asyncio.create_task(create_device_simulator_feature(hass, config_entry))

    # Return a minimal descriptor; the async task will complete the setup
    return {
        "feature_name": "device_simulator",
        "services_module": "services",
        "websocket_commands_module": "websocket",
    }


__all__ = [
    "create_device_simulator_feature",
    "load_feature",
    "async_restore_ramses_cc_gateway_topic",
    "async_restore_ramses_cc_state",
]
