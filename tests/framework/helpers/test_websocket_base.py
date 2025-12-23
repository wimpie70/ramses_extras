# tests/framework/helpers/test_websocket_base.py
"""Test websocket base classes and utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.websocket_base import (
    WEBSOCKET_COMMANDS,
    BaseWebSocketCommand,
    DeviceWebSocketCommand,
    GetEntityMappingsCommand,
    discover_websocket_commands,
    get_all_websocket_commands,
    get_websocket_commands_for_feature,
    register_websocket_command,
)


class TestBaseWebSocketCommand:
    """Test BaseWebSocketCommand class."""

    def test_init(self, hass):
        """Test initialization of BaseWebSocketCommand."""
        feature_name = "test_feature"
        command = BaseWebSocketCommand(hass, feature_name)

        assert command.hass == hass
        assert command.feature_name == feature_name
        assert (
            command._logger.name
            == "custom_components.ramses_extras.framework.helpers.websocket_base.test_feature"  # noqa: E501
        )  # noqa: E501

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self, hass):
        """Test that execute raises NotImplementedError."""
        command = BaseWebSocketCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 1, "type": "test"}

        with pytest.raises(
            NotImplementedError, match="Subclasses must implement execute"
        ):  # noqa: E501
            await command.execute(mock_connection, msg)

    def test_send_success(self, hass):
        """Test sending success response."""
        command = BaseWebSocketCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg_id = "msg_123"
        result = {"data": "test"}

        command._send_success(mock_connection, msg_id, result)

        mock_connection.send_result.assert_called_once_with(msg_id, result)

    def test_send_error(self, hass):
        """Test sending error response."""
        command = BaseWebSocketCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg_id = "msg_123"
        error_code = "test_error"
        error_message = "Test error message"

        command._send_error(mock_connection, msg_id, error_code, error_message)

        mock_connection.send_error.assert_called_once_with(
            msg_id, error_code, error_message
        )  # noqa: E501

    def test_log_command_without_device_id(self, hass):
        """Test logging command without device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")

        with patch.object(command._logger, "debug") as mock_debug:
            command._log_command("test_command")

            mock_debug.assert_called_once_with("Executing test_command")

    def test_log_command_with_device_id(self, hass):
        """Test logging command with device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")

        with patch.object(command._logger, "debug") as mock_debug:
            command._log_command("test_command", "32:153289")

            mock_debug.assert_called_once_with(
                "Executing test_command for device 32:153289"
            )  # noqa: E501

    def test_log_error_without_device_id(self, hass):
        """Test logging error without device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")
        error = Exception("Test error")

        with patch.object(command._logger, "error") as mock_error:
            command._log_error("test_command", error)

            mock_error.assert_called_once_with(
                "Error executing test_command: Test error"
            )  # noqa: E501

    def test_log_error_with_device_id(self, hass):
        """Test logging error with device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")
        error = Exception("Test error")

        with patch.object(command._logger, "error") as mock_error:
            command._log_error("test_command", error, "32:153289")

            mock_error.assert_called_once_with(
                "Error executing test_command for device 32:153289: Test error"
            )  # noqa: E501


class TestDeviceWebSocketCommand:
    """Test DeviceWebSocketCommand class."""

    def test_init(self, hass):
        """Test initialization of DeviceWebSocketCommand."""
        feature_name = "test_feature"
        hass.data = {"ramses_cc": {"test": "data"}}

        command = DeviceWebSocketCommand(hass, feature_name)

        assert command.hass == hass
        assert command.feature_name == feature_name
        assert command._ramses_data == {"test": "data"}

    def test_init_no_ramses_data(self, hass):
        """Test initialization when ramses_cc data is not available."""
        feature_name = "test_feature"
        hass.data = {}  # No ramses_cc data

        command = DeviceWebSocketCommand(hass, feature_name)

        assert command._ramses_data == {}


class TestWebsocketCommandRegistry:
    """Test WebSocket command registry functions."""

    def test_register_websocket_command(self, hass):
        """Test registering a WebSocket command."""
        feature_name = "test_feature"
        command_name = "test_command"
        handler_class = MagicMock

        # Clear registry first
        WEBSOCKET_COMMANDS.clear()

        register_websocket_command(feature_name, command_name, handler_class)

        assert feature_name in WEBSOCKET_COMMANDS
        assert command_name in WEBSOCKET_COMMANDS[feature_name]
        assert WEBSOCKET_COMMANDS[feature_name][command_name] == handler_class

    def test_register_websocket_command_multiple_features(self, hass):
        """Test registering commands for multiple features."""
        WEBSOCKET_COMMANDS.clear()

        # Register for feature1
        register_websocket_command("feature1", "cmd1", MagicMock)
        register_websocket_command("feature1", "cmd2", MagicMock)

        # Register for feature2
        register_websocket_command("feature2", "cmd3", MagicMock)

        assert len(WEBSOCKET_COMMANDS) == 2
        assert len(WEBSOCKET_COMMANDS["feature1"]) == 2
        assert len(WEBSOCKET_COMMANDS["feature2"]) == 1

    def test_get_websocket_commands_for_feature_existing(self, hass):
        """Test getting commands for an existing feature."""
        WEBSOCKET_COMMANDS.clear()
        handler_class = MagicMock
        WEBSOCKET_COMMANDS["test_feature"] = {"test_cmd": handler_class}

        result = get_websocket_commands_for_feature("test_feature")

        assert result == {"test_cmd": handler_class}

    def test_get_websocket_commands_for_feature_nonexistent(self, hass):
        """Test getting commands for a nonexistent feature."""
        WEBSOCKET_COMMANDS.clear()

        result = get_websocket_commands_for_feature("nonexistent_feature")

        assert result == {}

    def test_get_all_websocket_commands(self, hass):
        """Test getting all WebSocket commands."""
        WEBSOCKET_COMMANDS.clear()
        WEBSOCKET_COMMANDS["feature1"] = {"cmd1": MagicMock, "cmd2": MagicMock}
        WEBSOCKET_COMMANDS["feature2"] = {"cmd3": MagicMock}

        result = get_all_websocket_commands()

        assert result == WEBSOCKET_COMMANDS
        assert result is not WEBSOCKET_COMMANDS  # Should be a copy

    def test_discover_websocket_commands(self, hass):
        """Test discovering features with WebSocket commands."""
        WEBSOCKET_COMMANDS.clear()
        WEBSOCKET_COMMANDS["feature1"] = {"cmd1": MagicMock}
        WEBSOCKET_COMMANDS["feature2"] = {"cmd2": MagicMock, "cmd3": MagicMock}

        result = discover_websocket_commands()

        # Result should contain feature names (order may vary)
        assert set(result) == {"feature1", "feature2"}

    def test_discover_websocket_commands_empty(self, hass):
        """Test discovering commands when registry is empty."""
        WEBSOCKET_COMMANDS.clear()

        result = discover_websocket_commands()

        assert result == []


class TestGetEntityMappingsCommand:
    """Test GetEntityMappingsCommand class."""

    def test_init(self, hass):
        """Test initialization of GetEntityMappingsCommand."""
        feature_identifier = "test_feature"

        command = GetEntityMappingsCommand(hass, feature_identifier)

        assert command.hass == hass
        assert command.feature_name == feature_identifier
        assert command.feature_identifier == feature_identifier

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._is_sensor_control_enabled"
    )
    async def test_execute_success_no_device_id(
        self, mock_sensor_enabled, mock_get_mappings, hass
    ):  # noqa: E501
        """Test successful execution without device ID."""
        mock_sensor_enabled.return_value = False
        mock_get_mappings.return_value = {"sensor": {"temp": "temp_{device_id}"}}

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        # Should send success response
        mock_connection.send_result.assert_called_once()
        args, kwargs = mock_connection.send_result.call_args
        result = args[1]  # Second argument is the result dict

        assert result["success"] is True
        assert result["mappings"] == {"sensor": {"temp": "temp_{device_id}"}}
        assert result["device_id"] is None

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._is_sensor_control_enabled"
    )
    async def test_execute_success_with_device_id(
        self, mock_sensor_enabled, mock_get_mappings, hass
    ):  # noqa: E501
        """Test successful execution with device ID."""
        mock_sensor_enabled.return_value = False
        # Return flat dictionary as expected by _get_entity_mappings_from_feature
        mock_get_mappings.return_value = {
            "temp_state": "sensor.temp_{device_id}",
            "humidity_state": "sensor.humidity_{device_id}",
        }

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings", "device_id": "32:153289"}

        await command.execute(mock_connection, msg)

        # Should send success response
        mock_connection.send_result.assert_called_once()
        args, kwargs = mock_connection.send_result.call_args
        result = args[1]

        assert result["success"] is True
        assert result["device_id"] == "32:153289"
        # Templates should be parsed
        assert "sensor.temp_32_153289" in str(result["mappings"])
        assert "sensor.humidity_32_153289" in str(result["mappings"])

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    async def test_execute_no_mappings(self, mock_get_mappings, hass):
        """Test execution when no entity mappings are found."""
        mock_get_mappings.return_value = {}

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        # Should send error response
        mock_connection.send_error.assert_called_once_with(
            123, "no_entity_mappings", "No entity mappings found for test_feature"
        )

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    async def test_execute_exception_handling(self, mock_get_mappings, hass):
        """Test exception handling in execute method."""
        mock_get_mappings.side_effect = Exception("Test error")

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        # Should send error response
        mock_connection.send_error.assert_called_once_with(
            123, "get_entity_mappings_failed", "Test error"
        )

    def test_parse_entity_templates(self, hass):
        """Test parsing entity templates."""
        command = GetEntityMappingsCommand(hass, "test_feature")

        # The method expects a flat dictionary of entity_template strings
        entity_mappings = {
            "temp": "temp_{device_id}",
            "humidity": "humidity_{device_id}",
            "power": "power_{device_id}",
        }
        device_id = "32:153289"

        result = command._parse_entity_templates(entity_mappings, device_id)

        expected = {
            "temp": "temp_32_153289",
            "humidity": "humidity_32_153289",
            "power": "power_32_153289",
        }
        assert result == expected

    def test_parse_entity_templates_no_templates(self, hass):
        """Test parsing templates when no {device_id} placeholders exist."""
        command = GetEntityMappingsCommand(hass, "test_feature")

        # Templates without placeholders should remain unchanged
        entity_mappings = {
            "temp": "temperature",
            "humidity": "humidity_value",
            "power": "switch_power",
        }
        device_id = "32:153289"

        result = command._parse_entity_templates(entity_mappings, device_id)

        # Should return unchanged since no templates to parse
        assert result == entity_mappings

    def test_is_sensor_control_enabled(self, hass):
        """Test checking if sensor control is enabled."""
        command = GetEntityMappingsCommand(hass, "test_feature")

        # Mock the config_entry in hass.data
        from unittest.mock import MagicMock

        from custom_components.ramses_extras.const import DOMAIN

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {"sensor_control": True}}
        mock_config_entry.options = {}

        hass.data = {DOMAIN: {"config_entry": mock_config_entry}}

        result = command._is_sensor_control_enabled()
        assert result is True

    def test_is_sensor_control_enabled_disabled(self, hass):
        """Test checking when sensor control is disabled."""
        command = GetEntityMappingsCommand(hass, "test_feature")

        from unittest.mock import MagicMock

        from custom_components.ramses_extras.const import DOMAIN

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {"sensor_control": False}}
        mock_config_entry.options = {}

        hass.data = {DOMAIN: {"config_entry": mock_config_entry}}

        result = command._is_sensor_control_enabled()
        assert result is False

    def test_is_sensor_control_enabled_not_configured(self, hass):
        """Test checking when sensor control is not configured."""
        command = GetEntityMappingsCommand(hass, "test_feature")

        from unittest.mock import MagicMock

        from custom_components.ramses_extras.const import DOMAIN

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {}}
        mock_config_entry.options = {}

        hass.data = {DOMAIN: {"config_entry": mock_config_entry}}

        result = command._is_sensor_control_enabled()
        assert result is False
