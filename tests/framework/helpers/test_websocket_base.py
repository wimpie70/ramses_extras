# tests/framework/helpers/test_websocket_base.py
"""Test websocket base classes and utilities."""

from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.websocket_base import (
    BaseWebSocketCommand,
    DeviceWebSocketCommand,
    GetAllFeatureEntitiesCommand,
    GetEntityMappingsCommand,
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
        )

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self, hass):
        """Test that execute raises NotImplementedError."""
        command = BaseWebSocketCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 1, "type": "test"}

        with pytest.raises(
            NotImplementedError, match="Subclasses must implement execute"
        ):
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
        )

    def test_log_command_without_device_id(self, hass):
        """Test logging command without device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")

        with patch.object(command._logger, "debug") as mock_debug:
            command._log_command("test_command")

            mock_debug.assert_called_once_with("Executing %s", "test_command")

    def test_log_command_with_device_id(self, hass):
        """Test logging command with device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")

        with patch.object(command._logger, "debug") as mock_debug:
            command._log_command("test_command", "32:153289")

            mock_debug.assert_called_once_with(
                "Executing %s for device %s",
                "test_command",
                "32:153289",
            )

    def test_log_error_without_device_id(self, hass):
        """Test logging error without device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")
        error = Exception("Test error")

        with patch.object(command._logger, "error") as mock_error:
            command._log_error("test_command", error)

            mock_error.assert_called_once_with(
                "Error executing %s: %s",
                "test_command",
                error,
            )

    def test_log_error_with_device_id(self, hass):
        """Test logging error with device ID."""
        command = BaseWebSocketCommand(hass, "test_feature")
        error = Exception("Test error")

        with patch.object(command._logger, "error") as mock_error:
            command._log_error("test_command", error, "32:153289")

            mock_error.assert_called_once_with(
                "Error executing %s for device %s: %s",
                "test_command",
                "32:153289",
                error,
            )


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
    @pytest.mark.asyncio
    async def test_execute_success_no_device_id(self, mock_get_mappings, hass):
        """Test successful execution without device ID."""
        mock_get_mappings.return_value = {
            "temp_state": "sensor.temp_{device_id}",
            "humidity_state": "sensor.humidity_{device_id}",
        }

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        # Should send success response
        mock_connection.send_result.assert_called_once()
        args, _ = mock_connection.send_result.call_args
        result = args[1]

        assert result["success"] is True
        assert result["mappings"] == {
            "temp_state": "sensor.temp_{device_id}",
            "humidity_state": "sensor.humidity_{device_id}",
        }
        assert result["device_id"] is None

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @pytest.mark.asyncio
    async def test_execute_success_with_device_id(self, mock_get_mappings, hass):
        """Test successful execution with device ID."""
        mock_get_mappings.return_value = {
            "temp_state": "sensor.temp_{device_id}",
            "humidity_state": "sensor.humidity_{device_id}",
        }

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings", "device_id": "32:153289"}

        await command.execute(mock_connection, msg)

        mock_connection.send_result.assert_called_once()
        args, _ = mock_connection.send_result.call_args
        result = args[1]

        assert result["success"] is True
        assert result["device_id"] == "32:153289"
        assert result["mappings"]["temp_state"] == "sensor.temp_32_153289"
        assert result["mappings"]["humidity_state"] == "sensor.humidity_32_153289"

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @pytest.mark.asyncio
    async def test_execute_success_with_device_id_overlay_provider(
        self, mock_get_mappings, hass
    ):
        """Test overlay_provider gets called and merges its results."""
        mock_get_mappings.return_value = {
            "temp_state": "sensor.temp_{device_id}",
        }

        overlay_provider = AsyncMock(
            return_value={
                "mappings": {"temp_state": "sensor.override_32_153289"},
                "sources": {"temp_state": "external"},
            }
        )

        command = GetEntityMappingsCommand(
            hass,
            "test_feature",
            overlay_provider=overlay_provider,
        )
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings", "device_id": "32:153289"}

        await command.execute(mock_connection, msg)

        overlay_provider.assert_awaited_once_with(
            "32:153289",
            {"temp_state": "sensor.temp_32_153289"},
        )

        mock_connection.send_result.assert_called_once()
        args, _ = mock_connection.send_result.call_args
        result = args[1]

        assert result["mappings"]["temp_state"] == "sensor.override_32_153289"
        assert result["sources"] == {"temp_state": "external"}

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @pytest.mark.asyncio
    async def test_execute_overlay_provider_exception(self, mock_get_mappings, hass):
        """Test overlay_provider exceptions are handled by execute."""
        mock_get_mappings.return_value = {
            "temp_state": "sensor.temp_{device_id}",
        }

        overlay_provider = AsyncMock(side_effect=RuntimeError("overlay fail"))

        command = GetEntityMappingsCommand(
            hass,
            "test_feature",
            overlay_provider=overlay_provider,
        )
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings", "device_id": "32:153289"}

        await command.execute(mock_connection, msg)

        mock_connection.send_error.assert_called_once_with(
            123,
            "get_entity_mappings_failed",
            "overlay fail",
        )

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @pytest.mark.asyncio
    async def test_execute_no_mappings(self, mock_get_mappings, hass):
        """Test execution when no entity mappings are found."""
        mock_get_mappings.return_value = {}

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        mock_connection.send_error.assert_called_once_with(
            123, "no_entity_mappings", "No entity mappings found for test_feature"
        )

    @patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand._get_entity_mappings_from_feature"
    )
    @pytest.mark.asyncio
    async def test_execute_exception_handling(self, mock_get_mappings, hass):
        """Test exception handling in execute method."""
        mock_get_mappings.side_effect = Exception("Test error")

        command = GetEntityMappingsCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 123, "type": "get_entity_mappings"}

        await command.execute(mock_connection, msg)

        mock_connection.send_error.assert_called_once_with(
            123, "get_entity_mappings_failed", "Test error"
        )

    def test_parse_entity_templates(self, hass):
        """Test parsing entity templates."""
        command = GetEntityMappingsCommand(hass, "test_feature")
        entity_mappings = {
            "temp": "temp_{device_id}",
            "humidity": "humidity_{device_id}",
        }
        device_id = "32:153289"
        result = command._parse_entity_templates(entity_mappings, device_id)
        assert result == {"temp": "temp_32_153289", "humidity": "humidity_32_153289"}

    @pytest.mark.asyncio
    async def test_get_entity_mappings_from_feature_module_path(self, hass):
        """Test getting mappings using direct module path."""
        command = GetEntityMappingsCommand(hass, "test.const")

        mock_module = MagicMock()
        mock_module.FEATURE_DEFINITION = {
            "sensor_configs": {"s1": {"entity_template": "t1"}},
        }

        with patch("importlib.import_module", return_value=mock_module):
            mappings = await command._get_entity_mappings_from_feature()
            assert mappings == {"s1_state": "sensor.t1"}

    @pytest.mark.asyncio
    async def test_get_entity_mappings_from_feature_all_platforms(self, hass):
        """Test getting mappings for all platforms."""
        command = GetEntityMappingsCommand(hass, "test")

        mock_module = MagicMock()
        mock_module.FEATURE_DEFINITION = {
            "switch_configs": {"sw1": {"entity_template": "t_sw"}},
            "boolean_configs": {"bs1": {"entity_template": "t_bs"}},
            "sensor_configs": {"s1": {"entity_template": "t_s"}},
            "number_configs": {"n1": {"entity_template": "t_n"}},
        }

        with patch("importlib.import_module", return_value=mock_module):
            mappings = await command._get_entity_mappings_from_feature()
            assert mappings["sw1_state"] == "switch.t_sw"
            assert mappings["bs1_state"] == "binary_sensor.t_bs"
            assert mappings["s1_state"] == "sensor.t_s"
            assert mappings["n1_state"] == "number.t_n"

    @pytest.mark.asyncio
    async def test_get_entity_mappings_from_feature_fallback_const(self, hass):
        """Test explicit entity_mappings in FEATURE_DEFINITION."""
        command = GetEntityMappingsCommand(hass, "test")

        mock_module = MagicMock()
        mock_module.FEATURE_DEFINITION = {"entity_mappings": {"m1": "v1"}}

        with patch("importlib.import_module", return_value=mock_module):
            mappings = await command._get_entity_mappings_from_feature()
            assert mappings == {"m1": "v1"}

    @pytest.mark.asyncio
    async def test_get_entity_mappings_from_feature_exception(self, hass):
        """Test exception handling in _get_entity_mappings_from_feature."""
        command = GetEntityMappingsCommand(hass, "test")
        with patch("importlib.import_module", side_effect=ValueError("fail")):
            mappings = await command._get_entity_mappings_from_feature()
            assert mappings == {}

    # Note: sensor_control overlay logic and device type lookup were moved out of
    # the framework and into the default feature WebSocket handler.


class TestGetAllFeatureEntitiesCommand:
    """Test GetAllFeatureEntitiesCommand class."""

    def test_init(self, hass):
        """Test initialization."""
        command = GetAllFeatureEntitiesCommand(hass, "test_feature")
        assert command.hass == hass
        assert command.feature_identifier == "test_feature"

    @pytest.mark.asyncio
    async def test_execute_missing_device_id(self, hass):
        """Test execution when device_id is missing."""
        command = GetAllFeatureEntitiesCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 1, "type": "get_all_feature_entities"}
        await command.execute(mock_connection, msg)
        mock_connection.send_error.assert_called_once_with(1, "missing_device_id", ANY)

    @pytest.mark.asyncio
    async def test_execute_success(self, hass):
        """Test successful execution."""
        command = GetAllFeatureEntitiesCommand(hass, "test_feature")
        mock_connection = MagicMock()
        msg = {"id": 1, "type": "get_all_feature_entities", "device_id": "32:1"}
        mock_entities = {"sensor": {"t": {"entity_template": "t"}}}
        with (
            patch.object(
                command, "_get_all_entities_from_feature", return_value=mock_entities
            ),
            patch.object(
                command, "_parse_all_entity_templates", return_value={"parsed": "data"}
            ),
        ):
            await command.execute(mock_connection, msg)
            mock_connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_entities_from_feature(self, hass):
        """Test collecting all entities."""
        command = GetAllFeatureEntitiesCommand(hass, "test")

        mock_module = MagicMock()
        mock_module.FEATURE_DEFINITION = {
            "sensor_configs": {"s": {"entity_template": "t"}},
        }

        with patch("importlib.import_module", return_value=mock_module):
            entities = await command._get_all_entities_from_feature()
            assert "sensor" in entities

    @pytest.mark.asyncio
    async def test_get_all_entities_from_feature_exception(self, hass):
        """Test exception handling."""
        command = GetAllFeatureEntitiesCommand(hass, "test")
        with patch("importlib.import_module", side_effect=ValueError):
            assert await command._get_all_entities_from_feature() == {}

    def test_parse_all_entity_templates(self, hass):
        """Test parsing templates."""
        command = GetAllFeatureEntitiesCommand(hass, "test")
        entities = {"sensor": {"t": {"entity_template": "t_{device_id}"}}}
        result = command._parse_all_entity_templates(entities, "32:1")
        assert result["sensor"]["t"]["entity_id"] == "sensor.t_32:1"
