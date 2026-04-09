# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Device Simulator feature.

Simulates RAMSES devices at the communication endpoint (MQTT or serial),
allowing testing without physical RF hardware.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

import logging

_LOGGER = logging.getLogger(__name__)


async def async_create_device_simulator_feature(
    hass: "HomeAssistant",
    config_entry: "ConfigEntry",
) -> dict[str, Any]:
    """Factory function to create the Device Simulator feature.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry
    :return: Feature descriptor dict
    """
    from .comm_endpoint import MqttEndpoint
    from .device_db import DeviceDatabase
    from .scenario_engine import ScenarioEngine
    from .services import async_setup_services
    from .websocket import async_register_websocket_commands

    hass.data.setdefault("ramses_extras", {})
    registry = hass.data["ramses_extras"]

    if "device_simulator_db" not in registry:
        registry["device_simulator_db"] = DeviceDatabase()
        registry["device_simulator_db"].load_all()

    if "device_simulator_endpoint" not in registry:
        registry["device_simulator_endpoint"] = MqttEndpoint(hass)
        await registry["device_simulator_endpoint"].async_connect()

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
        "engine": registry["device_simulator_engine"],
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
    # Schedule async setup
    hass.async_create_task(async_create_device_simulator_feature(hass, config_entry))

    # Return a minimal descriptor; the async task will complete the setup
    return {
        "feature_name": "device_simulator",
        "services_module": "services",
        "websocket_commands_module": "websocket",
    }


__all__ = ["async_create_device_simulator_feature", "load_feature"]
