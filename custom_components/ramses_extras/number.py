"""Ramses Extras Number Platform.

This module provides the main Home Assistant number platform integration
for the ramses_extras custom component.

NOTE: This is now a thin wrapper that forwards to feature-specific platforms.
All entity classes and business logic have been moved to feature platforms.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform.

    This is a thin wrapper that forwards to feature-specific platforms.
    All feature-specific business logic is handled by the feature platforms.
    """
    _LOGGER.info("Setting up number platform (thin wrapper)")

    # Forward to humidity control feature platform
    try:
        from .features.humidity_control.platforms.number import (
            async_setup_entry as humidity_number_setup,
        )

        await humidity_number_setup(hass, config_entry, async_add_entities)
        _LOGGER.info("Successfully forwarded number setup to humidity control feature")

    except ImportError as e:
        _LOGGER.warning("Could not import humidity control number platform: %s", e)
    except Exception as e:
        _LOGGER.error("Error forwarding number setup to feature platforms: %s", e)
