"""Tests for websocket_integration.py."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras import websocket_integration
from custom_components.ramses_extras.const import DOMAIN
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


@pytest.mark.asyncio
async def test_get_websocket_commands_info(hass):
    """Test get_websocket_commands_info returns correct structure."""
    hass.data[DOMAIN] = {
        "enabled_features": {"feature1": True},
    }

    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"feature1": {"cmd1": "type1"}},
    ):
        info = websocket_integration.get_websocket_commands_info(hass)

        assert info["total_features"] == 1
        assert info["total_commands"] == 1
        assert "feature1" in info["commands_by_feature"]
        assert info["commands"][0]["name"] == "cmd1"
        assert info["commands"][0]["feature"] == "feature1"


@pytest.mark.asyncio
async def test_async_cleanup_websocket_integration(hass):
    """Test cleanup removes data from hass."""
    hass.data[DOMAIN] = {"websocket_integration": {"registered": True}}

    await websocket_integration.async_cleanup_websocket_integration(hass)

    assert "websocket_integration" not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_is_websocket_enabled(hass):
    """Test is_websocket_enabled check."""
    hass.data[DOMAIN] = {}
    assert websocket_integration.is_websocket_enabled(hass) is False

    hass.data[DOMAIN] = {"websocket_integration": {"registered": True}}
    assert websocket_integration.is_websocket_enabled(hass) is True


@pytest.mark.asyncio
async def test_async_register_websocket_commands_no_commands(hass):
    """Test register commands when none are available."""
    hass.data[DOMAIN] = {"enabled_features": {"f1": True}}
    with patch.object(extras_registry, "get_all_websocket_commands", return_value={}):
        await websocket_integration.async_register_websocket_commands(hass)
        # Should log warning and return early


@pytest.mark.asyncio
async def test_async_register_websocket_commands_list_config(hass):
    """Test register commands when features are provided as a list."""
    hass.data[DOMAIN] = {"enabled_features": ["f1"]}
    with (
        patch.object(
            extras_registry,
            "get_all_websocket_commands",
            return_value={"f1": {"c1": "t1"}},
        ),
        patch.object(websocket_integration, "_import_websocket_module") as mock_import,
        patch.object(
            websocket_integration, "_register_commands_from_module", return_value=1
        ),
    ):
        await websocket_integration.async_register_websocket_commands(hass)
        mock_import.assert_called_with("f1")


@pytest.mark.asyncio
async def test_get_websocket_commands_info_list_config(hass):
    """Test get_websocket_commands_info with list-based feature config."""
    hass.data[DOMAIN] = {"enabled_features": ["f1"]}
    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"f1": {"c1": "t1"}},
    ):
        info = websocket_integration.get_websocket_commands_info(hass)
        assert info["total_features"] == 1


@pytest.mark.asyncio
async def test_get_enabled_websocket_commands_disabled(hass):
    """Test get_enabled_websocket_commands when integration is disabled."""
    hass.data[DOMAIN] = {"websocket_integration": {"registered": False}}
    assert websocket_integration.get_enabled_websocket_commands(hass, "f1") == {}


@pytest.mark.asyncio
async def test_get_enabled_websocket_commands_list_config(hass):
    """Test get_enabled_websocket_commands with list-based feature config."""
    mock_entry = MagicMock()
    mock_entry.data = {"enabled_features": ["f1"]}
    mock_entry.options = {}
    hass.data[DOMAIN] = {
        "websocket_integration": {"registered": True},
        "config_entry": mock_entry,
    }
    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"f1": {"c1": "t1"}},
    ):
        assert websocket_integration.get_enabled_websocket_commands(hass, "f1") == {
            "c1": "t1"
        }
        assert websocket_integration.get_enabled_websocket_commands(hass, "f2") == {}


@pytest.mark.asyncio
async def test_async_register_websocket_commands_import_error(hass):
    """Test register commands handles ImportError for websocket_commands."""
    hass.data[DOMAIN] = {"enabled_features": {"f1": True}}
    with (
        patch.object(
            extras_registry,
            "get_all_websocket_commands",
            return_value={"f1": {"c1": "t1"}},
        ),
        patch.object(
            websocket_integration,
            "_import_websocket_module",
            side_effect=ImportError("websocket_commands not found"),
        ),
    ):
        await websocket_integration.async_register_websocket_commands(hass)
        # Should log debug and continue


@pytest.mark.asyncio
async def test_async_register_websocket_commands_generic_exception(hass):
    """Test register commands handles generic Exception."""
    hass.data[DOMAIN] = {"enabled_features": {"f1": True}}
    with (
        patch.object(
            extras_registry,
            "get_all_websocket_commands",
            return_value={"f1": {"c1": "t1"}},
        ),
        patch.object(
            websocket_integration,
            "_import_websocket_module",
            side_effect=Exception("Generic error"),
        ),
    ):
        await websocket_integration.async_register_websocket_commands(hass)
        # Should log error and continue


@pytest.mark.asyncio
async def test_async_setup_websocket_integration_exception(hass):
    """Test setup handles generic Exception."""
    with patch.object(
        websocket_integration,
        "async_register_websocket_commands",
        side_effect=Exception("Setup error"),
    ):
        result = await websocket_integration.async_setup_websocket_integration(hass)
        assert result is False


@pytest.mark.asyncio
async def test_async_cleanup_websocket_integration_exception(hass):
    """Test cleanup handles generic Exception."""
    # This is tricky because we need to trigger an exception in the try block
    # The try block has if DOMAIN in hass.data and ... del ...
    # We can mock hass.data to raise an error on 'get' or 'contains'
    mock_data = MagicMock()
    mock_data.__contains__.side_effect = Exception("Mock error")

    with patch.object(hass, "data", mock_data):
        await websocket_integration.async_cleanup_websocket_integration(hass)
        # Should log error and continue


@pytest.mark.asyncio
async def test_get_enabled_websocket_commands_default_feature(hass):
    """Test get_enabled_websocket_commands for default feature."""
    hass.data[DOMAIN] = {"websocket_integration": {"registered": True}}
    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"default": {"d1": "t1"}},
    ):
        assert websocket_integration.get_enabled_websocket_commands(
            hass, "default"
        ) == {"d1": "t1"}


@pytest.mark.asyncio
async def test_get_enabled_websocket_commands_list_enabled(hass):
    """Test get_enabled_websocket_commands when feature is in a list."""
    mock_entry = MagicMock()
    mock_entry.data = {"enabled_features": ["f1"]}
    mock_entry.options = {}
    hass.data[DOMAIN] = {
        "websocket_integration": {"registered": True},
        "config_entry": mock_entry,
    }
    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"f1": {"c1": "t1"}},
    ):
        assert websocket_integration.get_enabled_websocket_commands(hass, "f1") == {
            "c1": "t1"
        }


@pytest.mark.asyncio
async def test_get_enabled_websocket_commands_invalid_config(hass):
    """Test get_enabled_websocket_commands with invalid config format."""
    mock_entry = MagicMock()
    mock_entry.data = {"enabled_features": 123}  # Invalid type
    mock_entry.options = {}
    hass.data[DOMAIN] = {
        "websocket_integration": {"registered": True},
        "config_entry": mock_entry,
    }
    with patch.object(
        extras_registry,
        "get_all_websocket_commands",
        return_value={"f1": {"c1": "t1"}},
    ):
        assert websocket_integration.get_enabled_websocket_commands(hass, "f1") == {}
