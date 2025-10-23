import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .helpers.entities import calculate_absolute_humidity
from .helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
    remove_orphaned_entities,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the sensor platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    _LOGGER.info(f"Setting up sensor platform for {len(fans)} fans")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping sensor setup")
        return

    if not fans:
        _LOGGER.debug("No fans available for sensors")
        return

    sensors = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

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
                    supported_types = feature_config.get("supported_device_types", [])
                    if (
                        isinstance(supported_types, list)
                        and device_type in supported_types
                    ):
                        # Check if this sensor is required or optional for this feature
                        required_entities = feature_config.get("required_entities", {})
                        optional_entities = feature_config.get("optional_entities", {})

                        if isinstance(required_entities, dict):
                            required_sensors = required_entities.get("sensors", [])
                        else:
                            required_sensors = []

                        if isinstance(optional_entities, dict):
                            optional_sensors = optional_entities.get("sensors", [])
                        else:
                            optional_sensors = []

                        if (
                            isinstance(required_sensors, list)
                            and sensor_type in required_sensors
                        ) or (
                            isinstance(optional_sensors, list)
                            and sensor_type in optional_sensors
                        ):
                            is_needed = True
                            break

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["sensor"][sensor_type]
                    sensors.append(
                        RamsesExtraHumiditySensor(hass, fan_id, sensor_type, config)
                    )
                    _LOGGER.debug(f"Creating sensor: sensor.{fan_id}_{sensor_type}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities() -> None:
        try:
            # Get all possible sensor types for this device
            all_possible_sensors = []
            for _fan_id in fans:
                device_type = "HvacVentilator"
                if device_type in DEVICE_ENTITY_MAPPING:
                    entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                    all_possible_sensors = entity_mapping.get("sensors", [])
                    break

            await remove_orphaned_entities(
                "sensor",
                hass,
                fans,
                calculate_required_entities("sensor", enabled_features, fans),
                all_possible_sensors,
            )
        except Exception as e:
            _LOGGER.warning(f"Error during sensor entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

    async_add_entities(sensors, True)


class RamsesExtraHumiditySensor(SensorEntity):
    """Extra sensor for absolute humidity."""

    def __init__(
        self,
        hass: "HomeAssistant",
        fan_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._sensor_type = sensor_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        self._attr_unique_id = (
            f"{fan_id}_{sensor_type}"  # Format: 32:153289_indoor_abs_humid
        )
        self._attr_entity_category = config["entity_category"]
        self._attr_icon = config["icon"]
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_device_class = config["device_class"]

        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s updates for %s", signal, self.name)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle device update from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return calculated absolute humidity."""
        try:
            temp, rh = self._get_temp_and_humidity()
            return self._calculate_abs_humidity(temp, rh)
        except Exception as e:
            _LOGGER.debug("Error reading humidity for %s: %s", self._attr_name, e)
            return None

    def _get_temp_and_humidity(self) -> tuple[float, float]:
        """Get temperature and humidity data from ramses_cc entities."""
        # Map sensor types to the corresponding temp/humidity entity patterns
        entity_patterns = {
            "indoor_abs_humid": ("indoor_temp", "indoor_humidity"),
            "outdoor_abs_humid": ("outdoor_temp", "outdoor_humidity"),
        }

        if self._sensor_type not in entity_patterns:
            _LOGGER.warning(
                "Unknown sensor type for humidity calculation: %s", self._sensor_type
            )
            return 20.0, 50.0  # Default fallback

        temp_type, humidity_type = entity_patterns[self._sensor_type]

        # Construct entity IDs based on the fan_id
        # ramses_cc creates entities like: sensor.32_153289_indoor_temp
        temp_entity = f"sensor.{self._fan_id.replace(':', '_')}_{temp_type}"
        humidity_entity = f"sensor.{self._fan_id.replace(':', '_')}_{humidity_type}"

        try:
            # Get temperature from ramses_cc sensor
            temp_state = self.hass.states.get(temp_entity)
            if temp_state is None:
                _LOGGER.debug("Temperature entity not found: %s", temp_entity)
                return 20.0, 50.0  # Default fallback

            temp = float(temp_state.state)

            # Get humidity from ramses_cc sensor
            humidity_state = self.hass.states.get(humidity_entity)
            if humidity_state is None:
                _LOGGER.debug("Humidity entity not found: %s", humidity_entity)
                return temp, 50.0  # Use temp but default humidity

            humidity = float(humidity_state.state)

            _LOGGER.debug(
                "Got temp/humidity for %s: temp=%s, humidity=%s from %s/%s",
                self.name,
                temp,
                humidity,
                temp_entity,
                humidity_entity,
            )

            return temp, humidity

        except (ValueError, AttributeError) as e:
            _LOGGER.debug("Error parsing temp/humidity for %s: %s", self.name, e)
            return 20.0, 50.0  # Default fallback

    def _calculate_abs_humidity(
        self, temp: float | None, rh: float | None
    ) -> float | None:
        """Calculate absolute humidity using proper formula."""
        if temp is None or rh is None:
            return None

        # Use the calculation function from our helpers
        return calculate_absolute_humidity(temp, rh)

    @property
    def native_unit_of_measurement(self) -> str:
        return "g/m³"
