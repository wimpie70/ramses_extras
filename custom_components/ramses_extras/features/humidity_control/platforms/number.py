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
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

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
    _LOGGER.info(
        f"Humidity control number platform: found {len(devices)} devices: {devices}"
    )

    number = []
    for device_id in devices:
        # Create humidity control number
        device_number = await create_humidity_number(hass, device_id, config_entry)
        number.extend(device_number)
        _LOGGER.info(f"Created {len(device_number)} number for device {device_id}")

    _LOGGER.info(f"Total number created: {len(number)}")
    async_add_entities(number, True)


async def create_humidity_number(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[NumberEntity]:
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
        ExtrasBaseEntity.__init__(self, hass, device_id, number_type, config)

        self.config_entry = config_entry

        # Set number-specific attributes
        self._number_type = number_type
        self._attr_native_unit_of_measurement = config.get("unit", "%")
        self._attr_device_class = config.get("device_class")
        self._attr_native_min_value = config.get("min_value", 0.0)
        self._attr_native_max_value = config.get("max_value", 100.0)
        self._attr_native_step = config.get("step", 1.0)

        # Use automatic format detection with EntityHelpers
        device_id_underscore = device_id.replace(":", "_")

        # Get the template from config (e.g., "relative_humidity_minimum_{device_id}")
        entity_template = config.get("entity_template", f"{number_type}_{{device_id}}")

        try:
            # Generate entity_id using automatic format detection
            self.entity_id = EntityHelpers.generate_entity_name_from_template(
                "number", entity_template, device_id=device_id_underscore
            )
            self._attr_unique_id = self.entity_id.replace("number.", "")
        except Exception as e:
            _LOGGER.warning(
                f"Entity name generation failed for {number_type} device "
                f"{device_id_underscore}: {e}. "
                "This indicates a configuration issue that needs to be resolved."
            )

        # Set display name from template
        name_template = config.get(
            "name_template", f"{number_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

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
        return float(humidity_config.get(self._number_type, default_value))

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

        # Save to config entry
        if self.config_entry:
            device_key = self._device_id.replace(":", "_")
            options = dict(self.config_entry.options)
            if "humidity_control" not in options:
                options["humidity_control"] = {}
            if device_key not in options["humidity_control"]:
                options["humidity_control"][device_key] = {}
            options["humidity_control"][device_key][self._number_type] = value
            await self.hass.config_entries.async_update_entry(
                self.config_entry, options=options
            )

        _LOGGER.info(
            "Number %s value set to %s (min: %s, max: %s, step: %s)",
            self._attr_name,
            value,
            self._attr_native_min_value,
            self._attr_native_max_value,
            self._attr_native_step,
        )

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
