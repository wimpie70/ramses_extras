"""CO2 Control Sensor Platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from custom_components.ramses_extras.const import register_feature_platform
from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSensorEntity,
)
from custom_components.ramses_extras.framework.helpers.platform import PlatformSetup

_LOGGER = logging.getLogger(__name__)


class CO2ControlSensor(ExtrasSensorEntity):
    """CO2 Control sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control sensor."""
        super().__init__(hass, device_id, sensor_type, config)
        self._zone_status: str | None = None
        self._automation_attrs: dict[str, Any] = {}

    @property
    def native_value(self) -> StateType:
        """Return zone status information."""
        return self._zone_status if self._zone_status is not None else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return automation attributes for UI diagnostics/highlighting."""
        return self._automation_attrs

    def set_zone_status(self, status: str, attrs: dict[str, Any] | None = None) -> None:
        """Set zone status.

        Args:
            status: Status string
        """
        self._zone_status = status
        self._automation_attrs = attrs or {}
        self.async_write_ha_state()


def create_co2_sensor(
    hass: HomeAssistant,
    device_id: str,
    sensor_type: str,
    config: dict[str, Any],
) -> CO2ControlSensor:
    """Create CO2 control sensor entity."""
    return CO2ControlSensor(hass, device_id, sensor_type, config)


async def create_co2_sensor_entities(
    hass: HomeAssistant,
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None,
) -> list[SensorEntity]:
    """Factory to create CO2 sensors for a device."""
    entities: list[SensorEntity] = []
    for sensor_type, config in entity_configs.items():
        entities.append(create_co2_sensor(hass, device_id, sensor_type, config))
    return entities


async def sensor_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control sensor entities."""
    from ..const import CO2_SENSOR_CONFIGS

    await PlatformSetup.async_create_and_add_platform_entities(
        platform="sensor",
        hass=hass,
        config_entry=entry,
        async_add_entities=async_add_entities,
        entity_configs=CO2_SENSOR_CONFIGS,
        entity_factory=create_co2_sensor_entities,
        store_entities_for_automation=True,
        feature_id="co2_control",
    )


register_feature_platform("sensor", "co2_control", sensor_async_setup_entry)


__all__ = [
    "CO2ControlSensor",
    "create_co2_sensor",
    "create_co2_sensor_entities",
    "sensor_async_setup_entry",
]
