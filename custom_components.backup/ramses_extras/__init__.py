import logging
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from . import websocket_api as ws

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Ramses Extras integration."""
    _LOGGER.info("Setting up %s", DOMAIN)
    ws.register_ws_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up entry for Ramses Extras."""
    _LOGGER.debug("Setting up entry for Ramses Extras")
    return True


async def async_setup_platforms(hass: HomeAssistant):
    """Find Ramses FAN devices and register extras."""
    ramses_data = hass.data.get("ramses_rf")
    if not ramses_data:
        _LOGGER.warning("Ramses RF not found, skipping Ramses Extras setup.")
        return

    fans = []
    for entry_id, data in ramses_data.items():
        broker = data.get("broker")
        if not broker:
            continue
        devices = getattr(broker, "devices", {})
        for dev in devices.values():
            if dev.__class__.__name__.lower().startswith("hvacventilator"):
                fans.append(dev)

    if not fans:
        _LOGGER.info("No FAN devices found for Ramses Extras.")
        return

    _LOGGER.info("Found %d FAN devices", len(fans))

    hass.data.setdefault(DOMAIN, {})["fans"] = fans

    for platform in ("sensor", "switch"):
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, {}))