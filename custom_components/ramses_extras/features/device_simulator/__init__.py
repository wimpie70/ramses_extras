# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Device Simulator feature.

Simulates RAMSES devices at the communication endpoint (MQTT or serial),
allowing testing without physical RF hardware.
"""

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


# SIMULATOR_TOPIC_NS is imported from const
# ramses_rf requires RAMSES/GATEWAY prefix, but RAMSES/GATEWAY_SIM is valid
# This provides complete topic isolation from production traffic


async def _enforce_simulator_isolation(hass: "HomeAssistant") -> bool:
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
    hass: "HomeAssistant",
    config_entry: "ConfigEntry",
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

    # Enforce simulator isolation: reconfigure ramses_cc if needed
    _LOGGER.info("Device Simulator: calling _enforce_simulator_isolation")
    await _enforce_simulator_isolation(hass)

    hass.data.setdefault("ramses_extras", {})

    # Initialize system configuration profiles
    if "device_simulator_config_store" not in hass.data["ramses_extras"]:
        config_store = ConfigProfileStore()
        hass.data["ramses_extras"]["device_simulator_config_store"] = config_store
        _LOGGER.debug("Device Simulator: initialized config profile store")

        # Apply default timeout scaling (can be overridden by loaded profile)
        apply_timeout_scale(1.0)
    registry = hass.data["ramses_extras"]

    if "device_simulator_db" not in registry:
        registry["device_simulator_db"] = DeviceDatabase()
        await hass.async_add_executor_job(registry["device_simulator_db"].load_all)

    if "device_simulator_endpoint" not in registry:
        registry["device_simulator_endpoint"] = MqttEndpoint(
            hass, topic_base=SIMULATOR_TOPIC_NS
        )
        await registry["device_simulator_endpoint"].async_connect()

        # Send an initial HGI presence packet to announce the gateway
        # The retained online status (published by MqttEndpoint) triggers ramses_cc
        # binding
        hgi_device_id = SIMULATOR_HGI_ID  # 18:001234
        dst = "--:------"  # Broadcast
        code = "0005"  # HGI presence announcement packet
        payload = "0005DC0101F40205DC"  # HGI presence payload
        payload_len = len(payload) // 2  # 9 bytes
        # Format: RSSI(3) + space + VERB(2) + space + --- + SRC DST HGI code + len
        # Note: VERB is 2 chars (' I' = space + I), so we need 2 spaces after RSSI
        initial_frame = (
            f"040  I --- {hgi_device_id} {dst} --:------ {code} "
            f"{payload_len:03d} {payload}"
        )

        try:
            await registry["device_simulator_endpoint"].send_packet(initial_frame)
            _LOGGER.info("Sent initial HGI presence packet: %s", initial_frame)
        except Exception as err:
            _LOGGER.error("Failed to send initial HGI packet: %s", err)

    if "device_simulator_response_engine" not in registry:
        registry["device_simulator_response_engine"] = ResponseEngine(
            registry["device_simulator_db"],
            registry["device_simulator_endpoint"],
        )
        # Wire up response engine to handle inbound frames
        registry["device_simulator_endpoint"]._inbound_handler = registry[
            "device_simulator_response_engine"
        ].handle_inbound_frame

    if "device_simulator_periodic_emitter" not in registry:
        registry["device_simulator_periodic_emitter"] = PeriodicEmitter(
            registry["device_simulator_db"],
            registry["device_simulator_endpoint"],
        )
        await registry["device_simulator_periodic_emitter"].start()

    if "device_simulator_engine" not in registry:
        registry["device_simulator_engine"] = ScenarioEngine(
            hass,
            registry["device_simulator_endpoint"],
            registry["device_simulator_db"],
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
def load_feature(hass: "HomeAssistant", config_entry: "ConfigEntry") -> dict[str, Any]:
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
