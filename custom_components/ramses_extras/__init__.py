"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
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
from .framework.helpers.card_registry import ALL_CARDS, CardRegistry
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
    _LOGGER.info("🏠  Starting Ramses Extras from YAML configuration")

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
        _LOGGER.info("🔧 Setting up Ramses Extras from YAML configuration...")

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
    _LOGGER.info("🚀 STARTING Ramses Extras integration setup...")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})
    hass.data[DOMAIN]["PLATFORM_REGISTRY"] = (
        PLATFORM_REGISTRY  # Make registry available to platforms
    )

    _LOGGER.info(f"📋 Enabled features: {entry.data.get('enabled_features', {})}")

    # Load entity definitions from default feature and all enabled features
    _LOGGER.info("📊 Loading entity definitions from features...")
    from .extras_registry import extras_registry

    # Always load default feature definitions
    _LOGGER.info("🔧 Loading default entity definitions...")
    from .features.default.const import (
        DEFAULT_BOOLEAN_CONFIGS,
        DEFAULT_DEVICE_ENTITY_MAPPING,
        DEFAULT_NUMBER_CONFIGS,
        DEFAULT_SENSOR_CONFIGS,
        DEFAULT_SWITCH_CONFIGS,
    )

    extras_registry.register_sensor_configs(DEFAULT_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(DEFAULT_SWITCH_CONFIGS)
    extras_registry.register_number_configs(DEFAULT_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(DEFAULT_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(DEFAULT_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("default")

    # Load default feature's WebSocket commands and other feature components
    _LOGGER.info("🔧 Loading default feature...")
    from .features.default.commands import register_default_commands
    from .features.default.const import load_feature

    # Import WebSocket commands to ensure decorators are executed
    _LOGGER.info("🔌 Importing WebSocket commands module for decorator execution...")
    from .features.default import websocket_commands  # noqa: F401

    _LOGGER.info("✅ WebSocket commands module imported successfully")

    load_feature()

    # Register default device type commands
    _LOGGER.info("🔧 Registering default device type commands...")
    register_default_commands()

    # Load enabled feature definitions
    enabled_features_dict = entry.data.get("enabled_features", {})
    enabled_feature_names = [
        name for name, enabled in enabled_features_dict.items() if enabled
    ]

    _LOGGER.info(
        f"🔧 Loading definitions from {len(enabled_feature_names)} "
        f"enabled features: {enabled_feature_names}"
    )

    # Load each enabled feature dynamically
    for feature_name in enabled_feature_names:
        try:
            # Import the feature's const module
            module_name = (
                f"custom_components.ramses_extras.features.{feature_name}.const"
            )
            feature_module = __import__(module_name, fromlist=["load_feature"])

            # Call the feature's load function
            if hasattr(feature_module, "load_feature"):
                feature_module.load_feature()
                _LOGGER.info(f"✅ Loaded {feature_name} feature definitions")
            else:
                _LOGGER.warning(
                    f"⚠️  Feature '{feature_name}' has no load_feature function"
                )

            # Import platform modules to trigger registration
            try:
                # Import all platform modules for this feature
                platforms_dir = (
                    INTEGRATION_DIR / "features" / feature_name / "platforms"
                )
                if platforms_dir.exists():
                    for platform_file in platforms_dir.glob("*.py"):
                        if platform_file.name != "__init__.py":
                            module_path = f"custom_components.ramses_extras.features.{feature_name}.platforms.{platform_file.stem}"  # noqa: E501

                            # Import in executor to avoid blocking event loop
                            await _import_module_in_executor(module_path)

                # Import WebSocket commands to ensure decorators are executed
                try:
                    websocket_module_path = (
                        f"custom_components.ramses_extras.features.{feature_name}"
                        ".websocket_commands"
                    )
                    await _import_module_in_executor(websocket_module_path)
                    _LOGGER.info(f"✅ Imported WebSocket commands for {feature_name}")
                except ImportError:
                    _LOGGER.debug(
                        f"No WebSocket commands module found for {feature_name}"
                    )

            except ImportError:
                pass

        except ImportError as e:
            _LOGGER.warning(f"⚠️  Failed to load feature '{feature_name}': {e}")

    # Log loaded definitions for verification
    sensor_count = len(extras_registry.get_all_sensor_configs())
    switch_count = len(extras_registry.get_all_switch_configs())
    number_count = len(extras_registry.get_all_number_configs())
    boolean_count = len(extras_registry.get_all_boolean_configs())
    _LOGGER.info(
        f"✅ EntityRegistry loaded: {sensor_count} sensor, {switch_count} switch, "
        f"{number_count} number, {boolean_count} binary sensor"
    )

    _LOGGER.info("WebSocket functionality moved to feature-centric architecture")

    # ALWAYS register all card resources at startup using CardRegistry
    # This ensures cards are available before Lovelace parses dashboards
    await _register_cards_with_registry(hass, entry)

    # Copy helper files and expose feature config for card functionality
    await _setup_card_files_and_config(hass, entry)

    # Register services before setting up platforms
    _LOGGER.info("🔧 Registering services early...")
    await _register_services(hass)

    # Register WebSocket commands for features
    _LOGGER.info("🔌 Setting up WebSocket integration...")
    await _setup_websocket_integration(hass)

    # CRITICAL: Discover devices BEFORE setting up platforms
    # This ensures platforms have device data when they initialize
    _LOGGER.info("🔍 Discovering devices before platform setup...")
    await _discover_and_store_devices(hass)

    # Forward the setup to the sensor, switch, etc. platforms
    _LOGGER.info("🔧 Registering supported platforms...")
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.NUMBER],
    )

    # Continue with additional platform setup if needed
    _LOGGER.info("🔍 Starting async_setup_platforms...")
    await async_setup_platforms(hass)

    # STEP: Post-creation validation with SimpleEntityManager
    _LOGGER.info("🔍 Running SimpleEntityManager post-creation validation...")
    await _validate_startup_entities_simple(hass, entry)

    # Explicitly create and start feature instances for
    #  enabled features (including default)
    features = hass.data[DOMAIN].setdefault("features", {})
    enabled_feature_names = list(entry.data.get("enabled_features", {}).keys())
    # Always include default
    if "default" not in enabled_feature_names:
        enabled_feature_names.append("default")
    import importlib

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
                if feature_instance and "automation" in feature_instance:
                    automation_manager = feature_instance["automation"]
                    if (
                        automation_manager
                        and not automation_manager.is_automation_active()
                    ):
                        hass.async_create_task(automation_manager.start())

                features[feature_name] = feature_instance
                _LOGGER.info(f"✅ Created feature instance: {feature_name}")
        except Exception as e:
            _LOGGER.warning(
                f"⚠️ Failed to create feature instance '{feature_name}': {e}"
            )
    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    _LOGGER.info("Service registration delegated to feature managers")


async def _setup_websocket_integration(hass: HomeAssistant) -> None:
    """Set up WebSocket integration for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    try:
        from .websocket_integration import async_setup_websocket_integration

        success = await async_setup_websocket_integration(hass)
        if success:
            _LOGGER.info("✅ WebSocket integration setup complete")
        else:
            _LOGGER.warning("⚠️ WebSocket integration setup failed")

    except Exception as error:
        _LOGGER.error(f"❌ Error setting up WebSocket integration: {error}")
        # Don't fail the entire integration if WebSocket setup fails


# Legacy functions removed - CardRegistry handles all card registration
# Legacy function removed - CardRegistry handles all card registration


async def _expose_feature_config_to_frontend(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Expose feature configuration to frontend JavaScript for card feature toggles."""
    try:
        _LOGGER.info("🔧 Exposing feature configuration to frontend...")

        # Get enabled features from the entry
        enabled_features = entry.data.get("enabled_features", {})

        # Use json.dumps to properly convert Python values to JavaScript
        import json

        js_enabled_features = json.dumps(enabled_features, indent=2)

        js_content = f"""// Ramses Extras Feature Configuration
// Auto-generated during integration setup
window.ramsesExtras = window.ramsesExtras || {{}};
window.ramsesExtras.features = {js_enabled_features};

// Log feature configuration for debugging
console.log('🔧 Ramses Extras features loaded:', window.ramsesExtras.features);
"""

        # Write the JavaScript file to the helpers directory
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir
        )
        feature_config_file = destination_helpers_dir / "ramses-extras-features.js"

        # Write the file
        await asyncio.to_thread(feature_config_file.write_text, js_content)

        _LOGGER.info(
            f"✅ Feature configuration exposed to frontend: {feature_config_file}"
        )

    except Exception as e:
        _LOGGER.error(f"❌ Failed to expose feature configuration to frontend: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _copy_all_card_files(hass: HomeAssistant) -> None:
    """Copy all card files to Home Assistant's www directory regardless
    of feature status."""
    try:
        _LOGGER.info("📦 Starting unconditional card files copy process...")

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
            feature_name = card_file["feature_name"]

            if source_dir.exists():
                destination_dir.mkdir(parents=True, exist_ok=True)

                await asyncio.to_thread(
                    shutil.copytree,
                    source_dir,
                    destination_dir,
                    dirs_exist_ok=True,
                )
                _LOGGER.info(
                    f"✅ Copied {feature_name} card files to {destination_dir}"
                )
            else:
                _LOGGER.warning(f"⚠️ Card source directory not found: {source_dir}")

        _LOGGER.info("✅ All card files copy process complete")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to copy card files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


# Legacy function removed - now handled by CardRegistry


async def _copy_helper_files(hass: HomeAssistant) -> None:
    """Copy helper files to Home Assistant's www directory for card functionality."""
    try:
        _LOGGER.info("📦 Starting helper files copy process...")

        # Source and destination paths
        source_helpers_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir
        )

        _LOGGER.info(f"📁 Source helpers directory: {source_helpers_dir}")
        _LOGGER.info(f"📁 Destination helpers directory: {destination_helpers_dir}")
        _LOGGER.info(f"📂 Source directory exists: {source_helpers_dir.exists()}")

        if not source_helpers_dir.exists():
            _LOGGER.warning(f"⚠️ Helper files directory not found: {source_helpers_dir}")
            return

        # Create destination directory if it doesn't exist
        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info(f"📁 Created directory: {destination_helpers_dir}")

        # Copy all helper files
        await asyncio.to_thread(
            shutil.copytree,
            source_helpers_dir,
            destination_helpers_dir,
            dirs_exist_ok=True,
        )
        _LOGGER.info("✅ Helper files copied successfully")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to copy helper files: {e}")
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

        _LOGGER.info("✅ SimpleEntityManager startup validation completed")

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
        _LOGGER.info("🚀 Platform setup: integrating with device discovery...")

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info(f"🔍 Ramses CC loaded: {ramses_cc_loaded}")

        if ramses_cc_loaded:
            _LOGGER.info("🔍 Ramses CC is loaded, verifying device discovery...")

            # Check if device discovery was already completed
            device_data = hass.data.setdefault(DOMAIN, {})
            if "devices" in device_data and "device_discovery_complete" in device_data:
                _LOGGER.info(
                    "✅ Device discovery already completed, using cached results"
                )
                devices = device_data["devices"]
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                _LOGGER.info("📋 Using cached device IDs: %s", device_ids)
            else:
                # Re-discover devices and update storage
                devices = await _discover_ramses_devices(hass)
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                device_data["devices"] = devices
                device_data["device_discovery_complete"] = True
                _LOGGER.info("📋 Fresh discovery device IDs: %s", device_ids)

            if devices:
                _LOGGER.info(
                    "✅ Platform setup: Found %d Ramses devices: %s",
                    len(devices),
                    device_ids,
                )
            else:
                _LOGGER.info("⚠️ Platform setup: No Ramses devices found via any method")

            return
        _LOGGER.info("⚠️  Ramses CC not loaded yet, will retry in 60 seconds.")

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
            elif hasattr(broker_data, "broker"):
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


async def _register_cards_with_registry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Register all cards using clean CardRegistry for
     unconditional startup registration.

    This uses the new simplified CardRegistry that follows HA standards:
    - Uses standard lovelace_resources storage key
    - Registers all cards unconditionally at startup
    - Simple, reliable implementation
    - No feature-based conditional logic
    """
    try:
        _LOGGER.info("🔧 Starting clean CardRegistry-based card registration")

        # Create CardRegistry and register all cards unconditionally
        registry = CardRegistry(hass)
        await registry.register(ALL_CARDS)

        _LOGGER.info("✅ CardRegistry registration complete - all cards available")

    except Exception as e:
        _LOGGER.error(f"❌ CardRegistry registration failed: {e}")
        # Don't raise - let the integration continue without card registration
        # This ensures that card registration issues don't break the entire startup
        _LOGGER.warning("⚠️ Continuing integration startup without card registration")


async def _setup_card_files_and_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup card files and expose feature configuration to frontend.

    This handles the file copying and config exposure that cards need for functionality.
    """
    try:
        _LOGGER.info("🔧 Setting up card files and configuration")

        # Always copy helper files for card functionality
        await _copy_helper_files(hass)

        # Always copy all card files regardless of feature status
        await _copy_all_card_files(hass)

        # Expose feature configuration to frontend for card feature toggles
        await _expose_feature_config_to_frontend(hass, entry)

        _LOGGER.info("✅ Card files and configuration setup complete")

    except Exception as e:
        _LOGGER.error(f"❌ Card files and config setup failed: {e}")
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("🚫 Unloading Ramses Extras integration...")

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
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return bool(unload_ok)
