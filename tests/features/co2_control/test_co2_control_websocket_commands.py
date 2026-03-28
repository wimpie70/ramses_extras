"""Tests for CO2 Control WebSocket commands."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.websocket_commands import (
    async_register_websocket_commands,
    handle_get_co2_history,
    handle_get_co2_status,
    handle_get_zone_details,
    handle_update_zone_config,
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
        assert mock_ws_api.async_register_command.call_count == 4
        mock_ws_api.async_register_command.assert_any_call(hass, handle_get_co2_status)
        mock_ws_api.async_register_command.assert_any_call(
            hass, handle_get_zone_details
        )
        mock_ws_api.async_register_command.assert_any_call(
            hass, handle_update_zone_config
        )
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


def test_handle_get_zone_details_success(hass, connection, msg):
    """Test successful zone details retrieval."""
    # Setup mock zone
    mock_zone = MagicMock()
    mock_zone.zone_id = "living_room"
    mock_zone.zone_name = "Living Room"
    mock_zone.sensor_entity = "sensor.living_room_co2"
    mock_zone.threshold = 1000
    mock_zone.enabled = True
    mock_zone.current_co2 = 800
    mock_zone.is_triggered = False
    mock_zone.trigger_count = 0
    mock_zone.last_update = None
    mock_zone.valve_entity = "valve.living_room"

    # Setup mock zone manager
    mock_zone_manager = MagicMock()
    mock_zone_manager.zones = {"living_room": mock_zone}

    # Setup mock automation
    mock_automation = MagicMock()
    mock_automation._zone_managers = {"test_device": mock_zone_manager}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"

    handle_get_zone_details(hass, connection, msg)

    # Check result was sent
    expected_result = {
        "zone_id": "living_room",
        "zone_name": "Living Room",
        "sensor_entity": "sensor.living_room_co2",
        "threshold": 1000,
        "enabled": True,
        "current_co2": 800,
        "is_triggered": False,
        "trigger_count": 0,
        "last_update": None,
        "valve_entity": "valve.living_room",
    }
    connection.send_result.assert_called_once_with(msg["id"], expected_result)
    connection.send_error.assert_not_called()


def test_handle_get_zone_details_automation_not_found(hass, connection, msg):
    """Test zone details retrieval when automation not found."""
    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"

    handle_get_zone_details(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "CO2 automation not found"
    )
    connection.send_result.assert_not_called()


def test_handle_get_zone_details_zone_manager_not_found(hass, connection, msg):
    """Test zone details retrieval when zone manager not found."""
    # Setup mock automation without zone manager
    mock_automation = MagicMock()
    mock_automation._zone_managers = {}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"

    handle_get_zone_details(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "Zone manager not found for device test_device"
    )
    connection.send_result.assert_not_called()


def test_handle_get_zone_details_zone_not_found(hass, connection, msg):
    """Test zone details retrieval when zone not found."""
    # Setup mock zone manager without zone
    mock_zone_manager = MagicMock()
    mock_zone_manager.zones = {}

    # Setup mock automation
    mock_automation = MagicMock()
    mock_automation._zone_managers = {"test_device": mock_zone_manager}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"

    handle_get_zone_details(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "Zone living_room not found"
    )
    connection.send_result.assert_not_called()


def test_handle_get_zone_details_exception(hass, connection, msg):
    """Test zone details retrieval with exception."""
    # Setup mock automation that raises exception
    mock_automation = MagicMock()
    mock_automation._zone_managers = MagicMock()
    mock_automation._zone_managers.get.side_effect = Exception("Test error")
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"

    handle_get_zone_details(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "unknown_error", "Test error"
    )
    connection.send_result.assert_not_called()


def test_handle_update_zone_config_success(hass, connection, msg):
    """Test successful zone config update."""
    # Setup mock zone manager
    mock_zone_manager = MagicMock()
    mock_zone_manager.update_zone_config.return_value = True

    # Setup mock automation
    mock_automation = MagicMock()
    mock_automation._zone_managers = {"test_device": mock_zone_manager}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"
    msg["updates"] = {"threshold": 1200, "enabled": False}

    handle_update_zone_config(hass, connection, msg)

    # Check result was sent
    connection.send_result.assert_called_once_with(msg["id"], {"success": True})
    connection.send_error.assert_not_called()

    # Check update was called
    mock_zone_manager.update_zone_config.assert_called_once_with(
        "living_room", {"threshold": 1200, "enabled": False}
    )


def test_handle_update_zone_config_automation_not_found(hass, connection, msg):
    """Test zone config update when automation not found."""
    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"
    msg["updates"] = {"threshold": 1200}

    handle_update_zone_config(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "CO2 automation not found"
    )
    connection.send_result.assert_not_called()


def test_handle_update_zone_config_zone_manager_not_found(hass, connection, msg):
    """Test zone config update when zone manager not found."""
    # Setup mock automation without zone manager
    mock_automation = MagicMock()
    mock_automation._zone_managers = {}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"
    msg["updates"] = {"threshold": 1200}

    handle_update_zone_config(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "Zone manager not found for device test_device"
    )
    connection.send_result.assert_not_called()


def test_handle_update_zone_config_zone_not_found(hass, connection, msg):
    """Test zone config update when zone not found."""
    # Setup mock zone manager
    mock_zone_manager = MagicMock()
    mock_zone_manager.update_zone_config.return_value = False

    # Setup mock automation
    mock_automation = MagicMock()
    mock_automation._zone_managers = {"test_device": mock_zone_manager}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"
    msg["updates"] = {"threshold": 1200}

    handle_update_zone_config(hass, connection, msg)

    # Check error was sent
    connection.send_error.assert_called_once_with(
        msg["id"], "not_found", "Zone living_room not found"
    )
    connection.send_result.assert_not_called()


def test_handle_update_zone_config_empty_updates(hass, connection, msg):
    """Test zone config update with empty updates."""
    # Setup mock zone manager
    mock_zone_manager = MagicMock()
    mock_zone_manager.update_zone_config.return_value = True

    # Setup mock automation
    mock_automation = MagicMock()
    mock_automation._zone_managers = {"test_device": mock_zone_manager}
    hass.data["ramses_extras"]["co2_automation"] = mock_automation

    msg["device_id"] = "test_device"
    msg["zone_id"] = "living_room"
    msg["updates"] = {}

    handle_update_zone_config(hass, connection, msg)

    # Check result was sent
    connection.send_result.assert_called_once_with(msg["id"], {"success": True})

    # Check update was called with empty dict
    mock_zone_manager.update_zone_config.assert_called_once_with("living_room", {})


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
