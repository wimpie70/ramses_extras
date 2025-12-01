# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Hello World Switch Card feature factory."""

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

import logging

from ...framework.helpers.platform import PlatformSetup
from .const import DOMAIN as HELLO_WORLD_DOMAIN
from .entities import HelloWorldEntities
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
        """Register available Hello World cards."""
        try:
            _LOGGER.info("🎴 Starting Hello World card registration")

            # Get card configurations from const.py
            from .const import HELLO_WORLD_CARD_CONFIGS

            _LOGGER.info(
                f"📋 Card configurations found: {len(HELLO_WORLD_CARD_CONFIGS)}"
            )
            _LOGGER.info(f"📄 Card configs: {HELLO_WORLD_CARD_CONFIGS}")

            # Register each card
            for card_config in HELLO_WORLD_CARD_CONFIGS:
                _LOGGER.info(f"🔄 Registering card config: {card_config}")
                card_info = await self._register_single_card(card_config)

                if card_info:
                    card_id_str = str(
                        card_config["card_id"]
                    )  # Explicit string conversion
                    self._registered_cards[card_id_str] = card_info
                    _LOGGER.info(
                        f"✅ Hello World Card registered successfully: "
                        f"{card_info['name']}"
                    )
                    _LOGGER.info(f"📦 Card info: {card_info}")
                else:
                    _LOGGER.warning(f"⚠️ Failed to register card: {card_config}")

            _LOGGER.info(f"🎯 Final registered cards: {self._registered_cards}")
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
            Card registration information or None if failed
        """
        try:
            card_id = card_config["card_id"]
            card_name = card_config["card_name"]
            card_location = card_config.get("location", card_id)

            _LOGGER.info(f"🔍 Registering single card: {card_id} ({card_name})")
            _LOGGER.info(f"📍 Card location: {card_location}")

            # Check if card files exist
            from pathlib import Path

            from ...const import INTEGRATION_DIR
            from ...framework.helpers.paths import DEPLOYMENT_PATHS

            # Use DEPLOYMENT_PATHS for proper deployment structure
            card_path = DEPLOYMENT_PATHS.get_source_feature_path(
                INTEGRATION_DIR, "hello_world_card"
            )
            card_js_path = card_path / f"{card_id}.js"

            _LOGGER.info(f"📁 Card directory path: {card_path}")
            _LOGGER.info(f"📄 Card JS path: {card_js_path}")
            _LOGGER.info(f"📂 Card directory exists: {card_path.exists()}")
            _LOGGER.info(f"📄 Card JS file exists: {card_js_path.exists()}")

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
                "feature": "hello_world_card",
            }

            _LOGGER.info(f"✅ Card registration info created for {card_id}")
            _LOGGER.info(f"📦 Registration info: {registration_info}")
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
        """Cleanup card resources."""
        _LOGGER.info("Cleaning up Hello World card manager")
        self._registered_cards.clear()

    def get_registered_cards(self) -> dict[str, dict[str, Any]]:
        """Get all registered cards.

        Returns:
            Dictionary of registered card information
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
    return {
        "entities": HelloWorldEntities(hass, config_entry),
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
