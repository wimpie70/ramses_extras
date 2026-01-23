# tests/platforms/test_switch.py
"""Test switch platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras import switch


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass):
    """Test successful setup of switch platform."""
    # Mock the hass data structure
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "switch": {
                    "humidity_control": AsyncMock(),
                    "switch_control": AsyncMock(),
                }
            },
            "enabled_features": {
                "humidity_control": True,
                "switch_control": False,  # disabled feature
            },
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    # Call the setup function
    await switch.async_setup_entry(hass, config_entry, async_add_entities)

    # Verify enabled feature setup was called
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["switch"][
        "humidity_control"
    ].assert_awaited_once_with(hass, config_entry, async_add_entities)

    # Verify disabled feature setup was not called
    hass.data["ramses_extras"]["PLATFORM_REGISTRY"]["switch"][
        "switch_control"
    ].assert_not_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_no_registry(hass):
    """Test setup when platform registry has no switch platforms."""
    # Mock hass data with empty switch registry
    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "switch": {}  # Empty switch platforms
            },
            "enabled_features": {},
        }
    }

    config_entry = MagicMock()
    async_add_entities = MagicMock()

    # Call the setup function - should not raise
    await switch.async_setup_entry(hass, config_entry, async_add_entities)

    # No assertions needed - just verify no exceptions


@pytest.mark.asyncio
async def test_async_setup_entry_exception_handling(hass, caplog):
    """Test exception handling during setup."""
    mock_setup_func = AsyncMock(side_effect=Exception("Test error"))

    hass.data = {
        "ramses_extras": {
            "PLATFORM_REGISTRY": {
                "switch": {
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
    await switch.async_setup_entry(hass, config_entry, async_add_entities)

    # Verify error was logged
    assert (
        "Error setting up switch platform for humidity_control: Test error"
        in caplog.text
    )  # noqa: E501
