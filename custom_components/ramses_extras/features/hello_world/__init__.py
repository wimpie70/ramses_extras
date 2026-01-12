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

from ...framework.helpers.entity.simple_entity_manager import SimpleEntityManager
from .automation import create_hello_world_automation
from .const import DOMAIN as HELLO_WORLD_DOMAIN

# HELLO_WORLD_CONFIGS removed - now handled by CardRegistry
from .platforms.binary_sensor import (
    async_setup_entry as binary_sensor_async_setup_entry,
)
from .platforms.sensor import async_setup_entry as sensor_async_setup_entry
from .platforms.switch import async_setup_entry as switch_async_setup_entry

_LOGGER = logging.getLogger(__name__)


# Card manager removed - CardRegistry handles all card registration
def create_hello_world_feature(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    skip_automation_setup: bool = False,
) -> dict[str, Any]:
    """Factory function to create Hello World card feature.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param config_entry: Configuration entry containing integration configuration
    :type config_entry: ConfigEntry
    :param skip_automation_setup: If True, don't start the automation manager
    :type skip_automation_setup: bool
    :return: Hello World card feature with card management capabilities
    :rtype: dict[str, Any]
    """
    hass.data.setdefault("ramses_extras", {})
    registry = hass.data["ramses_extras"]

    entities_manager = registry.get("hello_world_entities")
    if entities_manager is None:
        entities_manager = SimpleEntityManager(hass)
        registry["hello_world_entities"] = entities_manager

    automation_manager = registry.get("hello_world_automation")
    automation_created = False
    if automation_manager is None:
        automation_manager = create_hello_world_automation(hass, config_entry)
        registry["hello_world_automation"] = automation_manager
        automation_created = True

    # Start the automation manager if not skipped
    if not skip_automation_setup and automation_created:
        hass.async_create_task(automation_manager.start())

    _LOGGER.debug(
        "✅ Hello World feature created with framework entities manager and automation"
    )

    return {
        "entities": entities_manager,
        "automation": automation_manager,
        # Card manager removed - CardRegistry handles card registration
        "platforms": {
            "switch": switch_async_setup_entry,
            "binary_sensor": binary_sensor_async_setup_entry,
            "sensor": sensor_async_setup_entry,  # Placeholder
        },
        "feature_name": HELLO_WORLD_DOMAIN,
    }


__all__ = [
    "create_hello_world_feature",
]
