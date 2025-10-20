import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SWITCH_TYPES

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for switches")
        return

    switches = [RamsesDehumidifySwitch(hass, fan) for fan in fans]
    async_add_entities(switches, True)


class RamsesDehumidifySwitch(SwitchEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(self, hass, fan):
        self.hass = hass
        self._fan = fan
        self._attr_name = f"Dehumidify ({fan.id})"
        self._attr_unique_id = f"{fan.id}_dehumidify"
        self._is_on = False
        self._unsub = None

    async def async_added_to_hass(self):
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan.id}"
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
        if hasattr(self._fan, "dehumidifying"):
            return bool(getattr(self._fan, "dehumidifying"))
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Activate dehumidify mode."""
        if hasattr(self._fan, "set_dehumidify"):
            await self._fan.set_dehumidify(True)
        else:
            _LOGGER.warning("%s does not support dehumidify control", self._fan.id)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Deactivate dehumidify mode."""
        if hasattr(self._fan, "set_dehumidify"):
            await self._fan.set_dehumidify(False)
        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {"dehumidifying": self.is_on}
