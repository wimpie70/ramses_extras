import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, ENTITY_TYPE_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


async def _get_required_entities_for_features(enabled_features, fans):
    """Calculate which entities are required by the enabled features."""
    required_entities = set()

    for fan_id in fans:
        device_type = "HvacVentilator"  # In real implementation, look this up

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            for feature_key, is_enabled in enabled_features.items():
                if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                    continue

                feature_config = AVAILABLE_FEATURES[feature_key]

                if device_type not in feature_config.get("supported_device_types", []):
                    continue

                # Add required sensor entities
                for sensor_type in feature_config.get("required_entities", {}).get("sensors", []):
                    if sensor_type in entity_mapping.get("sensors", []):
                        required_entities.add(f"sensor.{fan_id}_{sensor_type}")

                # Add optional sensor entities
                for sensor_type in feature_config.get("optional_entities", {}).get("sensors", []):
                    if sensor_type in entity_mapping.get("sensors", []):
                        required_entities.add(f"sensor.{fan_id}_{sensor_type}")

    return required_entities


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    _LOGGER.info(f"Setting up sensor platform for {len(hass.data.get(DOMAIN, {}).get('fans', []))} fans")

    # Check if config entry is available (it might not be during initial load)
    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping sensor setup")
        return

    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for sensors")
        return

    sensors = []
    entities_to_remove = set()

    # Get enabled features from config entry
    enabled_features = config_entry.data.get("enabled_features", {})

    # Fallback: try to get from hass.data if config_entry doesn't have it
    if not enabled_features and DOMAIN in hass.data:
        entry_id = hass.data[DOMAIN].get("entry_id")
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry:
                enabled_features = entry.data.get("enabled_features", {})

    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Get entity registry for cleanup (may not be available during initial setup)
    if "entity_registry" not in hass.data:
        _LOGGER.warning("Entity registry not available, skipping cleanup")
        async_add_entities(sensors, True)
        return

    entity_registry = hass.data["entity_registry"]

    # Create sensors based on enabled features and their requirements
    for fan_id in fans:
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible sensor types for this device
            all_possible_sensors = entity_mapping.get("sensors", [])

            # Check each possible sensor type
            for sensor_type in all_possible_sensors:
                if sensor_type not in ENTITY_TYPE_CONFIGS["sensor"]:
                    continue

                # Check if this sensor is needed by any enabled feature
                is_needed = False
                for feature_key, is_enabled in enabled_features.items():
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    if device_type not in feature_config.get("supported_device_types", []):
                        continue

                    # Check if this sensor is required or optional for this feature
                    if (sensor_type in feature_config.get("required_entities", {}).get("sensors", []) or
                        sensor_type in feature_config.get("optional_entities", {}).get("sensors", [])):
                        is_needed = True
                        break

                # Build entity ID for this sensor (format: sensor.{unique_id})
                entity_id = f"sensor.{fan_id}_{sensor_type}"

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["sensor"][sensor_type]
                    sensors.append(RamsesExtraHumiditySensor(hass, fan_id, sensor_type, config))
                    _LOGGER.debug(f"Creating sensor: {entity_id}")
                else:
                    # Entity is not needed - check if it exists and mark for removal
                    if entity_id in entity_registry.entities:
                        entities_to_remove.add(entity_id)
                        _LOGGER.debug(f"Will remove unneeded sensor: {entity_id}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities():
        try:
            if "entity_registry" in hass.data:
                entity_registry = hass.data["entity_registry"]
                # Calculate which entities are currently required
                required_entities = await _get_required_entities_for_features(enabled_features, fans)

                # Find entities that should be removed (orphaned)
                entities_to_remove = []
                domain_prefix = f"{DOMAIN}."

                for entity_id, entity_entry in entity_registry.entities.items():
                    if not entity_id.startswith(domain_prefix):
                        continue

                    # Extract device_id and entity type from entity_id
                    # Format: ramses_extras.32_153289_indoor_temp
                    parts = entity_id.split('.')
                    if len(parts) >= 3:
                        device_entity_part = parts[1]  # 32_153289_indoor_temp

                        # Convert device_id format: 32_153289 -> 32:153289
                        device_id_underscore = device_entity_part.split('_')[0]  # 32_153289
                        device_id_colon = device_id_underscore.replace('_', ':')  # 32:153289

                        # Check if this entity is still needed
                        if device_id_colon in fans:
                            entity_type = '_'.join(device_entity_part.split('_')[1:])  # indoor_temp

                            # Build expected entity ID
                            expected_entity_id = f"sensor.{device_id_underscore}_{entity_type}"

                            if expected_entity_id not in required_entities:
                                entities_to_remove.append(entity_id)
                                _LOGGER.info(f"Will remove orphaned entity: {entity_id}")

                # Remove orphaned entities
                for entity_id in entities_to_remove:
                    try:
                        entity_registry.async_remove(entity_id)
                        _LOGGER.info(f"Removed orphaned entity: {entity_id}")
                    except Exception as e:
                        _LOGGER.warning(f"Failed to remove entity {entity_id}: {e}")
        except Exception as e:
            _LOGGER.warning(f"Error during entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

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
        self._attr_unique_id = f"{fan_id}_{sensor_type}"  # Format: 32:153289_indoor_abs_humid
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
