"""Humidity Control Feature.

This module provides humidity control functionality including automation,
services, entities, and configuration specific to humidity management.

Updated to include platform exports for clean separation of HA integration
and feature-specific business logic.
"""

from typing import Any, Dict

from .automation import HumidityAutomationManager
from .config import HumidityConfig
from .const import (
    HUMIDITY_BOOLEAN_CONFIGS,
    HUMIDITY_CONTROL_CONST,
    HUMIDITY_DEVICE_ENTITY_MAPPING,
    HUMIDITY_NUMBER_CONFIGS,
    HUMIDITY_SWITCH_CONFIGS,
)
from .entities import HumidityEntities

# Import platform classes for HA integration
from .platforms import (
    HumidityAbsoluteSensor,
    HumidityControlBinarySensor,
    HumidityControlNumber,
    HumidityControlSwitch,
    binary_sensor_async_setup_entry,
    create_humidity_control_binary_sensor,
    create_humidity_number,
    create_humidity_sensors,
    create_humidity_switch,
    number_async_setup_entry,
    sensor_async_setup_entry,
    switch_async_setup_entry,
)
from .services import HumidityServices

__all__ = [
    # Existing feature exports
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_CONTROL_CONST",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
    # Platform class exports
    "HumidityAbsoluteSensor",
    "HumidityControlBinarySensor",
    "HumidityControlSwitch",
    "HumidityControlNumber",
    # Platform setup exports
    "sensor_async_setup_entry",
    "binary_sensor_async_setup_entry",
    "switch_async_setup_entry",
    "number_async_setup_entry",
    # Platform factory exports
    "create_humidity_sensors",
    "create_humidity_control_binary_sensor",
    "create_humidity_switch",
    "create_humidity_number",
]


def create_humidity_control_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create humidity control feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Humidity control feature instance with automation,
        entities, services, config, and platforms
    """
    return {
        "automation": HumidityAutomationManager(hass, config_entry),
        "entities": HumidityEntities(hass, config_entry),
        "services": HumidityServices(hass, config_entry),
        "config": HumidityConfig(hass, config_entry),
        "platforms": {
            "sensor": {
                "async_setup_entry": sensor_async_setup_entry,
                "create_sensors": create_humidity_sensors,
                "entity_class": HumidityAbsoluteSensor,
            },
            "binary_sensor": {
                "async_setup_entry": binary_sensor_async_setup_entry,
                "create_binary_sensors": create_humidity_control_binary_sensor,
                "entity_class": HumidityControlBinarySensor,
            },
            "switch": {
                "async_setup_entry": switch_async_setup_entry,
                "create_switches": create_humidity_switch,
                "entity_class": HumidityControlSwitch,
            },
            "number": {
                "async_setup_entry": number_async_setup_entry,
                "create_numbers": create_humidity_number,
                "entity_class": HumidityControlNumber,
            },
        },
    }
