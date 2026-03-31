"""Tests for sensor_control feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.sensor_control.const import (
    SENSOR_CONTROL_BOOLEAN_CONFIGS,
    SENSOR_CONTROL_DEVICE_ENTITY_MAPPING,
    SENSOR_CONTROL_NUMBER_CONFIGS,
    SENSOR_CONTROL_SENSOR_CONFIGS,
    SENSOR_CONTROL_SWITCH_CONFIGS,
    SENSOR_CONTROL_WEBSOCKET_COMMANDS,
)


class TestSensorControlConst:
    """Tests for sensor_control feature constants and load_feature function."""

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "sensor_control"

    def test_domain_constant(self):
        """Test DOMAIN constant is correctly defined."""
        from custom_components.ramses_extras.features.sensor_control.const import DOMAIN

        assert DOMAIN == "sensor_control"

    def test_supported_metrics_list(self):
        """Test SUPPORTED_METRICS contains all expected metrics."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            SUPPORTED_METRICS,
        )

        expected_metrics = [
            "indoor_temperature",
            "indoor_humidity",
            "co2",
            "co2_zone_1",
            "co2_zone_2",
            "co2_zone_3",
            "outdoor_temperature",
            "outdoor_humidity",
            "indoor_abs_humidity",
            "outdoor_abs_humidity",
        ]

        assert len(SUPPORTED_METRICS) == len(expected_metrics)
        for metric in expected_metrics:
            assert metric in SUPPORTED_METRICS

    def test_internal_sensor_mappings_structure(self):
        """Test INTERNAL_SENSOR_MAPPINGS has correct structure."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            INTERNAL_SENSOR_MAPPINGS,
        )

        assert "FAN" in INTERNAL_SENSOR_MAPPINGS
        fan_mappings = INTERNAL_SENSOR_MAPPINGS["FAN"]

        # Check basic sensors
        assert fan_mappings["indoor_temperature"] == "sensor.{device_id}_temperature"
        assert fan_mappings["indoor_humidity"] == "sensor.{device_id}_humidity"
        assert fan_mappings["co2"] == "sensor.{device_id}_co2"

        # Check CO2 zone sensors
        assert fan_mappings["co2_zone_1"] == "sensor.co2_zone_1_{device_id}"
        assert fan_mappings["co2_zone_2"] == "sensor.co2_zone_2_{device_id}"
        assert fan_mappings["co2_zone_3"] == "sensor.co2_zone_3_{device_id}"

        # Check outdoor sensors
        assert (
            fan_mappings["outdoor_temperature"]
            == "sensor.{device_id}_outdoor_temperature"
        )
        assert fan_mappings["outdoor_humidity"] == "sensor.{device_id}_outdoor_humidity"

    def test_configuration_keys(self):
        """Test configuration key constants."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
            SENSOR_CONTROL_AREA_SENSORS_KEY,
            SENSOR_CONTROL_SOURCES_KEY,
        )

        assert SENSOR_CONTROL_SOURCES_KEY == "sources"
        assert SENSOR_CONTROL_AREA_SENSORS_KEY == "area_sensors"
        assert SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY == "abs_humidity_inputs"

    def test_config_dictionaries_initially_empty(self):
        """Test config dictionaries start empty."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            SENSOR_CONTROL_BOOLEAN_CONFIGS,
            SENSOR_CONTROL_DEVICE_ENTITY_MAPPING,
            SENSOR_CONTROL_NUMBER_CONFIGS,
            SENSOR_CONTROL_SENSOR_CONFIGS,
            SENSOR_CONTROL_SWITCH_CONFIGS,
            SENSOR_CONTROL_WEBSOCKET_COMMANDS,
        )

        # All should start empty and be populated at runtime
        assert SENSOR_CONTROL_SENSOR_CONFIGS == {}
        assert SENSOR_CONTROL_SWITCH_CONFIGS == {}
        assert SENSOR_CONTROL_NUMBER_CONFIGS == {}
        assert SENSOR_CONTROL_BOOLEAN_CONFIGS == {}
        assert SENSOR_CONTROL_DEVICE_ENTITY_MAPPING == {}
        assert SENSOR_CONTROL_WEBSOCKET_COMMANDS == {}

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "sensor_control"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "number_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION

        # Check that all config dicts are referenced
        assert FEATURE_DEFINITION["sensor_configs"] is SENSOR_CONTROL_SENSOR_CONFIGS
        assert FEATURE_DEFINITION["switch_configs"] is SENSOR_CONTROL_SWITCH_CONFIGS
        assert FEATURE_DEFINITION["number_configs"] is SENSOR_CONTROL_NUMBER_CONFIGS
        assert FEATURE_DEFINITION["boolean_configs"] is SENSOR_CONTROL_BOOLEAN_CONFIGS
        assert (
            FEATURE_DEFINITION["device_entity_mapping"]
            is SENSOR_CONTROL_DEVICE_ENTITY_MAPPING
        )
        assert (
            FEATURE_DEFINITION["websocket_commands"]
            is SENSOR_CONTROL_WEBSOCKET_COMMANDS
        )

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.sensor_control.const import (
            DOMAIN,
            SENSOR_CONTROL_WEBSOCKET_COMMANDS,
            load_feature,
        )

        mock_registry = MagicMock()
        mock_registry.register_websocket_commands = MagicMock()
        mock_registry.register_feature = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry",
                mock_registry,
            ),
            patch(
                "custom_components.ramses_extras.features.sensor_control.sensor_control_yaml.load_validator"
            ) as mock_load_sensor,
            patch(
                "custom_components.ramses_extras.features.sensor_control.zones_yaml.load_validator"
            ) as mock_load_zones,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_websocket_commands.assert_called_once_with(
                DOMAIN, SENSOR_CONTROL_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with(DOMAIN)

            # Check validator loading
            mock_load_sensor.assert_called_once()
            mock_load_zones.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.sensor_control import const

        expected_exports = [
            "DOMAIN",
            "FEATURE_DEFINITION",
            "SUPPORTED_METRICS",
            "INTERNAL_SENSOR_MAPPINGS",
            "SENSOR_CONTROL_SOURCES_KEY",
            "SENSOR_CONTROL_AREA_SENSORS_KEY",
            "SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY",
            "SENSOR_CONTROL_SENSOR_CONFIGS",
            "SENSOR_CONTROL_SWITCH_CONFIGS",
            "SENSOR_CONTROL_NUMBER_CONFIGS",
            "SENSOR_CONTROL_BOOLEAN_CONFIGS",
            "SENSOR_CONTROL_DEVICE_ENTITY_MAPPING",
            "SENSOR_CONTROL_WEBSOCKET_COMMANDS",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
