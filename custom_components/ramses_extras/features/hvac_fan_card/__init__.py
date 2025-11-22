"""HVAC Fan Card Feature.

This module provides card management functionality for HVAC fan cards,
following the feature-centric architecture pattern where each feature
handles its own business logic.

Cards are configured within the feature folder similar to entities,
enabling multiple cards and/or entities within a single feature.
"""

import logging
from pathlib import Path
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import CARD_FOLDER, INTEGRATION_DIR

_LOGGER = logging.getLogger(__name__)


class HvacFanCardManager:
    """Manages HVAC fan cards within the feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the HVAC fan card manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        self.hass = hass
        self.config_entry = config_entry
        self._registered_cards: dict[str, dict[str, Any]] = {}

        _LOGGER.info("HVAC Fan Card manager initialized")

    async def async_register_cards(self) -> dict[str, dict[str, Any]]:
        """Register available HVAC fan cards.

        Returns:
            Dictionary of registered card information
        """
        try:
            _LOGGER.debug("Starting HVAC fan card registration")

            # Get card configurations from const.py
            from .const import HVAC_FAN_CARD_CONFIGS

            # Register each card
            for card_config in HVAC_FAN_CARD_CONFIGS:
                card_info = await self._register_single_card(card_config)

                if card_info:
                    self._registered_cards[card_config["card_id"]] = card_info
                    _LOGGER.info(
                        f"✅ HVAC Fan Card registered successfully: {card_info['name']}"
                    )

            return self._registered_cards

        except Exception as e:
            _LOGGER.error(f"Failed to register HVAC fan cards: {e}")
            import traceback

            _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")
            return {}

    async def _register_single_card(
        self, card_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Register a single card based on configuration.

        Args:
            card_config: Card configuration from const.py

        Returns:
            Card registration information or None if failed
        """
        try:
            card_id = card_config["card_id"]
            card_name = card_config["card_name"]
            card_location = card_config.get("location", card_id)

            # Check if card files exist
            from pathlib import Path

            from ...const import CARD_FOLDER, INTEGRATION_DIR

            card_path = INTEGRATION_DIR / CARD_FOLDER / card_location
            card_js_path = card_path / f"{card_id}.js"

            if not card_path.exists():
                _LOGGER.warning(f"Card directory not found at {card_path}")
                return None

            if not card_js_path.exists():
                _LOGGER.warning(f"Card JavaScript file not found at {card_js_path}")
                return None

            # Create card registration info
            registration_info = {
                "type": card_id,
                "name": card_name,
                "description": card_config.get("description", ""),
                "preview": card_config.get("preview", True),
                "documentation_url": card_config.get(
                    "documentation_url", "https://github.com/wimpie70/ramses_extras"
                ),
                "js_path": str(card_js_path.relative_to(INTEGRATION_DIR)),
                "location": card_location,
                "feature": "hvac_fan_card",
            }

            _LOGGER.debug(f"Card registration info created for {card_id}")
            return registration_info

        except Exception as e:
            _LOGGER.error(
                f"Failed to register card {card_config.get('card_id', 'unknown')}: {e}"
            )
            return None

    async def async_cleanup(self) -> None:
        """Cleanup card resources."""
        _LOGGER.info("Cleaning up HVAC fan card manager")
        self._registered_cards.clear()

    def get_registered_cards(self) -> dict[str, dict[str, Any]]:
        """Get all registered cards.

        Returns:
            Dictionary of registered card information
        """
        return self._registered_cards.copy()


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
        "feature_name": "hvac_fan_card",
    }


__all__ = [
    "HvacFanCardManager",
    "create_hvac_fan_card_feature",
]
