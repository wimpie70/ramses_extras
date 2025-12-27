"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    DOMAIN,
    PLATFORM_REGISTRY,
    register_feature_platform,
)

# Import CardRegistry for simplified card registration
from .framework.helpers.card_registry import CardRegistry
from .framework.helpers.paths import DEPLOYMENT_PATHS, PathConstants

# Since this integration can only be set up from config entries,
# use the config_entry_only_config_schema to avoid the warning
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).parent
_setup_in_progress = False


async def _import_module_in_executor(module_path: str) -> Any:
    """Import module in executor to avoid blocking event loop."""
    import asyncio

    def _do_import() -> Any:
        return importlib.import_module(module_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_import)


async def _handle_startup_event(
    event: Event, hass: HomeAssistant, config: ConfigType
) -> None:
    """Handle Home Assistant startup event."""
    # This will only be called if the user has Ramses Extras configured
    # from a YAML file. If configured via UI, async_setup_entry will handle it.
    _LOGGER.info("Starting Ramses Extras from YAML configuration")

    await async_setup_yaml_config(hass, config)


# Component will be loaded when hass starts up.
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras integration from YAML configuration."""

    # Use module-level function with explicit parameters to avoid closure issues
    # and thread-safe execution using run_coroutine_threadsafe
    def _startup_callback(event: Event) -> None:
        """Thread-safe callback for startup event."""
        import asyncio

        # Use run_coroutine_threadsafe for thread safety
        asyncio.run_coroutine_threadsafe(
            _handle_startup_event(event, hass, config), hass.loop
        )

    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _startup_callback)

    return True


async def async_setup_yaml_config(hass: HomeAssistant, config: ConfigType) -> None:
    """Set up Ramses Extras from YAML config if present."""

    yaml_config = config.get(DOMAIN, {})
    if not yaml_config:
        return

    try:
        _LOGGER.info("Setting up Ramses Extras from YAML configuration...")

        # Create a config entry from YAML for the integrations to use
        entry_data = {
            "yaml": True,
            "enabled_features": yaml_config.get("enabled_features", {}),
        }

        # Note: This will trigger the normal setup flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "yaml"},
                data=entry_data,
            )
        )

    except Exception:
        _LOGGER.exception("Failed to set up Ramses Extras from YAML")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry for Ramses Extras."""
    _LOGGER.info("Starting Ramses Extras integration setup...")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})
    hass.data[DOMAIN]["PLATFORM_REGISTRY"] = (
        PLATFORM_REGISTRY  # Make registry available to platforms
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.debug("Enabled features: %s", entry.data.get("enabled_features", {}))

    async def _load_feature_definitions_and_platforms(
        hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Load feature definitions, platforms, and WebSocket modules.

        This is the single authoritative place for loading:
        - Feature definitions (via load_feature)
        - Platform registrations (via async_forward_entry_setups)
        - WebSocket integration (via async_setup_websocket_integration)
        """
        from .extras_registry import extras_registry

        # Load default feature definitions
        from .features.default.commands import register_default_commands
        from .features.default.const import load_feature

        load_feature()
        register_default_commands()

        # Load enabled feature definitions
        enabled_features_dict = entry.data.get("enabled_features", {})
        enabled_feature_names = [
            name for name, enabled in enabled_features_dict.items() if enabled
        ]

        _LOGGER.info(
            "Loading definitions from %d enabled features: %s",
            len(enabled_feature_names),
            enabled_feature_names,
        )

        for feature_name in enabled_feature_names:
            try:
                module_name = (
                    f"custom_components.ramses_extras.features.{feature_name}.const"
                )
                feature_module = __import__(module_name, fromlist=["load_feature"])

                if hasattr(feature_module, "load_feature"):
                    feature_module.load_feature()
                    _LOGGER.debug("Loaded %s feature definitions", feature_name)
                else:
                    _LOGGER.warning(
                        "Feature '%s' has no load_feature function", feature_name
                    )

                # Import platform modules to trigger registration
                if feature_name == "default":
                    # Default feature has platforms in subdirectories
                    try:
                        __import__(
                            "custom_components.ramses_extras.features.default.platforms.sensor"
                        )
                    except ImportError:
                        pass
                    try:
                        __import__(
                            "custom_components.ramses_extras.features.default.platforms.switch"
                        )
                    except ImportError:
                        pass
                    try:
                        __import__(
                            "custom_components.ramses_extras.features.default.platforms.binary_sensor"
                        )
                    except ImportError:
                        pass
                    try:
                        __import__(
                            "custom_components.ramses_extras.features.default.platforms.number"
                        )
                    except ImportError:
                        pass
                else:
                    # Other features use standard platform module structure
                    platform_module_name = (
                        f"custom_components.ramses_extras.features."
                        f"{feature_name}.platform"
                    )
                    try:
                        __import__(platform_module_name)
                    except ImportError:
                        pass

            except ImportError as e:
                _LOGGER.warning("Failed to load feature '%s': %s", feature_name, e)

        # CRITICAL: Discover devices BEFORE setting up platforms
        await _discover_and_store_devices(hass)

        # Forward the setup to the sensor, switch, etc. platforms
        await hass.config_entries.async_forward_entry_setups(
            entry,
            [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.NUMBER],
        )

        # Register WebSocket commands for features
        await _setup_websocket_integration(hass)

        # Log loaded definitions for verification
        sensor_count = len(extras_registry.get_all_sensor_configs())
        switch_count = len(extras_registry.get_all_switch_configs())
        number_count = len(extras_registry.get_all_number_configs())
        boolean_count = len(extras_registry.get_all_boolean_configs())
        _LOGGER.info(
            "Entity registry loaded: %d sensor, %d switch, %d number, %d binary sensor",
            sensor_count,
            switch_count,
            number_count,
            boolean_count,
        )

    await _load_feature_definitions_and_platforms(hass, entry)

    _LOGGER.debug("WebSocket functionality uses feature-centric architecture")

    # ALWAYS register all card resources at startup using CardRegistry
    # This ensures cards are available before Lovelace parses dashboards
    await _register_cards(hass)

    # Copy helper files and expose feature config for card functionality
    await _setup_card_files_and_config(hass, entry)

    # Register services before setting up platforms
    await _register_services(hass)

    # Continue with additional platform setup if needed
    await async_setup_platforms(hass)

    # STEP: Post-creation validation with SimpleEntityManager
    await _validate_startup_entities_simple(hass, entry)

    # Explicitly create and start feature instances for
    #  enabled features (including default)
    features = hass.data[DOMAIN].setdefault("features", {})
    feature_ready = hass.data[DOMAIN].setdefault("feature_ready", {})
    hass.data[DOMAIN].setdefault("cards_enabled", False)
    hass.data[DOMAIN]["cards_pending_features"] = set()
    enabled_features = entry.data.get("enabled_features") or entry.options.get(
        "enabled_features"
    )
    if not isinstance(enabled_features, dict):
        enabled_features = {}
    enabled_feature_names = [k for k, v in enabled_features.items() if v is True]
    # Always include default
    if "default" not in enabled_feature_names:
        enabled_feature_names.append("default")
    import importlib

    automation_managers_to_start: list[Any] = []
    cards_pending_features: set[str] = set()

    @callback  # type: ignore[untyped-decorator]
    def _on_feature_ready(event: Event[dict[str, Any]]) -> None:
        feature_id = event.data.get("feature_id")
        if not isinstance(feature_id, str):
            return

        pending = hass.data.get(DOMAIN, {}).get("cards_pending_features")
        if not isinstance(pending, set):
            return

        if feature_id not in pending:
            return

        pending.discard(feature_id)

        _LOGGER.debug(
            "Cards latch: received feature_ready for %s, remaining pending=%s",
            feature_id,
            sorted(pending),
        )

        if pending:
            return

        if hass.data[DOMAIN].get("cards_enabled") is True:
            return

        hass.data[DOMAIN]["cards_enabled"] = True
        _LOGGER.debug("Cards latch: cards_enabled=True")
        hass.bus.async_fire("ramses_extras_cards_enabled", {})

    hass.data[DOMAIN]["cards_pending_features"] = cards_pending_features

    existing_unsub = hass.data[DOMAIN].get("_cards_enabled_unsub")
    if callable(existing_unsub):
        existing_unsub()

    hass.data[DOMAIN]["_cards_enabled_unsub"] = hass.bus.async_listen(
        "ramses_extras_feature_ready", _on_feature_ready
    )

    for feature_name in enabled_feature_names:
        if feature_name in features:
            continue  # Already created
        try:
            feature_module_name = (
                f"custom_components.ramses_extras.features.{feature_name}"
            )
            # Run the blocking import operation in a thread pool
            feature_module = await asyncio.to_thread(
                importlib.import_module, feature_module_name
            )
            # Create feature instance if create function exists
            create_func_name = f"create_{feature_name.replace('-', '_')}_feature"
            if hasattr(feature_module, create_func_name):
                create_feature_func = getattr(feature_module, create_func_name)
                # Handle both sync and async create functions

                if asyncio.iscoroutinefunction(create_feature_func):
                    feature_instance = await create_feature_func(hass, entry)
                else:
                    feature_instance = create_feature_func(hass, entry)

                # Start the automation manager if it exists in the feature instance
                automation_manager = None
                if isinstance(feature_instance, dict):
                    automation_manager = feature_instance.get("automation")

                if automation_manager:
                    feature_ready.setdefault(feature_name, False)
                    cards_pending_features.add(feature_name)
                    if not automation_manager.is_automation_active():
                        automation_managers_to_start.append(automation_manager)
                else:
                    feature_ready[feature_name] = True
                    hass.bus.async_fire(
                        "ramses_extras_feature_ready", {"feature_id": feature_name}
                    )

                features[feature_name] = feature_instance
                _LOGGER.info("Created feature instance: %s", feature_name)
        except Exception as e:
            _LOGGER.warning(
                "Failed to create feature instance '%s': %s", feature_name, e
            )

    if not cards_pending_features:
        hass.data[DOMAIN]["cards_enabled"] = True
        _LOGGER.debug("Cards latch: cards_enabled=True (no pending automations)")
        hass.bus.async_fire("ramses_extras_cards_enabled", {})

    for automation_manager in automation_managers_to_start:
        hass.async_create_task(automation_manager.start())

    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    _LOGGER.info("Registering Ramses Extras services")

    from .features.default.services import async_setup_services

    await async_setup_services(hass)


async def _setup_websocket_integration(hass: HomeAssistant) -> None:
    """Set up WebSocket integration for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    try:
        from .websocket_integration import async_setup_websocket_integration

        success = await async_setup_websocket_integration(hass)
        if success:
            _LOGGER.info("WebSocket integration setup complete")
        else:
            _LOGGER.warning("WebSocket integration setup failed")

    except Exception as error:
        _LOGGER.error("Error setting up WebSocket integration: %s", error)
        # Don't fail the entire integration if WebSocket setup fails


# Legacy functions removed - CardRegistry handles all card registration
# Legacy function removed - CardRegistry handles all card registration


async def _expose_feature_config_to_frontend(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Expose feature configuration to frontend JavaScript for card feature toggles."""
    try:
        _LOGGER.info("Exposing feature configuration to frontend...")

        # Get enabled features from the entry
        enabled_features = (
            entry.data.get("enabled_features")
            or entry.options.get("enabled_features")
            or {}
        )

        # Use json.dumps to properly convert Python values to JavaScript
        import json

        js_enabled_features = json.dumps(enabled_features, indent=2)

        js_content = f"""// Ramses Extras Feature Configuration
// Auto-generated during integration setup
window.ramsesExtras = window.ramsesExtras || {{}};
window.ramsesExtras.features = {js_enabled_features};

// Log feature configuration for debugging
console.log('Ramses Extras features loaded:', window.ramsesExtras.features);
"""

        # Write the JavaScript file to the helpers directory
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir
        )
        feature_config_file = destination_helpers_dir / "ramses-extras-features.js"

        # Write the file
        await asyncio.to_thread(feature_config_file.write_text, js_content)

        _LOGGER.info(
            "Feature configuration exposed to frontend: %s", feature_config_file
        )

    except Exception as e:
        _LOGGER.error("Failed to expose feature configuration to frontend: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    try:
        data = hass.data.setdefault(DOMAIN, {})

        old_enabled_features_raw = data.get("enabled_features")
        new_enabled_features_raw = (
            entry.data.get("enabled_features")
            or entry.options.get("enabled_features")
            or {}
        )

        old_enabled_features = (
            old_enabled_features_raw
            if isinstance(old_enabled_features_raw, dict)
            else {}
        )
        new_enabled_features = (
            new_enabled_features_raw
            if isinstance(new_enabled_features_raw, dict)
            else {}
        )

        old_matrix_state_raw = data.get("device_feature_matrix")
        new_matrix_state_raw = entry.data.get("device_feature_matrix") or {}

        old_matrix_state = (
            old_matrix_state_raw if isinstance(old_matrix_state_raw, dict) else {}
        )
        new_matrix_state = (
            new_matrix_state_raw if isinstance(new_matrix_state_raw, dict) else {}
        )

        data["enabled_features"] = new_enabled_features
        data["device_feature_matrix"] = new_matrix_state

        await _expose_feature_config_to_frontend(hass, entry)

        enabled_features_changed = old_enabled_features != new_enabled_features
        matrix_changed = old_matrix_state != new_matrix_state

        if enabled_features_changed or matrix_changed:
            if data.get("_reload_pending") is True:
                return

            data["_reload_pending"] = True

            async def _do_reload() -> None:
                try:
                    await hass.config_entries.async_reload(entry.entry_id)
                finally:
                    hass.data.get(DOMAIN, {}).pop("_reload_pending", None)

            hass.async_create_task(_do_reload())
    except Exception as e:
        _LOGGER.warning("Failed to update frontend feature configuration: %s", e)


async def _copy_all_card_files(hass: HomeAssistant) -> None:
    """Copy all card files to Home Assistant's www directory regardless
    of feature status."""
    try:
        _LOGGER.info("Starting unconditional card files copy process...")

        # Card files to copy (regardless of feature status)
        card_files_to_copy = [
            {
                "source": INTEGRATION_DIR
                / "features"
                / "hello_world"
                / "www"
                / "hello_world",
                "destination": DEPLOYMENT_PATHS.get_destination_features_path(
                    hass.config.config_dir, "hello_world"
                ),
                "feature_name": "hello_world",
            },
            {
                "source": INTEGRATION_DIR
                / "features"
                / "hvac_fan_card"
                / "www"
                / "hvac_fan_card",
                "destination": DEPLOYMENT_PATHS.get_destination_features_path(
                    hass.config.config_dir, "hvac_fan_card"
                ),
                "feature_name": "hvac_fan_card",
            },
        ]

        for card_file in card_files_to_copy:
            source_dir = Path(card_file["source"])  # type: ignore[arg-type]
            destination_dir = Path(card_file["destination"])  # type: ignore[arg-type]

            if source_dir.exists():
                destination_dir.mkdir(parents=True, exist_ok=True)

                await asyncio.to_thread(
                    shutil.copytree,
                    source_dir,
                    destination_dir,
                    dirs_exist_ok=True,
                )
                _LOGGER.info("Card file copied: %s -> %s", source_dir, destination_dir)
            else:
                _LOGGER.warning(f"Card source directory not found: {source_dir}")

        _LOGGER.info("All card files copy process complete")

    except Exception as e:
        _LOGGER.error(f"Failed to copy card files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


# Legacy function removed - now handled by CardRegistry


async def _copy_helper_files(hass: HomeAssistant) -> None:
    """Copy helper files to Home Assistant's www directory for card functionality."""
    try:
        _LOGGER.info("Starting helper files copy process...")

        # Source and destination paths
        source_helpers_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir
        )

        _LOGGER.info(f"Source helpers directory: {source_helpers_dir}")
        _LOGGER.info(f"Destination helpers directory: {destination_helpers_dir}")
        _LOGGER.info(f"Source directory exists: {source_helpers_dir.exists()}")

        if not source_helpers_dir.exists():
            _LOGGER.warning(f"Helper files directory not found: {source_helpers_dir}")
            return

        # Create destination directory if it doesn't exist
        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info(f"Created directory: {destination_helpers_dir}")

        # Copy all helper files
        await asyncio.to_thread(
            shutil.copytree,
            source_helpers_dir,
            destination_helpers_dir,
            dirs_exist_ok=True,
        )
        _LOGGER.info("Helper files copied successfully")

    except Exception as e:
        _LOGGER.error(f"Failed to copy helper files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


# Legacy functions removed - CardRegistry handles all card registration


async def _validate_startup_entities_simple(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Validate startup entity creation and fix discrepancies using SimpleEntityManager.

    This function runs after all platforms have been set up to ensure that
    the actual entities match the expected configuration. It uses SimpleEntityManager
    to detect and fix any discrepancies.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    try:
        from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
            SimpleEntityManager,
        )

        # Create SimpleEntityManager for validation
        entity_manager = SimpleEntityManager(hass)

        # Restore matrix state from config entry if available
        matrix_state = entry.data.get("device_feature_matrix", {})
        if matrix_state:
            entity_manager.restore_device_feature_matrix_state(matrix_state)
            _LOGGER.info(f"Restored matrix state with {len(matrix_state)} devices")

        # Validate entities on startup
        await entity_manager.validate_entities_on_startup()

        _LOGGER.info("SimpleEntityManager startup validation completed")

    except Exception as e:
        _LOGGER.error(f"SimpleEntityManager startup validation failed: {e}")
        # Don't fail startup if validation fails - log error and continue
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _discover_and_store_devices(hass: HomeAssistant) -> None:
    """Discover devices and store them in hass.data for platform access.

    We store full device objects so that config flows can use DeviceFilter
    and other helpers that rely on device attributes such as slugs or types.
    """
    devices = await _discover_ramses_devices(hass)

    # Store devices in a location that platforms can access
    data = hass.data.setdefault(DOMAIN, {})
    data["devices"] = devices
    data["device_discovery_complete"] = True

    device_ids = [getattr(device, "id", str(device)) for device in devices]
    _LOGGER.info(
        "💾 Stored %d devices for platform access: %s",
        len(devices),
        device_ids,
    )


async def async_setup_platforms(hass: HomeAssistant) -> None:
    """Enhanced platform setup with reliable device discovery integration."""
    global _setup_in_progress

    # Prevent multiple simultaneous setup attempts
    if _setup_in_progress:
        _LOGGER.debug("Platform setup already in progress, skipping")
        return

    _setup_in_progress = True

    try:
        _LOGGER.info("Platform setup: integrating with device discovery...")

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info(f"Ramses CC loaded: {ramses_cc_loaded}")

        if ramses_cc_loaded:
            _LOGGER.info("Ramses CC is loaded, verifying device discovery...")

            # Check if device discovery was already completed
            device_data = hass.data.setdefault(DOMAIN, {})
            if "devices" in device_data and "device_discovery_complete" in device_data:
                _LOGGER.info("Device discovery already completed, using cached results")
                devices = device_data["devices"]
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                _LOGGER.info("Using cached device IDs: %s", device_ids)
            else:
                # Re-discover devices and update storage
                devices = await _discover_ramses_devices(hass)
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                device_data["devices"] = devices
                device_data["device_discovery_complete"] = True
                _LOGGER.info("Fresh discovery device IDs: %s", device_ids)

            if devices:
                _LOGGER.info(
                    "Platform setup: Found %d Ramses devices: %s",
                    len(devices),
                    device_ids,
                )
            else:
                _LOGGER.info("Platform setup: No Ramses devices found via any method")

            return
        _LOGGER.info("Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:

            async def delayed_retry() -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            # Use async_call_later instead of async_add_job
            hass.call_later(60.0, hass.async_create_task(delayed_retry))

    except Exception as e:
        _LOGGER.error(f"Error in platform setup: {e}")
    finally:
        # Reset setup flag
        _setup_in_progress = False


async def _discover_ramses_devices(hass: HomeAssistant) -> list[Any]:
    """Discover Ramses devices from ramses_cc integration with improved reliability.

    This function leverages ramses_cc to discover devices by looking for
    ramses_cc entities in the entity registry with multiple fallback methods.
    """

    # Access the broker from the ramses_cc integration
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No ramses_cc entries found")
        return await _discover_devices_from_entity_registry(hass)

    # Use the first ramses_cc entry
    entry = ramses_cc_entries[0]

    try:
        # Method 1: Try to get broker from hass.data (most reliable)
        broker = None
        if "ramses_cc" in hass.data and entry.entry_id in hass.data["ramses_cc"]:
            broker_data = hass.data["ramses_cc"][entry.entry_id]
            # The broker is stored directly, not nested under a "broker" key
            if (
                hasattr(broker_data, "__class__")
                and "Broker" in broker_data.__class__.__name__
            ):
                broker = broker_data
            elif isinstance(broker_data, dict) and "broker" in broker_data:
                broker = broker_data["broker"]
            elif not isinstance(broker_data, dict) and hasattr(broker_data, "broker"):
                broker = broker_data.broker
            else:
                # Direct assignment if broker is stored directly
                broker = broker_data
            _LOGGER.debug(f"Found broker via hass.data method: {broker}")

        # Method 2: If not found, try getting broker from the entry
        if broker is None and hasattr(entry, "broker"):
            broker = entry.broker
            _LOGGER.debug(f"Found broker via entry method: {broker}")

        # Method 3: Try to access through the integration registry
        if broker is None:
            # Look for ramses_cc integration instance in integration registry
            for integration in hass.data.get("integrations", {}).values():
                if hasattr(integration, "broker") and integration.broker:
                    broker = integration.broker
                    _LOGGER.debug(f"Found broker via integration registry: {broker}")
                    break

        # Method 4: Direct import and access (new fallback)
        if broker is None:
            try:
                from ramses_cc.gateway import Gateway

                # Try to find gateway through Home Assistant's component registry
                gateway_entries = [
                    e for e in ramses_cc_entries if hasattr(e, "gateway")
                ]
                if gateway_entries:
                    broker = gateway_entries[0].gateway
                    _LOGGER.debug(f"Found broker via direct gateway access: {broker}")
            except ImportError:
                _LOGGER.debug("ramses_cc module not available for direct access")

        if broker is None:
            _LOGGER.warning("Could not find ramses_cc broker via any method")
            # Fallback: try to find devices from entity registry
            return await _discover_devices_from_entity_registry(hass)

        # Get devices from the broker with robust access
        # The broker stores devices as _devices (list), not devices (dict)
        devices = getattr(broker, "_devices", None)
        if devices is None:
            # Try alternative attribute names
            devices = getattr(broker, "devices", None)

        if not devices:
            _LOGGER.debug("No devices found in broker, using entity registry fallback")
            return await _discover_devices_from_entity_registry(hass)

        # Normalize to a plain list of device objects
        if isinstance(devices, dict):
            devices_list = list(devices.values())
        elif isinstance(devices, (list, set, tuple)):
            devices_list = list(devices)
        else:
            devices_list = [devices]

        # Log summary of discovered devices by ID for debugging
        device_ids = [getattr(device, "id", str(device)) for device in devices_list]
        _LOGGER.info(
            "Found %d devices from broker for config flows: %s",
            len(devices_list),
            device_ids,
        )

        # Return full device objects so downstream code can filter by slugs/types
        return devices_list

    except Exception as e:
        _LOGGER.error(f"Error accessing ramses_cc broker: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")
        # Fallback to entity registry discovery
        return await _discover_devices_from_entity_registry(hass)


async def _discover_devices_from_entity_registry(hass: HomeAssistant) -> list[str]:
    """Fallback method to discover devices from entity registry with comprehensive
    device support."""
    try:
        from homeassistant.helpers.entity_registry import async_get

        entity_registry = async_get(hass)
        device_ids = []

        # Look for ramses_cc entities across multiple domains
        relevant_domains = [
            "fan",
            "climate",
            "sensor",
            "switch",
            "number",
            "binary_sensor",
        ]

        for entity in entity_registry.entities.values():
            if (
                entity.domain in relevant_domains
                and entity.platform == "ramses_cc"
                and hasattr(entity, "device_id")
            ):
                device_id = entity.device_id
                if device_id and device_id not in device_ids:
                    device_ids.append(device_id)

        _LOGGER.info(
            f"Found {len(device_ids)} devices via entity registry fallback: "
            f"{device_ids}"
        )
        return device_ids

    except Exception as e:
        _LOGGER.error(f"Error discovering devices from entity registry: {e}")
        return []


async def _register_cards(hass: HomeAssistant) -> None:
    """Register all cards using feature-centric CardRegistry.

    This uses the new feature-centric CardRegistry that follows HA standards:
    - Uses standard lovelace_resources storage key
    - Discovers cards from feature const.py files dynamically
    - Maintains feature-centric architecture
    - Simple, reliable implementation
    """
    try:
        _LOGGER.info("Starting feature-centric CardRegistry registration")

        # Create CardRegistry and register discovered cards from features
        registry = CardRegistry(hass)
        await registry.register_discovered_cards()

        _LOGGER.info("Feature-centric CardRegistry registration complete")

    except Exception as e:
        _LOGGER.error(f"CardRegistry registration failed: {e}")
        # Don't raise - let the integration continue without card registration
        # This ensures that card registration issues don't break the entire startup
        _LOGGER.warning("Continuing integration startup without card registration")


async def _setup_card_files_and_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup card files and expose feature configuration to frontend.

    This handles the file copying and config exposure that cards need for functionality.
    """
    try:
        _LOGGER.info("Setting up card files and configuration")

        # Always copy helper files for card functionality
        await _copy_helper_files(hass)

        # Always copy all card files regardless of feature status
        await _copy_all_card_files(hass)

        # Expose feature configuration to frontend for card feature toggles
        await _expose_feature_config_to_frontend(hass, entry)

        _LOGGER.info("Card files and configuration setup complete")

    except Exception as e:
        _LOGGER.error(f"Card files and config setup failed: {e}")
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Ramses Extras integration...")

    # Forward the unload to our platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            Platform.SENSOR,
            Platform.SWITCH,
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
        ],
    )

    if unload_ok:
        # Clean up stored data (single-instance integration)
        hass.data.pop(DOMAIN, None)

    return bool(unload_ok)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry.

    For this single-instance integration, ensure we don't leave orphaned entity
    registry entries behind when the user removes the integration.
    """

    # Remove entities
    entity_registry = er.async_get(hass)
    entity_entries = list(entity_registry.entities.values())
    for entity_entry in entity_entries:
        if entity_entry.platform != DOMAIN:
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    # Remove devices created by ramses_extras (but not ramses_cc devices)
    device_registry = dr.async_get(hass)
    device_entries = list(device_registry.devices.values())
    for device_entry in device_entries:
        # Only remove devices that were created by ramses_extras
        # Check if the device has our integration as a config entry
        if entry.id in device_entry.config_entries:
            device_registry.async_remove_device(device_entry.id)


async def _cleanup_orphaned_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_registry: Any | None = None,
    entity_registry: Any | None = None,
) -> None:
    """Clean up orphaned devices.

    Simple logic: if a device has no entities, it's orphaned and should be removed.
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    device_registry = cast(Any, device_registry or dr.async_get(hass))
    entity_registry = cast(Any, entity_registry or er.async_get(hass))

    if device_registry is None:
        _LOGGER.warning("Device registry unavailable, skipping cleanup")
        return

    if entity_registry is None:
        _LOGGER.warning("Entity registry unavailable, skipping cleanup")
        return

    # Get all devices that belong to ramses_extras
    ramses_devices = []
    for device_entry in device_registry.devices.values():
        if any(identifier[0] == DOMAIN for identifier in device_entry.identifiers):
            ramses_devices.append(device_entry)

    # Find orphaned devices: devices that have no entities
    orphaned_devices = []
    for device_entry in ramses_devices:
        # Check if this device has any entities
        entities = entity_registry.entities.get(device_entry.id, [])
        if not entities:
            # No entities found - this device is orphaned
            device_id = list(device_entry.identifiers)[0][1]  # Extract device ID
            orphaned_devices.append((device_id, device_entry))
            _LOGGER.info(f"Found orphaned device: {device_id} (no entities)")

    if not orphaned_devices:
        _LOGGER.debug("No orphaned devices found")
        return

    _LOGGER.info(f"Removing {len(orphaned_devices)} orphaned devices")

    # Remove orphaned devices
    for device_id, device_entry in orphaned_devices:
        try:
            if entry.entry_id in device_entry.config_entries:
                device_registry.async_remove_device(device_entry.id)
                _LOGGER.info(f"Removed orphaned device: {device_id}")
            else:
                _LOGGER.debug(
                    f"Device {device_id} not owned by ramses_extras, skipping"
                )
        except Exception as e:
            _LOGGER.warning(f"Failed to remove device {device_id}: {e}")
