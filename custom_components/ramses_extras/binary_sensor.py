"""Binary sensor platform for Ramses Extras."""

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
    """Set up the binary sensor platform - dynamically discover and call feature
    platforms."""
    _LOGGER.info("MAIN BINARY_SENSOR PLATFORM: Starting setup")
    # Get registered feature binary_sensor platforms with enabled feature filtering
    platform_registry = hass.data["ramses_extras"]["PLATFORM_REGISTRY"]
    enabled_features = hass.data["ramses_extras"]["enabled_features"]

    for feature_name, setup_func in platform_registry.get("binary_sensor", {}).items():
        # Only call setup functions for enabled features
        if enabled_features.get(feature_name, False):
            _LOGGER.info(
                f"MAIN BINARY_SENSOR PLATFORM: Calling setup for enabled feature "
                f"{feature_name}"
            )
            try:
                await setup_func(hass, config_entry, async_add_entities)
            except Exception as e:
                _LOGGER.error(
                    f"Error setting up binary_sensor platform for {feature_name}: {e}"
                )
        else:
            _LOGGER.debug(f"Skipping disabled binary_sensor feature: {feature_name}")
