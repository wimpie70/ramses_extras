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
        1,
        {
            "enabled_features": {"humidity_control": True},
            "options": {},
        },
    )

    # Test error path
    hass.data = None
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_error.assert_called()


async def test_ws_get_enabled_features_config_entry_fallback(connection):
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "config_entry": MagicMock(
                data={},
                options={
                    "enabled_features": {"default": True},
                    "ramses_debugger_default_poll_ms": 1234,
                },
            )
        }
    }

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": {"default": True},
            "options": {"ramses_debugger_default_poll_ms": 1234},
        },
    )


async def test_ws_get_enabled_features_list_enabled(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {"enabled_features": ["default", "debug"]}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": ["default", "debug"],
            "options": {},
        },
    )


async def test_ws_get_enabled_features_no_config_entry(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": {},
            "options": {},
        },
    )


async def test_ws_get_cards_enabled(hass, connection):
    """Test ws_get_cards_enabled command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}
    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_result.assert_called_once_with(
        1, {"cards_enabled": True, "_backend_version": "0.0.0"}
    )


async def test_ws_get_cards_enabled_error_path(connection):
    hass = MagicMock()
    hass.data = None  # triggers AttributeError in handler
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}

    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_error.assert_called_with(1, "get_cards_enabled_failed", ANY)


async def test_ws_get_entity_mappings_missing_identifier(hass, connection):
    """Test ws_get_entity_mappings with missing feature identifier."""
    msg = {"id": 1, "type": "ramses_extras/get_entity_mappings"}
    await ws_get_entity_mappings(hass, connection, msg)
    connection.send_error.assert_called_with(
        1,
        "missing_feature_identifier",
        "Either feature_id or const_module must be provided",
    )


async def test_ws_get_available_devices_empty_list(hass, connection):
    """Test ws_get_available_devices with empty devices list."""
    hass.data[DOMAIN]["devices"] = []
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)
    connection.send_result.assert_called_once_with(1, {"devices": []})


async def test_ws_get_available_devices_with_slugs(hass, connection):
    """Test ws_get_available_devices extracts device slugs correctly."""
    mock_device = MagicMock()
    mock_device.id = "32:123456"
    mock_device.type = "FAN"
    hass.data[DOMAIN]["devices"] = [mock_device]
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)
    connection.send_result.assert_called_once()


async def test_ws_get_bound_rem(hass, connection):
    """Test ws_get_bound_rem command."""
    msg = {"id": 1, "type": "ramses_extras/get_bound_rem", "device_id": "32:123456"}
    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.RamsesCommands"
    ) as MockCommands:  # noqa: N806
        mock_commands = MagicMock()
        mock_commands._get_bound_rem_device = AsyncMock(return_value="37:654321")
        MockCommands.return_value = mock_commands
        await ws_get_bound_rem(hass, connection, msg)
        connection.send_result.assert_called_once_with(
            1, {"device_id": "32:123456", "bound_rem": "37:654321"}
        )


async def test_ws_get_2411_schema_with_states(hass, connection):
    """Test ws_get_2411_schema returns schema from existing states."""
    mock_state = MagicMock()
    mock_state.entity_id = "number.32_123456_param_01"
    mock_state.attributes = {
        "friendly_name": "Parameter 01",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit_of_measurement": "%",
    }
    hass.states.async_all.return_value = [mock_state]
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}
    await ws_get_2411_schema(hass, connection, msg)
    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "01" in schema
    assert schema["01"]["min_value"] == 0
    assert schema["01"]["max_value"] == 100


async def test_ws_get_2411_schema_multiple_params(hass, connection):
    """Test ws_get_2411_schema with multiple parameter entities."""
    states = []
    for i in range(3):
        mock_state = MagicMock()
        mock_state.entity_id = f"number.32_123456_param_0{i}"
        mock_state.attributes = {"friendly_name": f"Parameter 0{i}"}
        states.append(mock_state)
    hass.states.async_all.return_value = states
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}
    await ws_get_2411_schema(hass, connection, msg)
    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert len(schema) == 3
