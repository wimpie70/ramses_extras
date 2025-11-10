"""Sensor Management Feature.

This module provides sensor management functionality including automation,
services, entities, and configuration for sensor calibration and monitoring.
"""

from typing import Any, Dict

from .automation import SensorAutomationManager
from .config import SensorConfig
from .const import SENSOR_MANAGEMENT_CONST
from .entities import SensorEntities
from .services import SensorServices

__all__ = [
    "SensorAutomationManager",
    "SensorEntities",
    "SensorServices",
    "SensorConfig",
    "SENSOR_MANAGEMENT_CONST",
]


def create_sensor_management_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create sensor management feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Sensor management feature instance
    """
    return {
        "automation": SensorAutomationManager(hass, config_entry),
        "entities": SensorEntities(hass, config_entry),
        "services": SensorServices(hass, config_entry),
        "config": SensorConfig(hass, config_entry),
    }
