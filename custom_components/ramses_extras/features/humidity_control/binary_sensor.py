"""Humidity Control Binary Sensor.

This module provides a custom binary sensor implementation for the
humidity control feature,
extending the platform's base binary sensor to add feature-specific automation logic.
"""

import logging
from typing import TYPE_CHECKING, Any

from custom_components.ramses_extras.binary_sensor import RamsesBinarySensor
from custom_components.ramses_extras.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HumidityControlBinarySensor(RamsesBinarySensor):
    """Custom binary sensor for humidity control feature.

    This class extends the platform's base binary sensor to add
    humidity-specific automation logic for the dehumidifying_active entity.
    """

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        boolean_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity control binary sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            boolean_type: Type of binary sensor
            config: Configuration dictionary
        """
        # Initialize base binary sensor
        super().__init__(hass, device_id, boolean_type, config)

        _LOGGER.info(
            f"🔧 Created humidity control binary sensor: {self._attr_name} "
            f"(device: {device_id})"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to entity changes and start automation for humidity control."""
        # Call base class method first
        await super().async_added_to_hass()

        # For dehumidifying_active, integrate with humidity control feature
        if self._boolean_type == "dehumidifying_active":
            _LOGGER.info(
                f"🔧 Starting humidity automation for binary sensor {self._attr_name} "
                f"(device: {self._device_id})"
            )

            try:
                from .automation import create_humidity_control_automation

                # Create humidity control automation for this device
                automation_manager = create_humidity_control_automation(
                    self.hass, self.hass.data[DOMAIN]["config_entry"]
                )

                # Pass this binary sensor reference to the automation
                automation_manager.set_binary_sensor(self)

                # Start the automation
                await automation_manager.start()

                # Store the automation manager for the switch to use
                self.hass.data.setdefault(DOMAIN, {}).setdefault("automations", {})[
                    self._device_id
                ] = automation_manager

                _LOGGER.info(
                    f"✅ Started and stored humidity automation for device "
                    f"{self._device_id}"
                )

            except Exception as e:
                _LOGGER.error(
                    f"❌ Failed to start humidity automation for device "
                    f"{self._device_id}: {e}"
                )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for humidity control binary sensor."""
        base_attrs = super().extra_state_attributes or {}

        # Add humidity-specific attributes
        humidity_attrs = {
            "boolean_type": self._boolean_type,
            "controlled_by": "humidity_automation"
            if self._boolean_type == "dehumidifying_active"
            else "platform",
            "feature": "humidity_control"
            if self._boolean_type == "dehumidifying_active"
            else "base",
        }

        return {**base_attrs, **humidity_attrs}


def create_humidity_control_binary_sensor(
    hass: "HomeAssistant", device_id: str, boolean_type: str, config: dict[str, Any]
) -> HumidityControlBinarySensor:
    """Create a humidity control binary sensor instance.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        boolean_type: Type of binary sensor
        config: Configuration dictionary

    Returns:
        HumidityControlBinarySensor instance
    """
    return HumidityControlBinarySensor(hass, device_id, boolean_type, config)


__all__ = [
    "HumidityControlBinarySensor",
    "create_humidity_control_binary_sensor",
]
