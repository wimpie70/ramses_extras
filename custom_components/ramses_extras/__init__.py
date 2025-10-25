import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    DEVICE_ENTITY_MAPPING,
    DEVICE_SERVICE_MAPPING,
    DOMAIN,
    INTEGRATION_DIR,
)
from .managers import FeatureManager
from .managers.automation_manager import AutomationManager
from .managers.card_manager import CardManager
from .managers.entity_manager import EntityManager

if TYPE_CHECKING:
    pass

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


async def _register_services(
    hass: HomeAssistant, feature_manager: FeatureManager
) -> None:
    """Register services based on enabled features and discovered devices."""
    from .helpers.device import (
        find_ramses_device,
        get_all_device_ids,
        get_device_type,
        validate_device_for_service,
    )
    from .services import fan_services

    # Get discovered devices
    device_ids = get_all_device_ids(hass)

    if device_ids:
        # Register services for discovered device types
        for device_id in device_ids:
            device = find_ramses_device(hass, device_id)
            if device:
                device_type = get_device_type(device)
                if device_type in DEVICE_SERVICE_MAPPING:
                    services_for_device = DEVICE_SERVICE_MAPPING[device_type]
                    for service_name in services_for_device:
                        if service_name == "set_fan_speed_mode":
                            fan_services.register_fan_services(hass)
                            _LOGGER.info(
                                f"Registered fan services for device {device_id} "
                                f"({device_type})"
                            )
                            return  # Only need to register once

    _LOGGER.debug("No services registered - no supported devices found")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry for Ramses Extras."""
    _LOGGER.debug("Setting up entry for Ramses Extras")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})

    # Register enabled card resources dynamically
    await _register_enabled_card_resources(hass, entry.data.get("enabled_features", {}))

    # Discover devices and set up platforms
    await async_setup_platforms(hass)

    # Load platforms for this config entry
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Ramses Extras entry."""
    _LOGGER.debug("Unloading Ramses Extras entry")

    # Clean up humidity automations when feature is disabled
    enabled_features = entry.data.get("enabled_features", {})
    if enabled_features.get("humidity_control", False):
        await _cleanup_humidity_automations(hass)

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
                    if device_type in DEVICE_SERVICE_MAPPING:
                        services_for_device = DEVICE_SERVICE_MAPPING[device_type]
                        for service_name in services_for_device:
                            if service_name == "set_fan_speed_mode":
                                # Unregister the service
                                hass.services.async_remove(DOMAIN, service_name)
                                _LOGGER.info(
                                    "Unregistered %s service for device %s (%s)",
                                    service_name,
                                    device_id,
                                    device_type,
                                )
                                break

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
        _LOGGER.info("Looking for Ramses devices using ramses_cc entity discovery...")

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        if ramses_cc_loaded:
            _LOGGER.info("Ramses CC is loaded, discovering devices from entities...")

            # Discover devices by looking for ramses_cc entities
            device_ids = await _discover_ramses_devices(hass)

            if device_ids:
                _LOGGER.info("Found %d Ramses devices: %s", len(device_ids), device_ids)
                hass.data.setdefault(DOMAIN, {})["fans"] = device_ids

                # Initialize managers
                feature_manager = FeatureManager(hass)
                card_manager = CardManager(hass)
                entity_manager = EntityManager(hass)
                automation_manager = AutomationManager(hass)

                # Load current feature state
                config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
                if config_entry:
                    feature_manager.load_enabled_features(config_entry)

                # Get enabled features by category
                enabled_cards = feature_manager.get_enabled_cards()
                # enabled_automations = feature_manager.get_enabled_automations()  # noqa: E501  # TODO: implement

                # Install enabled cards
                await card_manager.install_cards(enabled_cards)

                # Set up entities and automations
                await _setup_entities_and_automations(
                    hass,
                    device_ids,
                    feature_manager,
                    entity_manager,
                    automation_manager,
                    config_entry,
                )

                # Register services for discovered devices
                await _register_services(hass, feature_manager)

                return
            _LOGGER.info("No Ramses devices found in entity registry")
        else:
            _LOGGER.info("Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:

            async def delayed_retry() -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            await asyncio.sleep(60)
            hass.async_create_task(delayed_retry())
        else:
            _LOGGER.info("Ramses CC is loaded but no devices found, not retrying")
    finally:
        _setup_in_progress = False


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
                "ramses_extras_dehumidifier_"
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
