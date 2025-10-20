import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for sensors")
        return

    sensors = []
    for fan in fans:
        sensors.append(RamsesExtraHumiditySensor(hass, fan, "indoor_abs_humid"))
        sensors.append(RamsesExtraHumiditySensor(hass, fan, "outdoor_abs_humid"))

    async_add_entities(sensors, True)


class RamsesExtraHumiditySensor(SensorEntity):
    """Extra sensor for absolute humidity."""

    def __init__(self, hass, fan_id: str, sensor_type: str):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._sensor_type = sensor_type
        self._attr_name = f"{SENSOR_TYPES[sensor_type]} ({fan_id})"
        self._attr_unique_id = f"{fan_id.replace(':', '_')}_{sensor_type}"  # Format: 32_153289_indoor_abs_humid
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._unsub = None


    async def async_added_to_hass(self):
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
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
        """Get temperature and humidity data from ramses_cc entities."""
        # For now, return placeholder values - in a real implementation,
        # you would query the actual ramses_cc entities for this data
        if self._sensor_type == "indoor_abs_humid":
            # Placeholder: would get from climate entity or sensor entity
            return 20.0, 50.0  # temp, rh
        else:
            # Placeholder: would get from outdoor sensor
            return 15.0, 60.0  # temp, rh

    def _calculate_abs_humidity(self, temp, rh):
        """Calculate absolute humidity using proper formula."""
        if temp is None or rh is None:
            return None
        # Absolute humidity formula: AH = (RH/100) * 6.112 * exp((17.62*T)/(243.12+T)) / (273.15+T) * 2.167
        # Where T is temperature in Celsius, RH is relative humidity in %
        saturation_pressure = 6.112 * (2.71828 ** ((17.62 * temp) / (243.12 + temp)))
        actual_pressure = (rh / 100.0) * saturation_pressure
        abs_humidity = actual_pressure * 2.167 / (273.15 + temp)
        return round(abs_humidity, 2)

    @property
    def native_unit_of_measurement(self):
        return "g/m³"
