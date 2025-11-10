"""Humidity Control Feature.

This module provides humidity control functionality including automation,
services, entities, and configuration specific to humidity management.
"""

from typing import Any, Dict

from .automation import HumidityAutomationManager
from .config import HumidityConfig
from .const import HUMIDITY_CONTROL_CONST
from .entities import HumidityEntities
from .services import HumidityServices

__all__ = [
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_CONTROL_CONST",
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
