"""Tests for temp_control feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestTempControlConst:
    """Tests for temp_control feature constants and load_feature function."""

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.temp_control.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "temp_control"

    def test_temp_control_switch_configs(self):
        """Test TEMP_CONTROL_SWITCH_CONFIGS structure."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_SWITCH_CONFIGS,
        )

        assert "temp_control" in TEMP_CONTROL_SWITCH_CONFIGS
        config = TEMP_CONTROL_SWITCH_CONFIGS["temp_control"]

        assert config["icon"] == "mdi:thermometer-auto"
        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["entity_template"] == "temp_control_{device_id}"

    def test_temp_control_select_configs(self):
        """Test TEMP_CONTROL_SELECT_CONFIGS structure."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_SELECT_CONFIGS,
        )

        assert "temp_control_desired_speed" in TEMP_CONTROL_SELECT_CONFIGS
        config = TEMP_CONTROL_SELECT_CONFIGS["temp_control_desired_speed"]

        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["options"] == ["low", "medium", "high"]
        assert config["default_option"] == "high"

    def test_temp_control_boolean_configs(self):
        """Test TEMP_CONTROL_BOOLEAN_CONFIGS structure."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_BOOLEAN_CONFIGS,
        )

        assert "temp_control_active" in TEMP_CONTROL_BOOLEAN_CONFIGS
        config = TEMP_CONTROL_BOOLEAN_CONFIGS["temp_control_active"]

        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["device_class"] == "running"

    def test_temp_control_sensor_configs(self):
        """Test TEMP_CONTROL_SENSOR_CONFIGS structure."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_SENSOR_CONFIGS,
        )

        assert "temp_control_status" in TEMP_CONTROL_SENSOR_CONFIGS
        config = TEMP_CONTROL_SENSOR_CONFIGS["temp_control_status"]

        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["icon"] == "mdi:thermostat"

    def test_temp_control_device_entity_mapping(self):
        """Test TEMP_CONTROL_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_DEVICE_ENTITY_MAPPING,
        )

        assert "HvacVentilator" in TEMP_CONTROL_DEVICE_ENTITY_MAPPING
        mapping = TEMP_CONTROL_DEVICE_ENTITY_MAPPING["HvacVentilator"]

        assert "switch" in mapping
        assert "select" in mapping
        assert "binary_sensor" in mapping
        assert "sensor" in mapping
        assert "temp_control" in mapping["switch"]
        assert "temp_control_desired_speed" in mapping["select"]
        assert "temp_control_active" in mapping["binary_sensor"]
        assert "temp_control_status" in mapping["sensor"]

    def test_temp_control_websocket_commands(self):
        """Test TEMP_CONTROL_WEBSOCKET_COMMANDS has get_device_config."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_WEBSOCKET_COMMANDS,
        )

        assert "get_device_config" in TEMP_CONTROL_WEBSOCKET_COMMANDS
        assert (
            TEMP_CONTROL_WEBSOCKET_COMMANDS["get_device_config"]
            == "ramses_extras/temp_control/get_device_config"
        )

    def test_temp_control_defaults(self):
        """Test TEMP_CONTROL_DEFAULTS has expected values."""
        from custom_components.ramses_extras.features.temp_control.const import (
            TEMP_CONTROL_DEFAULTS,
        )

        assert TEMP_CONTROL_DEFAULTS["enabled"] is True
        assert TEMP_CONTROL_DEFAULTS["comfort_delta_activate"] == 1.0
        assert TEMP_CONTROL_DEFAULTS["comfort_delta_deactivate"] == 0.5
        assert TEMP_CONTROL_DEFAULTS["cooling_delta_activate"] == 1.0
        assert TEMP_CONTROL_DEFAULTS["cooling_delta_deactivate"] == 0.5
        assert TEMP_CONTROL_DEFAULTS["min_outdoor_temp"] == 10.0
        assert TEMP_CONTROL_DEFAULTS["min_bypass_mode_interval_seconds"] == 180
        assert TEMP_CONTROL_DEFAULTS["default_desired_speed"] == "high"

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.temp_control.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "temp_control"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "select_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "required_entities" in FEATURE_DEFINITION
        assert "entity_mappings" in FEATURE_DEFINITION

    def test_entity_mappings_contain_all_inputs(self):
        """Test entity_mappings has all required input entity references."""
        from custom_components.ramses_extras.features.temp_control.const import (
            FEATURE_DEFINITION,
        )

        mappings = FEATURE_DEFINITION["entity_mappings"]

        # Self entities
        assert "temp_control" in mappings
        assert "desired_speed" in mappings
        assert "temp_control_active" in mappings

        # Input entities
        assert "indoor_temp" in mappings
        assert "supply_temp" in mappings
        assert "comfort_temp" in mappings
        assert "indoor_rh" in mappings
        assert "min_rh" in mappings
        assert "max_rh" in mappings
        assert "dehumidifying_active" in mappings
        assert "co2_active" in mappings

    def test_load_feature_function(self):
        """Test load_feature registers with extras_registry."""
        from custom_components.ramses_extras.features.temp_control import const

        with patch(
            "custom_components.ramses_extras.extras_registry.extras_registry"
        ) as mock_registry:
            const.load_feature()

            mock_registry.register_switch_configs.assert_called_once()
            mock_registry.register_select_configs.assert_called_once()
            mock_registry.register_boolean_configs.assert_called_once()
            mock_registry.register_sensor_configs.assert_called_once()
            mock_registry.register_device_mappings.assert_called_once()
            mock_registry.register_websocket_commands.assert_called_once()
            mock_registry.register_feature.assert_called_once_with("temp_control")

    def test_all_exports(self):
        """Test that __all__ includes all expected exports."""
        from custom_components.ramses_extras.features.temp_control import const

        expected = [
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "TEMP_CONTROL_SWITCH_CONFIGS",
            "TEMP_CONTROL_SELECT_CONFIGS",
            "TEMP_CONTROL_BOOLEAN_CONFIGS",
            "TEMP_CONTROL_SENSOR_CONFIGS",
            "TEMP_CONTROL_DEVICE_ENTITY_MAPPING",
            "TEMP_CONTROL_DEFAULTS",
            "load_feature",
        ]
        for name in expected:
            assert name in const.__all__, f"{name} missing from __all__"
