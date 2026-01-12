# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Number platform for Hello World Switch Card feature.

This module provides a placeholder implementation for the number platform,
which can be extended to add numeric control functionality to the Hello World feature.

:platform: Home Assistant
:feature: Hello World Number Platform
:components: Number Entity (Placeholder)
:status: Placeholder Implementation
:extension_point: Numeric Control Functionality
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up Hello World number platform.

    This is a placeholder implementation for the number platform in the Hello World
    feature. Currently, it does not provide any functional number entities.

    To extend this platform with actual numeric control functionality:
    1. Create a HelloWorldNumberEntity class that extends ExtrasNumberEntity
    2. Implement the required number entity methods (set_value, etc.)
    3. Create and add number entities using the async_add_entities callback
    4. Define number configurations in const.py

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry for the integration
    :param async_add_entities: Callback function to add entities to Home Assistant
    """
    # Placeholder implementation - not functional by default
    # Extend ExtrasNumberEntity when adding numeric controls
    pass  # noqa: PIE790
