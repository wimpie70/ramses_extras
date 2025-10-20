import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the switch platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for switches")
        return

    switches = [RamsesDehumidifySwitch(hass, fan) for fan in fans]
    async_add_entities(switches, True)


class RamsesDehumidifySwitch(SwitchEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(self, hass, fan_id: str):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._attr_name = f"Dehumidify ({fan_id})"
        self._attr_unique_id = f"{fan_id}_dehumidify"
        self._is_on = False
        self._unsub = None

    async def async_added_to_hass(self):
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for switch %s", signal, self.name)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args, **kwargs):
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Return true if dehumidify is active."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Activate dehumidify mode."""
        # For now, just update local state since we don't have device access
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Deactivate dehumidify mode."""
        # For now, just update local state since we don't have device access
        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {"dehumidifying": self.is_on}
