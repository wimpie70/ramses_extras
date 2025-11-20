"""Sensor platform for Ramses Extras."""

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
    """Set up the sensor platform - thin wrapper that forwards to feature platforms."""
    # Get platform registry and enabled features
    platform_registry = hass.data["ramses_extras"]["PLATFORM_REGISTRY"]
    enabled_features = hass.data["ramses_extras"]["enabled_features"]

    # Forward to enabled feature platform setup functions
    for feature_name, setup_func in platform_registry.get("sensor", {}).items():
        # Always set up default feature, others only if explicitly enabled
        if feature_name == "default" or enabled_features.get(feature_name, False):
            try:
                await setup_func(hass, config_entry, async_add_entities)
                _LOGGER.debug(f"Set up sensor platform for feature: {feature_name}")
            except Exception as e:
                _LOGGER.error(
                    f"Error setting up sensor platform for {feature_name}: {e}"
                )
        else:
            _LOGGER.debug(f"Skipping disabled sensor feature: {feature_name}")
