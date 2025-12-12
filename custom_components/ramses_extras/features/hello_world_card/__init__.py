# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more debugrmation
#
"""Hello World Switch Card feature factory.

This module provides the main factory function and manager for the
 Hello World Switch Card feature,
which demonstrates the complete Ramses Extras architecture pattern.

:platform: Home Assistant
:feature: Hello World Switch Card
:architecture: Ramses Extras Framework
"""

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

import logging

from ...framework.base_classes.base_card_manager import BaseCardManager
from ...framework.helpers.entity.simple_entity_manager import SimpleEntityManager
from ...framework.helpers.platform import PlatformSetup
from .automation import create_hello_world_automation
from .const import DOMAIN as HELLO_WORLD_DOMAIN
from .const import HELLO_WORLD_CARD_CONFIGS
from .platforms.binary_sensor import (
    async_setup_entry as binary_sensor_async_setup_entry,
)
from .platforms.number import async_setup_entry as number_async_setup_entry
from .platforms.sensor import async_setup_entry as sensor_async_setup_entry
from .platforms.switch import async_setup_entry as switch_async_setup_entry

_LOGGER = logging.getLogger(__name__)


class HelloWorldCardManager(BaseCardManager):
    """Manages Hello World cards within the feature."""

    def __init__(self, hass: "HomeAssistant", config_entry: ConfigEntry):
        """Initialize the Hello World card manager.

        :param hass: Home Assistant instance
        :type hass: HomeAssistant
        :param config_entry: Configuration entry containing integration configuration
        :type config_entry: ConfigEntry
        """
        super().__init__(hass, config_entry, HELLO_WORLD_DOMAIN)

    def _get_card_configurations(self) -> list[dict[str, Any]]:
        """Get card configurations from the feature's const module.

        :return: List of card configuration dictionaries
        :rtype: list[dict[str, Any]]
        """
        return HELLO_WORLD_CARD_CONFIGS


def create_hello_world_card_feature(
    hass: "HomeAssistant", config_entry: ConfigEntry
) -> dict[str, Any]:
    """Factory function to create Hello World card feature.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param config_entry: Configuration entry containing integration configuration
    :type config_entry: ConfigEntry
    :return: Hello World card feature with card management capabilities
    :rtype: dict[str, Any]
    """
    # Use framework's SimpleEntityManager instead of custom HelloWorldEntities
    entities_manager = SimpleEntityManager(hass)

    # Create automation manager
    automation_manager = create_hello_world_automation(hass, config_entry)

    # Store in Home Assistant data for access by WebSocket commands
    if not hasattr(hass, "data"):
        hass.data = {}
    if "ramses_extras" not in hass.data:
        hass.data["ramses_extras"] = {}
    hass.data["ramses_extras"]["hello_world_entities"] = entities_manager
    hass.data["ramses_extras"]["hello_world_automation"] = automation_manager

    _LOGGER.debug(
        "✅ Hello World feature created with framework entities manager and automation"
    )

    return {
        "entities": entities_manager,
        "automation": automation_manager,
        "card_manager": HelloWorldCardManager(hass, config_entry),
        "platforms": {
            "switch": switch_async_setup_entry,
            "binary_sensor": binary_sensor_async_setup_entry,
            "sensor": sensor_async_setup_entry,  # Placeholder
            "number": number_async_setup_entry,  # Placeholder
        },
        "feature_name": HELLO_WORLD_DOMAIN,
    }


__all__ = [
    "HelloWorldCardManager",
    "create_hello_world_card_feature",
]
