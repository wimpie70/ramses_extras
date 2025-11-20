"""Default feature sensor platform - creates base humidity sensor for all devices."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up default feature sensor platform."""
    _LOGGER.info("Setting up default feature sensor")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        f"Default feature sensor platform: found {len(devices)} devices: {devices}"
    )

    sensor: list[SensorEntity] = []
    for device_id in devices:
        # Create default sensor for this device
        device_sensor = await create_default_sensor(hass, device_id, config_entry)
        sensor.extend(device_sensor)
        _LOGGER.info(
            f"Created {len(device_sensor)} default sensor for device {device_id}"
        )

    _LOGGER.info(f"Total default sensor created: {len(sensor)}")
    async_add_entities(sensor, True)


async def create_default_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[SensorEntity]:
    """Create default sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of sensor entities
    """
    # Import default sensor configurations
    from ..const import DEFAULT_SENSOR_CONFIGS

    sensor_list: list[SensorEntity] = []

    # Create sensor for each configured sensor type
    for sensor_type, config in DEFAULT_SENSOR_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            # Create sensor
            sensor_entity = DefaultHumiditySensor(hass, device_id, sensor_type, config)
            sensor_list.append(sensor_entity)
            _LOGGER.debug(
                f"Created default {sensor_type} sensor for device {device_id}"
            )

    return sensor_list


class DefaultHumiditySensor(SensorEntity, ExtrasBaseEntity):
    """Default humidity sensor for the default feature.

    This creates base absolute humidity sensor for all devices.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize default humidity sensor.

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "sensor_type": self._sensor_type}


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("sensor", "default", async_setup_entry)

__all__ = [
    "DefaultHumiditySensor",
    "async_setup_entry",
    "create_default_sensor",
]
