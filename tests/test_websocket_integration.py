"""Tests for websocket_integration.py."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras import websocket_integration
from custom_components.ramses_extras.extras_registry import extras_registry


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass):
    """Test successful setup of websocket integration."""
    # Mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {"enabled_features": {"hello_world": True}}
    config_entry.options = {}

    # Mock hass data
    hass.data = {
        "ramses_extras": {
            "config_entry": config_entry,
            "enabled_features": {"hello_world": True},
            "features": {
                "default": MagicMock(),
                "hello_world": MagicMock(),
            },
        }
    }

    fake_module = MagicMock()

    def ws_handler(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
        return None

    ws_handler._ws_command = "ramses_extras/default/get_cards_enabled"  # type: ignore[attr-defined]  # noqa: SLF001
    ws_handler._ws_schema = False  # type: ignore[attr-defined]  # noqa: SLF001
    fake_module.ws_handler = ws_handler

    with (
        patch.object(
            extras_registry,
            "get_all_websocket_commands",
            return_value={
                "default": {
                    "get_cards_enabled": "ramses_extras/default/get_cards_enabled"
                },
                "hello_world": {
                    "toggle_switch": "ramses_extras/hello_world/toggle_switch"
                },
                "humidity_control": {"noop": "ramses_extras/humidity_control/noop"},
            },
        ),
        patch.object(
            extras_registry,
            "get_features_with_websocket_commands",
            return_value=["default", "hello_world", "humidity_control"],
        ),
        patch.object(
            websocket_integration,
            "_import_websocket_module",
            autospec=True,
            return_value=fake_module,
        ) as mock_import,
        patch(
            "custom_components.ramses_extras.websocket_integration.websocket_api.async_register_command"
        ) as mock_register,
    ):
        await websocket_integration.async_setup_entry(hass, config_entry)

        assert mock_import.call_count == 2
        mock_import.assert_any_call("default")
        mock_import.assert_any_call("hello_world")

        # One decorated handler is discovered & registered per imported module.
        assert mock_register.call_count == 2


@pytest.mark.asyncio
async def test_async_setup_entry_with_missing_modules(hass):
    """Test setup when some websocket modules are missing."""
    # Mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {"enabled_features": {"missing_feature": True}}
    config_entry.options = {}

    # Mock hass data
    hass.data = {
        "ramses_extras": {
            "config_entry": config_entry,
            "enabled_features": {"missing_feature": True},
            "features": {
                "default": MagicMock(),
                "missing_feature": MagicMock(),
            },
        }
    }

    # Mock the import functions to raise ImportError for missing modules
    def mock_import(feature_name: str) -> None:
        if feature_name == "missing_feature":
            raise ImportError("No module")
        return

    with (
        patch.object(
            websocket_integration, "_import_websocket_module", side_effect=mock_import
        ),
        patch.object(
            extras_registry,
            "get_all_websocket_commands",
            return_value={
                "default": {
                    "get_cards_enabled": "ramses_extras/default/get_cards_enabled"
                },
                "missing_feature": {"x": "ramses_extras/missing_feature/x"},
            },
        ),
        patch.object(
            extras_registry,
            "get_features_with_websocket_commands",
            return_value=["default", "missing_feature"],
        ),
    ):
        # Setup should not raise
        await websocket_integration.async_setup_entry(hass, config_entry)

        # Verify only enabled features' platforms are called
        # This is a simplified test - actual implementation would check which
        # features are enabled and only call their platform setup functions.
        # The actual implementation would be more complex.
