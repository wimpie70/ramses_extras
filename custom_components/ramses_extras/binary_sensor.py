import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, BOOLEAN_CONFIGS, DEVICE_ENTITY_MAPPING, AVAILABLE_FEATURES
from .helpers.platform import (
    get_enabled_features,
    calculate_required_entities,
    remove_orphaned_entities,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: "HomeAssistant", config_entry: Optional[ConfigEntry], async_add_entities: "AddEntitiesCallback") -> None:
    """Set up the binary sensor platform."""
    _LOGGER.info(f"Setting up binary_sensor platform for {len(hass.data.get(DOMAIN, {}).get('fans', []))} fans")

    # Check if config entry is available (it might not be during initial load)
    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping binary_sensor setup")
        return

    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    if not fans:
        _LOGGER.debug("No fans available for binary sensors")
        return

    binary_sensors = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create binary sensors based on enabled features and their requirements
    for fan_id in fans:
        device_type = "HvacVentilator"

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible binary sensor types for this device
            all_possible_booleans = entity_mapping.get("booleans", [])

            # Check each possible binary sensor type
            for boolean_type in all_possible_booleans:
                if boolean_type not in BOOLEAN_CONFIGS:
                    continue

                # Check if this binary sensor is needed by any enabled feature
                is_needed = False
                for feature_key, is_enabled in enabled_features.items():
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    supported_types = feature_config.get("supported_device_types", [])
                    if isinstance(supported_types, list) and device_type in supported_types:

                        # Check if this binary sensor is required for this feature
                        required_entities = feature_config.get("required_entities", {})

                        if isinstance(required_entities, dict):
                            required_booleans = required_entities.get("booleans", [])
                        else:
                            required_booleans = []

                        if isinstance(required_booleans, list) and boolean_type in required_booleans:
                            is_needed = True
                            break

                if is_needed:
                    # Entity is needed - create it
                    config = BOOLEAN_CONFIGS[boolean_type]
                    binary_sensors.append(RamsesBinarySensor(hass, fan_id, boolean_type, config))
                    _LOGGER.debug(f"Creating binary sensor: binary_sensor.{fan_id}_{boolean_type}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities() -> None:
        try:
            # Get all possible binary sensor types for this device
            all_possible_booleans = []
            for fan_id in fans:
                device_type = "HvacVentilator"
                if device_type in DEVICE_ENTITY_MAPPING:
                    entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                    all_possible_booleans = entity_mapping.get("booleans", [])
                    break

            await remove_orphaned_entities("binary_sensor", hass, fans, calculate_required_entities("binary_sensor", enabled_features, fans), all_possible_booleans)
        except Exception as e:
            _LOGGER.warning(f"Error during binary_sensor entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

    async_add_entities(binary_sensors, True)


class RamsesBinarySensor(BinarySensorEntity):
    """Binary sensor for Ramses device states."""

    def __init__(self, hass: "HomeAssistant", fan_id: str, boolean_type: str, config: Dict[str, Any]):
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

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for binary sensor %s", signal, self.name)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None  # type: ignore[unreachable]

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor state is on."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"device_id": self._fan_id, "boolean_type": self._boolean_type}
