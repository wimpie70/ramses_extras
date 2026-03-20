"""CO2 Control Sensor Platform."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSensorEntity,
)

_LOGGER = logging.getLogger(__name__)


class CO2ControlSensor(ExtrasSensorEntity):
    """CO2 Control sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Entity configuration
        """
        super().__init__(hass, device_id, "co2_zone_status", config)
        self._zone_status: str | None = None
        self._attr_native_unit_of_measurement = config.get("unit")

    @property
    def native_value(self) -> StateType:
        """Return zone status information."""
        return self._zone_status if self._zone_status is not None else "unknown"

    def set_zone_status(self, status: str) -> None:
        """Set zone status.

        Args:
            status: Status string
        """
        self._zone_status = status
        self.async_write_ha_state()


def create_co2_sensor(
    hass: HomeAssistant,
    device_id: str,
    config: dict[str, Any],
) -> CO2ControlSensor:
    """Create CO2 control sensor entity.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config: Entity configuration

    Returns:
        CO2ControlSensor entity
    """
    return CO2ControlSensor(hass, device_id, config)


async def sensor_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control sensor entities.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    # Implementation will be completed in Phase 4


__all__ = ["CO2ControlSensor", "create_co2_sensor", "sensor_async_setup_entry"]
