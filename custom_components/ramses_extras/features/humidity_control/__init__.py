"""Humidity Control Feature.

This module provides humidity control functionality including automation,
services, entities, and configuration specific to humidity management.
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
from .services import HumidityServices

__all__ = [
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_CONTROL_CONST",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
]


def create_humidity_control_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create humidity control feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Humidity control feature instance
    """
    return {
        "automation": HumidityAutomationManager(hass, config_entry),
        "entities": HumidityEntities(hass, config_entry),
        "services": HumidityServices(hass, config_entry),
        "config": HumidityConfig(hass, config_entry),
    }
