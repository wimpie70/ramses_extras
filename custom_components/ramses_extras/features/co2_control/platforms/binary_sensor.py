"""CO2 Control Binary Sensor Platform."""

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)

_LOGGER = logging.getLogger(__name__)


class CO2ControlBinarySensor(ExtrasBinarySensorEntity):
    """CO2 Control binary sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control binary sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Entity configuration
        """
        super().__init__(hass, device_id, "co2_active", config)
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
    config: dict[str, Any],
) -> CO2ControlBinarySensor:
    """Create CO2 control binary sensor entity.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config: Entity configuration

    Returns:
        CO2ControlBinarySensor entity
    """
    return CO2ControlBinarySensor(hass, device_id, config)


async def binary_sensor_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control binary sensor entities.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    # Implementation will be completed in Phase 4


__all__ = [
    "CO2ControlBinarySensor",
    "create_co2_control_binary_sensor",
    "binary_sensor_async_setup_entry",
]
