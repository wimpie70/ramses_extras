import asyncio
import logging
import shutil
from pathlib import Path
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES, INTEGRATION_DIR, CARD_FOLDER
from . import config_flow  # noqa: F401

_LOGGER = logging.getLogger(__name__)

# Global flag to track if static paths have been registered
_STATIC_PATHS_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras."""
    _LOGGER.debug("Setting up Ramses Extras integration")

    global _STATIC_PATHS_REGISTERED
    if not _STATIC_PATHS_REGISTERED:
        # Only register static paths for card files that exist
        # Frontend resources will be registered dynamically in async_setup_entry based on selection
        card_features = []

        # Find all card features and check if their files exist
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get("category") == "cards":
                location = feature_config.get("location", "")
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
                        StaticPathConfig(f"/local/ramses_extras/{feature_key}", str(card_path.parent), True)
                    )

                if static_configs:
                    await hass.http.async_register_static_paths(static_configs)
                    _STATIC_PATHS_REGISTERED = True
                    _LOGGER.info(f"Registered static paths for {len(card_features)} card features")

            except RuntimeError as e:
                if "already registered" in str(e):
                    _STATIC_PATHS_REGISTERED = True
                    _LOGGER.debug("Static paths for cards already registered")
                else:
                    _LOGGER.error(f"Failed to register static paths: {e}")
        else:
            _LOGGER.warning("No card features found in AVAILABLE_FEATURES")

    return True

async def _register_enabled_card_resources(hass: HomeAssistant, enabled_features: dict):
    """Register frontend resources for enabled card features only."""
    _LOGGER.debug("Registering enabled card resources")

    enabled_cards = []
    disabled_cards = []

    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            if enabled_features.get(feature_key, False):
                location = feature_config.get("location", "")
                if location:
                    card_path = INTEGRATION_DIR / CARD_FOLDER / location
                    if card_path.exists():
                        resource_url = f"/local/ramses_extras/{feature_key}/{card_path.name}"
                        enabled_cards.append((feature_key, resource_url))
                    else:
                        _LOGGER.warning(f"Card file not found for enabled card {feature_key}: {card_path}")
                else:
                    _LOGGER.warning(f"No location specified for enabled card {feature_key}")
            else:
                disabled_cards.append(feature_key)

    # Register enabled cards
    for feature_key, resource_url in enabled_cards:
        try:
            from homeassistant.components import frontend
            await hass.async_add_executor_job(
                frontend.add_extra_js_url,
                hass,
                resource_url
            )
            _LOGGER.info(f"Registered enabled card resource: {resource_url}")
        except Exception as e:
            _LOGGER.warning(f"Could not register resource {resource_url}: {e}")

    # Log disabled cards for clarity
    if disabled_cards:
        _LOGGER.info(f"Cards disabled (not loaded): {disabled_cards}")

    if enabled_cards:
        _LOGGER.info(f"Dynamically loaded {len(enabled_cards)} enabled cards based on config selection")
    else:
        _LOGGER.info("No cards are currently enabled in config flow")


async def _manage_cards(hass: HomeAssistant, enabled_features: dict):
    """Install or remove custom cards based on enabled features."""
    www_community_path = Path(hass.config.path("www", "community"))

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            # Use the same path resolution as the rest of the code
            card_source_path = INTEGRATION_DIR / CARD_FOLDER / feature_config.get("location", "")
            card_dest_path = www_community_path / feature_key

            if enabled_features.get(feature_key, False):
                if card_source_path.exists():
                    _LOGGER.info(f"Card {feature_key} is automatically registered")
                else:
                    _LOGGER.warning(f"Cannot register {feature_key}: source file not found at {card_source_path}")
            else:
                # Remove card from community folder if it exists
                await _remove_card(hass, card_dest_path)


async def _remove_card(hass: HomeAssistant, card_path: Path):
    """Remove a custom card."""
    try:
        if card_path.exists():
            await hass.async_add_executor_job(shutil.rmtree, card_path)
            _LOGGER.info(f"Successfully removed card from {card_path}")
        else:
            _LOGGER.debug(f"Card path does not exist, nothing to remove: {card_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to remove card: {e}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up entry for Ramses Extras."""
    _LOGGER.debug("Setting up entry for Ramses Extras")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    # Register enabled card resources dynamically
    await _register_enabled_card_resources(hass, entry.data.get("enabled_features", {}))

    # Install/remove cards based on enabled features
    await _manage_cards(hass, entry.data.get("enabled_features", {}))

    # Initialize the platforms
    await async_setup_platforms(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Ramses Extras entry."""
    _LOGGER.debug("Unloading Ramses Extras entry")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "switch", "binary_sensor"]
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle migration of a config entry."""
    _LOGGER.debug("Migrating config entry from version %s", entry.version)

    if entry.version < 2:
        new_data = {**entry.data}
        hass.config_entries.async_update_entry(entry, version=2, data=new_data)

    _LOGGER.debug("Migration to version %s successful", entry.version)
    return True


async def async_setup_platforms(hass: HomeAssistant):
    """Find Ramses FAN devices and register extras."""
    # Prevent multiple simultaneous setup attempts
    if hasattr(async_setup_platforms, '_is_running') and async_setup_platforms._is_running:
        _LOGGER.debug("Setup already in progress, skipping")
        return

    async_setup_platforms._is_running = True

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

                if not hass.data[DOMAIN].get("platforms_loaded"):
                    # Load platforms using proper Home Assistant platform loading
                    _LOGGER.info("Loading sensor and switch platforms...")

                    # Get the entry for this integration
                    entry = hass.config_entries.async_get_entry(hass.data[DOMAIN]["entry_id"])

                    # Load platforms properly
                    await hass.config_entries.async_forward_entry_setups(
                        entry, ["sensor", "switch", "binary_sensor"]
                    )

                    hass.data[DOMAIN]["platforms_loaded"] = True
                    _LOGGER.info("Platforms loaded successfully")
                return
            else:
                _LOGGER.info("No Ramses devices found in entity registry")
        else:
            _LOGGER.info("Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:
            async def delayed_retry():
                async_setup_platforms._is_running = False
                await async_setup_platforms(hass)

            await asyncio.sleep(60)
            hass.async_create_task(delayed_retry())
        else:
            _LOGGER.info("Ramses CC is loaded but no devices found, not retrying")
    finally:
        async_setup_platforms._is_running = False


async def _discover_ramses_devices(hass: HomeAssistant):
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
                _LOGGER.info(f"Successfully discovered {len(device_ids)} devices via broker")
                return device_ids

            _LOGGER.warning("No supported devices found in broker")

    except Exception as e:
        _LOGGER.warning("Error discovering Ramses devices: %s", e)

    return device_ids


async def _handle_device(device) -> list:
    """Handle a device based on its type using the configured handler."""
    device_ids = []

    # Check if this device type is supported
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if device.__class__.__name__ in feature_config.get("supported_device_types", []):
            handler_name = feature_config.get("handler", "handle_hvac_ventilator")
            handler = globals().get(handler_name)
            if handler:
                result = await handler(device)
                if result:
                    device_ids.extend(result)
                    _LOGGER.info(f"Handled {device.__class__.__name__} device: {device.id}")
            else:
                _LOGGER.warning(f"No handler found for {device.__class__.__name__}: {handler_name}")
            break

    return device_ids


async def handle_hvac_ventilator(device) -> list:
    """Handle HVAC Ventilator devices - create entities based on mapping."""
    device_id = device.id

    # Check what entities this device type should have
    if device.__class__.__name__ not in DEVICE_ENTITY_MAPPING:
        _LOGGER.warning(f"No entity mapping found for device type: {device.__class__.__name__}")
        return []

    entity_mapping = DEVICE_ENTITY_MAPPING[device.__class__.__name__]

    # Check if this device type has any entities defined
    has_entities = (
        entity_mapping.get("sensors") or
        entity_mapping.get("switches") or
        entity_mapping.get("booleans")
    )

    return [device_id] if has_entities else []
    
# Add more device handlers here as needed
# async def handle_hvac_controller(device) -> list:
#     """Handle HVAC Controller devices."""
#     return [device.id]
#
# async def handle_thermostat(device) -> list:
#     """Handle Thermostat devices."""
#     return [device.id]