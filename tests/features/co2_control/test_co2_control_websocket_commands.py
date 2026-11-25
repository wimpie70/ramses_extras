"""Tests for CO2 Control WebSocket commands."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.websocket_commands import (
    async_register_websocket_commands,
    handle_get_co2_history,
    handle_get_co2_status,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {"ramses_extras": {}}
    return hass


@pytest.fixture
def connection():
    """Mock WebSocket connection."""
    return MagicMock()


@pytest.fixture
def msg():
    """Mock WebSocket message."""
    return {"id": "test_id", "type": "test"}


def test_async_register_websocket_commands(hass):
    """Test registering WebSocket commands."""
    with patch(
        "custom_components.ramses_extras.features.co2_control.websocket_commands.websocket_api"
    ) as mock_ws_api:
        async_register_websocket_commands(hass)

        # Check all commands were registered
        assert mock_ws_api.async_register_command.call_count == 2
        mock_ws_api.async_register_command.assert_any_call(hass, handle_get_co2_status)
        mock_ws_api.async_register_command.assert_any_call(hass, handle_get_co2_history)


def test_handle_get_co2_status_success(hass, connection, msg):
    """Test successful CO2 status retrieval."""
    # Setup mock CO2 automation
    mock_automation = MagicMock()
    mock_automation.get_status.return_value = {"enabled": True, "zones": 3}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"

    handle_get_co2_status(hass, connection, msg)

    # Check result was sent
    connection.send_result.assert_called_once_with(
        msg["id"], {"enabled": True, "zones": 3}
    )
    connection.send_error.assert_not_called()


def test_handle_get_co2_status_not_found(hass, connection, msg):
    """Test CO2 status retrieval when automation not found."""
    msg["device_id"] = "test_device"

    handle_get_co2_status(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "CO2 automation not found"
    )
    connection.send_result.assert_not_called()


def test_handle_get_co2_status_exception(hass, connection, msg):
    """Test CO2 status retrieval with exception."""
    # Setup mock automation that raises exception
    mock_automation = MagicMock()
    mock_automation.get_status.side_effect = Exception("Test error")
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"

    handle_get_co2_status(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "unknown_error", "Test error"
    )
    connection.send_result.assert_not_called()


def test_handle_get_co2_history_success(hass, connection, msg):
    """Test successful CO2 history retrieval."""
    msg["device_id"] = "test_device"
    msg["hours"] = 12

    handle_get_co2_history(hass, connection, msg)

    # Check result was sent
    expected_result = {
        "device_id": "test_device",
        "hours": 12,
        "data": [],
        "message": "History integration not yet implemented",
    }
    connection.send_result.assert_called_once_with(msg["id"], expected_result)
    connection.send_error.assert_not_called()


def test_handle_get_co2_history_default_hours(hass, connection, msg):
    """Test CO2 history retrieval with default hours."""
    msg["device_id"] = "test_device"
    # Don't set hours, should default to 24

    handle_get_co2_history(hass, connection, msg)

    # Check result was sent with default hours
    expected_result = {
        "device_id": "test_device",
        "hours": 24,  # Default value
        "data": [],
        "message": "History integration not yet implemented",
    }
    connection.send_result.assert_called_once_with(msg["id"], expected_result)


def test_handle_get_co2_history_exception(hass, connection, msg):
    """Test CO2 history retrieval with exception."""
    # Mock connection.send_result to raise exception
    connection.send_result.side_effect = Exception("Test error")

    msg["device_id"] = "test_device"

    handle_get_co2_history(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "unknown_error", "Test error"
    )
