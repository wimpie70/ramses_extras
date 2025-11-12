import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import AVAILABLE_FEATURES, DOMAIN
from .extras_registry import extras_registry
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

    # Get entity definitions from EntityRegistry
    all_device_mappings = extras_registry.get_all_device_mappings()
    all_sensor_configs = extras_registry.get_all_sensor_configs()

    _LOGGER.info(f"Creating sensors for {len(devices)} devices")
    _LOGGER.info(f"Available device mappings: {list(all_device_mappings.keys())}")
    _LOGGER.info(f"Available sensor configs: {list(all_sensor_configs.keys())}")

    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(f"Device {device_id} not found, skipping sensor creation")
            continue

        device_type = get_device_type(device)
        _LOGGER.info(f"Processing device {device_id} of type {device_type}")

        if device_type in all_device_mappings:
            entity_mapping = all_device_mappings[device_type]
            sensors_for_device = entity_mapping.get("sensors", [])
            _LOGGER.info(
                f"Device {device_id} ({device_type}) should have sensors: "
                f"{sensors_for_device}"
            )

            for sensor_type in sensors_for_device:
                if sensor_type not in all_sensor_configs:
                    _LOGGER.warning(
                        f"Sensor type {sensor_type} not found in sensor configs"
                    )
                    continue

                config = all_sensor_configs[sensor_type]
                _LOGGER.info(f"Creating sensor {sensor_type} for device {device_id}")
                sensors.append(
                    RamsesExtraHumiditySensor(hass, device_id, sensor_type, config)
                )
        else:
            _LOGGER.info(f"No sensor mapping found for device type {device_type}")

    _LOGGER.info(f"Created {len(sensors)} sensors total")
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

        # Convert device_id to underscore format for entity generation
        device_id_underscore = device_id.replace(":", "_")

        # Set unique_id to prevent duplicate entities
        self._attr_unique_id = f"{sensor_type}_{device_id_underscore}"

        # Set human-friendly name from template
        name_template = (
            config.get("name_template", f"{sensor_type} {device_id_underscore}")
            or f"{sensor_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._sensor_type} {self._device_id.replace(':', '_')}"
        )

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
            if temp_state is None or temp_state.state in (
                "unavailable",
                "unknown",
                "uninitialized",
            ):
                _LOGGER.debug(
                    "Missing temperature entity %s for %s - "
                    "absolute humidity cannot be calculated",
                    temp_entity,
                    self._attr_name,
                )
                return None, None

            temp = float(temp_state.state)

            # Get humidity from ramses_cc sensor
            humidity_state = self.hass.states.get(humidity_entity)
            if humidity_state is None or humidity_state.state in (
                "unavailable",
                "unknown",
                "uninitialized",
            ):
                _LOGGER.debug(
                    "Missing humidity entity %s for %s - "
                    "absolute humidity cannot be calculated",
                    humidity_entity,
                    self._attr_name,
                )
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

            _LOGGER.debug(
                "Got temp=%.1f°C, humidity=%.1f%% for %s - "
                "calculating absolute humidity",
                temp,
                humidity,
                self._attr_name,
            )

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
