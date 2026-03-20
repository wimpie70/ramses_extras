"""CO2 Control Feature.

This module provides CO2-based ventilation control functionality including automation,
services, entities, and configuration specific to CO2 management.

CO2 Control has priority over Humidity Control in the ventilation automation system.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .automation import CO2AutomationManager
from .config import CO2Config
from .const import (
    CO2_BINARY_SENSOR_CONFIGS,
    CO2_DEVICE_ENTITY_MAPPING,
    CO2_NUMBER_CONFIGS,
    CO2_SENSOR_CONFIGS,
    CO2_SWITCH_CONFIGS,
    ENHANCED_CO2_BINARY_SENSOR_CONFIGS,
    ENHANCED_CO2_NUMBER_CONFIGS,
    ENHANCED_CO2_SENSOR_CONFIGS,
    ENHANCED_CO2_SWITCH_CONFIGS,
)
from .platforms import (
    CO2ControlBinarySensor,
    CO2ControlNumber,
    CO2ControlSensor,
    CO2ControlSwitch,
    binary_sensor_async_setup_entry,
    create_co2_control_binary_sensor,
    create_co2_number,
    create_co2_sensor,
    number_async_setup_entry,
    sensor_async_setup_entry,
    switch_async_setup_entry,
)
from .zone_manager import CO2Zone, CO2ZoneManager

_LOGGER = logging.getLogger(__name__)


class CO2ControlFeature:
    """CO2 Control feature manager."""

    def __init__(self, hass: HomeAssistant, device_id: str, config: dict[str, Any]):
        """Initialize CO2 control feature.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Feature configuration
        """
        self.hass = hass
        self.device_id = device_id
        self.config = CO2Config(hass, device_id, config)
        self.zone_manager = CO2ZoneManager(hass, device_id, config)

        _LOGGER.info("CO2 Control feature initialized for device %s", device_id)

    async def async_setup(self) -> bool:
        """Set up the CO2 control feature.

        Returns:
            True if setup successful
        """
        _LOGGER.debug("Setting up CO2 control feature for device %s", self.device_id)

        # Validate configuration
        is_valid, errors = self.config.validate()
        if not is_valid:
            _LOGGER.error(
                "CO2 control configuration validation failed for device %s: %s",
                self.device_id,
                errors,
            )
            return False

        return True

    async def async_unload(self) -> bool:
        """Unload the CO2 control feature.

        Returns:
            True if unload successful
        """
        _LOGGER.debug("Unloading CO2 control feature for device %s", self.device_id)
        return True


async def async_create_co2_control_feature(
    hass: HomeAssistant, device_id: str, config: dict[str, Any]
) -> CO2ControlFeature:
    """Create and set up CO2 control feature.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config: Feature configuration

    Returns:
        CO2ControlFeature instance
    """
    feature = CO2ControlFeature(hass, device_id, config)
    await feature.async_setup()
    return feature


def _get_humidity_automation(hass: HomeAssistant) -> Any | None:
    features = hass.data.get("ramses_extras", {}).get("features", {})
    humidity_feature = (
        features.get("humidity_control") if isinstance(features, dict) else None
    )
    if isinstance(humidity_feature, dict):
        return humidity_feature.get("automation")
    return None


async def create_co2_control_feature(
    hass: HomeAssistant, config_entry: Any
) -> dict[str, Any]:
    """Factory function to create CO2 control feature for framework startup."""
    automation = CO2AutomationManager(hass, config_entry)
    humidity_automation = _get_humidity_automation(hass)
    if humidity_automation is not None:
        automation.set_humidity_manager(humidity_automation)

    return {
        "automation": automation,
        "config": CO2Config(hass, "", config_entry.options.get("co2_control", {})),
        "platforms": {
            "switch": {"async_setup_entry": switch_async_setup_entry},
            "number": {"async_setup_entry": number_async_setup_entry},
            "binary_sensor": {"async_setup_entry": binary_sensor_async_setup_entry},
            "sensor": {"async_setup_entry": sensor_async_setup_entry},
        },
    }


__all__ = [
    "CO2ControlFeature",
    "CO2AutomationManager",
    "create_co2_control_feature",
    "async_create_co2_control_feature",
    "CO2Config",
    "CO2Zone",
    "CO2ZoneManager",
    # Platform exports
    "CO2ControlSwitch",
    "CO2ControlNumber",
    "CO2ControlBinarySensor",
    "CO2ControlSensor",
    "create_co2_switch",
    "create_co2_number",
    "create_co2_control_binary_sensor",
    "create_co2_sensor",
    "switch_async_setup_entry",
    "number_async_setup_entry",
    "binary_sensor_async_setup_entry",
    "sensor_async_setup_entry",
    # Const exports
    "CO2_SWITCH_CONFIGS",
    "CO2_NUMBER_CONFIGS",
    "CO2_BINARY_SENSOR_CONFIGS",
    "CO2_SENSOR_CONFIGS",
    "CO2_DEVICE_ENTITY_MAPPING",
    "ENHANCED_CO2_SWITCH_CONFIGS",
    "ENHANCED_CO2_NUMBER_CONFIGS",
    "ENHANCED_CO2_BINARY_SENSOR_CONFIGS",
    "ENHANCED_CO2_SENSOR_CONFIGS",
]
