"""Tests for co2_control feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestCo2ControlConst:
    """Tests for co2_control feature constants and load_feature function."""

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.co2_control.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "co2_control"

    def test_co2_switch_configs_structure(self):
        """Test CO2_SWITCH_CONFIGS has correct structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_SWITCH_CONFIGS,
        )

        assert "co2_control" in CO2_SWITCH_CONFIGS
        config = CO2_SWITCH_CONFIGS["co2_control"]

        assert config["name_template"] == "CO2 Control {device_id}"
        assert config["icon"] == "mdi:molecule-co2"
        assert "entity_category" in config
        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["entity_template"] == "co2_control_{device_id}"

    def test_co2_number_configs_structure(self):
        """Test CO2_NUMBER_CONFIGS contains all expected number configs."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_NUMBER_CONFIGS,
        )

        expected_numbers = [
            "co2_threshold",
            "co2_activation_hysteresis",
            "co2_deactivation_hysteresis",
        ]

        assert len(CO2_NUMBER_CONFIGS) == len(expected_numbers)
        for number in expected_numbers:
            assert number in CO2_NUMBER_CONFIGS

        # Check specific config
        threshold = CO2_NUMBER_CONFIGS["co2_threshold"]
        assert threshold["unit"] == "ppm"
        assert threshold["min_value"] == 400
        assert threshold["max_value"] == 2000
        assert threshold["default_value"] == 1000

    def test_co2_binary_sensor_configs(self):
        """Test CO2_BINARY_SENSOR_CONFIGS structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_BINARY_SENSOR_CONFIGS,
        )

        assert "co2_active" in CO2_BINARY_SENSOR_CONFIGS
        config = CO2_BINARY_SENSOR_CONFIGS["co2_active"]

        assert config["name_template"] == "CO2 Active {device_id}"
        assert config["device_class"] == "running"
        assert config["entity_category"] is not None

    def test_co2_sensor_configs(self):
        """Test CO2_SENSOR_CONFIGS structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_SENSOR_CONFIGS,
        )

        assert "co2_zone_status" in CO2_SENSOR_CONFIGS
        config = CO2_SENSOR_CONFIGS["co2_zone_status"]

        assert config["name_template"] == "CO2 Zone Status {device_id}"
        assert config["icon"] == "mdi:home-analytics"
        assert config["entity_category"] is not None

    def test_co2_device_entity_mapping(self):
        """Test CO2_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_DEVICE_ENTITY_MAPPING,
        )

        assert "HvacVentilator" in CO2_DEVICE_ENTITY_MAPPING
        mapping = CO2_DEVICE_ENTITY_MAPPING["HvacVentilator"]

        assert "switch" in mapping
        assert "number" in mapping
        assert "binary_sensor" in mapping
        assert "sensor" in mapping

        assert mapping["switch"] == ["co2_control"]
        assert len(mapping["number"]) == 3  # threshold + 2 hysteresis
        assert mapping["binary_sensor"] == ["co2_active"]
        assert mapping["sensor"] == ["co2_zone_status"]

    def test_co2_websocket_commands(self):
        """Test CO2_CONTROL_WEBSOCKET_COMMANDS structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_CONTROL_WEBSOCKET_COMMANDS,
        )

        expected_commands = [
            "get_co2_status",
            "get_zone_details",
            "update_zone_config",
            "get_co2_history",
        ]

        assert len(CO2_CONTROL_WEBSOCKET_COMMANDS) == len(expected_commands)
        for cmd in expected_commands:
            assert cmd in CO2_CONTROL_WEBSOCKET_COMMANDS
            assert CO2_CONTROL_WEBSOCKET_COMMANDS[cmd].startswith("ramses_extras/co2/")

    def test_enhanced_configs_have_default_enabled(self):
        """Test enhanced configs have default_enabled flag."""
        from custom_components.ramses_extras.features.co2_control.const import (
            ENHANCED_CO2_BINARY_SENSOR_CONFIGS,
            ENHANCED_CO2_NUMBER_CONFIGS,
            ENHANCED_CO2_SENSOR_CONFIGS,
            ENHANCED_CO2_SWITCH_CONFIGS,
        )

        # Check that all enhanced configs have default_enabled: True
        for config in ENHANCED_CO2_SWITCH_CONFIGS.values():
            assert config.get("default_enabled") is True

        for config in ENHANCED_CO2_NUMBER_CONFIGS.values():
            assert config.get("default_enabled") is True

        for config in ENHANCED_CO2_BINARY_SENSOR_CONFIGS.values():
            assert config.get("default_enabled") is True

        for config in ENHANCED_CO2_SENSOR_CONFIGS.values():
            assert config.get("default_enabled") is True

    def test_co2_control_defaults(self):
        """Test CO2_CONTROL_DEFAULTS structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_CONTROL_DEFAULTS,
        )

        assert CO2_CONTROL_DEFAULTS["enabled"] is True
        assert CO2_CONTROL_DEFAULTS["automation_enabled"] is False
        assert CO2_CONTROL_DEFAULTS["default_threshold"] == 1000
        assert CO2_CONTROL_DEFAULTS["activation_hysteresis"] == 100
        assert CO2_CONTROL_DEFAULTS["deactivation_hysteresis"] == -100
        assert CO2_CONTROL_DEFAULTS["zones"] == []
        assert CO2_CONTROL_DEFAULTS["max_runtime_minutes"] == 120
        assert CO2_CONTROL_DEFAULTS["cooldown_period_minutes"] == 15
        assert CO2_CONTROL_DEFAULTS["priority_over_humidity"] is True

    def test_co2_control_validation_rules(self):
        """Test CO2_CONTROL_VALIDATION_RULES structure."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_CONTROL_VALIDATION_RULES,
        )

        # Check threshold validation
        threshold_rule = CO2_CONTROL_VALIDATION_RULES["default_threshold"]
        assert threshold_rule["type"] == "numeric"
        assert threshold_rule["min"] == 400
        assert threshold_rule["max"] == 2000

        # Check hysteresis validation
        act_hyst_rule = CO2_CONTROL_VALIDATION_RULES["activation_hysteresis"]
        assert act_hyst_rule["type"] == "numeric"
        assert act_hyst_rule["min"] == 0
        assert act_hyst_rule["max"] == 500

        deact_hyst_rule = CO2_CONTROL_VALIDATION_RULES["deactivation_hysteresis"]
        assert deact_hyst_rule["type"] == "numeric"
        assert deact_hyst_rule["min"] == -500
        assert deact_hyst_rule["max"] == 0

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.co2_control.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "co2_control"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "number_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "required_entities" in FEATURE_DEFINITION
        assert "entity_mappings" in FEATURE_DEFINITION

        # Check required entities
        required = FEATURE_DEFINITION["required_entities"]
        assert "co2_threshold" in required["number"]
        assert "co2_control" in required["switch"]
        assert "co2_active" in required["binary_sensor"]
        assert "co2_zone_status" in required["sensor"]

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.co2_control.const import (
            CO2_BINARY_SENSOR_CONFIGS,
            CO2_CONTROL_WEBSOCKET_COMMANDS,
            CO2_DEVICE_ENTITY_MAPPING,
            CO2_NUMBER_CONFIGS,
            CO2_SENSOR_CONFIGS,
            CO2_SWITCH_CONFIGS,
            load_feature,
        )

        mock_registry = MagicMock()
        mock_registry.register_sensor_configs = MagicMock()
        mock_registry.register_switch_configs = MagicMock()
        mock_registry.register_number_configs = MagicMock()
        mock_registry.register_boolean_configs = MagicMock()
        mock_registry.register_device_mappings = MagicMock()
        mock_registry.register_websocket_commands = MagicMock()
        mock_registry.register_feature = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry",
                mock_registry,
            ),
            patch(
                "custom_components.ramses_extras.features.co2_control.co2_control_yaml.load_validator"
            ) as mock_load_validator,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_sensor_configs.assert_called_once_with(
                CO2_SENSOR_CONFIGS
            )
            mock_registry.register_switch_configs.assert_called_once_with(
                CO2_SWITCH_CONFIGS
            )
            mock_registry.register_number_configs.assert_called_once_with(
                CO2_NUMBER_CONFIGS
            )
            mock_registry.register_boolean_configs.assert_called_once_with(
                CO2_BINARY_SENSOR_CONFIGS
            )
            mock_registry.register_device_mappings.assert_called_once_with(
                CO2_DEVICE_ENTITY_MAPPING
            )
            mock_registry.register_websocket_commands.assert_called_once_with(
                "co2_control", CO2_CONTROL_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with("co2_control")

            # Check validator loading
            mock_load_validator.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.co2_control import const

        expected_exports = [
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "CO2_SWITCH_CONFIGS",
            "CO2_NUMBER_CONFIGS",
            "CO2_BINARY_SENSOR_CONFIGS",
            "CO2_SENSOR_CONFIGS",
            "CO2_DEVICE_ENTITY_MAPPING",
            "CO2_CONTROL_WEBSOCKET_COMMANDS",
            "CO2_CONTROL_DEFAULTS",
            "CO2_CONTROL_VALIDATION_RULES",
            "ENHANCED_CO2_SWITCH_CONFIGS",
            "ENHANCED_CO2_NUMBER_CONFIGS",
            "ENHANCED_CO2_BINARY_SENSOR_CONFIGS",
            "ENHANCED_CO2_SENSOR_CONFIGS",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
