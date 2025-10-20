import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES
from . import config_flow  # noqa: F401

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up entry for Ramses Extras."""
    _LOGGER.debug("Setting up entry for Ramses Extras")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id  # Store entry_id for platform setup

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

                # Load platforms using proper Home Assistant platform loading
                _LOGGER.info("Loading sensor and switch platforms...")

                # Get the entry for this integration
                entry = hass.config_entries.async_get_entry(hass.data[DOMAIN]["entry_id"])

                # Load platforms properly - check if already loaded first
                if not hass.data[DOMAIN].get("platforms_loaded", False):
                    _LOGGER.info("Loading sensor and switch platforms...")

                    # Get the entry for this integration
                    entry = hass.config_entries.async_get_entry(hass.data[DOMAIN]["entry_id"])

                    # Load platforms properly
                    await hass.config_entries.async_forward_entry_setups(
                        entry, ["sensor", "switch"]
                    )

                    hass.data[DOMAIN]["platforms_loaded"] = True
                    _LOGGER.info("Platforms loaded successfully")
                else:
                    _LOGGER.debug("Platforms already loaded, skipping")
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

    # For now, just return the device ID for each entity type
    # In a more sophisticated implementation, this could check device capabilities
    entities_needed = []

    # Add sensors
    for sensor_type in entity_mapping.get("sensors", []):
        entities_needed.append(f"sensor_{device_id}_{sensor_type}")

    # Add switches
    for switch_type in entity_mapping.get("switches", []):
        entities_needed.append(f"switch_{device_id}_{switch_type}")

    return [device_id] if entities_needed else []


# Add more device handlers here as needed
# async def handle_hvac_controller(device) -> list:
#     """Handle HVAC Controller devices."""
#     return [device.id]
#
# async def handle_thermostat(device) -> list:
#     """Handle Thermostat devices."""
#     return [device.id]