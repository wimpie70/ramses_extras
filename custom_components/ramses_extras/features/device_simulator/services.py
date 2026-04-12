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

from custom_components.ramses_extras.const import DOMAIN as INTEGRATION_DOMAIN

from .const import (
    LOGGER,
    SCENARIO_AUTONOMOUS_EMISSIONS,
    SCENARIO_DEVICE_PLAYBACK,
    SCENARIO_DEVICE_SUITE,
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_DISCOVERY_TEST,
    SCENARIO_FLOODING_TEST,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_RUN_CONVERSATION,
    SCENARIO_TIMEOUT_TEST,
)
from .scenario_engine import ActiveDevice, ScenarioEngine
from .system_config import SIM_DEVICE_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SERVICE_INJECT_MESSAGE = "device_simulator_inject_message"
SERVICE_RUN_SCENARIO = "device_simulator_run_scenario"
SERVICE_STOP_SCENARIO = "device_simulator_stop_scenario"
SERVICE_ACTIVATE_DEVICE = "device_simulator_activate_device"
SERVICE_SILENCE_DEVICE = "device_simulator_silence_device"
SERVICE_RUN_CONVERSATION = "device_simulator_run_conversation"
SERVICE_IMPORT_USER_CONFIG = "device_simulator_import_user_config"

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
                SCENARIO_AUTONOMOUS_EMISSIONS,
                SCENARIO_DEVICE_PLAYBACK,
                SCENARIO_DEVICE_SUITE,
                SCENARIO_DEVICE_UNAVAILABILITY,
                SCENARIO_HVAC_DEVICE_LOSS,
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
        vol.Optional("device_id"): str,  # For stopping specific device emissions
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

        scenario_type = call.data["scenario_type"]
        params = call.data.get("params", {})

        if scenario_type == SCENARIO_AUTONOMOUS_EMISSIONS:
            # Start autonomous I frame emissions (e.g., for device discovery)
            device_id = params.get("device_id", SIM_DEVICE_ID["FAN"])
            device_type = params.get("device_type", "FAN")
            variant_id = params.get("variant_id", "default")
            # Default to silencing 1FC9 unless explicitly requested
            excluded_codes = params.get("excluded_codes")
            if excluded_codes is None:
                excluded_codes = ["1FC9"]

            device = ActiveDevice(
                device_id=device_id,
                slug=device_type,
                variant_id=variant_id,
                excluded_codes=excluded_codes,
                suppress_autonomous=False,  # Enable autonomous
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

        if scenario_type == SCENARIO_DEVICE_PLAYBACK:
            # Playback device messages from packet log
            log_file = params.get("log_file")
            if not log_file:
                return {"success": False, "error": "Missing log_file param"}
            return await engine.async_run_device_playback(log_file, params)

        if scenario_type == SCENARIO_DEVICE_SUITE:
            # Run a suite of standard device tests
            slugs = params.get("slugs", ["FAN", "REM", "CO2"])
            duration = params.get("duration", 300)
            return await engine.async_run_device_suite(slugs, duration)

        if scenario_type == SCENARIO_DISCOVERY_TEST:
            # Test device discovery by simulating new devices
            return await engine.async_run_discovery_test(params)

        if scenario_type == SCENARIO_TIMEOUT_TEST:
            # Test timeout handling with slow responses
            delay = params.get("delay", 10.0)
            return await engine.async_run_timeout_test(delay)

        if scenario_type == SCENARIO_FLOODING_TEST:
            # Test flooding/burst message handling
            count = params.get("count", 100)
            interval = params.get("interval", 0.1)
            return await engine.async_run_flooding_test(count, interval)

        if scenario_type == SCENARIO_DEVICE_UNAVAILABILITY:
            return await engine.async_run_unavailability_test(
                device_id=params.get("device_id"),
                silence_after=float(params.get("silence_after", 30.0)),
                resume_after=float(params.get("resume_after", 60.0)),
            )

        if scenario_type == SCENARIO_HVAC_DEVICE_LOSS:
            device_id = params.get("device_id")
            if not device_id:
                return {"success": False, "error": "Missing device_id param"}
            restore = params.get("restore_after")
            return await engine.async_run_hvac_device_loss(
                device_id=device_id,
                loss_after=float(params.get("loss_after", 30.0)),
                restore_after=float(restore) if restore is not None else None,
            )

        return {"success": False, "error": f"Unknown scenario type: {scenario_type}"}

    async def handle_stop_scenario(call: ServiceCall) -> dict[str, Any]:
        """Stop a scenario."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        scenario_id = call.data.get("scenario_id", "")
        device_id = call.data.get("device_id")

        # Handle autonomous_emissions scenario stop
        if scenario_id == SCENARIO_AUTONOMOUS_EMISSIONS or device_id:
            target_device = device_id or SIM_DEVICE_ID["FAN"]
            await engine.async_silence_device(target_device)
            return {
                "success": True,
                "message": f"Autonomous emissions stopped for {target_device}",
            }

        # Cancel timed scenarios by id
        if scenario_id in (SCENARIO_DEVICE_UNAVAILABILITY, SCENARIO_HVAC_DEVICE_LOSS):
            await engine.async_cancel_scenario(scenario_id)
            return {"success": True, "message": f"Scenario '{scenario_id}' cancelled"}

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
        from pathlib import Path

        import yaml

        source = call.data["source"]
        name = call.data["name"]
        attach_log = call.data.get("attach_log")

        try:
            # Load ramses_cc config
            config_path = Path(source)
            if not config_path.exists():
                return {"success": False, "error": f"Config file not found: {source}"}

            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # Normalise v1 vs v2 ramses_cc config entry format.
            # v2 (>=0.56.3): known_list is top-level in options.
            # v1 (<0.56.3):  known_list was nested under ramses_rf.
            known_list: dict = (
                config.get("known_list")
                or config.get("ramses_rf", {}).get("known_list")
                or {}
            )
            schema: dict = config.get("schema") or {}
            enforce_known_list: bool = bool(
                config.get("ramses_rf", {}).get("enforce_known_list", False)
            )

            # Create profile structure
            profile = {
                "name": name,
                "source_config": str(config_path),
                "imported_at": str(hass.loop.time()),
                "config": config,
                "known_list": known_list,
                "schema": schema,
                "enforce_known_list": enforce_known_list,
                "config_version": 2 if "known_list" in config else 1,
                "attached_log": attach_log,
            }

            # Store profile in hass.data for later use
            profiles = hass.data.get("ramses_extras", {}).setdefault(
                "device_simulator_profiles", {}
            )
            profiles[name] = profile

            LOGGER.info(
                "Imported profile '%s' from %s (config v%s, %d devices)",
                name,
                source,
                profile["config_version"],
                len(known_list),
            )
            return {
                "success": True,
                "profile_name": name,
                "config_version": profile["config_version"],
                "known_devices": len(known_list),
                "has_log": attach_log is not None,
            }

        except Exception as err:
            LOGGER.error("Failed to import profile: %s", err)
            return {"success": False, "error": str(err)}

    # Register services under ramses_extras domain (not device_simulator)
    # to avoid "IntegrationNotFound: device_simulator" errors
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_INJECT_MESSAGE,
        handle_inject_message,
        schema=SCHEMA_INJECT_MESSAGE,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_RUN_SCENARIO,
        handle_run_scenario,
        schema=SCHEMA_RUN_SCENARIO,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_STOP_SCENARIO,
        handle_stop_scenario,
        schema=SCHEMA_STOP_SCENARIO,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_ACTIVATE_DEVICE,
        handle_activate_device,
        schema=SCHEMA_ACTIVATE_DEVICE,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_SILENCE_DEVICE,
        handle_silence_device,
        schema=SCHEMA_SILENCE_DEVICE,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_RUN_CONVERSATION,
        handle_run_conversation,
        schema=SCHEMA_RUN_CONVERSATION,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
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
        hass.services.async_remove(INTEGRATION_DOMAIN, service)
