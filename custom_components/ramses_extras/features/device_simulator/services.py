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
  - import_user_config: import ramses_cc config + packet log
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import ServiceCall

from custom_components.ramses_extras.const import DOMAIN as INTEGRATION_DOMAIN

from .const import (
    LOGGER,
    SCENARIO_DEVICE_PLAYBACK,
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_DISCOVERY_TEST,
    SCENARIO_FLOODING_TEST,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_LOAD_PROFILE_YAML,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PROFILE_EMISSIONS,
    SCENARIO_TIMEOUT_TEST,
)
from .profile_loader import async_apply_profile, build_profile_from_yaml
from .scenario_engine import ActiveDevice, ScenarioEngine
from .system_config import (
    SIM_DEVICE_ID,
    ConfigProfileStore,
    SystemConfigProfile,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SERVICE_INJECT_MESSAGE = "device_simulator_inject_message"
SERVICE_RUN_SCENARIO = "device_simulator_run_scenario"
SERVICE_STOP_SCENARIO = "device_simulator_stop_scenario"
SERVICE_ACTIVATE_DEVICE = "device_simulator_activate_device"
SERVICE_SILENCE_DEVICE = "device_simulator_silence_device"
SERVICE_RESUME_DEVICE = "device_simulator_resume_device"
SERVICE_RESUME_ALL = "device_simulator_resume_all"
SERVICE_IMPORT_USER_CONFIG = "device_simulator_import_user_config"
SERVICE_IMPORT_USER_LOG = "device_simulator_import_user_log"

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
                SCENARIO_MANUAL_DEVICE_INJECTION,
                SCENARIO_LOAD_PROFILE_YAML,
                SCENARIO_PROFILE_EMISSIONS,
                SCENARIO_DEVICE_PLAYBACK,
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

SCHEMA_RESUME_DEVICE = vol.Schema(
    {
        vol.Required("device_id"): str,
    }
)

SCHEMA_RESUME_ALL = vol.Schema({})

SCHEMA_IMPORT_USER_CONFIG = vol.Schema(
    {
        vol.Required("source"): str,
        vol.Required("name"): str,
        vol.Optional("attach_log"): str,
    }
)

SCHEMA_IMPORT_USER_LOG = vol.Schema(
    {
        vol.Optional("path"): str,
        vol.Required("name"): str,
        vol.Optional("content"): str,
        vol.Optional("save_yaml", default=True): bool,
    }
)


def _get_engine(hass: HomeAssistant) -> ScenarioEngine | None:
    """Get the scenario engine from hass data."""
    from typing import cast

    registry = hass.data.get("ramses_extras", {})
    return cast(ScenarioEngine | None, registry.get("device_simulator_engine"))


def _get_config_store(hass: HomeAssistant) -> ConfigProfileStore | None:
    """Get the config profile store from hass data."""
    from typing import cast

    from .system_config import ConfigProfileStore

    registry = hass.data.get("ramses_extras", {})
    return cast(
        ConfigProfileStore | None, registry.get("device_simulator_config_store")
    )


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

        if scenario_type == SCENARIO_MANUAL_DEVICE_INJECTION:
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
                origin="manual",
            )
            await engine.async_activate_device(device)
            return {
                "success": True,
                "scenario_id": SCENARIO_MANUAL_DEVICE_INJECTION,
                "device_id": device_id,
                "message": f"Manual device injection started for {device_id}",
            }

        if scenario_type == SCENARIO_LOAD_PROFILE_YAML:
            config_store = _get_config_store(hass)
            if not config_store:
                return {"success": False, "error": "Profile store not available"}

            yaml_blob = params.get("profile_yaml")
            if not yaml_blob:
                return {"success": False, "error": "profile_yaml param is required"}

            profile_name = (params.get("profile_name") or "imported_profile").strip()
            if not profile_name:
                profile_name = "imported_profile"

            try:
                profile = build_profile_from_yaml(profile_name, yaml_blob)
            except ValueError as err:
                return {"success": False, "error": str(err)}

            config_store.save_profile(profile)
            config_store.set_active_profile(profile.name)
            await config_store.async_save_state()

            ra = hass.data.setdefault("ramses_extras", {})
            ra["device_simulator_active_profile"] = profile.name

            try:
                result = await async_apply_profile(
                    hass,
                    profile_name=profile.name,
                    profile=profile,
                    reload_ramses_cc=params.get("reload_ramses", True),
                    speed=params.get("speed"),
                    auto_start_devices=False,
                )
            except Exception as err:  # noqa: BLE001
                return {"success": False, "error": str(err)}

            result.setdefault("started_devices", 0)
            result.setdefault(
                "message",
                "Profile applied. Use the profile emissions scenario to start devices.",
            )

            return result

        if scenario_type == SCENARIO_PROFILE_EMISSIONS:
            config_store = _get_config_store(hass)
            if not config_store:
                return {"success": False, "error": "Profile store not available"}
            active_profile_name = config_store.get_active_profile()
            if not active_profile_name:
                return {
                    "success": False,
                    "error": "Load a simulator profile before starting "
                    "profile emissions",
                }
            active_profile: SystemConfigProfile | None = config_store.get_profile(
                active_profile_name
            )
            if not active_profile:
                return {
                    "success": False,
                    "error": "Active profile is missing or invalid",
                }
            if engine.is_scenario_running(SCENARIO_PROFILE_EMISSIONS):
                return {
                    "success": False,
                    "error": "Profile device emissions are already running",
                }
            conflicts = engine.check_scenario_conflicts(SCENARIO_PROFILE_EMISSIONS)
            if conflicts:
                return {
                    "success": False,
                    "error": "Conflicts with running scenarios: "
                    + ", ".join(conflicts),
                }
            profile_devices = engine.build_profile_devices(active_profile)
            if not profile_devices:
                return {
                    "success": False,
                    "error": "Active profile does not define any devices",
                }
            started_ids: list[str] = []
            for device in profile_devices:
                await engine.async_activate_device(device)
                started_ids.append(device.device_id)
            engine.set_running_metadata(
                SCENARIO_PROFILE_EMISSIONS,
                {"profile": active_profile_name, "devices": started_ids},
            )
            return {
                "success": True,
                "scenario_id": SCENARIO_PROFILE_EMISSIONS,
                "message": f"Started profile devices ({len(started_ids)})",
            }

        if engine.has_scenario_definition(scenario_type):
            return await engine.async_run_registered_scenario(scenario_type, params)

        return {"success": False, "error": f"Unknown scenario type: {scenario_type}"}

    async def handle_stop_scenario(call: ServiceCall) -> dict[str, Any]:
        """Stop a scenario."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        scenario_id = call.data.get("scenario_id", "")
        device_id = call.data.get("device_id")

        # Handle autonomous_emissions scenario stop
        if scenario_id == SCENARIO_MANUAL_DEVICE_INJECTION or device_id:
            target_id = device_id
            if target_id and not engine.is_manual_device(target_id):
                return {
                    "success": False,
                    "error": f"Device '{target_id}' is not a manual injection",
                }
            if target_id:
                await engine.async_stop_manual_devices(target_id)
                return {
                    "success": True,
                    "message": f"Manual device injection stopped for {target_id}",
                }
            await engine.async_stop_manual_devices()
            return {
                "success": True,
                "message": "Manual device injections stopped",
            }

        if scenario_id == SCENARIO_PROFILE_EMISSIONS:
            await engine.async_stop_profile_devices()
            engine.clear_running_metadata(SCENARIO_PROFILE_EMISSIONS)
            return {
                "success": True,
                "message": "Profile device emissions stopped",
            }

        if scenario_id:
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

    async def handle_resume_device(call: ServiceCall) -> dict[str, Any]:
        """Resume a device (start autonomous emission)."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        await engine.async_resume_device(call.data["device_id"])
        return {"success": True}

    async def handle_resume_all(call: ServiceCall) -> dict[str, Any]:
        """Resume all active devices (start autonomous emission)."""
        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        await engine.async_resume_all()
        return {"success": True}

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

    async def handle_import_user_log(call: ServiceCall) -> dict[str, Any]:
        """Import a user's ramses.log file as a conversation for playback."""
        from pathlib import Path

        path = call.data.get("path")
        name = call.data["name"]
        content = call.data.get("content")
        save_yaml = call.data.get("save_yaml", True)

        engine = _get_engine(hass)
        if not engine:
            return {"success": False, "error": "Engine not available"}

        db = engine.device_db
        if not db:
            return {"success": False, "error": "Device database not available"}

        # Import the log file (from path or content) and persist by default
        success = await db.import_user_log(path, name, content, save_yaml=save_yaml)
        if success:
            return {
                "success": True,
                "conversation_name": name,
                "message": f"Imported log as conversation '{name}'",
            }
        return {"success": False, "error": "Failed to import log"}

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
        SERVICE_RESUME_DEVICE,
        handle_resume_device,
        schema=SCHEMA_RESUME_DEVICE,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_RESUME_ALL,
        handle_resume_all,
        schema=SCHEMA_RESUME_ALL,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_IMPORT_USER_CONFIG,
        handle_import_user_config,
        schema=SCHEMA_IMPORT_USER_CONFIG,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_IMPORT_USER_LOG,
        handle_import_user_log,
        schema=SCHEMA_IMPORT_USER_LOG,
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
        SERVICE_RESUME_DEVICE,
        SERVICE_RESUME_ALL,
        SERVICE_IMPORT_USER_CONFIG,
        SERVICE_IMPORT_USER_LOG,
    ):
        hass.services.async_remove(INTEGRATION_DOMAIN, service)
