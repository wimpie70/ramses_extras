"""Test select platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras import select


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass):
    """Test successful setup of select platform."""
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "select": {
                    "temp_control": AsyncMock(),
                    "sensor_control": AsyncMock(),
                }
            },
            "enabled_features": {
                "temp_control": True,
                "sensor_control": False,
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await select.async_setup_entry(hass, config_entry, async_add_entities)

    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["select"][
        "temp_control"
    ].assert_awaited_once_with(hass, config_entry, async_add_entities)

    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["select"][
        "sensor_control"
    ].assert_not_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_no_registry(hass):
    """Test setup when platform registry has no select platforms."""
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "select": {},
            },
            "enabled_features": {},
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await select.async_setup_entry(hass, config_entry, async_add_entities)


@pytest.mark.asyncio
async def test_async_setup_entry_exception_handling(hass, caplog):
    """Test exception handling during setup."""
    mock_setup_func = AsyncMock(side_effect=Exception("Test error"))

    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "select": {
                    "temp_control": mock_setup_func,
                }
            },
            "enabled_features": {
                "temp_control": True,
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await select.async_setup_entry(hass, config_entry, async_add_entities)

    assert (
        "Error setting up select platform for temp_control: Test error" in caplog.text
    )


@pytest.mark.asyncio
async def test_async_setup_entry_disabled_feature_skipped(hass, caplog):
    """Test that disabled features are skipped with debug log."""
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "select": {
                    "temp_control": AsyncMock(),
                }
            },
            "enabled_features": {
                "temp_control": False,
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    import logging

    caplog.set_level(logging.DEBUG)

    await select.async_setup_entry(hass, config_entry, async_add_entities)

    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["select"][
        "temp_control"
    ].assert_not_awaited()

    assert "Skipping disabled select feature: temp_control" in caplog.text
