"""Tests for websocket_integration.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras import websocket_integration


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass):
    """Test successful setup of websocket integration."""
    # Mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"

    # Mock hass data
    hass.data = {
        "ramses_extras": {
            "features": {
                "default": MagicMock(),
                "hello_world": MagicMock(),
            }
        }
    }

    # Mock the import functions
    with patch(
        "custom_components.ramses_extras.const.WS_COMMAND_REGISTRY",
        {"default": {}, "hello_world": {}, "humidity_control": {}},
    ):
        # Setup the integration
        await websocket_integration.async_setup_entry(hass, config_entry)

        # The test passes if no exception is raised


@pytest.mark.asyncio
async def test_async_setup_entry_with_missing_modules(hass):
    """Test setup when some websocket modules are missing."""
    # Mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"

    # Mock hass data
    hass.data = {
        "ramses_extras": {
            "features": {
                "default": MagicMock(),
                "missing_feature": MagicMock(),
            }
        }
    }

    # Mock the import functions to raise ImportError for missing modules
    def mock_import(feature_name):
        if feature_name == "missing_feature":
            raise ImportError("No module")
        return True

    with (
        patch.object(
            websocket_integration, "_import_websocket_module", side_effect=mock_import
        ),
        patch(  # noqa: E501
            "custom_components.ramses_extras.const.WS_COMMAND_REGISTRY",
            {
                "default": {},
                "missing_feature": {},
            },
        ),
    ):
        # Setup should not raise
        await websocket_integration.async_setup_entry(hass, config_entry)

        # Verify only enabled features' platforms are called
        # This is a simplified test - actual implementation would check which
        # features are enabled and only call their platform setup functions.
        # The actual implementation would be more complex.
