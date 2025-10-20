import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from . import websocket_api as ws
from . import config_flow  # noqa: F401

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Ramses Extras integration."""
    _LOGGER.info("Setting up %s", DOMAIN)

    # Register websocket commands
    ws.register_ws_commands(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up entry for Ramses Extras."""
    _LOGGER.debug("Setting up entry for Ramses Extras")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    # Initialize the platforms - handle case where ramses_rf might not be ready yet
    await async_setup_platforms(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Ramses Extras entry."""
    _LOGGER.debug("Unloading Ramses Extras entry")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


async def async_setup_platforms(hass: HomeAssistant):
    """Find Ramses FAN devices and register extras."""
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

            # Load platforms - use the modern approach
            from homeassistant.helpers import discovery
            for platform in ("sensor", "switch"):
                discovery.load_platform(hass, DOMAIN, platform, {}, hass.config)

            return
        else:
            _LOGGER.info("No Ramses devices found in entity registry")
    else:
        _LOGGER.info("Ramses CC not loaded yet, will retry in 30 seconds.")

    # Schedule a retry in 30 seconds
    async def delayed_retry():
        await asyncio.sleep(30)
        await async_setup_platforms(hass)

    hass.async_create_task(delayed_retry())


async def _discover_ramses_devices(hass: HomeAssistant):
    """Discover Ramses devices by looking at ramses_cc entities."""
    device_ids = []

    try:
        # Access the entity registry to find ramses_cc entities
        from homeassistant.helpers import entity_registry, device_registry

        ent_reg = entity_registry.async_get(hass)
        dev_reg = device_registry.async_get(hass)

        # Look for entities created by ramses_cc
        for entity_id, entity_entry in ent_reg.entities.items():
            # Check if this entity was created by ramses_cc
            if (hasattr(entity_entry, 'platform') and
                entity_entry.platform == 'ramses_cc'):

                # Get the device associated with this entity
                if entity_entry.device_id:
                    try:
                        device = dev_reg.async_get_device(entity_entry.device_id)

                        if device and hasattr(device, 'identifiers'):
                            # Check if this device has Ramses identifiers
                            for identifier in device.identifiers:
                                if any('ramses' in str(id_part).lower() for id_part in identifier):
                                    device_ids.append(entity_entry.device_id)
                                    break
                    except Exception as e:
                        _LOGGER.debug("Error getting device %s: %s", entity_entry.device_id, e)

    except Exception as e:
        _LOGGER.warning("Error discovering Ramses devices: %s", e)

    return device_ids