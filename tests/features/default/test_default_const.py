"""Tests for default feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestDefaultConst:
    """Tests for default feature constants and load_feature function."""

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.default.const import FEATURE_ID

        assert FEATURE_ID == "default"

    def test_domain_constant(self):
        """Test DOMAIN constant is correctly defined."""
        from custom_components.ramses_extras.features.default.const import DOMAIN

        assert DOMAIN == "default"

    def test_default_sensor_configs_structure(self):
        """Test DEFAULT_SENSOR_CONFIGS has correct structure for humidity sensors."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_SENSOR_CONFIGS,
        )

        assert "indoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS
        assert "outdoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS

        indoor_config = DEFAULT_SENSOR_CONFIGS["indoor_absolute_humidity"]
        assert indoor_config["name_template"] == "Indoor Absolute Humidity {device_id}"
        assert indoor_config["unit"] == "g/m³"
        assert "FAN" in indoor_config["supported_device_types"]

        outdoor_config = DEFAULT_SENSOR_CONFIGS["outdoor_absolute_humidity"]
        assert (
            outdoor_config["name_template"] == "Outdoor Absolute Humidity {device_id}"
        )
        assert outdoor_config["unit"] == "g/m³"
        assert "FAN" in outdoor_config["supported_device_types"]

    def test_default_switch_configs_empty(self):
        """Test DEFAULT_SWITCH_CONFIGS is empty dict."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_SWITCH_CONFIGS,
        )

        assert DEFAULT_SWITCH_CONFIGS == {}

    def test_default_number_configs_empty(self):
        """Test DEFAULT_NUMBER_CONFIGS is empty dict."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_NUMBER_CONFIGS,
        )

        assert DEFAULT_NUMBER_CONFIGS == {}

    def test_default_boolean_configs_empty(self):
        """Test DEFAULT_BOOLEAN_CONFIGS is empty dict."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_BOOLEAN_CONFIGS,
        )

        assert DEFAULT_BOOLEAN_CONFIGS == {}

    def test_default_device_entity_mapping(self):
        """Test DEFAULT_DEVICE_ENTITY_MAPPING has correct structure."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_DEVICE_ENTITY_MAPPING,
        )

        assert "FAN" in DEFAULT_DEVICE_ENTITY_MAPPING
        assert "sensor" in DEFAULT_DEVICE_ENTITY_MAPPING["FAN"]
        assert (
            "indoor_absolute_humidity" in DEFAULT_DEVICE_ENTITY_MAPPING["FAN"]["sensor"]
        )
        assert (
            "outdoor_absolute_humidity"
            in DEFAULT_DEVICE_ENTITY_MAPPING["FAN"]["sensor"]
        )

    def test_entity_patterns(self):
        """Test ENTITY_PATTERNS maps sensor types to underlying entity patterns."""
        from custom_components.ramses_extras.features.default.const import (
            ENTITY_PATTERNS,
        )

        assert ENTITY_PATTERNS["indoor_absolute_humidity"] == (
            "indoor_temp",
            "indoor_humidity",
        )
        assert ENTITY_PATTERNS["outdoor_absolute_humidity"] == (
            "outdoor_temp",
            "outdoor_humidity",
        )

    def test_websocket_command_constants(self):
        """Test all WebSocket command constants are defined."""
        from custom_components.ramses_extras.features.default.const import (
            WS_CMD_GET_2411_SCHEMA,
            WS_CMD_GET_ALL_FEATURE_ENTITIES,
            WS_CMD_GET_AVAILABLE_DEVICES,
            WS_CMD_GET_BOUND_REM,
            WS_CMD_GET_CARDS_ENABLED,
            WS_CMD_GET_ENABLED_FEATURES,
            WS_CMD_GET_ENTITY_MAPPINGS,
            WS_CMD_SEND_FAN_COMMAND,
        )

        assert "ramses_extras/" in WS_CMD_GET_AVAILABLE_DEVICES
        assert "ramses_extras/" in WS_CMD_GET_BOUND_REM
        assert "ramses_extras/" in WS_CMD_GET_2411_SCHEMA
        assert "ramses_extras/default/" in WS_CMD_SEND_FAN_COMMAND
        assert "ramses_extras/default/" in WS_CMD_GET_ENABLED_FEATURES
        assert "ramses_extras/default/" in WS_CMD_GET_CARDS_ENABLED
        assert "ramses_extras/" in WS_CMD_GET_ENTITY_MAPPINGS
        assert "ramses_extras/" in WS_CMD_GET_ALL_FEATURE_ENTITIES

    def test_default_websocket_commands_mapping(self):
        """Test DEFAULT_WEBSOCKET_COMMANDS maps names to command types."""
        from custom_components.ramses_extras.features.default.const import (
            DEFAULT_WEBSOCKET_COMMANDS,
        )

        assert "get_available_devices" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_bound_rem" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_2411_schema" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_enabled_features" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_cards_enabled" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_entity_mappings" in DEFAULT_WEBSOCKET_COMMANDS
        assert "get_all_feature_entities" in DEFAULT_WEBSOCKET_COMMANDS

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.default.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "default"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "number_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "required_entities" in FEATURE_DEFINITION
        assert "sensor" in FEATURE_DEFINITION["required_entities"]

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.default import const

        expected_exports = [
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "DEFAULT_SENSOR_CONFIGS",
            "DEFAULT_SWITCH_CONFIGS",
            "DEFAULT_NUMBER_CONFIGS",
            "DEFAULT_BOOLEAN_CONFIGS",
            "DEFAULT_DEVICE_ENTITY_MAPPING",
            "ENTITY_PATTERNS",
            "WS_CMD_GET_AVAILABLE_DEVICES",
            "WS_CMD_GET_BOUND_REM",
            "WS_CMD_GET_2411_SCHEMA",
            "WS_CMD_SEND_FAN_COMMAND",
            "WS_CMD_GET_ENABLED_FEATURES",
            "WS_CMD_GET_CARDS_ENABLED",
            "WS_CMD_GET_ENTITY_MAPPINGS",
            "WS_CMD_GET_ALL_FEATURE_ENTITIES",
            "DEFAULT_WEBSOCKET_COMMANDS",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
