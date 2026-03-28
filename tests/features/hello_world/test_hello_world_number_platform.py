"""Tests for Hello World number platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.hello_world.platforms.number import (
    async_setup_entry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def config_entry():
    """Mock config entry."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    return config_entry


@pytest.fixture
def async_add_entities():
    """Mock async_add_entities callback."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_async_setup_entry(hass, config_entry, async_add_entities):
    """Test setting up Hello World number platform."""
    # Call the setup function
    await async_setup_entry(hass, config_entry, async_add_entities)

    # The function is a placeholder and doesn't add any entities
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_config(hass, config_entry, async_add_entities):
    """Test setting up Hello World number platform with config."""
    config_entry.data = {"number_config": {"enabled": True}}

    # Call the setup function
    await async_setup_entry(hass, config_entry, async_add_entities)

    # The function is a placeholder and doesn't add any entities
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_is_async(hass, config_entry, async_add_entities):
    """Test that async_setup_entry is indeed async."""
    import inspect

    assert inspect.iscoroutinefunction(async_setup_entry)

    # Should be awaitable
    result = async_setup_entry(hass, config_entry, async_add_entities)
    assert inspect.isawaitable(result)

    # Await it
    await result


@pytest.mark.asyncio
async def test_async_setup_entry_no_exceptions(hass, config_entry, async_add_entities):
    """Test that async_setup_entry doesn't raise exceptions."""
    # Should not raise any exceptions
    try:
        await async_setup_entry(hass, config_entry, async_add_entities)
    except Exception as e:
        pytest.fail(f"async_setup_entry raised {type(e).__name__} unexpectedly!")


@pytest.mark.asyncio
async def test_async_setup_entry_multiple_calls(hass, config_entry, async_add_entities):
    """Test calling async_setup_entry multiple times."""
    # Call the setup function multiple times
    await async_setup_entry(hass, config_entry, async_add_entities)
    await async_setup_entry(hass, config_entry, async_add_entities)
    await async_setup_entry(hass, config_entry, async_add_entities)

    # Should still not have added any entities
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_with_different_entries(hass, async_add_entities):
    """Test setting up with different config entries."""
    entries = [MagicMock() for _ in range(3)]
    for i, entry in enumerate(entries):
        entry.entry_id = f"test_entry_{i}"

    # Call setup for each entry
    for entry in entries:
        await async_setup_entry(hass, entry, async_add_entities)

    # Should still not have added any entities
    async_add_entities.assert_not_called()
