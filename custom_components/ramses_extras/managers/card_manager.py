"""Card Manager for Ramses Extras integration."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant import config_entries
from homeassistant.helpers import selector

from ..const import AVAILABLE_FEATURES, CARD_FOLDER, DOMAIN, INTEGRATION_DIR

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class CardManager:
    """Manages installation and removal of custom cards."""

    def __init__(self, hass: "HomeAssistant") -> None:
        """Initialize card manager."""
        self.hass = hass
        self.www_community_path = Path(hass.config.path("www", "community"))

    async def install_cards(self, enabled_cards: list[str]) -> None:
        """Install enabled cards."""
        _LOGGER.info(f"Installing cards: {enabled_cards}")

        for feature_key in enabled_cards:
            feature_config = AVAILABLE_FEATURES.get(feature_key)
            if not feature_config or feature_config.get("category") != "cards":
                continue

            card_source_path = (
                INTEGRATION_DIR / CARD_FOLDER / str(feature_config.get("location", ""))
            )

            if card_source_path.exists():
                # For automatic registration, we don't need to copy files anymore
                # The card is registered as a static resource in async_setup_entry
                _LOGGER.info(f"Card {feature_key} is automatically registered")
            else:
                _LOGGER.warning(
                    f"Cannot register {feature_key}: {card_source_path} not found"
                )

    async def remove_cards(self, disabled_cards: list[str]) -> None:
        """Remove disabled cards."""
        _LOGGER.info(f"Removing cards: {disabled_cards}")

        for feature_key in disabled_cards:
            feature_config = AVAILABLE_FEATURES.get(feature_key)
            if not feature_config or feature_config.get("category") != "cards":
                continue

            card_dest_path = self.www_community_path / feature_key
            await self._remove_card(card_dest_path)

    async def _remove_card(self, card_path: Path) -> None:
        """Remove a custom card."""
        try:
            if card_path.exists():
                import shutil

                await self.hass.async_add_executor_job(shutil.rmtree, card_path)
                _LOGGER.info(f"Successfully removed card from {card_path}")
            else:
                _LOGGER.debug(
                    f"Card path does not exist, nothing to remove: {card_path}"
                )
        except Exception as e:
            _LOGGER.error(f"Failed to remove card: {e}")

    async def update_card_resources(self, enabled_cards: list[str]) -> None:
        """Update card resources for enabled cards."""
        _LOGGER.info(f"Updating card resources for: {enabled_cards}")

        for feature_key in enabled_cards:
            feature_config = AVAILABLE_FEATURES.get(feature_key)
            if not feature_config or feature_config.get("category") != "cards":
                continue

            location = str(feature_config.get("location", ""))
            if location:
                card_path = INTEGRATION_DIR / CARD_FOLDER / location
                if card_path.exists():
                    resource_url = (
                        f"/local/ramses_extras/{feature_key}/{card_path.name}"
                    )
                    _LOGGER.info(f"Card resource available: {resource_url}")
                else:
                    _LOGGER.warning(
                        f"Card file not found for {feature_key}: {card_path}"
                    )
