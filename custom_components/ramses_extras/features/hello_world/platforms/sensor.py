# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Sensor platform for Hello World Switch Card feature.

This module provides a placeholder implementation for the sensor platform,
which can be extended to add sensor functionality to the Hello World feature.

:platform: Home Assistant
:feature: Hello World Sensor Platform
:components: Sensor Entity (Placeholder)
:status: Placeholder Implementation
:extension_point: Sensor Functionality
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up Hello World sensor platform.

    This is a placeholder implementation for the sensor platform in the Hello World
    feature. Currently, it does not provide any functional sensor entities.

    To extend this platform with actual sensor functionality:
    1. Create a HelloWorldSensorEntity class that extends ExtrasSensorEntity
    2. Implement the required sensor entity methods (update, etc.)
    3. Create and add sensor entities using the async_add_entities callback
    4. Define sensor configurations in const.py

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry for the integration
        async_add_entities: Callback function to add entities to Home Assistant

    Note:
        This placeholder implementation allows the feature to be loaded without
        errors while providing a clear extension point for future development.
    """
    # Placeholder implementation - not functional by default
    # Extend ExtrasSensorEntity when adding sensor functionality
    pass  # noqa: PIE790
