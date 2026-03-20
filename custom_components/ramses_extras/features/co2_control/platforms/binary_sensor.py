"""CO2 Control Binary Sensor Platform."""

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.const import register_feature_platform
from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)
from custom_components.ramses_extras.framework.helpers.platform import PlatformSetup

_LOGGER = logging.getLogger(__name__)


class CO2ControlBinarySensor(ExtrasBinarySensorEntity):
    """CO2 Control binary sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control binary sensor."""
        super().__init__(hass, device_id, sensor_type, config)
        self._attr_is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if CO2 control is active."""
        return self._attr_is_on

    def set_state(self, is_active: bool) -> None:
        """Set the active state.

        Args:
            is_active: Whether CO2 control is active
        """
        self._attr_is_on = is_active
        self.async_write_ha_state()


def create_co2_control_binary_sensor(
    hass: HomeAssistant,
    device_id: str,
    sensor_type: str,
    config: dict[str, Any],
) -> CO2ControlBinarySensor:
    """Create CO2 control binary sensor entity."""
    return CO2ControlBinarySensor(hass, device_id, sensor_type, config)


async def create_co2_binary_sensor_entities(
    hass: HomeAssistant,
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None,
) -> list[BinarySensorEntity]:
    """Factory to create CO2 binary sensor entities."""
    entities: list[BinarySensorEntity] = []
    for sensor_type, config in entity_configs.items():
        entities.append(
            create_co2_control_binary_sensor(hass, device_id, sensor_type, config)
        )
    return entities


async def binary_sensor_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control binary sensor entities."""
    from ..const import CO2_BINARY_SENSOR_CONFIGS

    await PlatformSetup.async_create_and_add_platform_entities(
        platform="binary_sensor",
        hass=hass,
        config_entry=entry,
        async_add_entities=async_add_entities,
        entity_configs=CO2_BINARY_SENSOR_CONFIGS,
        entity_factory=create_co2_binary_sensor_entities,
        feature_id="co2_control",
    )


register_feature_platform(
    "binary_sensor", "co2_control", binary_sensor_async_setup_entry
)


__all__ = [
    "CO2ControlBinarySensor",
    "create_co2_control_binary_sensor",
    "create_co2_binary_sensor_entities",
    "binary_sensor_async_setup_entry",
]
