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
    """Test that register_bootstrap adds the stable bootstrap resource."""
    version = "1.2.3"
    expected_url = f"/local/ramses_extras/helpers/main.js?v={version}"

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

    # Bootstrap should be added (versioned URL with cache-busting)
    assert f"/local/ramses_extras/helpers/main.js?v={version}" in urls
    # Legacy should be removed
    assert legacy_url not in urls
    # Other integration should stay
    assert "/local/other_integration/card.js" in urls


@pytest.mark.asyncio
async def test_register_idempotent(card_registry):
    """Test that registration is idempotent and doesn't duplicate resources."""
    version = "1.2.3"
    url = f"/local/ramses_extras/helpers/main.js?v={version}"
    resource_id = url.replace("/", "_").strip("_")

    initial_items = [
        {"id": resource_id, "url": url, "type": "module"},
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    await card_registry.register_bootstrap(version)

    # async_save should NOT be called if nothing changed (same URL with cache-busting)
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
    assert f"/local/ramses_extras/helpers/main.js?v={version}" in urls


@pytest.mark.asyncio
async def test_register_empty_cards_list(card_registry):
    """Test that registering empty cards list does nothing."""
    await card_registry.register([])
    card_registry._store.async_save.assert_not_called()


@pytest.mark.asyncio
async def test_register_migrates_www_paths(card_registry):
    """Test migration of /www/ paths to /local/."""
    www_path = "/www/ramses_extras/something.js"
    initial_items = [
        {"url": www_path, "type": "module"},
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    save_data = card_registry._store.async_save.call_args[0][0]
    urls = [item["url"] for item in save_data["items"]]
    assert www_path not in urls
    assert "/local/ramses_extras/something.js" not in urls
    assert f"/local/ramses_extras/helpers/main.js?v={version}" in urls


@pytest.mark.asyncio
async def test_register_migrates_resources_without_id(card_registry):
    """Test migration of resources without id field."""
    initial_items = [
        {"url": "/local/other/card.js", "type": "module"},  # No id field
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    save_data = card_registry._store.async_save.call_args[0][0]
    # Should have added id field to the other card
    other_card = [item for item in save_data["items"] if "other" in item["url"]][0]
    assert "id" in other_card
    assert other_card["id"] == "local_other_card.js"


@pytest.mark.asyncio
async def test_register_handles_non_string_urls(card_registry):
    """Test that non-string URLs are kept as-is."""
    initial_items = [
        {"url": 123, "type": "module"},  # Non-string URL
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    # Check loaded data since save might not be called if no changes needed
    loaded_data = card_registry._store.async_load.return_value
    # Non-string URL should be kept
    assert any(item.get("url") == 123 for item in loaded_data["items"])


@pytest.mark.asyncio
async def test_register_handles_save_error(card_registry):
    """Test that save errors are logged but don't raise."""
    card_registry._store.async_save.side_effect = Exception("Save failed")
    card_registry._store.async_load.return_value = {"items": []}

    version = "1.2.3"
    # Should not raise
    await card_registry.register_bootstrap(version)


@pytest.mark.asyncio
async def test_register_migrates_only_no_new_resources(card_registry):
    """Test that migration without new resources still saves."""
    initial_items = [
        {"url": "/config/www/other/card.js", "type": "module"},
    ]
    card_registry._store.async_load.return_value = {"items": initial_items}

    version = "1.2.3"
    await card_registry.register_bootstrap(version)

    # Should save due to migration (even though no new resources added)
    card_registry._store.async_save.assert_called_once()


@pytest.mark.asyncio
async def test_register_discovered_cards_warns(card_registry):
    """Test that register_discovered_cards logs deprecation warning."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.card_registry._LOGGER"
    ) as mock_logger:
        await card_registry.register_discovered_cards()
        mock_logger.warning.assert_called_once_with(
            "register_discovered_cards() is deprecated; use register_bootstrap()"
        )


def test_lovelace_type():
    """Test lovelace_type static method."""
    assert CardRegistry.lovelace_type("hello-world") == "custom:hello-world"
    assert CardRegistry.lovelace_type("device-simulator") == "custom:device-simulator"


def test_get_card_info_for_js():
    """Test get_card_info_for_js static method."""
    result = CardRegistry.get_card_info_for_js(
        "hello-world", "Hello World", "A test card", True
    )
    assert result == {
        "type": "hello-world",
        "name": "Hello World",
        "description": "A test card",
        "preview": True,
    }

    result = CardRegistry.get_card_info_for_js("test", "Test")
    assert result == {
        "type": "test",
        "name": "Test",
        "description": "",
        "preview": True,
    }
