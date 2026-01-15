"""Clean CardRegistry for Ramses Extras Lovelace Cards.

This module provides a simple, standards-compliant registry for managing
Home Assistant Lovelace custom cards. It follows the architectural principle:
- Resources are registered unconditionally at startup
- Features control behavior, not existence
- Cards are defined in feature const.py files (feature-centric)

The registry uses Home Assistant's standard lovelace_resources storage
and proper path resolution for reliable card registration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

# Standard HA Lovelace resources storage key
STORAGE_KEY = "lovelace_resources"
STORAGE_VERSION = 1


@dataclass(frozen=True)
class LovelaceCard:
    """Definition of a Lovelace custom card.

    This dataclass serves as the single source of truth for all card definitions.
    All cards must be defined here for proper registration.

    Attributes:
        type: Card type identifier (e.g., "hello-world")
        resource_path: Resource path for HA (/config/www/ramses_extras/...)
        name: Human readable card name
        description: Card description
        preview: Whether card should show preview in editor
    """

    type: str
    resource_path: str
    name: str
    description: str = ""
    preview: bool = True


class CardRegistry:
    """Clean CardRegistry for Ramses Extras Lovelace cards.

    This class provides simple, reliable registration using Home Assistant's
    standard lovelace_resources storage system. It follows these principles:

    1. Unconditional registration at startup (before dashboards load)
    2. Standard HA storage patterns (lovelace_resources)
    3. Proper path resolution using PathConstants
    4. Feature-centric card definitions from const.py files
    5. Simple, maintainable implementation

    Usage:
        registry = CardRegistry(hass)
        await registry.register_discovered_cards()
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the CardRegistry.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    @staticmethod
    def bootstrap_resource(version: str) -> LovelaceCard:
        """Return the single Lovelace resource needed for Ramses Extras cards.

        With the MutationObserver-based loader, we register only a tiny bootstrap
        module (`main.js`) and let it dynamically import feature cards/editors.

        The resource URL is versioned to make it easier to diagnose user issues
        (reported URLs include the integration version).
        """

        return LovelaceCard(
            type="ramses-extras",
            resource_path=f"/local/ramses_extras/v{version}/helpers/main.js",
            name="Ramses Extras (bootstrap)",
        )

    async def register(self, cards: Iterable[LovelaceCard]) -> None:
        """Register cards with Home Assistant's Lovelace system.

        This method registers all provided cards using Home Assistant's standard
        lovelace_resources storage system. Cards are registered unconditionally,
        ensuring they are available before Lovelace parses any dashboards.

        Args:
            cards: Iterable of LovelaceCard definitions to register

        Note:
            This should be called once during integration startup, before any
            dashboards are loaded. All cards should be registered together.
        """
        cards_list = list(cards)

        if not cards_list:
            _LOGGER.debug("No cards to register")
            return

        _LOGGER.info("🔧 Registering %d cards with Lovelace resources", len(cards_list))

        try:
            # Load existing resources
            data = await self._store.async_load() or {"items": []}

            # Migrate existing resources that might not have an 'id' field
            needs_save = False
            for item in data["items"]:
                if "url" in item and isinstance(item["url"], str):
                    # Migrate invalid legacy filesystem URLs to browser URLs
                    # (HA serves /config/www as /local)
                    if item["url"].startswith("/config/www/"):
                        item["url"] = item["url"].replace("/config/www", "/local", 1)
                        item["id"] = item["url"].replace("/", "_").strip("_")
                        needs_save = True
                        _LOGGER.info(
                            "🔧 Migrated legacy resource URL to: %s", item["url"]
                        )

                if "id" not in item:
                    # Generate a unique ID for the resource from its URL
                    item["id"] = item["url"].replace("/", "_").strip("_")
                    needs_save = True
                    _LOGGER.info("🔧 Migrated resource: %s", item["url"])

            # Remove legacy Ramses Extras resources. We only want the versioned
            # bootstrap entrypoint to be listed in lovelace_resources.
            allowed_urls = {card.resource_path for card in cards_list}
            if data.get("items"):
                filtered_items = []
                removed = 0
                for item in data["items"]:
                    url = item.get("url")
                    if not isinstance(url, str):
                        filtered_items.append(item)
                        continue

                    is_ramses_extras = url.startswith("/local/ramses_extras/")
                    if is_ramses_extras and url not in allowed_urls:
                        removed += 1
                        needs_save = True
                        continue

                    filtered_items.append(item)

                if removed:
                    _LOGGER.info(
                        "Removed %d legacy Ramses Extras Lovelace resources",
                        removed,
                    )
                data["items"] = filtered_items

            existing_resources = {item["url"] for item in data["items"]}

            # Add new resources
            new_resources_added = 0
            for card in cards_list:
                if card.resource_path not in existing_resources:
                    # Generate a unique ID for the resource
                    # Use the URL as the ID since it should be unique
                    resource_id = card.resource_path.replace("/", "_").strip("_")
                    resource_entry = {
                        "id": resource_id,
                        "url": card.resource_path,
                        "type": "module",
                    }
                    data["items"].append(resource_entry)
                    existing_resources.add(card.resource_path)
                    new_resources_added += 1
                    needs_save = True
                    _LOGGER.info(
                        "📝 Added resource: %s -> %s", card.type, card.resource_path
                    )
                else:
                    _LOGGER.debug("Resource already exists: %s", card.resource_path)

            # Save if new resources were added or migrations were needed
            if new_resources_added > 0 or needs_save:
                await self._store.async_save(data)
                if new_resources_added > 0:
                    _LOGGER.info(
                        "✅ CardRegistry: Added %d new resources (total: %d)",
                        new_resources_added,
                        len(data["items"]),
                    )
                else:
                    _LOGGER.debug("CardRegistry: Migrated existing resources")
            else:
                _LOGGER.debug("CardRegistry: No changes needed")

        except Exception as e:
            _LOGGER.error("❌ CardRegistry registration failed: %s", str(e))
            # Don't raise - let the integration continue
            # Card registration issues shouldn't break startup

    async def register_discovered_cards(self) -> None:
        """Deprecated compatibility wrapper.

        Use :meth:`register_bootstrap` instead.
        """
        _LOGGER.warning(
            "register_discovered_cards() is deprecated; use register_bootstrap()"
        )

    async def register_bootstrap(self, version: str) -> None:
        """Register the versioned bootstrap resource for Ramses Extras cards."""

        await self.register([self.bootstrap_resource(version)])

    @staticmethod
    def lovelace_type(card_type: str) -> str:
        """Get the Lovelace YAML type for a card.

        This method returns the proper type string for use in
        Lovelace YAML configuration. The custom: prefix is added here
        because it's only needed in YAML, not internally.

        Args:
            card_type: Card type identifier (e.g., "hello-world")

        Returns:
            Type string for YAML (e.g., "custom:hello-world")

        Example:
            CardRegistry.lovelace_type("hello-world")  # returns "custom:hello-world"
        """
        return f"custom:{card_type}"

    @staticmethod
    def get_card_info_for_js(
        card_type: str, name: str, description: str = "", preview: bool = True
    ) -> dict:
        """Get card info for JavaScript customCards registration.

        This method provides the correct format for window.customCards
        registration. The type should NOT include the custom: prefix.

        Args:
            card_type: Card type identifier (e.g., "hello-world")
            name: Human readable card name
            description: Card description
            preview: Whether card should show preview in editor

        Returns:
            Dictionary for window.customCards.push()
        """
        return {
            "type": card_type,  # No custom: prefix for internal registration
            "name": name,
            "description": description,
            "preview": preview,
        }
