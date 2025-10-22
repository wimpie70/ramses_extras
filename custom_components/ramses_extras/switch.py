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
    required_entities = []  # Track which entities are actually needed
    all_possible_switches = []  # Track all possible switch types

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
            current_switches = entity_mapping.get("switches", [])
            all_possible_switches.extend(current_switches)

            # Check each possible switch type
            for switch_type in current_switches:
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
                        required_entities.append(f"switch.{fan_id}_{switch_type}")
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

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities():
        try:
            _LOGGER.info(f"Starting switch cleanup for fans: {fans}")
            _LOGGER.info(f"Entity registry available: {'entity_registry' in hass.data}")

            # Calculate which entities are currently required (inside cleanup function)
            current_required_entities = []
            device_type = "HvacVentilator"  # Define device type for cleanup
            for fan_id in fans:
                for feature_key, is_enabled in enabled_features.items():
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    if device_type not in feature_config.get("supported_device_types", []):
                        continue

                    # Check if this switch is required or optional for this feature
                    for switch_type in all_possible_switches:
                        if (switch_type in feature_config.get("required_entities", {}).get("switches", []) or
                            switch_type in feature_config.get("optional_entities", {}).get("switches", [])):
                            current_required_entities.append(f"switch.{fan_id}_{switch_type}")
                            break

            _LOGGER.info(f"Required switch entities: {current_required_entities}")

            if "entity_registry" in hass.data:
                entity_registry = hass.data["entity_registry"]
                _LOGGER.info(f"Found {len(entity_registry.entities)} entities in registry")

                # Debug: Log all switch entities for our devices
                switch_entities = [eid for eid in entity_registry.entities.keys() if eid.startswith("switch.")]
                _LOGGER.info(f"All switch entities in registry: {switch_entities}")

                # Find entities that should be removed (orphaned)
                entities_to_remove = []

                for entity_id, entity_entry in entity_registry.entities.items():
                    if not entity_id.startswith("switch."):
                        continue

                    # Extract device_id from entity_id
                    # Format: switch.{name}_{fan_id} where fan_id is 32_153289
                    parts = entity_id.split('.')
                    if len(parts) >= 2:
                        entity_name_and_fan = parts[1]  # name_fan_id

                        # Check if this entity belongs to one of our devices
                        for fan_id in fans:
                            # Convert fan_id to underscore format: 32:153289 -> 32_153289
                            fan_id_underscore = fan_id.replace(':', '_')
                            if fan_id_underscore in entity_name_and_fan:
                                # This entity belongs to our device, check if it's still needed
                                for switch_type in all_possible_switches:
                                    # Check if this switch_type is still required
                                    if f"switch.{fan_id}_{switch_type}" not in current_required_entities:
                                        entities_to_remove.append(entity_id)
                                        _LOGGER.info(f"Will remove orphaned switch: {entity_id} (type: {switch_type})")
                                        break
                                break

                _LOGGER.info(f"Found {len(entities_to_remove)} orphaned switch entities to remove")

                # Remove orphaned entities
                for entity_id in entities_to_remove:
                    try:
                        entity_registry.async_remove(entity_id)
                        _LOGGER.info(f"Removed orphaned switch entity: {entity_id}")
                    except Exception as e:
                        _LOGGER.warning(f"Failed to remove switch entity {entity_id}: {e}")
            else:
                _LOGGER.warning("Entity registry not available for switch cleanup")
        except Exception as e:
            _LOGGER.warning(f"Error during switch entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

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
