import asyncio
import logging
import shutil
from pathlib import Path
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES, INTEGRATION_DIR
from . import config_flow  # noqa: F401

_LOGGER = logging.getLogger(__name__)

# Global flag to track if static paths have been registered
_STATIC_PATHS_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Ramses Extras."""
    _LOGGER.debug("Setting up Ramses Extras integration")

    # Register static paths once globally
    global _STATIC_PATHS_REGISTERED
    if not _STATIC_PATHS_REGISTERED:
        www_path = Path(__file__).parent / "www" / "hvac-fan-card.js"
        if www_path.exists():
            from homeassistant.components.http import StaticPathConfig
            try:
                await hass.http.async_register_static_paths([
                    StaticPathConfig("/ramses_extras/hvac-fan-card.js", str(www_path), True)
                ])
                _STATIC_PATHS_REGISTERED = True
                _LOGGER.info("Registered static path for hvac-fan-card globally")
            except RuntimeError as e:
                if "already registered" in str(e):
                    _STATIC_PATHS_REGISTERED = True
                    _LOGGER.debug("Static path for hvac-fan-card already registered")
                else:
                    _LOGGER.error(f"Failed to register static path: {e}")

    return True


async def _manage_cards(hass: HomeAssistant, enabled_features: dict):
    """Install or remove custom cards based on enabled features."""
    www_community_path = Path(hass.config.path("www", "community"))

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            card_source_path = INTEGRATION_DIR / feature_config.get("folder", "")
            card_dest_path = www_community_path / feature_key

            if enabled_features.get(feature_key, False):
                if card_source_path.exists():
                    # For automatic registration, we don't need to copy files anymore
                    # The card is registered as a static resource in async_setup_entry
                    _LOGGER.info(f"Card {feature_key} is automatically registered")
                else:
                    _LOGGER.warning(f"Cannot register {feature_key}: source file not found at {card_source_path}")
            else:
                # Remove card from community folder if it exists
                await _remove_card(hass, card_dest_path)


async def _install_card(hass: HomeAssistant, source_path: Path, dest_path: Path):
    """Install a custom card by copying files."""
    try:
        if source_path.exists():
            # Create destination directory if it doesn't exist
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy all files from source to destination using executor
            await hass.async_add_executor_job(_copy_card_files, source_path, dest_path)

            _LOGGER.info(f"Successfully installed card to {dest_path}")
        else:
            _LOGGER.warning(f"Card source path does not exist: {source_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to install card: {e}")


def _copy_card_files(source_path: Path, dest_path: Path):
    """Copy card files from source to destination (runs in executor)."""
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(source_path)
            dest_file_path = dest_path / relative_path

            # Create subdirectories if needed
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file_path, dest_file_path)


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
    hass.data[DOMAIN]["entry_id"] = entry.entry_id  # Store entry_id for platform setup

    # Add to Lovelace resources for automatic discovery using proper API
    try:
        from homeassistant.components.lovelace import async_add_resource
        await async_add_resource(hass, "/ramses_extras/hvac-fan-card.js", "module")
        _LOGGER.info("Registered hvac-fan-card as Lovelace resource")
    except ImportError:
        # Fallback for older HA versions - use deprecated direct access
        try:
            hass.data.setdefault("lovelace", {})
            if isinstance(hass.data["lovelace"], dict):
                hass.data["lovelace"]["resources"] = hass.data["lovelace"].get("resources", [])

                resource = {
                    "url": "/ramses_extras/hvac-fan-card.js",
                    "type": "module",
                }

                if resource not in hass.data["lovelace"]["resources"]:
                    hass.data["lovelace"]["resources"].append(resource)
                    _LOGGER.info("Registered hvac-fan-card as Lovelace resource (fallback method)")
        except Exception as e:
            _LOGGER.warning(f"Could not register Lovelace resource (fallback): {e}. Card may not appear in dashboard editor")

    # Install/remove cards based on enabled features
    await _manage_cards(hass, entry.data.get("enabled_features", {}))

    # Initialize the platforms - handle case where ramses_rf might not be ready yet
    await async_setup_platforms(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Ramses Extras entry."""
    _LOGGER.debug("Unloading Ramses Extras entry")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle migration of a config entry."""
    _LOGGER.debug("Migrating config entry from version %s", entry.version)

    # Example: upgrade from version 1 to 2 if needed
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

        # Schedule a retry in 60 seconds (increased from 30) - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:
            async def delayed_retry():
                async_setup_platforms._is_running = False
                await async_setup_platforms(hass)

            hass.async_create_task(asyncio.sleep(60))
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

            # Get the first loaded Ramses entry (if multiple, pick one explicitly)
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
        # No fallback - if broker access fails, no devices found

async def _handle_device(device) -> list:
    """Handle a device based on its type using the configured handler."""
    device_ids = []

    # Check if this device type is supported by checking against available features
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