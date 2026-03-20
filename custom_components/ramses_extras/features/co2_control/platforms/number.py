"""CO2 Control Number Platform."""

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasNumberEntity,
)

_LOGGER = logging.getLogger(__name__)


class CO2ControlNumber(ExtrasNumberEntity):
    """CO2 Control number entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize CO2 control number.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Entity configuration
        """
        super().__init__(hass, device_id, "co2_threshold", config)
        self._attr_native_min_value = config.get("min_value", 0)
        self._attr_native_max_value = config.get("max_value", 2000)
        self._attr_native_step = config.get("step", 1)
        self._attr_native_value = config.get("default_value", 1000)
        self._attr_native_unit_of_measurement = config.get("unit")

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return (
            self._attr_native_value if self._attr_native_value is not None else 1000.0
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.debug(
            "CO2 number %s set to %s for device %s",
            self.entity_id,
            value,
            self.device_id,
        )


def create_co2_number(
    hass: HomeAssistant,
    device_id: str,
    config: dict[str, Any],
) -> CO2ControlNumber:
    """Create CO2 control number entity.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config: Entity configuration

    Returns:
        CO2ControlNumber entity
    """
    return CO2ControlNumber(hass, device_id, config)


async def number_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control number entities.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    # Implementation will be completed in Phase 4


__all__ = ["CO2ControlNumber", "create_co2_number", "number_async_setup_entry"]
