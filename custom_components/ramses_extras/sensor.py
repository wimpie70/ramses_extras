import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, ENTITY_TYPE_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for sensors")
        return

    sensors = []

    # Get enabled features from config entry
    enabled_features = config_entry.data.get("enabled_features", {})

    # Create sensors based on enabled features and their requirements
    for fan_id in fans:
        # Find the device type for this fan_id (in a real implementation, you'd look this up)
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Check each enabled feature to see if it needs sensors
            for feature_key, is_enabled in enabled_features.items():
                if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                    continue

                feature_config = AVAILABLE_FEATURES[feature_key]

                # Check if this feature supports this device type
                if device_type not in feature_config.get("supported_device_types", []):
                    continue

                # Create required sensors for this feature
                for sensor_type in feature_config.get("required_entities", {}).get("sensors", []):
                    if sensor_type in entity_mapping.get("sensors", []):
                        if sensor_type in ENTITY_TYPE_CONFIGS["sensor"]:
                            config = ENTITY_TYPE_CONFIGS["sensor"][sensor_type]
                            sensors.append(RamsesExtraHumiditySensor(hass, fan_id, sensor_type, config))

                # Create optional sensors for this feature if they exist in mapping
                for sensor_type in feature_config.get("optional_entities", {}).get("sensors", []):
                    if sensor_type in entity_mapping.get("sensors", []):
                        if sensor_type in ENTITY_TYPE_CONFIGS["sensor"]:
                            config = ENTITY_TYPE_CONFIGS["sensor"][sensor_type]
                            sensors.append(RamsesExtraHumiditySensor(hass, fan_id, sensor_type, config))

    async_add_entities(sensors, True)


class RamsesExtraHumiditySensor(SensorEntity):
    """Extra sensor for absolute humidity."""

    def __init__(self, hass, fan_id: str, sensor_type: str, config: dict):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._sensor_type = sensor_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        self._attr_unique_id = f"{fan_id.replace(':', '_')}_{sensor_type}"  # Format: 32_153289_indoor_abs_humid
        self._attr_entity_category = config['entity_category']
        self._attr_icon = config['icon']
        self._attr_native_unit_of_measurement = config['unit']
        self._attr_device_class = config['device_class']

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
