"""HVAC Fan Card Feature.

This module provides card management functionality for HVAC fan cards,
following the feature-centric architecture pattern where each feature
handles its own business logic.

Cards are configured within the feature folder similar to entities,
enabling multiple cards and/or entities within a single feature.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import CARD_FOLDER, INTEGRATION_DIR
from ...framework.base_classes.base_card_manager import BaseCardManager
from .const import DOMAIN as HVAC_FAN_CARD_DOMAIN
from .const import HVAC_FAN_CARD_CONFIGS

_LOGGER = logging.getLogger(__name__)


class HvacFanCardManager(BaseCardManager):
    """Manages HVAC fan cards within the feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the HVAC fan card manager.

        :param hass: Home Assistant instance
        :type hass: HomeAssistant
        :param config_entry: Configuration entry containing integration configuration
        :type config_entry: ConfigEntry
        """
        super().__init__(hass, config_entry, HVAC_FAN_CARD_DOMAIN)
        _LOGGER.info("HVAC Fan Card manager initialized")

    def _get_card_configurations(self) -> list[dict[str, Any]]:
        """Get card configurations from the feature's const module.

        :return: List of card configuration dictionaries
        :rtype: list[dict[str, Any]]
        """
        return HVAC_FAN_CARD_CONFIGS


def create_hvac_fan_card_feature(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Factory function to create HVAC fan card feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HVAC fan card feature with card management capabilities
    """
    return {
        "card_manager": HvacFanCardManager(hass, config_entry),
        "feature_name": HVAC_FAN_CARD_DOMAIN,
    }


__all__ = [
    "HvacFanCardManager",
    "create_hvac_fan_card_feature",
]
