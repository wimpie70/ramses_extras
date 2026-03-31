"""Tests for humidity_control feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestHumidityControlConst:
    """Tests for humidity_control feature constants and load_feature function."""

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "humidity_control"

    def test_device_models_structure(self):
        """Test device model configurations."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            ORCON_DEVICE_MODELS,
            ZEHNDER_DEVICE_MODELS,
        )

        # Check Orcon models
        assert "HRV400" in ORCON_DEVICE_MODELS
        hrv400 = ORCON_DEVICE_MODELS["HRV400"]
        assert hrv400["max_fan_speed"] == 5
        assert hrv400["humidity_range"] == (30, 80)
        assert "auto" in hrv400["supported_modes"]
        assert "filter_timer" in hrv400["special_entities"]

        # Check Zehnder models
        assert "ComfoAir Q350" in ZEHNDER_DEVICE_MODELS
        q350 = ZEHNDER_DEVICE_MODELS["ComfoAir Q350"]
        assert q350["max_fan_speed"] == 4
        assert q350["humidity_range"] == (30, 75)
        assert "co2_sensor" in q350["special_entities"]

    def test_humidity_switch_configs(self):
        """Test HUMIDITY_SWITCH_CONFIGS structure."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_SWITCH_CONFIGS,
        )

        assert "dehumidify" in HUMIDITY_SWITCH_CONFIGS
        config = HUMIDITY_SWITCH_CONFIGS["dehumidify"]

        assert config["name_template"] == "Balance {device_id}"
        assert config["icon"] == "mdi:water-percent"
        assert config["supported_device_types"] == ["HvacVentilator"]
        assert config["entity_template"] == "dehumidify_{device_id}"

    def test_humidity_number_configs(self):
        """Test HUMIDITY_NUMBER_CONFIGS contains all expected configs."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_NUMBER_CONFIGS,
        )

        expected_numbers = [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ]

        assert len(HUMIDITY_NUMBER_CONFIGS) == len(expected_numbers)
        for number in expected_numbers:
            assert number in HUMIDITY_NUMBER_CONFIGS

        # Check specific configs
        min_humidity = HUMIDITY_NUMBER_CONFIGS["relative_humidity_minimum"]
        assert min_humidity["unit"] == "%"
        assert min_humidity["min_value"] == 30
        assert min_humidity["max_value"] == 80
        assert min_humidity["default_value"] == 40

        max_humidity = HUMIDITY_NUMBER_CONFIGS["relative_humidity_maximum"]
        assert max_humidity["unit"] == "%"
        assert max_humidity["min_value"] == 50
        assert max_humidity["max_value"] == 90
        assert max_humidity["default_value"] == 60

        offset = HUMIDITY_NUMBER_CONFIGS["absolute_humidity_offset"]
        assert offset["unit"] == "g/m³"
        assert offset["min_value"] == -3.0
        assert offset["max_value"] == 3.0
        assert offset["default_value"] == 0.4

    def test_humidity_boolean_configs(self):
        """Test HUMIDITY_BOOLEAN_CONFIGS structure."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_BOOLEAN_CONFIGS,
        )

        assert "dehumidifying_active" in HUMIDITY_BOOLEAN_CONFIGS
        config = HUMIDITY_BOOLEAN_CONFIGS["dehumidifying_active"]

        assert config["name_template"] == "Balance Active {device_id}"
        assert config["device_class"] == "running"
        assert config["entity_category"] is not None

    def test_humidity_device_entity_mapping(self):
        """Test HUMIDITY_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_DEVICE_ENTITY_MAPPING,
        )

        assert "HvacVentilator" in HUMIDITY_DEVICE_ENTITY_MAPPING
        mapping = HUMIDITY_DEVICE_ENTITY_MAPPING["HvacVentilator"]

        assert "switch" in mapping
        assert "number" in mapping
        assert "binary_sensor" in mapping

        assert mapping["switch"] == ["dehumidify"]
        assert len(mapping["number"]) == 3
        assert mapping["binary_sensor"] == ["dehumidifying_active"]

    def test_humidity_websocket_commands_empty(self):
        """Test HUMIDITY_CONTROL_WEBSOCKET_COMMANDS is empty."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_CONTROL_WEBSOCKET_COMMANDS,
        )

        assert HUMIDITY_CONTROL_WEBSOCKET_COMMANDS == {}

    def test_enhanced_configs_have_default_enabled(self):
        """Test enhanced configs have default_enabled flag."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            ENHANCED_HUMIDITY_BOOLEAN_CONFIGS,
            ENHANCED_HUMIDITY_NUMBER_CONFIGS,
            ENHANCED_HUMIDITY_SWITCH_CONFIGS,
        )

        # Check that all enhanced configs have default_enabled: True
        for config in ENHANCED_HUMIDITY_SWITCH_CONFIGS.values():
            assert config.get("default_enabled") is True

        for config in ENHANCED_HUMIDITY_NUMBER_CONFIGS.values():
            assert config.get("default_enabled") is True

        for config in ENHANCED_HUMIDITY_BOOLEAN_CONFIGS.values():
            assert config.get("default_enabled") is True

    def test_humidity_control_defaults(self):
        """Test HUMIDITY_CONTROL_DEFAULTS structure."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_CONTROL_DEFAULTS,
        )

        assert HUMIDITY_CONTROL_DEFAULTS["enabled"] is True
        assert HUMIDITY_CONTROL_DEFAULTS["automation_enabled"] is False
        assert HUMIDITY_CONTROL_DEFAULTS["default_min_humidity"] == 40.0
        assert HUMIDITY_CONTROL_DEFAULTS["default_max_humidity"] == 60.0
        assert HUMIDITY_CONTROL_DEFAULTS["activation_threshold"] == 1.0
        assert HUMIDITY_CONTROL_DEFAULTS["deactivation_threshold"] == -1.0
        assert HUMIDITY_CONTROL_DEFAULTS["indoor_sensor_entity"] is None
        assert HUMIDITY_CONTROL_DEFAULTS["outdoor_sensor_entity"] is None
        assert HUMIDITY_CONTROL_DEFAULTS["max_runtime_minutes"] == 120
        assert HUMIDITY_CONTROL_DEFAULTS["cooldown_period_minutes"] == 15

    def test_humidity_control_validation_rules(self):
        """Test HUMIDITY_CONTROL_VALIDATION_RULES structure."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_CONTROL_VALIDATION_RULES,
        )

        # Check min humidity validation
        min_rule = HUMIDITY_CONTROL_VALIDATION_RULES["default_min_humidity"]
        assert min_rule["type"] == "numeric"
        assert min_rule["min"] == 0
        assert min_rule["max"] == 100
        assert "range_relationship" in min_rule

        # Check max humidity validation
        max_rule = HUMIDITY_CONTROL_VALIDATION_RULES["default_max_humidity"]
        assert max_rule["type"] == "numeric"
        assert max_rule["min"] == 0
        assert max_rule["max"] == 100

        # Check debounce validation
        debounce_rule = HUMIDITY_CONTROL_VALIDATION_RULES["automation_debounce_seconds"]
        assert debounce_rule["type"] == "numeric"
        assert debounce_rule["min"] == 1
        assert debounce_rule["max"] == 300

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "humidity_control"
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
        assert "relative_humidity_minimum" in required["number"]
        assert "relative_humidity_maximum" in required["number"]
        assert "absolute_humidity_offset" in required["number"]
        assert "dehumidify" in required["switch"]
        assert "dehumidifying_active" in required["binary_sensor"]

        # Check entity mappings
        mappings = FEATURE_DEFINITION["entity_mappings"]
        assert mappings["indoor_abs"] == "sensor.indoor_absolute_humidity_{device_id}"
        assert mappings["outdoor_abs"] == "sensor.outdoor_absolute_humidity_{device_id}"
        assert mappings["indoor_rh"] == "sensor.{device_id}_indoor_humidity"

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.humidity_control.const import (
            HUMIDITY_BOOLEAN_CONFIGS,
            HUMIDITY_CONTROL_WEBSOCKET_COMMANDS,
            HUMIDITY_DEVICE_ENTITY_MAPPING,
            HUMIDITY_NUMBER_CONFIGS,
            HUMIDITY_SWITCH_CONFIGS,
            load_feature,
        )

        mock_registry = MagicMock()
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
                "custom_components.ramses_extras.features.humidity_control.humidity_control_yaml.load_validator"
            ) as mock_load_validator,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_switch_configs.assert_called_once_with(
                HUMIDITY_SWITCH_CONFIGS
            )
            mock_registry.register_number_configs.assert_called_once_with(
                HUMIDITY_NUMBER_CONFIGS
            )
            mock_registry.register_boolean_configs.assert_called_once_with(
                HUMIDITY_BOOLEAN_CONFIGS
            )
            mock_registry.register_device_mappings.assert_called_once_with(
                HUMIDITY_DEVICE_ENTITY_MAPPING
            )
            mock_registry.register_websocket_commands.assert_called_once_with(
                "humidity_control", HUMIDITY_CONTROL_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with("humidity_control")

            # Check validator loading
            mock_load_validator.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.humidity_control import const

        expected_exports = [
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "HUMIDITY_SWITCH_CONFIGS",
            "HUMIDITY_NUMBER_CONFIGS",
            "HUMIDITY_BOOLEAN_CONFIGS",
            "HUMIDITY_DEVICE_ENTITY_MAPPING",
            "HUMIDITY_CONTROL_WEBSOCKET_COMMANDS",
            "HUMIDITY_CONTROL_DEFAULTS",
            "HUMIDITY_CONTROL_VALIDATION_RULES",
            "ORCON_DEVICE_MODELS",
            "ZEHNDER_DEVICE_MODELS",
            "ENHANCED_HUMIDITY_SWITCH_CONFIGS",
            "ENHANCED_HUMIDITY_NUMBER_CONFIGS",
            "ENHANCED_HUMIDITY_BOOLEAN_CONFIGS",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
