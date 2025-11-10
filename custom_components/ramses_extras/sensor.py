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
from .framework.base_classes import ExtrasBaseEntity
from .framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)
from .framework.helpers.entities import calculate_absolute_humidity
from .framework.helpers.entity.core import EntityHelpers
from .framework.helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
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
    _LOGGER.info("Starting sensor platform setup")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping sensor setup")
        return

    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    if not devices:
        _LOGGER.warning("No devices available for sensors")
        return

    sensors = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(f"Device {device_id} not found, skipping sensor creation")
            continue

        device_type = get_device_type(device)

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
            all_possible_sensors = entity_mapping.get("sensors", [])

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
                    config = ENTITY_TYPE_CONFIGS["sensor"][sensor_type]
                    sensors.append(
                        RamsesExtraHumiditySensor(hass, device_id, sensor_type, config)
                    )

    async_add_entities(sensors, True)


class RamsesExtraHumiditySensor(SensorEntity, ExtrasBaseEntity):
    """Extra sensor for absolute humidity."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, sensor_type, config)

        # Set sensor-specific attributes
        self._sensor_type = sensor_type
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_device_class = config["device_class"]

        # Set unique_id to prevent duplicate entities
        self._attr_unique_id = f"{sensor_type}_{device_id.replace(':', '_')}"

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle device update from Ramses RF."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return calculated absolute humidity."""
        try:
            temp, rh = self._get_temp_and_humidity()
            result = self._calculate_abs_humidity(temp, rh)
            return result if result is not None else None
        except Exception as e:
            _LOGGER.debug("Error reading humidity for %s: %s", self._attr_name, e)
            return None

    def _get_temp_and_humidity(self) -> tuple[float | None, float | None]:
        """Get temperature and humidity data from ramses_cc entities.

        Returns:
            tuple: (temperature, humidity) or (None, None) if sensors are missing/failed
        """
        # Map sensor types to the corresponding temp/humidity entity patterns
        entity_patterns = {
            "indoor_absolute_humidity": ("indoor_temp", "indoor_humidity"),
            "outdoor_absolute_humidity": ("outdoor_temp", "outdoor_humidity"),
        }

        if self._sensor_type not in entity_patterns:
            _LOGGER.error(
                "Unknown sensor type for humidity calculation: %s", self._sensor_type
            )
            return None, None

        temp_type, humidity_type = entity_patterns[self._sensor_type]

        # Construct entity IDs based on the device_id
        temp_entity = f"sensor.{self._device_id.replace(':', '_')}_{temp_type}"
        humidity_entity = f"sensor.{self._device_id.replace(':', '_')}_{humidity_type}"

        try:
            # Get temperature from ramses_cc sensor
            temp_state = self.hass.states.get(temp_entity)
            if temp_state is None or temp_state.state in ("unavailable", "unknown"):
                return None, None

            temp = float(temp_state.state)

            # Get humidity from ramses_cc sensor
            humidity_state = self.hass.states.get(humidity_entity)
            if humidity_state is None or humidity_state.state in (
                "unavailable",
                "unknown",
            ):
                return None, None

            humidity = float(humidity_state.state)

            # Validate humidity range
            if not (0 <= humidity <= 100):
                _LOGGER.error(
                    "Invalid humidity value %.1f%% for %s (must be 0-100%%)",
                    humidity,
                    self._attr_name,
                )
                return None, None

            return temp, humidity

        except (ValueError, AttributeError) as e:
            _LOGGER.debug(
                "Error parsing temp/humidity for %s: %s",
                self._attr_name,
                e,
            )
            return None, None

    def _calculate_abs_humidity(
        self, temp: float | None, rh: float | None
    ) -> float | None:
        """Calculate absolute humidity using proper formula."""
        if temp is None or rh is None:
            return None

        # Use the calculation function from our helpers
        result = calculate_absolute_humidity(temp, rh)
        return float(result) if result is not None else None

    @property
    def native_unit_of_measurement(self) -> str:
        return "g/m³"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "sensor_type": self._sensor_type}
