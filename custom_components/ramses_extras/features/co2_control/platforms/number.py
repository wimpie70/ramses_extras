"""CO2 Control Number Platform."""

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.const import register_feature_platform
from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasNumberEntity,
)
from custom_components.ramses_extras.framework.helpers.platform import PlatformSetup

_LOGGER = logging.getLogger(__name__)


class CO2ControlNumber(ExtrasNumberEntity):
    """CO2 Control number entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        number_type: str,
        config: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize CO2 control number."""
        super().__init__(hass, device_id, number_type, config, config_entry)
        self._attr_native_min_value = config.get(
            "min_value", self._attr_native_min_value
        )
        self._attr_native_max_value = config.get(
            "max_value", self._attr_native_max_value
        )
        self._attr_native_step = config.get("step", self._attr_native_step)
        self._attr_native_value = config.get("default_value", self._native_value)
        self._attr_native_unit_of_measurement = config.get(
            "unit", self._attr_native_unit_of_measurement
        )

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
    number_type: str,
    config: dict[str, Any],
    config_entry: ConfigEntry | None = None,
) -> CO2ControlNumber:
    """Create a single CO2 control number entity."""
    return CO2ControlNumber(hass, device_id, number_type, config, config_entry)


async def create_co2_number_entities(
    hass: HomeAssistant,
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None,
) -> list[NumberEntity]:
    """Factory to create CO2 number entities for a device."""
    entities: list[NumberEntity] = []
    for number_type, config in entity_configs.items():
        entities.append(
            create_co2_number(hass, device_id, number_type, config, config_entry)
        )
    return entities


async def number_async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CO2 control number entities."""
    from ..const import CO2_NUMBER_CONFIGS

    await PlatformSetup.async_create_and_add_platform_entities(
        platform="number",
        hass=hass,
        config_entry=entry,
        async_add_entities=async_add_entities,
        entity_configs=CO2_NUMBER_CONFIGS,
        entity_factory=create_co2_number_entities,
        feature_id="co2_control",
    )


register_feature_platform("number", "co2_control", number_async_setup_entry)

__all__ = [
    "CO2ControlNumber",
    "create_co2_number",
    "create_co2_number_entities",
    "number_async_setup_entry",
]
