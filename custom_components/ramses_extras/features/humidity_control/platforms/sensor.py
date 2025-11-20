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
from homeassistant.helpers.event import async_track_state_change

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control sensor platform."""
    _LOGGER.info("Setting up humidity control sensor")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        f"Humidity control sensor platform: found {len(devices)} devices: {devices}"
    )

    sensor = []
    for device_id in devices:
        # Create humidity-specific sensor
        device_sensor = await create_humidity_sensor(hass, device_id, config_entry)
        sensor.extend(device_sensor)
        _LOGGER.info(f"Created {len(device_sensor)} sensor for device {device_id}")

    _LOGGER.info(f"Total sensor created: {len(sensor)}")
    async_add_entities(sensor, True)


async def _check_underlying_entities_exist(
    hass: HomeAssistant, device_id: str, sensor_type: str
) -> bool:
    """Check if the underlying ramses_cc entities exist for a humidity sensor.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        sensor_type: Type of humidity sensor

    Returns:
        True if underlying entities exist, False otherwise
    """
    from homeassistant.helpers import entity_registry

    entity_patterns = {
        "indoor_absolute_humidity": ("indoor_temp", "indoor_humidity"),
        "outdoor_absolute_humidity": ("outdoor_temp", "outdoor_humidity"),
    }

    if sensor_type not in entity_patterns:
        return False

    temp_type, humidity_type = entity_patterns[sensor_type]
    device_id_underscore = device_id.replace(":", "_")

    temp_entity = f"sensor.{device_id_underscore}_{temp_type}"
    humidity_entity = f"sensor.{device_id_underscore}_{humidity_type}"

    # Check entity registry instead of states,
    #  as states may not be available during setup
    registry = entity_registry.async_get(hass)
    temp_entity_entry = registry.async_get(temp_entity)
    humidity_entity_entry = registry.async_get(humidity_entity)

    exists = temp_entity_entry is not None and humidity_entity_entry is not None
    if not exists:
        _LOGGER.debug(
            f"Underlying entities not found for {sensor_type}: {temp_entity}="
            f"{temp_entity_entry is not None}, {humidity_entity}="
            f"{humidity_entity_entry is not None}"
        )

    return exists


async def create_humidity_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[SensorEntity]:
    """Create humidity sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of sensor entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    # entity_manager = HumidityEntities(hass, config_entry)
    sensor: list[Any] = []

    # Humidity_control doesn't create any sensor in its platform
    # - indoor_absolute_humidity is created by default feature
    # - outdoor_absolute_humidity calculation is handled differently
    # This platform only provides control entities (switch, number, binary_sensor)

    return sensor  # noqa: RET504


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

        # Track if we have listeners set up
        self._listeners_set_up = False

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._sensor_type} {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        # Set up listeners for underlying temperature and humidity sensor
        await self._setup_listeners()

    async def _setup_listeners(self) -> None:
        """Set up listeners for temperature and humidity sensor changes."""
        if self._listeners_set_up:
            return

        entity_patterns = {
            "indoor_absolute_humidity": ("indoor_temp", "indoor_humidity"),
            "outdoor_absolute_humidity": ("outdoor_temp", "outdoor_humidity"),
        }

        if self._sensor_type not in entity_patterns:
            return

        temp_type, humidity_type = entity_patterns[self._sensor_type]

        # Construct entity IDs based on the device_id
        temp_entity = f"sensor.{self._device_id.replace(':', '_')}_{temp_type}"
        humidity_entity = f"sensor.{self._device_id.replace(':', '_')}_{humidity_type}"

        # Track state changes on both temperature and humidity sensor
        async def state_changed_listener(*args: Any) -> None:
            """Handle state changes on temperature or humidity sensor."""
            await self._recalculate_and_update()

        # Listen for state changes on both sensor
        async_track_state_change(
            self.hass, [temp_entity, humidity_entity], state_changed_listener
        )

        self._listeners_set_up = True
        _LOGGER.debug(
            "Set up state change listeners for %s: %s, %s",
            self._attr_name,
            temp_entity,
            humidity_entity,
        )

    async def _recalculate_and_update(self) -> None:
        """Recalculate absolute humidity and update sensor state."""
        try:
            temp, rh = self._get_temp_and_humidity()
            result = self._calculate_abs_humidity(temp, rh)

            if result is not None:
                _LOGGER.debug(
                    "Recalculated absolute humidity for"
                    " %s: %.2f g/m³ (T=%.1f°C, RH=%.1f%%)",
                    self._attr_name,
                    result,
                    temp,
                    rh,
                )
                self._attr_native_value = result
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.debug("Error recalculating humidity for %s: %s", self._attr_name, e)

    def _get_temp_and_humidity(self) -> tuple[float | None, float | None]:
        """Get temperature and humidity data from ramses_cc entities.

        Returns:
            tuple: (temperature, humidity) or (None, None) if sensor are missing/failed
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


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("sensor", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityAbsoluteSensor",
    "async_setup_entry",
    "create_humidity_sensor",
]
