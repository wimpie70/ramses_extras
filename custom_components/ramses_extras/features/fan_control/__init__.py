"""Fan Control Feature.

This module provides fan control functionality including automation,
services, entities, and configuration for ventilation system control.
"""

from typing import Any, Dict

from .automation import FanAutomationManager
from .config import FanConfig
from .const import FAN_CONTROL_CONST
from .entities import FanEntities
from .services import FanServices

__all__ = [
    "FanAutomationManager",
    "FanEntities",
    "FanServices",
    "FanConfig",
    "FAN_CONTROL_CONST",
]


def create_fan_control_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create fan control feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Fan control feature instance
    """
    return {
        "automation": FanAutomationManager(hass, config_entry),
        "entities": FanEntities(hass, config_entry),
        "services": FanServices(hass, config_entry),
        "config": FanConfig(hass, config_entry),
    }
