"""Ramses Extras Number Platform.

This module provides the main Home Assistant number platform integration
for the ramses_extras custom component.

NOTE: This dynamically discovers and calls feature-specific platforms.
All entity classes and business logic have been moved to feature platforms.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_feature_platform_setups(platform: str) -> list[Any]:
    """Get registered feature platform setup functions."""
    from .const import get_feature_platform_setups

    return get_feature_platform_setups(platform)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform - dynamically discover and call feature platforms."""
    # Get registered feature number platforms
    feature_setups = _get_feature_platform_setups("number")

    # Call each discovered feature platform
    for setup_func in feature_setups:
        try:
            await setup_func(hass, config_entry, async_add_entities)
        except Exception as e:
            _LOGGER.error(f"Error setting up number platform: {e}")
