"""Humidity Control Binary Sensor Platform.

This module provides Home Assistant binary sensor platform integration
for humidity control feature.
"""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
)
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control binary sensor platform."""
    _LOGGER.info("Setting up humidity control binary sensor")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        f"Humidity control binary sensor platform: found {len(devices)} "
        f"devices: {devices}"
    )

    if not devices:
        _LOGGER.warning(
            "No devices found for humidity control binary sensors "
            "- automation will not start"
        )
        return

    binary_sensor = []
    for device_id in devices:
        try:
            # Create humidity control binary sensor
            device_sensor = await create_humidity_control_binary_sensor(
                hass, device_id, config_entry
            )
            binary_sensor.extend(device_sensor)
            _LOGGER.info(
                f"Created {len(device_sensor)} binary sensor for device {device_id}"
            )
        except Exception as e:
            _LOGGER.error(f"Failed to create binary sensor for device {device_id}: {e}")

    _LOGGER.info(f"Total binary sensor created: {len(binary_sensor)}")
    if binary_sensor:
        async_add_entities(binary_sensor, True)
        _LOGGER.info("Humidity control binary sensors added to Home Assistant")
    else:
        _LOGGER.warning("No binary sensors created - automation will not start")


async def create_humidity_control_binary_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[BinarySensorEntity]:
    """Create humidity control binary sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of binary sensor entities
    """
    # Import entity configurations from registry
    from ..const import HUMIDITY_BOOLEAN_CONFIGS

    binary_sensor = []

    # Create dehumidifying_active binary sensor
    for binary_type, config in HUMIDITY_BOOLEAN_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            binary_sensor_entity = HumidityControlBinarySensor(
                hass, device_id, binary_type, config
            )
            binary_sensor.append(binary_sensor_entity)

    return binary_sensor


class HumidityControlBinarySensor(BinarySensorEntity, ExtrasBaseEntity):
    """Binary sensor for humidity control feature.

    This class handles the state of dehumidifying equipment and
    tracks humidity control automation state.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        binary_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity control binary sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            binary_type: Type of binary sensor
            config: Binary sensor configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, binary_type, config)

        # Set binary sensor-specific attributes
        self._binary_type = binary_type
        self._attr_device_class = config.get("device_class")

        # Use automatic format detection with EntityHelpers
        device_id_underscore = device_id.replace(":", "_")

        # Get the template from config (e.g., "dehumidifying_active_{device_id}")
        entity_template = config.get("entity_template", f"{binary_type}_{{device_id}}")

        try:
            # Generate entity_id using automatic format detection
            self.entity_id = EntityHelpers.generate_entity_name_from_template(
                "binary_sensor", entity_template, device_id=device_id_underscore
            )
            self._attr_unique_id = self.entity_id.replace("binary_sensor.", "")
        except Exception as e:
            _LOGGER.warning(
                f"Entity name generation failed for {binary_type} device "
                f"{device_id_underscore}: {e}. "
                "This indicates a configuration issue that needs to be resolved."
            )

        # Set display name from template
        name_template = config.get(
            "name_template", f"{binary_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        # Initialize state
        self._is_on = False
        self._current_fan_speed = "auto"  # Track current fan speed

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"{self._binary_type} {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.info(
            f"HumidityControlBinarySensor async_added_to_hass called for "
            f"{self.entity_id}"
        )

        _LOGGER.info(
            f"Binary sensor {self._attr_name} registered with automation for device "
            f"{self._device_id}"
        )
        # Register this binary sensor with the automation manager
        await self._register_with_automation()

        _LOGGER.debug("Binary sensor %s added to hass", self._attr_name)

    async def _register_with_automation(self) -> None:
        """Register this binary sensor with the humidity automation manager."""
        try:
            # Get the automation instance from the feature manager
            # The automation should already be created by the main feature setup
            ramses_data = self.hass.data.get("ramses_extras", {})
            features = ramses_data.get("features", {})

            # Look for the humidity_control feature
            humidity_feature = features.get("humidity_control")
            if humidity_feature and "automation" in humidity_feature:
                automation = humidity_feature["automation"]
                automation.set_binary_sensor(self)
                _LOGGER.info(
                    "Registered binary sensor %s with existing humidity automation "
                    "for device %s",
                    self._attr_name,
                    self._device_id,
                )
            else:
                _LOGGER.warning(
                    "Humidity control automation not found in feature manager "
                    "for device %s. Binary sensor registration deferred until "
                    "automation is available.",
                    self._device_id,
                )
        except Exception as e:
            _LOGGER.error(
                "Failed to register binary sensor %s with automation: %s",
                self._attr_name,
                e,
            )

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor state is on."""
        # For dehumidifying_active: read-only, controlled by automation
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the binary sensor - controlled by automation only."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned ON by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the binary sensor - controlled by automation only."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned OFF by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    def set_state(self, is_on: bool) -> None:
        """Set the binary sensor state (used by automation)."""
        self._is_on = is_on
        self.async_write_ha_state()
        _LOGGER.debug("Binary sensor %s state set to %s", self._attr_name, is_on)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "binary_type": self._binary_type,
            "controlled_by": "automation",
            "current_fan_speed": self._current_fan_speed,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("binary_sensor", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlBinarySensor",
    "async_setup_entry",
    "create_humidity_control_binary_sensor",
]
