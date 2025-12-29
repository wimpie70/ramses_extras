"""Tests for default feature WebSocket commands."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import websocket_api

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.websocket_commands import (
    ws_get_2411_schema,
    ws_get_all_feature_entities,
    ws_get_available_devices,
    ws_get_bound_rem,
    ws_get_cards_enabled,
    ws_get_enabled_features,
    ws_get_entity_mappings,
    ws_websocket_info,
)

# Unwrap decorators for testing
ws_get_enabled_features = ws_get_enabled_features.__wrapped__
ws_get_cards_enabled = ws_get_cards_enabled.__wrapped__
ws_websocket_info = ws_websocket_info.__wrapped__
ws_get_entity_mappings = ws_get_entity_mappings.__wrapped__
ws_get_all_feature_entities = ws_get_all_feature_entities.__wrapped__
ws_get_available_devices = ws_get_available_devices.__wrapped__
ws_get_bound_rem = ws_get_bound_rem.__wrapped__
ws_get_2411_schema = ws_get_2411_schema.__wrapped__


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "enabled_features": {"humidity_control": True},
            "cards_enabled": True,
            "devices": [
                MagicMock(id="32:123456", type="FAN"),
                "37:654321",
            ],
        }
    }
    hass.states = MagicMock()
    hass.states.async_all.return_value = []
    return hass


@pytest.fixture
def connection():
    """Mock WebSocket connection."""
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


async def test_ws_get_enabled_features(hass, connection):
    """Test ws_get_enabled_features command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_once_with(
        1, {"enabled_features": {"humidity_control": True}}
    )

    # Test error path
    hass.data = None
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_error.assert_called()


async def test_ws_get_cards_enabled(hass, connection):
    """Test ws_get_cards_enabled command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}
    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_result.assert_called_once_with(1, {"cards_enabled": True})


async def test_ws_websocket_info(hass, connection):
    """Test ws_websocket_info command."""
    msg = {"id": 1, "type": "ramses_extras/websocket_info"}

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.extras_registry"
    ) as mock_registry:
        mock_registry.get_all_websocket_commands.return_value = {
            "default": {"test_cmd": "ramses_extras/test"}
        }
        mock_registry.get_features_with_websocket_commands.return_value = ["default"]

        await ws_websocket_info(hass, connection, msg)

        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "commands" in result
        assert result["total_commands"] == 1
        assert result["features"] == ["default"]


async def test_ws_get_entity_mappings(hass, connection):
    """Test ws_get_entity_mappings command."""
    msg = {
        "id": 1,
        "type": "ramses_extras/get_entity_mappings",
        "feature_id": "humidity_control",
        "device_id": "32:123456",
    }

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.GetEntityMappingsCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock()
        mock_cmd_class.return_value = mock_cmd

        await ws_get_entity_mappings(hass, connection, msg)
        mock_cmd.execute.assert_called_once_with(connection, msg)

    # Error path - missing identifiers
    msg_error = {"id": 2, "type": "ramses_extras/get_entity_mappings"}
    await ws_get_entity_mappings(hass, connection, msg_error)
    connection.send_error.assert_called_with(2, "missing_feature_identifier", ANY)


async def test_ws_get_all_feature_entities(hass, connection):
    """Test ws_get_all_feature_entities command."""
    msg = {
        "id": 1,
        "type": "ramses_extras/get_all_feature_entities",
        "feature_id": "humidity_control",
        "device_id": "32:123456",
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetAllFeatureEntitiesCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock()
        mock_cmd_class.return_value = mock_cmd

        await ws_get_all_feature_entities(hass, connection, msg)
        mock_cmd.execute.assert_called_once_with(connection, msg)


async def test_ws_get_available_devices(hass, connection):
    """Test ws_get_available_devices command."""
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)

    connection.send_result.assert_called_once()
    devices = connection.send_result.call_args[0][1]["devices"]
    assert len(devices) == 2
    assert devices[0]["device_id"] == "32:123456"
    assert devices[1]["device_id"] == "37:654321"


async def test_ws_get_bound_rem(hass, connection):
    """Test ws_get_bound_rem command."""
    msg = {"id": 1, "type": "ramses_extras/get_bound_rem", "device_id": "32:123456"}

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands._get_bound_rem_device = AsyncMock(return_value="18:123456")
        mock_commands_class.return_value = mock_commands

        await ws_get_bound_rem(hass, connection, msg)
        connection.send_result.assert_called_once_with(
            1, {"device_id": "32:123456", "bound_rem": "18:123456"}
        )


async def test_ws_get_2411_schema(hass, connection):
    """Test ws_get_2411_schema command."""
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}

    mock_state = MagicMock()
    mock_state.entity_id = "number.32_123456_param_01"
    mock_state.attributes = {
        "friendly_name": "Test Param",
        "min": 0,
        "max": 100,
        "step": 1,
    }
    hass.states.async_all.return_value = [mock_state]

    await ws_get_2411_schema(hass, connection, msg)

    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "01" in schema
    assert schema["01"]["name"] == "Test Param"
