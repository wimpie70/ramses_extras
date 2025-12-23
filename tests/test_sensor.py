# tests/test_sensor.py
"""Test sensor platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras import sensor


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass):
    """Test successful setup of sensor platform."""
    # Mock the hass data structure
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "sensor": {
                    "default": AsyncMock(),
                    "humidity_control": AsyncMock(),
                }
            },
            "enabled_features": {
                "humidity_control": True,
                "sensor_control": False,  # disabled feature
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    # Call the setup function
    await sensor.async_setup_entry(hass, config_entry, async_add_entities)

    # Verify default feature setup was called (always enabled)
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["sensor"][
        "default"
    ].assert_awaited_once_with(hass, config_entry, async_add_entities)

    # Verify enabled feature setup was called
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["sensor"][
        "humidity_control"
    ].assert_awaited_once_with(hass, config_entry, async_add_entities)


@pytest.mark.asyncio
async def test_async_setup_entry_no_registry(hass):
    """Test setup when platform registry has no sensor platforms."""
    # Mock hass data with empty sensor registry
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "sensor": {}  # Empty sensor platforms
            },
            "enabled_features": {},
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    # Call the setup function - should not raise
    await sensor.async_setup_entry(hass, config_entry, async_add_entities)

    # No assertions needed - just verify no exceptions


@pytest.mark.asyncio
async def test_async_setup_entry_exception_handling(hass, caplog):
    """Test exception handling during setup."""
    mock_setup_func = AsyncMock(side_effect=Exception("Test error"))

    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "sensor": {
                    "humidity_control": mock_setup_func,
                }
            },
            "enabled_features": {
                "humidity_control": True,
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    # Call the setup function
    await sensor.async_setup_entry(hass, config_entry, async_add_entities)

    # Verify error was logged
    assert (
        "Error setting up sensor platform for humidity_control: Test error"
        in caplog.text
    )


@pytest.mark.asyncio
async def test_async_setup_entry_default_feature_always_enabled(hass):
    """Test that default feature is always set up regardless of enabled_features."""
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "sensor": {
                    "default": AsyncMock(),
                    "other_feature": AsyncMock(),
                }
            },
            "enabled_features": {
                "default": False,  # Even if marked as disabled
                "other_feature": True,
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await sensor.async_setup_entry(hass, config_entry, async_add_entities)

    # Default feature should always be called
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["sensor"][
        "default"
    ].assert_awaited_once()

    # Other features should respect enabled_features setting
    # This assertion checks that other features are only set up if enabled
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["sensor"][
        "other_feature"
    ].assert_awaited_once()
