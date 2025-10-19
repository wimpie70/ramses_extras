import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for sensors")
        return

    sensors = []
    for fan in fans:
        sensors.append(RamsesExtraHumiditySensor(fan, "indoor_abs_humid"))
        sensors.append(RamsesExtraHumiditySensor(fan, "outdoor_abs_humid"))

    async_add_entities(sensors, True)


class RamsesExtraHumiditySensor(SensorEntity):
    """Extra sensor for absolute humidity."""

    def __init__(self, hass, fan, sensor_type: str):
        self.hass = hass
        self._fan = fan
        self._sensor_type = sensor_type
        self._attr_name = f"{SENSOR_TYPES[sensor_type]} ({fan.id})"
        self._attr_unique_id = f"{fan.id}_{sensor_type}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._unsub = None


    async def async_added_to_hass(self):
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan.id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s updates for %s", signal, self.name)

    async def async_will_remove_from_hass(self):
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args, **kwargs):
        """Handle device update from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return calculated absolute humidity."""
        try:
            temp, rh = self._get_temp_and_humidity()
            return self._calculate_abs_humidity(temp, rh)
        except Exception as e:
            _LOGGER.debug("Error reading humidity for %s: %s", self._attr_name, e)
            return None

    def _get_temp_and_humidity(self):
        """Pulls data from fan device (replace these with real attributes)."""
        if self._sensor_type == "indoor_abs_humid":
            temp = getattr(self._fan, "_indoor_temp", None)
            rh = getattr(self._fan, "_indoor_humidity", None)
        else:
            temp = getattr(self._fan, "_outdoor_temp", None)
            rh = getattr(self._fan, "_outdoor_humidity", None)
        return temp, rh

    def _calculate_abs_humidity(self, temp, rh):
        """Placeholder for your real formula."""
        if temp is None or rh is None:
            return None
        # You can replace this formula with your exact one later
        return round(0.2167 * (rh / 100.0) * (6.112 * (2.71828 ** ((17.62 * temp) / (243.12 + temp))) / (273.15 + temp)), 2)

    @property
    def native_unit_of_measurement(self):
        return "g/m³"
