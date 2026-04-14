# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Device Simulator feature.

Simulates RAMSES devices at the communication endpoint (MQTT or serial),
allowing testing without physical RF hardware."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

import logging

from .comm_endpoint import MqttEndpoint
from .const import (
    DOMAIN,
    FEATURE_DEFINITION,
    LOGGER,
    SIMULATOR_HGI_ID,
    SIMULATOR_TOPIC_NS,
)

_LOGGER = logging.getLogger(__name__)

_RAMSES_CC_STORAGE_VERSION = 1
_RAMSES_CC_STORAGE_KEY = "ramses_cc"
_SZ_CLIENT_STATE = "client_state"
_SZ_SCHEMA = "schema"
_SZ_PACKETS = "packets"


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
        # Remove mqtt:// prefix
        url_body = port_name[7:]  # after mqtt://

        # Split auth and host
        if "@" in url_body:
            auth_host = url_body.split("@", 1)[1]
        else:
            auth_host = url_body

        # Split host:port and path
        if "/" in auth_host:
            host_port, _ = auth_host.split("/", 1)
        else:
            host_port = auth_host

        # Rebuild with simulator topic and HGI
        if "@" in url_body:
            auth = url_body.split("@", 1)[0] + "@"
        else:
            auth = ""

        # ramses_rf requires RAMSES/GATEWAY* prefix, SIMULATOR_TOPIC_NS is valid
        new_port_name = (
            f"mqtt://{auth}{host_port}/{SIMULATOR_TOPIC_NS}/{SIMULATOR_HGI_ID}"
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

        # Pre-clear ramses_cc store schema if last active profile enforced known_list.
        # This ensures that when _enforce_simulator_isolation triggers a ramses_cc
        # reload below, ramses_cc starts with a clean schema instead of the stale
        # schema from the previous session's sim devices.
        last_profile_name = config_store.get_active_profile()
        if last_profile_name:
            last_profile = config_store.get_profile(last_profile_name)
            if last_profile is not None:
                _ekl = last_profile.device_configs.get("_enforce_known_list", False)
                enforce = (
                    bool(_ekl.get("enabled", False))
                    if isinstance(_ekl, dict)
                    else bool(_ekl)
                )
                if enforce:
                    await _pre_clear_ramses_cc_schema(hass, last_profile_name)

    registry = hass.data["ramses_extras"]

    # Enforce simulator isolation: reconfigure ramses_cc if needed.
    # If isolation was already configured this returns immediately, but
    # the schema was already cleared above so the next profile load will
    # still reload ramses_cc with a clean store.
    _LOGGER.info("Device Simulator: calling _enforce_simulator_isolation")
    await _enforce_simulator_isolation(hass)

    if "device_simulator_db" not in registry:
        registry["device_simulator_db"] = DeviceDatabase()
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

    if "device_simulator_engine" not in registry:
        registry["device_simulator_engine"] = ScenarioEngine(
            hass,
            registry["device_simulator_endpoint"],
            registry["device_simulator_db"],
        )

    # Restore persisted auto_answer setting into the freshly-created engine.
    _engine_now = registry["device_simulator_engine"]
    _cs = registry.get("device_simulator_config_store")
    if _cs is not None:
        _engine_now.set_auto_answer(_cs.get_auto_answer())
        _LOGGER.info(
            "Startup: restored auto_answer=%s from persisted state",
            _cs.get_auto_answer(),
        )

    # Auto-start devices for the persisted active profile on HA restart.
    # Deferred to a background task so MQTT has time to (re)connect before the
    # startup burst fires — the same reason ws_load_profile uses asyncio.sleep(3).
    config_store = registry.get("device_simulator_config_store")
    last_profile_name = config_store.get_active_profile() if config_store else None
    if last_profile_name:
        last_profile = config_store.get_profile(last_profile_name)
        known_list = (
            last_profile.device_configs.get("_known_list") if last_profile else None
        ) or {}
        boot_devices = {
            dev_id: dev_cfg
            for dev_id, dev_cfg in known_list.items()
            if dev_cfg.get("class") != "HGI"
        }
        _LOGGER.info("Boot devices: %s", list(boot_devices.keys()))
        if boot_devices:
            from .scenario_engine import ActiveDevice

            _engine = registry["device_simulator_engine"]

            async def _deferred_boot_start() -> None:
                await asyncio.sleep(3)
                started: list[str] = []
                # Separate devices: those that are bound targets (e.g. REM) vs
                # those that bind (e.g. FAN)
                bound_targets: dict[str, dict] = {}
                binders: dict[str, dict] = {}
                for dev_id, dev_cfg in boot_devices.items():
                    if dev_cfg.get("bound"):
                        # This device binds to another (e.g. FAN with bound: REM)
                        binders[dev_id] = dev_cfg
                    else:
                        # This device might be a bound target (e.g. REM)
                        bound_targets[dev_id] = dev_cfg
                # Activate bound targets first, then binders
                for dev_id, dev_cfg in {**bound_targets, **binders}.items():
                    # If this is a FAN with a bound REM, emit a packet for the REM
                    # BEFORE activating the FAN, so REM is discovered first
                    bound_device_id = dev_cfg.get("bound")
                    if dev_cfg.get("class") == "FAN" and bound_device_id:
                        from .scenario_engine import VERB_I

                        rem_packet = _engine._build_packet(
                            bound_device_id, "--:------", VERB_I, "0000", ""
                        )
                        try:
                            await _engine._endpoint.send_packet(rem_packet)
                            _LOGGER.info(
                                "Emitted discovery packet for bound REM %s before "
                                "activating FAN %s",
                                bound_device_id,
                                dev_id,
                            )
                            # Longer delay to ensure REM is processed by ramses_rf
                            # before FAN activation
                            await asyncio.sleep(1.0)
                        except Exception as err:  # noqa: BLE001
                            _LOGGER.warning(
                                "Failed to emit discovery packet for %s: %s",
                                bound_device_id,
                                err,
                            )

                    device = ActiveDevice(
                        device_id=dev_id,
                        slug=dev_cfg.get("class", "FAN"),
                        variant_id="default",
                        excluded_codes=["1FC9"],
                        suppress_autonomous=False,
                        suppress_responses=False,
                        enabled=True,
                        bound_device_id=bound_device_id,
                    )
                    await _engine.async_activate_device(device)
                    started.append(dev_id)
                _LOGGER.info(
                    "Startup: auto-started %d device(s) from profile '%s': %s",
                    len(started),
                    last_profile_name,
                    started,
                )
                # Wait briefly for ramses_rf to process the burst frames, then
                # trigger discovery so HA entities are created immediately.
                await asyncio.sleep(1)
                from .websocket import _trigger_ramses_discovery

                await _trigger_ramses_discovery(hass)

            hass.async_create_background_task(
                _deferred_boot_start(),
                name="device_simulator_boot_autostart",
            )

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


__all__ = ["create_device_simulator_feature", "load_feature"]
