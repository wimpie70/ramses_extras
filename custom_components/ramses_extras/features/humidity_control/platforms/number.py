"""Humidity Control Number Platform.

This module provides Home Assistant number platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
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
    """Set up humidity control number platform."""
    _LOGGER.info("Setting up humidity control number entities")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])

    numbers = []
    for device_id in devices:
        # Create humidity control numbers
        numbers.extend(await create_humidity_numbers(hass, device_id, config_entry))

    async_add_entities(numbers, True)


async def create_humidity_numbers(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[NumberEntity]:
    """Create humidity control numbers for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of number entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, config_entry)
    numbers = []

    # Create configuration number entities
    for number_type in [
        "relative_humidity_minimum",
        "relative_humidity_maximum",
        "absolute_humidity_offset",
    ]:
        config = entity_manager.get_entity_config("numbers", number_type)
        if config:
            number = HumidityControlNumber(hass, device_id, number_type, config)
            numbers.append(number)

    return numbers


def create_humidity_number(
    hass: HomeAssistant, device_id: str, number_type: str, config: dict[str, Any]
) -> NumberEntity:
    """Create a humidity control number (legacy function for compatibility)."""
    return HumidityControlNumber(hass, device_id, number_type, config)


class HumidityControlNumber(NumberEntity, ExtrasBaseEntity):
    """Number entity for humidity control feature.

    This class handles configuration parameters for humidity control,
    such as minimum/maximum humidity thresholds and offsets.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        number_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity control number.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            number_type: Type of number entity
            config: Number configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, number_type, config)

        # Set number-specific attributes
        self._number_type = number_type
        self._attr_native_unit_of_measurement = config.get("unit", "%")
        self._attr_device_class = config.get("device_class")
        self._attr_native_min_value = config.get("min_value", 0.0)
        self._attr_native_max_value = config.get("max_value", 100.0)
        self._attr_native_step = config.get("step", 1.0)

        # Set unique_id and name
        device_id_underscore = device_id.replace(":", "_")
        self._attr_unique_id = f"{number_type}_{device_id_underscore}"

        name_template = config.get(
            "name_template", f"{number_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        # Initialize value
        self._native_value: float = config.get("default_value", 50.0)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._number_type} {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.debug("Number %s added to hass", self._attr_name)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._native_value = value
        self.async_write_ha_state()
        _LOGGER.info(
            "Number %s value set to %s (min: %s, max: %s, step: %s)",
            self._attr_name,
            value,
            self._attr_native_min_value,
            self._attr_native_max_value,
            self._attr_native_step,
        )

    def set_value(self, value: float) -> None:
        """Set the value (synchronous version)."""
        self._native_value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "number_type": self._number_type,
            "min_value": self._attr_native_min_value,
            "max_value": self._attr_native_max_value,
            "step": self._attr_native_step,
        }


__all__ = [
    "HumidityControlNumber",
    "async_setup_entry",
    "create_humidity_number",
    "create_humidity_numbers",
]
