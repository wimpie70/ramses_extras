"""Select platform for Ramses Extras."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform - dynamically discover and call feature platforms."""

    platform_registry = hass.data["ramses_extras"]["PLATFORM_REGISTRY"]
    enabled_features = hass.data["ramses_extras"]["enabled_features"]

    for feature_name, setup_func in platform_registry.get("select", {}).items():
        if enabled_features.get(feature_name, False):
            try:
                await setup_func(hass, config_entry, async_add_entities)
            except Exception as err:
                _LOGGER.error(
                    "Error setting up select platform for %s: %s",
                    feature_name,
                    err,
                )
        else:
            _LOGGER.debug("Skipping disabled select feature: %s", feature_name)
