import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, ENTITY_TYPE_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the switch platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for switches")
        return

    switches = []

    # Get enabled features from config entry
    enabled_features = config_entry.data.get("enabled_features", {})

    # Create switches based on enabled features and their requirements
    for fan_id in fans:
        # Find the device type for this fan_id (in a real implementation, you'd look this up)
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Check each enabled feature to see if it needs switches
            for feature_key, is_enabled in enabled_features.items():
                if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                    continue

                feature_config = AVAILABLE_FEATURES[feature_key]

                # Check if this feature supports this device type
                if device_type not in feature_config.get("supported_device_types", []):
                    continue

                # Create required switches for this feature
                for switch_type in feature_config.get("required_entities", {}).get("switches", []):
                    if switch_type in entity_mapping.get("switches", []):
                        if switch_type in ENTITY_TYPE_CONFIGS["switch"]:
                            config = ENTITY_TYPE_CONFIGS["switch"][switch_type]
                            switches.append(RamsesDehumidifySwitch(hass, fan_id, switch_type, config))

                # Create optional switches for this feature if they exist in mapping
                for switch_type in feature_config.get("optional_entities", {}).get("switches", []):
                    if switch_type in entity_mapping.get("switches", []):
                        if switch_type in ENTITY_TYPE_CONFIGS["switch"]:
                            config = ENTITY_TYPE_CONFIGS["switch"][switch_type]
                            switches.append(RamsesDehumidifySwitch(hass, fan_id, switch_type, config))

    async_add_entities(switches, True)


class RamsesDehumidifySwitch(SwitchEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(self, hass, fan_id: str, switch_type: str, config: dict):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._switch_type = switch_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        self._attr_unique_id = f"{fan_id}_dehumidify"
        self._attr_icon = config['icon']
        self._attr_entity_category = config['entity_category']

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
