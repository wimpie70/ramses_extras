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
from ...framework.helpers.platform import PlatformSetup
from .automation import create_hello_world_automation
from .const import DOMAIN as HELLO_WORLD_DOMAIN
from .platforms.binary_sensor import (
    async_setup_entry as binary_sensor_async_setup_entry,
)
from .platforms.number import async_setup_entry as number_async_setup_entry
from .platforms.sensor import async_setup_entry as sensor_async_setup_entry
from .platforms.switch import async_setup_entry as switch_async_setup_entry

_LOGGER = logging.getLogger(__name__)


class HelloWorldCardManager:
    """Manages Hello World cards within the feature."""

    def __init__(self, hass: "HomeAssistant", config_entry: ConfigEntry):
        """Initialize the Hello World card manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._registered_cards: dict[str, dict[str, Any]] = {}

    async def async_register_cards(self) -> dict[str, dict[str, Any]]:
        """Register available Hello World cards.

        This method registers all Hello World cards defined in the configuration.
        It checks for card files, validates their existence, and creates registration
        debugrmation for each card.

        Returns:
            Dictionary of registered card debugrmation,
            where keys are card IDs and values
            are card registration details.

        Raises:
            Exception: If there are errors during card registration.
        """
        try:
            _LOGGER.debug("🎴 Starting Hello World card registration")

            # Get card configurations from const.py
            from .const import HELLO_WORLD_CARD_CONFIGS

            _LOGGER.debug(
                f"📋 Card configurations found: {len(HELLO_WORLD_CARD_CONFIGS)}"
            )
            _LOGGER.debug(f"📄 Card configs: {HELLO_WORLD_CARD_CONFIGS}")

            # Register each card
            for card_config in HELLO_WORLD_CARD_CONFIGS:
                _LOGGER.debug(f"🔄 Registering card config: {card_config}")
                card_debug = await self._register_single_card(card_config)

                if card_debug:
                    card_id_str = str(
                        card_config["card_id"]
                    )  # Explicit string conversion
                    self._registered_cards[card_id_str] = card_debug
                    _LOGGER.debug(
                        f"✅ Hello World Card registered successfully: "
                        f"{card_debug['name']}"
                    )
                    _LOGGER.debug(f"📦 Card debug: {card_debug}")
                else:
                    _LOGGER.warning(f"⚠️ Failed to register card: {card_config}")

            _LOGGER.debug(f"🎯 Final registered cards: {self._registered_cards}")
            return self._registered_cards

        except Exception as e:
            _LOGGER.error(f"❌ Failed to register Hello World cards: {e}")
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
            Card registration debugrmation or None if failed
        """
        try:
            card_id = card_config["card_id"]
            card_name = card_config["card_name"]
            card_location = card_config.get("location", card_id)

            _LOGGER.debug(f"🔍 Registering single card: {card_id} ({card_name})")
            _LOGGER.debug(f"📍 Card location: {card_location}")

            # Check if card files exist
            from pathlib import Path

            from ...const import INTEGRATION_DIR
            from ...framework.helpers.paths import DEPLOYMENT_PATHS

            # Use DEPLOYMENT_PATHS for proper deployment structure
            card_path = DEPLOYMENT_PATHS.get_source_feature_path(
                INTEGRATION_DIR, "hello_world_card"
            )
            card_js_path = card_path / f"{card_id}.js"

            _LOGGER.debug(f"📁 Card directory path: {card_path}")
            _LOGGER.debug(f"📄 Card JS path: {card_js_path}")
            _LOGGER.debug(f"📂 Card directory exists: {card_path.exists()}")
            _LOGGER.debug(f"📄 Card JS file exists: {card_js_path.exists()}")

            if not card_path.exists():
                _LOGGER.error(f"❌ Card directory not found at {card_path}")
                return None

            if not card_js_path.exists():
                _LOGGER.error(f"❌ Card JavaScript file not found at {card_js_path}")
                return None

            # Create card registration debug
            registration_debug = {
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
                "feature": "hello_world_card",
            }

            _LOGGER.debug(f"✅ Card registration debug created for {card_id}")
            _LOGGER.debug(f"📦 Registration debug: {registration_debug}")
            return registration_debug

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
        _LOGGER.debug("Cleaning up Hello World card manager")
        self._registered_cards.clear()

    def get_registered_cards(self) -> dict[str, dict[str, Any]]:
        """Get all registered cards.

        Returns a copy of the registered cards dictionary to prevent external
         modifications to the internal state.

        Returns:
            Dictionary of registered card debugrmation,
             where keys are card IDs and values are card registration details.
        """
        return self._registered_cards.copy()


def create_hello_world_card_feature(
    hass: "HomeAssistant", config_entry: ConfigEntry
) -> dict[str, Any]:
    """Factory function to create Hello World card feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Hello World card feature with card management capabilities
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
        "feature_name": "hello_world_card",
    }


__all__ = [
    "HelloWorldCardManager",
    "create_hello_world_card_feature",
]
