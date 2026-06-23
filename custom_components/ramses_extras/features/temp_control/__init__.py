"""Temperature control (bypass) feature.

Factory entrypoint: create_temp_control_feature

The framework will call `create_<feature_id>_feature` for enabled features.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .automation import TempControlAutomationManager
from .config import TempControlConfig
from .platforms import (
    binary_sensor_async_setup_entry,
    create_temp_control_active_binary_sensor,
    create_temp_control_desired_speed_select,
    create_temp_control_status_sensor,
    create_temp_control_switch,
    select_async_setup_entry,
    sensor_async_setup_entry,
    switch_async_setup_entry,
)

_LOGGER = logging.getLogger(__name__)


def create_temp_control_feature(
    hass: HomeAssistant, config_entry: Any
) -> dict[str, Any]:
    """Factory function to create temp_control feature for framework startup."""

    automation = TempControlAutomationManager(hass, config_entry)

    return {
        "automation": automation,
        "config": TempControlConfig(hass, config_entry),
        "platforms": {
            "switch": {"async_setup_entry": switch_async_setup_entry},
            "select": {"async_setup_entry": select_async_setup_entry},
            "binary_sensor": {"async_setup_entry": binary_sensor_async_setup_entry},
            "sensor": {"async_setup_entry": sensor_async_setup_entry},
        },
        "entities": {
            "switch": create_temp_control_switch,
            "select": create_temp_control_desired_speed_select,
            "binary_sensor": create_temp_control_active_binary_sensor,
            "sensor": create_temp_control_status_sensor,
        },
    }


__all__ = ["create_temp_control_feature"]
