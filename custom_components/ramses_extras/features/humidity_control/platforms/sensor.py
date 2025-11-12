"""Humidity Control Sensor Platform.

This module provides Home Assistant sensor platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes import ExtrasBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control sensor platform."""
    _LOGGER.info("Setting up humidity control sensors")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])

    sensors = []
    for device_id in devices:
        # Create humidity-specific sensors
        sensors.extend(await create_humidity_sensors(hass, device_id, config_entry))

    async_add_entities(sensors, True)


async def create_humidity_sensors(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[SensorEntity]:
    """Create humidity sensors for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of sensor entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, config_entry)
    sensors = []

    for sensor_type in ["indoor_absolute_humidity", "outdoor_absolute_humidity"]:
        config = entity_manager.get_entity_config("sensors", sensor_type)
        if config:
            sensor = HumidityAbsoluteSensor(hass, device_id, sensor_type, config)
            sensors.append(sensor)

    return sensors


class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
    """Absolute humidity sensor for humidity control feature.

    This class handles the calculation and display of absolute humidity
    based on temperature and relative humidity data from ramses_cc entities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity absolute sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            sensor_type: Type of humidity sensor
            config: Sensor configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, sensor_type, config)

        # Set sensor-specific attributes
        self._sensor_type = sensor_type
        self._attr_native_unit_of_measurement = config.get("unit", "g/m³")
        self._attr_device_class = config.get("device_class")

        # Set unique_id and name
        device_id_underscore = device_id.replace(":", "_")
        self._attr_unique_id = f"{sensor_type}_{device_id_underscore}"

        name_template = config.get(
            "name_template", f"{sensor_type} {device_id_underscore}"
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
        # Import humidity calculation helper
        from custom_components.ramses_extras.framework.helpers.entities import (
            calculate_absolute_humidity,
        )

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
            _LOGGER.debug("Error parsing temp/humidity for %s: %s", self._attr_name, e)
            return None, None

    def _calculate_abs_humidity(
        self, temp: float | None, rh: float | None
    ) -> float | None:
        """Calculate absolute humidity using proper formula."""
        if temp is None or rh is None:
            return None

        # Import humidity calculation helper
        from custom_components.ramses_extras.framework.helpers.entities import (
            calculate_absolute_humidity,
        )

        result = calculate_absolute_humidity(temp, rh)
        return float(result) if result is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "sensor_type": self._sensor_type}


__all__ = [
    "HumidityAbsoluteSensor",
    "async_setup_entry",
    "create_humidity_sensors",
]
