import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    CARD_HELPERS_FOLDER,
    DOMAIN,
    INTEGRATION_DIR,
)

# Entity definitions now managed by framework entity registry
# All constants are loaded from feature modules during startup
# Platform files should use EntityRegistry for entity definitions

# Legacy managers removed - now using feature-centric architecture
# from .managers import FeatureManager
# from .managers.automation_manager import AutomationManager
# from .managers.card_manager import CardManager
# from .managers.device_monitor import DeviceMonitor
# from .managers.entity_manager import EntityManager
# from .managers.platform_reloader import PlatformReloader

# Register platforms
PLATFORMS = ["sensor", "switch", "binary_sensor", "number"]

_LOGGER = logging.getLogger(__name__)

# Global flag to prevent multiple simultaneous setup attempts
_setup_in_progress = False

# Global flag to track if static paths have been registered
_STATIC_PATHS_REGISTERED = False

# Integration only uses config entries, no YAML configuration needed
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras."""
    _LOGGER.debug("Setting up Ramses Extras integration")

    global _STATIC_PATHS_REGISTERED
    if not _STATIC_PATHS_REGISTERED:
        # Only register static paths for card files that exist
        # Frontend resources will be registered dynamically in async_setup_entry
        # based on selection
        card_features = []

        # Find all card features and check if their files exist
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get("category") == "cards":
                # Import card configuration from the feature module
                card_location = None
                card_editor = None

                try:
                    if feature_key == "hvac_fan_card":
                        from .features.hvac_fan_card.const import HVAC_FAN_CARD_CONFIG

                        card_location = HVAC_FAN_CARD_CONFIG.get("location")
                        card_editor = HVAC_FAN_CARD_CONFIG.get("editor")
                    # Add other card features here as needed...

                except ImportError as e:
                    _LOGGER.warning(
                        f"Could not import card config for {feature_key}: {e}"
                    )
                    continue

                if card_location and isinstance(card_location, str):
                    card_path = INTEGRATION_DIR / Path(CARD_FOLDER) / card_location
                    if card_path.exists():
                        card_features.append((feature_key, card_location, card_editor))

        if card_features:
            try:
                # Register all card folders as static paths (for file access)
                static_configs = []

                for feature_key, location, editor in card_features:
                    if isinstance(location, str):
                        card_path = INTEGRATION_DIR / Path(CARD_FOLDER) / location
                        static_configs.append(
                            StaticPathConfig(
                                f"/local/ramses_extras/{feature_key}",
                                str(card_path.parent),
                                True,
                            )
                        )

                # Register helpers directory for shared modules
                helpers_path = INTEGRATION_DIR / Path(CARD_HELPERS_FOLDER)
                if helpers_path.exists():
                    static_configs.append(
                        StaticPathConfig(
                            "/local/ramses_extras/helpers",
                            str(helpers_path),
                            True,
                        )
                    )

                if static_configs:
                    await hass.http.async_register_static_paths(static_configs)
                    _STATIC_PATHS_REGISTERED = True
                    _LOGGER.info(
                        f"Registered static paths for {len(card_features)} cards"
                    )

            except RuntimeError as e:
                if "already registered" in str(e):
                    _STATIC_PATHS_REGISTERED = True
                    _LOGGER.debug("Static paths for cards already registered")
                else:
                    _LOGGER.error(f"Failed to register static paths: {e}")
        else:
            _LOGGER.warning("No card features found in AVAILABLE_FEATURES")

    return True


async def _register_enabled_card_resources(
    hass: HomeAssistant, enabled_features: dict[str, bool]
) -> None:
    """Register frontend resources for enabled card features only."""
    _LOGGER.debug("Registering enabled card resources")

    enabled_cards = []
    disabled_cards = []

    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            if enabled_features.get(feature_key, False):
                # Import card configuration from the feature module
                card_location = None
                card_editor = None

                try:
                    if feature_key == "hvac_fan_card":
                        from .features.hvac_fan_card.const import HVAC_FAN_CARD_CONFIG

                        card_location = HVAC_FAN_CARD_CONFIG.get("location")
                        card_editor = HVAC_FAN_CARD_CONFIG.get("editor")
                    # Add other card features here as needed...

                except ImportError as e:
                    _LOGGER.warning(
                        f"Could not import card config for {feature_key}: {e}"
                    )
                    continue

                if card_location and isinstance(card_location, str):
                    card_path = INTEGRATION_DIR / Path(CARD_FOLDER) / card_location
                    if card_path.exists():
                        resource_url = (
                            f"/local/ramses_extras/{feature_key}/{card_path.name}"
                        )
                        enabled_cards.append((feature_key, resource_url))
                    else:
                        _LOGGER.warning(
                            f"Card file not found for {feature_key}: {card_path}"
                        )

                # Register editor if available
                if card_editor and isinstance(card_editor, str):
                    editor_path = INTEGRATION_DIR / Path(CARD_FOLDER) / card_editor
                    if editor_path.exists():
                        editor_resource_url = (
                            f"/local/ramses_extras/{feature_key}/{editor_path.name}"
                        )
                        enabled_cards.append(
                            (f"{feature_key}_editor", editor_resource_url)
                        )
                        _LOGGER.info(
                            f"Registering editor for {feature_key}: "
                            f"{editor_resource_url}"
                        )
                    else:
                        _LOGGER.warning(
                            f"Editor file not found for {feature_key}: {editor_path}"
                        )
                else:
                    _LOGGER.warning(
                        f"No editor specified for enabled card {feature_key}"
                    )
            else:
                disabled_cards.append(feature_key)

    # Register enabled cards
    for feature_key, resource_url in enabled_cards:
        try:
            from homeassistant.components import frontend

            await hass.async_add_executor_job(
                frontend.add_extra_js_url, hass, resource_url
            )
            _LOGGER.info(f"Registered enabled card resource: {resource_url}")
        except Exception as e:
            _LOGGER.warning(f"Could not register resource {resource_url}: {e}")

    # Log disabled cards for clarity
    if disabled_cards:
        _LOGGER.info(f"Cards disabled (not loaded): {disabled_cards}")

    if enabled_cards:
        _LOGGER.info(
            f"Loaded {len(enabled_cards)} card resources based on config selection"
        )
    else:
        _LOGGER.info("No card resources are currently enabled in config flow")


async def _register_services_early(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services early in setup process."""
    # Legacy services moved to feature-specific implementations
    # No early service registration needed in new architecture


async def _register_services(
    hass: HomeAssistant,
    feature_manager: Any,  # Updated type hint
) -> None:
    """Register services based on enabled features and discovered devices.

    Services are now handled by feature-specific implementations.
    Legacy service registration removed in cleanup.
    """
    # Services are now feature-based and handled by feature managers
    _LOGGER.info("Service registration delegated to feature managers")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry for Ramses Extras."""
    _LOGGER.info("🚀 STARTING Ramses Extras integration setup...")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})

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

    # Load enabled feature definitions
    enabled_features_dict = entry.data.get("enabled_features", {})
    enabled_feature_names = [
        name for name, enabled in enabled_features_dict.items() if enabled
    ]

    _LOGGER.info(
        f"🔧 Loading definitions from {len(enabled_feature_names)} "
        f"enabled features: {enabled_feature_names}"
    )

    # Load each enabled feature
    for feature_name in enabled_feature_names:
        try:
            if feature_name == "humidity_control":
                from .features.humidity_control.const import (
                    HUMIDITY_BOOLEAN_CONFIGS,
                    HUMIDITY_DEVICE_ENTITY_MAPPING,
                    HUMIDITY_NUMBER_CONFIGS,
                    HUMIDITY_SWITCH_CONFIGS,
                )

                extras_registry.register_switch_configs(HUMIDITY_SWITCH_CONFIGS)
                extras_registry.register_number_configs(HUMIDITY_NUMBER_CONFIGS)
                extras_registry.register_boolean_configs(HUMIDITY_BOOLEAN_CONFIGS)
                extras_registry.register_device_mappings(HUMIDITY_DEVICE_ENTITY_MAPPING)
                extras_registry.register_feature("humidity_control")

                _LOGGER.info("✅ Loaded humidity_control feature definitions")

            elif feature_name == "hvac_fan_card":
                from .features.hvac_fan_card.const import (
                    HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING,
                )

                # HVAC Fan Card uses shared sensors from default feature
                extras_registry.register_device_mappings(
                    HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING
                )
                extras_registry.register_feature("hvac_fan_card")

                _LOGGER.info("✅ Loaded hvac_fan_card feature definitions")

            elif feature_name == "humidity_sensors":
                # Humidity Sensors feature - no additional definitions needed
                # Uses shared sensors from default feature
                extras_registry.register_feature("humidity_sensors")
                _LOGGER.info("✅ Loaded humidity_sensors feature definitions")

        except ImportError as e:
            _LOGGER.warning(f"⚠️  Failed to load feature '{feature_name}': {e}")

    # Log loaded definitions for verification
    sensor_count = len(extras_registry.get_all_sensor_configs())
    switch_count = len(extras_registry.get_all_switch_configs())
    number_count = len(extras_registry.get_all_number_configs())
    boolean_count = len(extras_registry.get_all_boolean_configs())
    _LOGGER.info(
        f"✅ EntityRegistry loaded: {sensor_count} sensors, {switch_count} switches, "
        f"{number_count} numbers, {boolean_count} binary sensors"
    )

    # WebSocket commands will be handled by feature-centric architecture
    # Legacy websocket_api.py removed
    _LOGGER.info("WebSocket functionality moved to feature-centric architecture")

    # Register services early (before automations are created)
    _LOGGER.info("🔧 Registering services early...")
    await _register_services_early(hass, entry)

    # Register enabled card resources dynamically
    _LOGGER.info("📦 Registering enabled card resources...")
    await _register_enabled_card_resources(hass, entry.data.get("enabled_features", {}))

    # Discover devices and set up platforms
    _LOGGER.info("🔍 Starting async_setup_platforms...")
    await async_setup_platforms(hass)

    # Clean up orphaned entities after all platforms are set up
    _LOGGER.info("🧹 Starting global orphaned entity cleanup...")
    await _cleanup_orphaned_entities_global(hass)

    # Load platforms for this config entry (ha's core method)
    _LOGGER.info("🖥️ Forwarding entry setups...")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("✅ Ramses Extras integration setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Ramses Extras entry."""
    _LOGGER.debug("Unloading Ramses Extras entry")

    # Clean up humidity automations and stop hardcoded automation
    await _cleanup_humidity_automations_and_automation(hass, entry)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "switch", "binary_sensor", "number"]
    )

    if unload_ok:
        # Get managers for cleanup
        from .framework.helpers.device.core import get_all_device_ids

        device_ids = get_all_device_ids(hass)
        if device_ids:
            # Initialize managers for cleanup (legacy managers removed in cleanup)
            # feature_manager = FeatureManager(hass)
            # card_manager = CardManager(hass)
            # entity_manager = EntityManager(hass)
            # automation_manager = AutomationManager(hass)

            # Stop device monitoring
            managers = hass.data.get(DOMAIN, {}).get("managers", {})
            device_monitor = managers.get("device_monitor")
            if device_monitor:
                await device_monitor.stop_monitoring()
                _LOGGER.info("Stopped device monitor")

            # Load current feature state (legacy manager calls removed)
            # config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
            # if config_entry:
            #     feature_manager.load_enabled_features(config_entry)

            # Get disabled features (all features are being disabled on unload)
            disabled_features = []
            disabled_cards = []
            disabled_automations = []

            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                if feature_config.get("category") == "cards":
                    disabled_cards.append(feature_key)
                elif feature_config.get("category") == "automations":
                    disabled_automations.append(feature_key)
                else:
                    disabled_features.append(feature_key)

            # Clean up disabled components (legacy manager calls removed)
            # if disabled_cards:
            #     await card_manager.cleanup_disabled_cards(disabled_cards)
            #
            # if disabled_automations:
            #     await automation_manager.remove_device_automations(
            #         device_ids, disabled_automations
            #     )
            #
            # if disabled_features:
            #     await entity_manager.cleanup_entities_for_disabled_features(
            #         device_ids, disabled_features
            #     )

        # Remove legacy services (moved to feature-based architecture)
        # Service cleanup now handled by feature-specific managers
        _LOGGER.info("Service cleanup delegated to feature managers")

        hass.data[DOMAIN].pop(entry.entry_id, None)

    return bool(unload_ok)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle migration of a config entry."""
    _LOGGER.debug("Migrating config entry from version %s", entry.version)

    if entry.version < 2:
        new_data = {**entry.data}
        hass.config_entries.async_update_entry(entry, version=2, data=new_data)

    _LOGGER.debug("Migration to version %s successful", entry.version)
    return True


async def async_setup_platforms(hass: HomeAssistant) -> None:
    """Find Ramses FAN devices and register extras using managers."""
    global _setup_in_progress

    # Prevent multiple simultaneous setup attempts
    if _setup_in_progress:
        _LOGGER.debug("Setup already in progress, skipping")
        return

    _setup_in_progress = True

    try:
        _LOGGER.info(
            "🚀 Looking for Ramses devices using ramses_cc entity discovery..."
        )

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info(f"🔍 Ramses CC loaded: {ramses_cc_loaded}")

        if ramses_cc_loaded:
            _LOGGER.info("🔍 Ramses CC is loaded, discovering devices from entities...")

            # Discover devices by looking for ramses_cc entities
            device_ids = await _discover_ramses_devices(hass)
            _LOGGER.info(f"📋 Discovered device IDs: {device_ids}")

            if device_ids:
                _LOGGER.info(
                    "✅ Found %d Ramses devices: %s", len(device_ids), device_ids
                )
                hass.data.setdefault(DOMAIN, {})["devices"] = device_ids

                # Initialize managers (legacy manager initialization removed)
                # _LOGGER.info("🏗️ Initializing managers...")
                # feature_manager = FeatureManager(hass)
                # card_manager = CardManager(hass)
                # entity_manager = EntityManager(hass)
                # automation_manager = AutomationManager(hass)

                # Initialize dynamic device management (legacy removed)
                # device_monitor = DeviceMonitor(hass)
                # config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
                # platform_reloader = PlatformReloader(hass, config_entry)

                # Store managers in hass.data for access by platforms
                # hass.data.setdefault(DOMAIN, {})["managers"] = {
                #     "device_monitor": device_monitor,
                #     "platform_reloader": platform_reloader,
                #     "feature_manager": feature_manager,
                #     "entity_manager": entity_manager,
                #     "automation_manager": automation_manager,
                #     "card_manager": card_manager,
                # }

                # Start device monitoring (legacy monitoring removed)
                # _LOGGER.info("📡 Starting device monitoring...")
                # await device_monitor.start_monitoring()

                # Load current feature state (legacy feature loading removed)
                # _LOGGER.info("⚙️ Loading current feature state...")
                # config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
                # if config_entry:
                #     feature_manager.load_enabled_features(config_entry)
                #     _LOGGER.info("✅ Feature state loaded")
                # else:
                #     _LOGGER.warning("⚠️ No config entry found for feature loading")

                # Get enabled features by category (legacy feature management removed)
                # enabled_cards = feature_manager.get_enabled_cards()
                # _LOGGER.info(f"🃏 Enabled cards: {enabled_cards}")
                # enabled_automations = feature_manager.get_enabled_automations()  # noqa: E501  # TODO: implement

                # Install enabled cards (legacy card management removed)
                # _LOGGER.info("📦 Installing enabled cards...")
                # await card_manager.install_cards(enabled_cards)

                # Set up entities and automations (legacy setup removed)
                # _LOGGER.info("🏗️ Calling _setup_entities_and_automations...")
                # await _setup_entities_and_automations(
                #     hass,
                #     device_ids,
                #     feature_manager,
                #     entity_manager,
                #     automation_manager,
                #     config_entry,
                # )

                _LOGGER.info(
                    "✅ _setup_entities_and_automations completed (legacy removed)"
                )

                _LOGGER.info("🔧 Registering services...")
                # await _register_services(hass, feature_manager)
                _LOGGER.info(
                    "Service registration deferred to feature-centric architecture"
                )

                return
            _LOGGER.info("❌ No Ramses devices found in entity registry")
        else:
            _LOGGER.info("⚠️ Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:

            async def delayed_retry() -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            await asyncio.sleep(60)
            hass.async_create_task(delayed_retry())
        else:
            _LOGGER.info("ℹ️ Ramses CC is loaded but no devices found, not retrying")
    finally:
        _setup_in_progress = False


async def _start_humidity_automation_if_enabled(
    hass: HomeAssistant, config_entry: ConfigEntry | None = None
) -> None:
    """Start hardcoded humidity automation if the feature is enabled."""
    _LOGGER.debug("=== DEBUG: _start_humidity_automation_if_enabled called ===")

    if not config_entry:
        _LOGGER.warning("No config entry provided for humidity automation")
        return

    try:
        _LOGGER.debug("Config entry found: %s", config_entry.entry_id)
        from .features.humidity_control.automation import HumidityAutomationManager

        _LOGGER.debug("Imported HumidityAutomationManager successfully")

        # Check if humidity_control feature is enabled
        enabled_features = config_entry.data.get("enabled_features", {})
        _LOGGER.debug("Enabled features: %s", enabled_features)

        humidity_control_enabled = enabled_features.get("humidity_control", False)
        _LOGGER.debug("Humidity control enabled: %s", humidity_control_enabled)

        if humidity_control_enabled:
            _LOGGER.info("Creating HumidityAutomationManager instance...")
            # Start hardcoded humidity automation
            humidity_automation = HumidityAutomationManager(hass, config_entry)
            _LOGGER.debug("HumidityAutomationManager created, storing in hass.data...")

            hass.data.setdefault(DOMAIN, {}).setdefault(config_entry.entry_id, {})[
                "humidity_automation"
            ] = humidity_automation
            _LOGGER.debug("Stored automation in hass.data, now starting...")

            # Start the automation (will wait for entities and register listeners)
            await humidity_automation.start()

            _LOGGER.info(
                "Started hardcoded humidity automation for humidity_control feature"
            )
            _LOGGER.debug("=== Humidity automation startup completed ===")
        else:
            _LOGGER.info("Humidity control not enabled - skipping automation startup")

    except Exception as e:
        _LOGGER.error(f"Failed to start humidity automation: {e}")
        _LOGGER.exception("Full exception details:")


async def _setup_entities_and_automations(
    hass: HomeAssistant,
    device_ids: list[str],
    feature_manager: Any,  # Updated type hint
    entity_manager: Any,  # Updated type hint
    automation_manager: Any,  # Updated type hint
    config_entry: ConfigEntry | None = None,
) -> None:
    """Set up entities and automations using managers."""
    try:
        # Get enabled features
        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = feature_manager.is_feature_enabled(
                feature_key
            )

        _LOGGER.info(f"Setting up components for enabled features: {enabled_features}")

        # Set up automations for enabled automation features
        enabled_automations = feature_manager.get_enabled_automations()
        if enabled_automations:
            await automation_manager.create_device_automations(
                device_ids, enabled_automations
            )

        # Set up entities using entity manager
        await entity_manager.setup_entities_for_devices(device_ids)

        # Start hardcoded humidity automation if enabled
        await _start_humidity_automation_if_enabled(hass, config_entry)

        _LOGGER.info(
            "🔧 Humidity automation startup called from _setup_entities_and_automations"
        )

        # Note: Platforms are already set up in async_setup_entry, no need to duplicate

        _LOGGER.info("Entity and automation setup completed via managers")

    except Exception as e:
        _LOGGER.error(f"Failed to setup entities and automations: {e}")


async def _discover_ramses_devices(hass: HomeAssistant) -> list[str]:
    """Discover Ramses devices by hooking into the ramses_cc broker."""
    device_ids = []

    try:
        # Access ramses_cc broker directly
        ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
        if ramses_cc_entries:
            _LOGGER.info("Found ramses_cc integration, accessing broker...")

            # Check if the broker is available in hass.data for the integration
            ramses_domain = "ramses_cc"

            # Get the first loaded Ramses entry
            if ramses_cc_entries:
                _LOGGER.info(f"Found {len(ramses_cc_entries)} ramses_cc entries")
                ramses_entry = ramses_cc_entries[0]
                ramses_entry_id = ramses_entry.entry_id
                _LOGGER.info(f"Using ramses_cc entry: {ramses_entry_id}")

                # Debug: Check what's available in hass.data for ramses_cc
                _LOGGER.debug(f"Available hass.data keys: {list(hass.data.keys())}")
                if ramses_domain in hass.data:
                    _LOGGER.debug(
                        f"ramses_cc data keys: {list(hass.data[ramses_domain].keys())}"
                    )

                # Check if the broker data is available for this entry
                if (
                    ramses_domain in hass.data
                    and ramses_entry_id in hass.data[ramses_domain]
                ):
                    broker = hass.data[ramses_domain][ramses_entry_id]
                    _LOGGER.debug(
                        f"Found broker: {type(broker)} "
                        f"with attributes: {list(dir(broker))}"
                    )
                else:
                    _LOGGER.warning("Ramses CC broker data not available in hass.data")
                    _LOGGER.warning(
                        f"Expected structure: "
                        f"hass.data['{ramses_domain}']['{ramses_entry_id}']"
                    )
                    # Try alternative structure
                    if hass_domain_data := hass.data.get(ramses_domain):
                        _LOGGER.warning(
                            f"Available entry IDs: {list(hass_domain_data.keys())}"
                        )
                    return []

                if not hasattr(broker, "client"):
                    _LOGGER.warning("Ramses CC broker does not have client attribute")
                    return []

                # Access devices through the broker's client
                gwy = broker.client
                _LOGGER.debug(
                    f"Gwy client type: {type(gwy)} with attributes: {list(dir(gwy))}"
                )

                if not hasattr(gwy, "devices"):
                    _LOGGER.warning("Ramses CC client does not have devices attribute")
                    return []

                _LOGGER.info(f"Found {len(gwy.devices)} devices in Ramses CC")
                for i, device in enumerate(gwy.devices):
                    _LOGGER.info(
                        f"Device {i}: {device.id} ({device.__class__.__name__})"
                    )

                # Discover devices using flexible handler approach
                for device in gwy.devices:
                    device_ids.extend(await _handle_device(device))

                if device_ids:
                    _LOGGER.info(
                        f"Successfully discovered {len(device_ids)} devices via broker"
                    )
                    return device_ids

                _LOGGER.warning("No supported devices found in broker")
            else:
                _LOGGER.warning("No ramses_cc config entries found")
        else:
            _LOGGER.warning("No ramses_cc integration found")

    except Exception as e:
        _LOGGER.warning("Error discovering Ramses devices: %s", e)

    return device_ids


async def _handle_device(device: Any) -> list[str]:
    """Handle a device based on its type using the configured handler."""
    device_ids = []

    # Check if this device type is supported
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        supported_types = feature_config.get("supported_device_types", [])
        if (
            isinstance(supported_types, list)
            and device.__class__.__name__ in supported_types
        ):
            handler_name = str(feature_config.get("handler", "handle_hvac_ventilator"))
            handler = globals().get(handler_name)
            if handler:
                result = await handler(device)
                if result:
                    device_ids.extend(result)
                    _LOGGER.info(
                        f"Handled {device.__class__.__name__} device: {device.id}"
                    )
            else:
                _LOGGER.warning(
                    f"No handler found for {device.__class__.__name__}: {handler_name}"
                )
            break

    return device_ids


async def _cleanup_humidity_automations_and_automation(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Clean up both YAML and hardcoded humidity automations
    when feature is disabled."""
    # Clean up hardcoded humidity automation
    try:
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(entry.entry_id, {})
        humidity_automation = entry_data.get("humidity_automation")

        if humidity_automation:
            await humidity_automation.stop()
            _LOGGER.info("Stopped hardcoded humidity automation")

        # Remove from hass.data
        if "humidity_automation" in entry_data:
            del entry_data["humidity_automation"]

    except Exception as e:
        _LOGGER.error(f"Failed to stop humidity automation: {e}")

    # Clean up YAML automations (legacy support)
    await _cleanup_humidity_automations(hass)


async def _cleanup_humidity_automations(hass: HomeAssistant) -> None:
    """Remove humidity control automations when feature is disabled."""
    automation_path = Path(hass.config.path("automations.yaml"))

    if not automation_path.exists():
        return

    try:
        import yaml

        # Read file content asynchronously
        def read_automations_file() -> str:
            with open(automation_path, encoding="utf-8") as f:
                return f.read()

        content_str = await hass.async_add_executor_job(read_automations_file)
        content = yaml.safe_load(content_str)

        if not content:
            return

        # Handle both formats: with or without automation wrapper
        if isinstance(content, list):
            # Direct automation list format (like user's working automations)
            automations_to_filter = content
        elif isinstance(content, dict) and "automation" in content:
            # Wrapped format with automation key
            automations_to_filter = content["automation"]
        else:
            return

        # Remove Ramses humidity control automations by ID
        filtered_automations = []
        for auto in automations_to_filter:
            automation_id = auto.get("id", "")
            is_ramses_humidity_auto = automation_id.startswith(
                ("ramses_extras_humidity_control_", "ramses_extras_dehumidifier_")
            )

            if not is_ramses_humidity_auto:
                filtered_automations.append(auto)

        # Update file if any automations were removed
        if len(filtered_automations) != len(automations_to_filter):

            def write_automations_file() -> None:
                if isinstance(content, list):
                    # Direct format - write list directly
                    with open(automation_path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            filtered_automations,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                        )
                else:
                    # Wrapped format - write with automation key
                    content["automation"] = filtered_automations
                    with open(automation_path, "w", encoding="utf-8") as f:
                        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

            await hass.async_add_executor_job(write_automations_file)
            _LOGGER.info("Removed humidity control automations from automations.yaml")

    except Exception as e:
        _LOGGER.error(f"Failed to cleanup humidity automations: {e}")


async def _cleanup_orphaned_entities_global(hass: HomeAssistant) -> None:
    """Clean up orphaned entities across all platforms after setup."""
    try:
        from .framework.helpers.entity_core import EntityHelpers
        from .framework.helpers.platform import (
            calculate_required_entities,
            get_enabled_features,
        )

        # Get devices and config entry
        devices = hass.data.get(DOMAIN, {}).get("devices", [])
        config_entry = hass.data.get(DOMAIN, {}).get("config_entry")

        if not devices or not config_entry:
            _LOGGER.debug("No devices or config entry available for global cleanup")
            return

        # Get enabled features
        enabled_features = get_enabled_features(hass, config_entry)

        # Clean up orphaned entities for all platforms
        platforms = ["sensor", "switch", "binary_sensor", "number"]

        for platform in platforms:
            try:
                # Calculate required entities for this platform
                required_entities = calculate_required_entities(
                    platform, enabled_features, devices, hass
                )

                # Convert device_ids to underscore format
                #  and generate expected entity IDs
                expected_entity_ids = set()
                for device_id in devices:
                    device_id_underscore = device_id.replace(":", "_")
                    for entity_name in required_entities:
                        entity_id = EntityHelpers.generate_entity_name_from_template(
                            platform, entity_name, device_id_underscore
                        )
                        if entity_id:
                            expected_entity_ids.add(entity_id)

                # Get all possible entity types for this platform
                from .extras_registry import extras_registry

                all_possible_types = []
                for device_id in devices:
                    from .framework.helpers.device.core import (
                        find_ramses_device,
                        get_device_type,
                    )

                    device = find_ramses_device(hass, device_id)
                    if device:
                        device_type = get_device_type(device)
                        device_mappings = extras_registry.get_all_device_mappings()
                        if device_type in device_mappings:
                            entity_mapping = device_mappings[device_type]
                            platform_key = (
                                f"{platform}s"  # Convert 'sensor' -> 'sensors'
                            )
                            all_possible_types.extend(
                                entity_mapping.get(platform_key, [])
                            )

                # Clean up orphaned entities with proper parameters
                removed_count = EntityHelpers.cleanup_orphaned_entities(
                    platform, hass, devices, expected_entity_ids, all_possible_types
                )

                if removed_count > 0:
                    _LOGGER.info(
                        f"Removed {removed_count} orphaned {platform} entities"
                    )

            except Exception as e:
                _LOGGER.warning(f"Error during {platform} cleanup: {e}")

    except Exception as e:
        _LOGGER.warning(f"Error during global orphaned entity cleanup: {e}")


async def handle_hvac_ventilator(device: Any) -> list[str]:
    """Handle HVAC Ventilator devices - create entities based on mapping."""
    device_id = device.id
    device_type = device.__class__.__name__

    _LOGGER.info(f"🔧 Handling HVAC device: {device_id} ({device_type})")

    # Get entity mappings from EntityRegistry
    from .extras_registry import extras_registry

    device_mappings = extras_registry.get_all_device_mappings()
    _LOGGER.debug(f"Available device mappings: {list(device_mappings.keys())}")

    # Check what entities this device type should have
    if device_type not in device_mappings:
        _LOGGER.warning(f"No entity mapping found for device type: {device_type}")
        return []

    entity_mapping = device_mappings[device_type]
    _LOGGER.debug(f"Entity mapping for {device_type}: {entity_mapping}")

    # Check if this device type has any entities defined
    has_entities = (
        entity_mapping.get("sensors")
        or entity_mapping.get("switches")
        or entity_mapping.get("binary_sensors")
        or entity_mapping.get("numbers")
    )

    if has_entities:
        _LOGGER.info(
            f"✅ Device {device_id} ({device_type}) "
            f"will create entities: {entity_mapping}"
        )
        return [device_id]

    _LOGGER.debug(f"Device {device_id} ({device_type}) has no entities defined")
    return []


# Add more device handlers here as needed
# async def handle_hvac_controller(device: Any) -> List[str]:
#     """Handle HVAC Controller devices."""
#     return [device.id]
#
# async def handle_thermostat(device: Any) -> List[str]:
#     """Handle Thermostat devices."""
#     return [device.id]
