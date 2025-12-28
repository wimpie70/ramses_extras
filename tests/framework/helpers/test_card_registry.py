"""Tests for CardRegistry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.card_registry import (
    STORAGE_KEY,
    CardRegistry,
    LovelaceCard,
)


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant instance."""
    return MagicMock()


@pytest.fixture
def card_registry(mock_hass):
    """CardRegistry instance with mocked store."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.card_registry.Store"
    ) as mock_store_class:
        mock_store = mock_store_class.return_value
        mock_store.async_load = AsyncMock(return_value={"items": []})
        mock_store.async_save = AsyncMock()
        return CardRegistry(mock_hass)


@pytest.mark.asyncio
async def test_register_bootstrap_adds_resource(card_registry):
    """Test that register_bootstrap adds the versioned bootstrap resource."""
    version = "1.2.3"
    expected_url = f"/local/ramses_extras/v{version}/helpers/main.js"

    await card_registry.register_bootstrap(version)

    # Verify async_save was called with the bootstrap resource
    save_data = card_registry._store.async_save.call_args[0][0]
    assert len(save_data["items"]) == 1
    assert save_data["items"][0]["url"] == expected_url
    assert save_data["items"][0]["type"] == "module"


@pytest.mark.asyncio
async def test_register_removes_legacy_resources(card_registry):
    """Test that legacy unversioned ramses_extras resources are removed."""
    # Setup initial data with legacy and non-ramses resources
    legacy_url = "/local/ramses_extras/features/hello_world/hello-world.js"
    initial_items = [
        {
            "id": "legacy_card",
            "url": legacy_url,
            "type": "module",
        },
        {
            "id": "other_card",
            "url": "/local/other_integration/card.js",
            "type": "module",
        },
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    # Verify legacy resource was removed but other integration's resource remains
    save_data = card_registry._store.async_save.call_args[0][0]
    urls = [item["url"] for item in save_data["items"]]

    # Bootstrap should be added
    assert f"/local/ramses_extras/v{version}/helpers/main.js" in urls
    # Legacy should be removed
    assert legacy_url not in urls
    # Other integration should stay
    assert "/local/other_integration/card.js" in urls


@pytest.mark.asyncio
async def test_register_idempotent(card_registry):
    """Test that registration is idempotent and doesn't duplicate resources."""
    version = "1.2.3"
    url = f"/local/ramses_extras/v{version}/helpers/main.js"
    resource_id = url.replace("/", "_").strip("_")

    initial_items = [
        {"id": resource_id, "url": url, "type": "module"},
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    await card_registry.register_bootstrap(version)

    # async_save should NOT be called if nothing changed
    card_registry._store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_register_migration_config_www(card_registry):
    """Test migration of legacy /config/www/ paths to /local/."""
    legacy_www_path = "/config/www/ramses_extras/something.js"
    initial_items = [
        {"url": legacy_www_path, "type": "module"},
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    # Should have migrated /config/www/ to /local/ and then removed it
    save_data = card_registry._store.async_save.call_args[0][0]
    urls = [item["url"] for item in save_data["items"]]
    assert legacy_www_path not in urls
    assert "/local/ramses_extras/something.js" not in urls
    assert f"/local/ramses_extras/v{version}/helpers/main.js" in urls
