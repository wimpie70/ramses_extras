# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Services for Device Simulator.

Provides HA service calls for programmatic control:
  - inject_message: send a single custom packet
  - run_scenario: start a named scenario
  - stop_scenario: stop a running scenario
  - activate_device: add a device to the simulation
  - silence_device: stop a device's autonomous emission
  - run_conversation: play a conversation block
  - import_user_config: import ramses_cc config + packet log
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import ServiceCall

from .const import (
    DOMAIN,
    LOGGER,
    SCENARIO_DEVICE_PLAYBACK,
    SCENARIO_DEVICE_SUITE,
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_DISCOVERY_TEST,
    SCENARIO_FLOODING_TEST,
    SCENARIO_RUN_CONVERSATION,
    SCENARIO_TIMEOUT_TEST,
)
from .scenario_engine import ActiveDevice, ScenarioEngine

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SERVICE_INJECT_MESSAGE = "inject_message"
SERVICE_RUN_SCENARIO = "run_scenario"
SERVICE_STOP_SCENARIO = "stop_scenario"
SERVICE_ACTIVATE_DEVICE = "activate_device"
SERVICE_SILENCE_DEVICE = "silence_device"
SERVICE_RUN_CONVERSATION = "run_conversation"
SERVICE_IMPORT_USER_CONFIG = "import_user_config"

SCHEMA_INJECT_MESSAGE = vol.Schema(
    {
        vol.Required("source_id"): str,
        vol.Required("code"): str,
        vol.Required("payload"): str,
        vol.Optional("dst", default="--:------"): str,
        vol.Optional("verb", default="I"): str,
    }
)

SCHEMA_RUN_SCENARIO = vol.Schema(
    {
        vol.Required("scenario_type"): vol.In(
            [
                SCENARIO_DEVICE_PLAYBACK,
                SCENARIO_DEVICE_SUITE,
                SCENARIO_DEVICE_UNAVAILABILITY,
                SCENARIO_DISCOVERY_TEST,
                SCENARIO_FLOODING_TEST,
                SCENARIO_TIMEOUT_TEST,
            ]
        ),
        vol.Optional("params", default={}): dict,
    }
)

SCHEMA_STOP_SCENARIO = vol.Schema(
    {
        vol.Required("scenario_id"): str,
    }
)

SCHEMA_ACTIVATE_DEVICE = vol.Schema(
    {
        vol.Required("device_id"): str,
        vol.Required("slug"): str,
        vol.Optional("variant_id"): str,
        vol.Optional("excluded_codes", default=[]): list,
        vol.Optional("suppress_autonomous", default=False): bool,
        vol.Optional("suppress_responses", default=False): bool,
        vol.Optional("enabled", default=True): bool,
    }
)

SCHEMA_SILENCE_DEVICE = vol.Schema(
    {
        vol.Required("device_id"): str,
    }
)

SCHEMA_RUN_CONVERSATION = vol.Schema(
    {
        vol.Required("ref"): str,
        vol.Required("device_map"): dict,
        vol.Optional("scheme"): str,
        vol.Optional("speed", default=1.0): vol.Coerce(float),
    }
)

SCHEMA_IMPORT_USER_CONFIG = vol.Schema(
    {
        vol.Required("source"): str,
        vol.Required("name"): str,
        vol.Optional("attach_log"): str,
    }
)


def _get_engine(hass: HomeAssistant) -> ScenarioEngine | None:
    """Get the scenario engine from hass data."""
    from typing import cast

    registry = hass.data.get("ramses_extras", {})
    return cast(ScenarioEngine | None, registry.get("device_simulator_engine"))


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Device Simulator services."""

    async def handle_inject_message(call: ServiceCall) -> dict[str, Any]:
        """Inject a single message."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        packet = engine._build_packet(
            call.data["source_id"],
            call.data["dst"],
            call.data["verb"],
            call.data["code"],
            call.data["payload"],
        )
        try:
            await engine._endpoint.send_packet(packet)
            return {"success": True}
        except Exception as err:
            return {"success": False, "error": str(err)}

    async def handle_run_scenario(call: ServiceCall) -> dict[str, Any]:
        """Run a scenario."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        # TODO: Implement full scenario runners
        return {"success": True, "message": "Scenario stub - needs implementation"}

    async def handle_stop_scenario(call: ServiceCall) -> dict[str, Any]:
        """Stop a scenario."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        # TODO: Track scenarios by ID
        return {"success": True}

    async def handle_activate_device(call: ServiceCall) -> dict[str, Any]:
        """Activate a device in the simulation."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        device = ActiveDevice(
            device_id=call.data["device_id"],
            slug=call.data["slug"],
            variant_id=call.data.get("variant_id"),
            excluded_codes=call.data.get("excluded_codes", []),
            suppress_autonomous=call.data.get("suppress_autonomous", False),
            suppress_responses=call.data.get("suppress_responses", False),
            enabled=call.data.get("enabled", True),
        )
        await engine.async_activate_device(device)
        return {"success": True, "device_id": device.device_id}

    async def handle_silence_device(call: ServiceCall) -> dict[str, Any]:
        """Silence a device (stop autonomous emission)."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        await engine.async_silence_device(call.data["device_id"])
        return {"success": True}

    async def handle_run_conversation(call: ServiceCall) -> dict[str, Any]:
        """Run a conversation block."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        result = await engine.async_play_conversation(
            ref=call.data["ref"],
            device_map=call.data["device_map"],
            scheme=call.data.get("scheme"),
            speed=call.data.get("speed", 1.0),
        )
        return {
            "success": result.success,
            "messages_sent": result.messages_sent,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors,
        }

    async def handle_import_user_config(call: ServiceCall) -> dict[str, Any]:
        """Import a user's ramses_cc config + packet log as a profile."""
        # TODO: Implement config profile import
        return {"success": False, "error": "Not implemented"}

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_INJECT_MESSAGE,
        handle_inject_message,
        schema=SCHEMA_INJECT_MESSAGE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_SCENARIO,
        handle_run_scenario,
        schema=SCHEMA_RUN_SCENARIO,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_SCENARIO,
        handle_stop_scenario,
        schema=SCHEMA_STOP_SCENARIO,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE_DEVICE,
        handle_activate_device,
        schema=SCHEMA_ACTIVATE_DEVICE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SILENCE_DEVICE,
        handle_silence_device,
        schema=SCHEMA_SILENCE_DEVICE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_CONVERSATION,
        handle_run_conversation,
        schema=SCHEMA_RUN_CONVERSATION,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_USER_CONFIG,
        handle_import_user_config,
        schema=SCHEMA_IMPORT_USER_CONFIG,
    )

    LOGGER.debug("Device Simulator services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove Device Simulator services."""
    for service in (
        SERVICE_INJECT_MESSAGE,
        SERVICE_RUN_SCENARIO,
        SERVICE_STOP_SCENARIO,
        SERVICE_ACTIVATE_DEVICE,
        SERVICE_SILENCE_DEVICE,
        SERVICE_RUN_CONVERSATION,
        SERVICE_IMPORT_USER_CONFIG,
    ):
        hass.services.async_remove(DOMAIN, service)
