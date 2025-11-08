import asyncio
import logging
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
    DEVICE_ENTITY_MAPPING,
    DEVICE_SERVICE_MAPPING,
    DOMAIN,
    INTEGRATION_DIR,
    SERVICE_REGISTRY,
)
from .managers import FeatureManager
from .managers.automation_manager import AutomationManager
from .managers.card_manager import CardManager
from .managers.device_monitor import DeviceMonitor
from .managers.entity_manager import EntityManager
from .managers.platform_reloader import PlatformReloader

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
                location = str(feature_config.get("location", ""))
                if location:
                    card_path = INTEGRATION_DIR / CARD_FOLDER / location
                    if card_path.exists():
                        card_features.append((feature_key, location))

        if card_features:
            try:
                # Register all card folders as static paths (for file access)
                static_configs = []

                for feature_key, location in card_features:
                    card_path = INTEGRATION_DIR / CARD_FOLDER / location
                    static_configs.append(
                        StaticPathConfig(
                            f"/local/ramses_extras/{feature_key}",
                            str(card_path.parent),
                            True,
                        )
                    )

                # Register helpers directory for shared modules
                helpers_path = INTEGRATION_DIR / CARD_HELPERS_FOLDER
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
                location = str(feature_config.get("location", ""))
                editor = feature_config.get("editor")

                if location:
                    card_path = INTEGRATION_DIR / CARD_FOLDER / location
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
                if editor and isinstance(editor, str):
                    editor_path = INTEGRATION_DIR / Path(CARD_FOLDER) / editor
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
    from .services import fan_services

    # Check if humidity_control feature is enabled
    enabled_features = entry.data.get("enabled_features", {})
    if enabled_features.get("humidity_control", False):
        fan_services.register_fan_services(hass)
        _LOGGER.info("Registered fan services early for humidity control")
    else:
        _LOGGER.info("Humidity control not enabled - fan services not registered early")


async def _register_services(
    hass: HomeAssistant, feature_manager: FeatureManager
) -> None:
    """Register services based on enabled features and discovered devices."""
    import importlib

    from .helpers.device import (
        find_ramses_device,
        get_all_device_ids,
        get_device_type,
        validate_device_for_service,
    )

    # Get discovered devices
    device_ids = get_all_device_ids(hass)

    # Track which services have been registered to avoid duplicates
    registered_services = set()

    if device_ids:
        # Register services for discovered device types
        for device_id in device_ids:
            device = find_ramses_device(hass, device_id)
            if device:
                device_type = get_device_type(device)
                if device_type in SERVICE_REGISTRY:
                    services_for_device = SERVICE_REGISTRY[device_type]
                    for service_name, handler_config in services_for_device.items():
                        if service_name not in registered_services:
                            try:
                                # Dynamic import and registration
                                # (run in executor to avoid blocking)
                                module = await hass.async_add_executor_job(
                                    importlib.import_module,
                                    handler_config["module"],
                                    __package__,
                                )
                                register_function = getattr(
                                    module, handler_config["function"]
                                )
                                register_function(hass)
                                registered_services.add(service_name)
                                _LOGGER.info(
                                    f"Registered {service_name} service for device "
                                    f"{device_id} ({device_type})"
                                )
                            except ModuleNotFoundError as e:
                                _LOGGER.error(
                                    f"Module not found for {service_name}: "
                                    f"{handler_config['module']} - {e}"
                                )
                            except Exception as e:
                                _LOGGER.error(f"Failed to register {service_name}: {e}")
                        break  # Only need to register once per service type

    if not registered_services:
        _LOGGER.debug("No services registered - no supported devices found")
    else:
        _LOGGER.info(
            f"Registered {len(registered_services)} services: {registered_services}"
        )


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

    # Register WebSocket commands
    from .websocket_api import register_ws_commands

    register_ws_commands(hass)
    _LOGGER.info("Registered WebSocket commands for Ramses Extras")

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
        from .helpers.device import get_all_device_ids

        device_ids = get_all_device_ids(hass)
        if device_ids:
            # Initialize managers for cleanup
            feature_manager = FeatureManager(hass)
            card_manager = CardManager(hass)
            entity_manager = EntityManager(hass)
            automation_manager = AutomationManager(hass)

            # Stop device monitoring
            managers = hass.data.get(DOMAIN, {}).get("managers", {})
            device_monitor = managers.get("device_monitor")
            if device_monitor:
                await device_monitor.stop_monitoring()
                _LOGGER.info("Stopped device monitor")

            # Load current feature state
            config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
            if config_entry:
                feature_manager.load_enabled_features(config_entry)

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

            # Clean up disabled components
            if disabled_cards:
                await card_manager.cleanup_disabled_cards(disabled_cards)

            if disabled_automations:
                await automation_manager.remove_device_automations(
                    device_ids, disabled_automations
                )

            if disabled_features:
                await entity_manager.cleanup_entities_for_disabled_features(
                    device_ids, disabled_features
                )

        # Remove services
        from .helpers.device import (
            find_ramses_device,
            get_all_device_ids,
            get_device_type,
        )

        device_ids = get_all_device_ids(hass)
        if device_ids:
            for device_id in device_ids:
                device = find_ramses_device(hass, device_id)
                if device:
                    device_type = get_device_type(device)
                    if device_type in SERVICE_REGISTRY:
                        services_for_device = SERVICE_REGISTRY[device_type]
                        for service_name in services_for_device.keys():
                            # Unregister the service
                            hass.services.async_remove(DOMAIN, service_name)
                            _LOGGER.info(
                                "Unregistered %s service for device %s (%s)",
                                service_name,
                                device_id,
                                device_type,
                            )

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

                # Initialize managers
                _LOGGER.info("🏗️ Initializing managers...")
                feature_manager = FeatureManager(hass)
                card_manager = CardManager(hass)
                entity_manager = EntityManager(hass)
                automation_manager = AutomationManager(hass)

                # Initialize dynamic device management
                device_monitor = DeviceMonitor(hass)
                config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
                platform_reloader = PlatformReloader(hass, config_entry)

                # Store managers in hass.data for access by platforms
                hass.data.setdefault(DOMAIN, {})["managers"] = {
                    "device_monitor": device_monitor,
                    "platform_reloader": platform_reloader,
                    "feature_manager": feature_manager,
                    "entity_manager": entity_manager,
                    "automation_manager": automation_manager,
                    "card_manager": card_manager,
                }

                # Start device monitoring
                _LOGGER.info("📡 Starting device monitoring...")
                await device_monitor.start_monitoring()

                # Load current feature state
                _LOGGER.info("⚙️ Loading current feature state...")
                config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
                if config_entry:
                    feature_manager.load_enabled_features(config_entry)
                    _LOGGER.info("✅ Feature state loaded")
                else:
                    _LOGGER.warning("⚠️ No config entry found for feature loading")

                # Get enabled features by category
                enabled_cards = feature_manager.get_enabled_cards()
                _LOGGER.info(f"🃏 Enabled cards: {enabled_cards}")
                # enabled_automations = feature_manager.get_enabled_automations()  # noqa: E501  # TODO: implement

                # Install enabled cards
                _LOGGER.info("📦 Installing enabled cards...")
                await card_manager.install_cards(enabled_cards)

                # Set up entities and automations
                _LOGGER.info("🏗️ Calling _setup_entities_and_automations...")
                await _setup_entities_and_automations(
                    hass,
                    device_ids,
                    feature_manager,
                    entity_manager,
                    automation_manager,
                    config_entry,
                )

                _LOGGER.info("✅ _setup_entities_and_automations completed")

                _LOGGER.info("🔧 Registering services...")
                await _register_services(hass, feature_manager)

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
        from .automations.humidity_automation import HumidityAutomationManager

        _LOGGER.debug("Imported HumidityAutomationManager successfully")

        # Check if humidity_control feature is enabled
        enabled_features = config_entry.data.get("enabled_features", {})
        _LOGGER.debug("Enabled features: %s", enabled_features)

        humidity_control_enabled = enabled_features.get("humidity_control", False)
        _LOGGER.debug("Humidity control enabled: %s", humidity_control_enabled)

        if humidity_control_enabled:
            _LOGGER.info("Creating HumidityAutomationManager instance...")
            # Start hardcoded humidity automation
            humidity_automation = HumidityAutomationManager(hass)
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
    feature_manager: FeatureManager,
    entity_manager: EntityManager,
    automation_manager: AutomationManager,
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

            ramses_domain = "ramses_cc"

            if ramses_domain not in hass.data:
                _LOGGER.warning("Ramses CC integration not loaded")
                return []

            # Get the first loaded Ramses entry
            ramses_entry_id = next(iter(hass.data[ramses_domain]))
            broker = hass.data[ramses_domain][ramses_entry_id]

            if not hasattr(broker, "client"):
                _LOGGER.warning("Ramses CC broker does not have client attribute")
                return []

            # Access devices through the broker's client
            gwy = broker.client

            # Discover devices using flexible handler approach
            for device in gwy.devices:
                device_ids.extend(await _handle_device(device))

            if device_ids:
                _LOGGER.info(
                    f"Successfully discovered {len(device_ids)} devices via broker"
                )
                return device_ids

            _LOGGER.warning("No supported devices found in broker")

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
        from .helpers.entity import EntityHelpers
        from .helpers.platform import (
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
                required_entities = calculate_required_entities(
                    platform, enabled_features, devices, hass
                )

                # Get all possible entity types for this platform
                all_possible_types = set()
                for device_id in devices:
                    from .helpers.device import find_ramses_device, get_device_type

                    device = find_ramses_device(hass, device_id)
                    if device:
                        device_type = get_device_type(device)
                        if device_type in DEVICE_ENTITY_MAPPING:
                            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                            platform_key = (
                                f"{platform}s"  # Convert 'sensor' -> 'sensors'
                            )
                            all_possible_types.update(
                                entity_mapping.get(platform_key, [])
                            )

                removed_count = EntityHelpers.cleanup_orphaned_entities(
                    platform, hass, devices, required_entities, list(all_possible_types)
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

    # Check what entities this device type should have
    if device.__class__.__name__ not in DEVICE_ENTITY_MAPPING:
        _LOGGER.warning(
            f"No entity mapping found for device type: {device.__class__.__name__}"
        )
        return []

    entity_mapping = DEVICE_ENTITY_MAPPING[device.__class__.__name__]

    # Check if this device type has any entities defined
    has_entities = (
        entity_mapping.get("sensors")
        or entity_mapping.get("switches")
        or entity_mapping.get("binary_sensors")
        or entity_mapping.get("numbers")
    )

    if has_entities:
        _LOGGER.info(
            f"Device {device_id} ({device.__class__.__name__}) will create entities"
        )
        return [device_id]

    _LOGGER.debug(
        f"Device {device_id} ({device.__class__.__name__}) has no entities defined"
    )
    return []


# Add more device handlers here as needed
# async def handle_hvac_controller(device: Any) -> List[str]:
#     """Handle HVAC Controller devices."""
#     return [device.id]
#
# async def handle_thermostat(device: Any) -> List[str]:
#     """Handle Thermostat devices."""
#     return [device.id]
