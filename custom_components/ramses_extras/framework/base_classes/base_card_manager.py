"""Base CardManager class for Ramses Extras integration.

This module provides a base class for card management that can be inherited
by feature-specific card managers. It implements common card registration,
cleanup, and management functionality.
"""

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import INTEGRATION_DIR
from ..helpers.paths import DEPLOYMENT_PATHS

_LOGGER = logging.getLogger(__name__)


class BaseCardManager:
    """Base class for managing cards within features.

    This class provides common functionality for card registration, validation,
    and cleanup that can be inherited by feature-specific card managers.
    """

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, feature_name: str
    ):
        """Initialize the base card manager.

        :param hass: Home Assistant instance
        :type hass: HomeAssistant
        :param config_entry: Configuration entry containing integration configuration
        :type config_entry: ConfigEntry
        :param feature_name: Name of the feature this manager belongs to
        :type feature_name: str
        """
        self.hass = hass
        self.config_entry = config_entry
        self.feature_name = feature_name
        self._registered_cards: dict[str, dict[str, Any]] = {}

    async def async_register_cards(self) -> dict[str, dict[str, Any]]:
        """Register available cards for the feature.

        This method should be overridden by subclasses to provide feature-specific
        card configurations, but can call the base implementation for common logic.

        :return: Dictionary of registered card information
        :rtype: dict[str, dict[str, Any]]
        """
        try:
            _LOGGER.debug(
                f"🎴 Starting card registration for feature: {self.feature_name}"
            )

            # Get card configurations from feature's const module
            card_configs = self._get_card_configurations()

            # Register each card
            for card_config in card_configs:
                card_info = await self._register_single_card(card_config)

                if card_info:
                    card_id = str(card_config["card_id"])  # Explicit string conversion
                    self._registered_cards[card_id] = card_info
                    _LOGGER.debug(
                        f"✅ Card registered successfully: {card_info['name']}"
                    )
                    _LOGGER.debug(f"📦 Card info: {card_info}")
                else:
                    _LOGGER.warning(f"⚠️ Failed to register card: {card_config}")

            _LOGGER.debug(f"🎯 Final registered cards: {self._registered_cards}")
            return self._registered_cards

        except Exception as e:
            _LOGGER.error(f"❌ Failed to register cards for {self.feature_name}: {e}")
            import traceback

            _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")
            return {}

    def _get_card_configurations(self) -> list[dict[str, Any]]:
        """Get card configurations from the feature's const module.

        This method should be overridden by subclasses to return the specific
        card configurations for their feature.

        :return: List of card configuration dictionaries
        :rtype: list[dict[str, Any]]
        """
        # This should be overridden by subclasses
        return []

    async def _register_single_card(
        self, card_config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Register a single card based on configuration.

        :param card_config: Card configuration from const.py
        :type card_config: dict[str, Any]
        :return: Card registration information or None if failed
        :rtype: dict[str, Any] | None
        """
        try:
            card_id = card_config["card_id"]
            card_name = card_config["card_name"]
            card_location = card_config.get("location", card_id)

            # _LOGGER.debug(f"🔍 Registering single card: {card_id} ({card_name})")
            # _LOGGER.debug(f"📍 Card location: {card_location}")

            # Check if card files exist
            card_path = DEPLOYMENT_PATHS.get_source_feature_path(
                INTEGRATION_DIR, self.feature_name
            )
            card_js_path = card_path / f"{card_id}.js"

            # _LOGGER.debug(f"📁 Card directory path: {card_path}")
            # _LOGGER.debug(f"📄 Card JS path: {card_js_path}")
            # _LOGGER.debug(f"📂 Card directory exists: {card_path.exists()}")
            # _LOGGER.debug(f"📄 Card JS file exists: {card_js_path.exists()}")

            if not card_path.exists():
                _LOGGER.error(f"❌ Card directory not found at {card_path}")
                return None

            if not card_js_path.exists():
                _LOGGER.error(f"❌ Card JavaScript file not found at {card_js_path}")
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
                "card_dir_path": str(card_path.relative_to(INTEGRATION_DIR)),
                "location": card_location,
                "feature": self.feature_name,
            }

            _LOGGER.debug(f"✅ Card registration info created for {card_id}")
            _LOGGER.debug(f"📦 Registration info: {registration_info}")
            return registration_info

        except Exception as e:
            _LOGGER.error(
                f"❌ Failed to register card "
                f"{card_config.get('card_id', 'unknown')}: {e}"
            )
            import traceback

            _LOGGER.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def async_cleanup(self) -> None:
        """Cleanup card resources.

        Clears all registered cards and performs cleanup operations.
        This method should be called when the feature is being unloaded.
        """
        _LOGGER.debug(f"Cleaning up {self.feature_name} card manager")
        self._registered_cards.clear()

    def get_registered_cards(self) -> dict[str, dict[str, Any]]:
        """Get all registered cards.

        Returns a copy of the registered cards dictionary to prevent external
        modifications to the internal state.

        :return: Dictionary of registered card information
        :rtype: dict[str, dict[str, Any]]
        """
        return self._registered_cards.copy()


__all__ = [
    "BaseCardManager",
]
