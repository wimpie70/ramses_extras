import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, BOOLEAN_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the binary sensor platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for binary sensors")
        return

    binary_sensors = []

    # Get enabled features from config entry
    enabled_features = config_entry.data.get("enabled_features", {})

    # Create binary sensors based on enabled features and their requirements
    for fan_id in fans:
        # Find the device type for this fan_id (in a real implementation, you'd look this up)
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Check each enabled feature to see if it needs binary sensors
            for feature_key, is_enabled in enabled_features.items():
                if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                    continue

                feature_config = AVAILABLE_FEATURES[feature_key]

                # Check if this feature supports this device type
                if device_type not in feature_config.get("supported_device_types", []):
                    continue

                # Create required binary sensors for this feature
                for boolean_type in feature_config.get("required_entities", {}).get("booleans", []):
                    if boolean_type in entity_mapping.get("booleans", []):
                        if boolean_type in BOOLEAN_CONFIGS:
                            config = BOOLEAN_CONFIGS[boolean_type]
                            binary_sensors.append(RamsesBinarySensor(hass, fan_id, boolean_type, config))

    async_add_entities(binary_sensors, True)


class RamsesBinarySensor(BinarySensorEntity):
    """Binary sensor for Ramses device states."""

    def __init__(self, hass, fan_id: str, boolean_type: str, config: dict):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._boolean_type = boolean_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        self._attr_unique_id = f"{fan_id}_{boolean_type}"
        self._attr_icon = config['icon']
        self._attr_entity_category = config['entity_category']

        self._is_on = False
        self._unsub = None

    async def async_added_to_hass(self):
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for binary sensor %s", signal, self.name)

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
        """Return true if the binary sensor state is on."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    @property
    def extra_state_attributes(self):
        return {"device_id": self._fan_id, "boolean_type": self._boolean_type}
