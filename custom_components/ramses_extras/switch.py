import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, ENTITY_TYPE_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the switch platform."""
    _LOGGER.info(f"Setting up switch platform for {len(hass.data.get(DOMAIN, {}).get('fans', []))} fans")

    # Check if config entry is available (it might not be during initial load)
    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping switch setup")
        return

    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for switches")
        return

    switches = []
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
        async_add_entities(switches, True)
        return

    entity_registry = hass.data["entity_registry"]

    # Create switches based on enabled features and their requirements
    for fan_id in fans:
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible switch types for this device
            all_possible_switches = entity_mapping.get("switches", [])

            # Check each possible switch type
            for switch_type in all_possible_switches:
                if switch_type not in ENTITY_TYPE_CONFIGS["switch"]:
                    continue

                # Check if this switch is needed by any enabled feature
                is_needed = False
                for feature_key, is_enabled in enabled_features.items():
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    if device_type not in feature_config.get("supported_device_types", []):
                        continue

                    # Check if this switch is required or optional for this feature
                    if (switch_type in feature_config.get("required_entities", {}).get("switches", []) or
                        switch_type in feature_config.get("optional_entities", {}).get("switches", [])):
                        is_needed = True
                        break

                # Build entity ID for this switch (format: switch.{unique_id})
                entity_id = f"switch.{fan_id}_{switch_type}"

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["switch"][switch_type]
                    switches.append(RamsesDehumidifySwitch(hass, fan_id, switch_type, config))
                    _LOGGER.debug(f"Creating switch: {entity_id}")
                else:
                    # Entity is not needed - check if it exists and mark for removal
                    if entity_id in entity_registry.entities:
                        entities_to_remove.add(entity_id)
                        _LOGGER.debug(f"Will remove unneeded switch: {entity_id}")

    # Remove orphaned entities
    for entity_id in entities_to_remove:
        try:
            entity_registry.async_remove(entity_id)
            _LOGGER.info(f"Removed orphaned switch entity: {entity_id}")
        except Exception as e:
            _LOGGER.warning(f"Failed to remove switch entity {entity_id}: {e}")

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
