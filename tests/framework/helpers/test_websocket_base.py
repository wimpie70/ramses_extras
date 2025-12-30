# tests/framework/helpers/test_websocket_base.py
"""Test websocket base classes and utilities."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

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

        from custom_components.ramses_extras.const import DOMAIN

        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {}}
        mock_config_entry.options = {}

        hass.data = {DOMAIN: {"config_entry": mock_config_entry}}

        result = command._is_sensor_control_enabled()
        assert result is False

    @pytest.mark.asyncio
    async def test_apply_sensor_control_overrides_success(self, hass):
        """Test successful application of sensor control overrides."""
        command = GetEntityMappingsCommand(hass, "test_feature")
        device_id = "32:153289"
        base_mappings = {"indoor_humidity": "sensor.base_rh"}

        with (
            patch.object(command, "_get_device_type", return_value="FAN"),
            patch(
                "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver"
            ) as mock_resolver_class,
        ):
            mock_resolver = mock_resolver_class.return_value
            mock_resolver.resolve_entity_mappings = AsyncMock(
                return_value={
                    "mappings": {"indoor_humidity": "sensor.override_rh"},
                    "sources": {"indoor_humidity": "external"},
                    "raw_internal": {},
                    "abs_humidity_inputs": {},
                }
            )

            result = await command._apply_sensor_control_overrides(
                device_id, base_mappings
            )

            assert result["mappings"]["indoor_humidity"] == "sensor.override_rh"
            assert result["sources"]["indoor_humidity"] == "external"

    @pytest.mark.asyncio
    async def test_apply_sensor_control_overrides_no_device_type(self, hass):
        """Test application when device type cannot be determined."""
        command = GetEntityMappingsCommand(hass, "test_feature")
        with patch.object(command, "_get_device_type", return_value=None):
            result = await command._apply_sensor_control_overrides(
                "32:153289", {"test": "mapping"}
            )
            assert result == {}

    def test_get_device_type(self, hass):
        """Test getting device type from hass data."""
        from custom_components.ramses_extras.const import DOMAIN

        command = GetEntityMappingsCommand(hass, "test_feature")
        device_id = "32:153289"

        # Mock devices in hass data
        mock_device = MagicMock()
        mock_device.device_id = "32_153289"
        mock_device.type = "FAN"

        hass.data = {DOMAIN: {"devices": [mock_device]}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.websocket_base.extract_device_id_as_string",
            return_value="32_153289",
        ):
            device_type = command._get_device_type(device_id)
            assert device_type == "FAN"

    def test_get_device_type_dict(self, hass):
        """Test getting device type from dict-based device info."""
        from custom_components.ramses_extras.const import DOMAIN

        command = GetEntityMappingsCommand(hass, "test_feature")
        hass.data = {DOMAIN: {"devices": [{"device_id": "32:153289", "type": "CO2"}]}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.websocket_base.extract_device_id_as_string",
            return_value="32_153289",
        ):
            assert command._get_device_type("32_153289") == "CO2"


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
        msg = {
            "id": 1,
            "type": "get_all_feature_entities",
            "device_id": "32:153289",
        }

        mock_entities = {"sensor": {"temp": {"entity_template": "temp_{device_id}"}}}

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
            args, _ = mock_connection.send_result.call_args
            assert args[1]["success"] is True
            assert args[1]["entities"] == {"parsed": "data"}

    @pytest.mark.asyncio
    async def test_get_all_entities_from_feature(self, hass):
        """Test collecting all entities from a feature."""
        command = GetAllFeatureEntitiesCommand(hass, "test_feature")

        mock_module = MagicMock()
        # Mocking the attributes that _get_all_entities_from_feature looks for
        mock_module.SENSOR_CONFIGS = {"temp": {"entity_template": "temp_t"}}
        mock_module.SWITCH_CONFIGS = {"main": {"entity_template": "main_t"}}
        mock_module.BINARY_SENSOR_CONFIGS = {"active": {"entity_template": "active_t"}}
        mock_module.NUMBER_CONFIGS = {"level": {"entity_template": "level_t"}}

        # Patch importlib and the module's dir()
        with (
            patch("importlib.import_module", return_value=mock_module),
            patch(
                "custom_components.ramses_extras.framework.helpers.websocket_base.dir",
                return_value=[
                    "SENSOR_CONFIGS",
                    "SWITCH_CONFIGS",
                    "BINARY_SENSOR_CONFIGS",
                    "NUMBER_CONFIGS",
                ],
            ),
        ):
            entities = await command._get_all_entities_from_feature()
            assert "sensor" in entities
            assert "temp" in entities["sensor"]
            assert "switch" in entities
            assert "main" in entities["switch"]
            assert "binary_sensor" in entities
            assert "active" in entities["binary_sensor"]
            assert "number" in entities
            assert "level" in entities["number"]

    def test_parse_all_entity_templates(self, hass):
        """Test parsing all entity templates."""
        command = GetAllFeatureEntitiesCommand(hass, "test_feature")
        all_entities = {
            "sensor": {"temp": {"entity_template": "temp_{device_id}"}},
            "switch": {"main": {"entity_template": "main_{device_id}"}},
        }
        device_id = "32_153289"

        result = command._parse_all_entity_templates(all_entities, device_id)

        assert result["sensor"]["temp"]["entity_id"] == "sensor.temp_32_153289"
        assert result["switch"]["main"]["entity_id"] == "switch.main_32_153289"
