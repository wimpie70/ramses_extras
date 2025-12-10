"""Humidity Control Number Platform.

This module provides Home Assistant number platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasNumberEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control number platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    # Use the framework's device filtering helper
    filtered_devices = platform.PlatformSetup.get_filtered_devices_for_feature(
        hass, "humidity_control", config_entry
    )

    if not filtered_devices:
        _LOGGER.info("No enabled devices for humidity control number platform")
        return

    entities = []
    for device_id in filtered_devices:
        # Create humidity number entities for this device
        try:
            device_entities = await create_humidity_number(
                hass, device_id, config_entry
            )
            entities.extend(device_entities)
            _LOGGER.info(
                "Created %d humidity number entities for device %s",
                len(device_entities),
                device_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to create humidity number entities for device %s: %e",
                device_id,
                e,
            )

    _LOGGER.info("Total humidity number entities created: %d", len(entities))
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("Humidity number entities added to Home Assistant")


async def create_humidity_number(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasNumberEntity]:
    """Create humidity control number for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of number entities
    """
    # Import entity configurations from registry
    from ..const import HUMIDITY_NUMBER_CONFIGS

    number_list = []

    # Create configuration number entities
    for number_type, config in HUMIDITY_NUMBER_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            number_entity = HumidityControlNumber(
                hass, device_id, number_type, config, config_entry
            )
            number_list.append(number_entity)

    return number_list


class HumidityControlNumber(ExtrasNumberEntity):
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
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize humidity control number.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            number_type: Type of number entity
            config: Number configuration
            config_entry: Configuration entry for saving values
        """
        # Initialize base entity
        super().__init__(hass, device_id, number_type, config, config_entry)

        # Initialize value - load from config entry if available, else default
        self._native_value: float = self._load_value_from_config(
            config.get("default_value", 50.0)
        )

    def _load_value_from_config(self, default_value: float) -> float:
        """Load the number value from config entry.

        Args:
            default_value: Default value if not found in config

        Returns:
            The stored value or default
        """
        if not self.config_entry:
            return default_value

        device_key = self._device_id.replace(":", "_")
        humidity_config = self.config_entry.options.get("humidity_control", {}).get(
            device_key, {}
        )
        return float(humidity_config.get(self._entity_type, default_value))

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
        # Use base class method which calls _save_value_to_config
        await super().async_set_native_value(value)

    async def _save_value_to_config(self, value: float) -> None:
        """Save number value to config entry with humidity_control feature key."""
        if not self.config_entry:
            return

        device_key = self.device_id.replace(":", "_")
        options = dict(self.config_entry.options)
        if "humidity_control" not in options:
            options["humidity_control"] = {}
        if device_key not in options["humidity_control"]:
            options["humidity_control"][device_key] = {}
        options["humidity_control"][device_key][self._entity_type] = value
        await self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "number_type": self._entity_type,
            "min_value": self._attr_native_min_value,
            "max_value": self._attr_native_max_value,
            "step": self._attr_native_step,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("number", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlNumber",
    "async_setup_entry",
    "create_humidity_number",
]
