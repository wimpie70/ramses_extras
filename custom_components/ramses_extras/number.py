"""Number platform for Ramses Extras."""

import logging
from typing import Any

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
    """Set up the number platform - dynamically discover and call feature platforms."""
    # Get registered feature number platforms with enabled feature filtering
    platform_registry = hass.data["ramses_extras"]["PLATFORM_REGISTRY"]
    enabled_features = hass.data["ramses_extras"]["enabled_features"]

    for feature_name, setup_func in platform_registry.get("number", {}).items():
        # Only call setup functions for enabled features
        if enabled_features.get(feature_name, False):
            try:
                await setup_func(hass, config_entry, async_add_entities)
            except Exception as e:
                _LOGGER.error(
                    f"Error setting up number platform for {feature_name}: {e}"
                )
        else:
            _LOGGER.debug(f"Skipping disabled number feature: {feature_name}")
