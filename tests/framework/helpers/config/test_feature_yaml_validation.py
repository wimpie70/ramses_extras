"""Tests for feature YAML validation modules.

This test module covers validation logic for all feature YAML modules:
- co2_control_yaml.py
- humidity_control_yaml.py
- default_yaml.py
- hello_world_yaml.py
- hvac_fan_card_yaml.py
- ramses_debugger_yaml.py
- remote_binding_yaml.py
- sensor_control_yaml.py
- zones_yaml.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.co2_control.co2_control_yaml import (
    CO2_CONTROL_CONFIG_SCHEMA,
    CO2_FAN_CONFIG_SCHEMA,
    CO2_ZONE_SCHEMA,
    co2_control_validator,
    export_co2_control_to_yaml,
    load_validator,
    merge_co2_control_config,
    parse_co2_control_yaml,
)
from custom_components.ramses_extras.features.default.default_yaml import (
    DEFAULT_FEATURE_CONFIG_SCHEMA,
    default_validator,
    export_default_to_yaml,
    merge_default_config,
    parse_default_yaml,
)
from custom_components.ramses_extras.features.default.default_yaml import (
    load_validator as load_default_validator,
)
from custom_components.ramses_extras.features.hello_world.hello_world_yaml import (
    HELLO_WORLD_CONFIG_SCHEMA,
    export_hello_world_to_yaml,
    hello_world_validator,
    merge_hello_world_config,
    parse_hello_world_yaml,
)
from custom_components.ramses_extras.features.hello_world.hello_world_yaml import (
    load_validator as load_hello_world_validator,
)
from custom_components.ramses_extras.features.humidity_control.humidity_control_yaml import (  # noqa: E501
    HUMIDITY_CONTROL_CONFIG_SCHEMA,
    HUMIDITY_FAN_CONFIG_SCHEMA,
    export_humidity_control_to_yaml,
    humidity_control_validator,
    merge_humidity_control_config,
    parse_humidity_control_yaml,
)
from custom_components.ramses_extras.features.humidity_control.humidity_control_yaml import (  # noqa: E501
    load_validator as load_humidity_validator,
)
from custom_components.ramses_extras.features.hvac_fan_card.hvac_fan_card_yaml import (
    HVAC_FAN_CARD_CONFIG_SCHEMA,
    export_hvac_fan_card_to_yaml,
    hvac_fan_card_validator,
    merge_hvac_fan_card_config,
    parse_hvac_fan_card_yaml,
)
from custom_components.ramses_extras.features.hvac_fan_card.hvac_fan_card_yaml import (
    load_validator as load_hvac_fan_card_validator,
)
from custom_components.ramses_extras.features.ramses_debugger.ramses_debugger_yaml import (  # noqa: E501
    RAMSES_DEBUGGER_CONFIG_SCHEMA,
    export_ramses_debugger_to_yaml,
    merge_ramses_debugger_config,
    parse_ramses_debugger_yaml,
    ramses_debugger_validator,
)
from custom_components.ramses_extras.features.ramses_debugger.ramses_debugger_yaml import (  # noqa: E501
    load_validator as load_ramses_debugger_validator,
)
from custom_components.ramses_extras.features.sensor_control.remote_binding_yaml import (  # noqa: E501
    FAN_REM_CONFIG_SCHEMA,
    REM_ENTRY_SCHEMA,
    REMOTE_BINDING_CONFIG_SCHEMA,
    export_remote_binding_to_yaml,
    merge_remote_binding_config,
    parse_remote_binding_yaml,
    remote_binding_validator,
)
from custom_components.ramses_extras.features.sensor_control.remote_binding_yaml import (  # noqa: E501
    load_validator as load_remote_binding_validator,
)
from custom_components.ramses_extras.features.sensor_control.sensor_control_yaml import (  # noqa: E501
    ABS_HUMIDITY_INPUT_SCHEMA,
    AREA_SENSOR_SCHEMA,
    FAN_CONFIG_SCHEMA,
    SENSOR_CONTROL_CONFIG_SCHEMA,
    SOURCE_SCHEMA,
    export_sensor_control_to_yaml,
    merge_sensor_control_config,
    parse_sensor_control_yaml,
    sensor_control_validator,
)
from custom_components.ramses_extras.features.sensor_control.sensor_control_yaml import (  # noqa: E501
    load_validator as load_sensor_control_validator,
)
from custom_components.ramses_extras.features.sensor_control.zones_yaml import (  # noqa: E501
    ZONE_ENTRY_SCHEMA,
    ZONES_CONFIG_SCHEMA,
    export_zones_to_yaml,
    merge_zones_config,
    parse_zones_yaml,
    validate_zone_references,
    zones_validator,
)
from custom_components.ramses_extras.features.sensor_control.zones_yaml import (  # noqa: E501
    load_validator as load_zones_validator,
)


class TestCO2ControlYAML:
    """Test cases for CO2 control YAML validation."""

    def test_co2_zone_schema_valid(self):
        """Test CO2 zone schema with valid data."""
        zone_data = {
            "zone_id": "bathroom",
            "name": "Bathroom",
            "threshold": 1000,
            "activation_hysteresis": 100,
            "deactivation_hysteresis": -100,
        }

        result = CO2_ZONE_SCHEMA(zone_data)
        assert result["zone_id"] == "bathroom"
        assert result["threshold"] == 1000

    def test_co2_zone_schema_defaults(self):
        """Test CO2 zone schema with default values."""
        zone_data = {"zone_id": "office"}

        result = CO2_ZONE_SCHEMA(zone_data)
        assert result["zone_id"] == "office"
        assert result["threshold"] == 1000
        assert result["activation_hysteresis"] == 100
        assert result["deactivation_hysteresis"] == -100

    def test_co2_zone_schema_invalid_threshold(self):
        """Test CO2 zone schema with invalid threshold."""
        zone_data = {"zone_id": "bathroom", "threshold": 3000}

        with pytest.raises(vol.Invalid):  # vol.Invalid
            CO2_ZONE_SCHEMA(zone_data)

    def test_co2_fan_config_schema_valid(self):
        """Test CO2 fan config schema with valid data."""
        fan_config = {
            "enabled": True,
            "automation_enabled": False,
            "threshold": 1000,
            "max_runtime_minutes": 120,
            "zones": [
                {
                    "zone_id": "bathroom",
                    "threshold": 800,
                }
            ],
        }

        result = CO2_FAN_CONFIG_SCHEMA(fan_config)
        assert result["enabled"] is True
        assert len(result["zones"]) == 1

    def test_co2_control_validator_valid(self):
        """Test CO2 control validator with valid configuration."""
        section = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "threshold": 1000,
                    "activation_hysteresis": 100,
                    "deactivation_hysteresis": -100,
                    "zones": [{"zone_id": "bathroom", "threshold": 800}],
                }
            }
        }

        errors = co2_control_validator(section)
        assert errors == []

    def test_co2_control_validator_invalid_fan_config(self):
        """Test CO2 control validator with invalid fan config."""
        section = {"FANs": {"32:153289": "not_a_dict"}}

        errors = co2_control_validator(section)
        assert len(errors) == 1
        assert "configuration must be a dictionary" in errors[0]

    def test_co2_control_validator_invalid_threshold(self):
        """Test CO2 control validator with invalid threshold."""
        section = {
            "FANs": {
                "32:153289": {
                    "threshold": 3000,  # Out of range
                }
            }
        }

        errors = co2_control_validator(section)
        assert len(errors) == 1
        assert "threshold 3000 out of range" in errors[0]

    def test_co2_control_validator_invalid_hysteresis(self):
        """Test CO2 control validator with invalid hysteresis."""
        section = {
            "FANs": {
                "32:153289": {
                    "activation_hysteresis": 600,  # Out of range
                    "deactivation_hysteresis": 100,  # Out of range
                }
            }
        }

        errors = co2_control_validator(section)
        assert len(errors) == 2
        assert "activation_hysteresis 600 out of range" in errors[0]
        assert "deactivation_hysteresis 100 out of range" in errors[1]

    def test_co2_control_validator_invalid_zones(self):
        """Test CO2 control validator with invalid zones."""
        section = {"FANs": {"32:153289": {"zones": "not_a_list"}}}

        errors = co2_control_validator(section)
        assert len(errors) == 1
        assert "zones must be a list" in errors[0]

    def test_export_co2_control_to_yaml(self):
        """Test CO2 control export to YAML."""
        config = {"FANs": {"32:153289": {"enabled": True}}}

        result = export_co2_control_to_yaml(config)
        assert result == config

    def test_parse_co2_control_yaml(self):
        """Test CO2 control YAML parsing."""
        yaml_data = {"FANs": {"32:153289": {"enabled": True}}}

        result = parse_co2_control_yaml(yaml_data)
        # Schema adds defaults but doesn't include zones if not provided
        expected = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "automation_enabled": False,
                    "threshold": 1000,
                    "activation_hysteresis": 100,
                    "deactivation_hysteresis": -100,
                    "max_runtime_minutes": 120,
                    "cooldown_period_minutes": 15,
                    "priority_over_humidity": True,
                }
            }
        }
        assert result == expected

    def test_merge_co2_control_config(self):
        """Test CO2 control config merging."""
        existing = {"FANs": {"32:153289": {"enabled": True}}}
        imported = {"FANs": {"32:153289": {"threshold": 1000}}}

        result = merge_co2_control_config(existing, imported)
        # The merge replaces the entire FAN entry
        expected = {"FANs": {"32:153289": {"threshold": 1000}}}
        assert result == expected

    def test_load_validator(self):
        """Test CO2 control validator loading."""
        load_validator()
        # Should not raise any exceptions


class TestHumidityControlYAML:
    """Test cases for Humidity control YAML validation."""

    def test_humidity_fan_config_schema_valid(self):
        """Test humidity fan config schema with valid data."""
        fan_config = {
            "enabled": True,
            "automation_enabled": False,
            "default_min_humidity": 40.0,
            "default_max_humidity": 60.0,
            "indoor_sensor_entity": "sensor.indoor_humidity",
            "outdoor_sensor_entity": "sensor.outdoor_humidity",
        }

        result = HUMIDITY_FAN_CONFIG_SCHEMA(fan_config)
        assert result["enabled"] is True
        assert result["default_min_humidity"] == 40.0

    def test_humidity_fan_config_schema_defaults(self):
        """Test humidity fan config schema with defaults."""
        fan_config = {}

        result = HUMIDITY_FAN_CONFIG_SCHEMA(fan_config)
        assert result["enabled"] is True
        assert result["default_min_humidity"] == 40.0
        assert result["default_max_humidity"] == 60.0

    def test_humidity_control_validator_valid(self):
        """Test humidity control validator with valid configuration."""
        section = {
            "FANs": {
                "32:153289": {
                    "default_min_humidity": 40.0,
                    "default_max_humidity": 60.0,
                }
            }
        }

        errors = humidity_control_validator(section)
        assert errors == []

    def test_humidity_control_validator_invalid_range(self):
        """Test humidity control validator with invalid min/max range."""
        section = {
            "FANs": {
                "32:153289": {
                    "default_min_humidity": 70.0,
                    "default_max_humidity": 60.0,
                }
            }
        }

        errors = humidity_control_validator(section)
        assert len(errors) == 1
        assert "min (70.0) must be less than max (60.0)" in errors[0]

    def test_humidity_control_validator_invalid_fan_config(self):
        """Test humidity control validator with invalid fan config."""
        section = {"FANs": {"32:153289": "not_a_dict"}}

        errors = humidity_control_validator(section)
        assert len(errors) == 1
        assert "configuration must be a dictionary" in errors[0]

    def test_export_humidity_control_to_yaml(self):
        """Test humidity control export to YAML."""
        config = {"FANs": {"32:153289": {"enabled": True}}}

        result = export_humidity_control_to_yaml(config)
        assert result == config

    def test_parse_humidity_control_yaml(self):
        """Test humidity control YAML parsing."""
        yaml_data = {"FANs": {"32:153289": {"enabled": True}}}

        result = parse_humidity_control_yaml(yaml_data)
        # Schema adds defaults
        expected = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "automation_enabled": False,
                    "default_min_humidity": 40.0,
                    "default_max_humidity": 60.0,
                    "max_runtime_minutes": 120,
                    "cooldown_period_minutes": 15,
                }
            }
        }
        assert result == expected

    def test_merge_humidity_control_config(self):
        """Test humidity control config merging."""
        existing = {"FANs": {"32:153289": {"enabled": True}}}
        imported = {"FANs": {"32:153289": {"default_min_humidity": 40.0}}}

        result = merge_humidity_control_config(existing, imported)
        # The merge replaces the entire FAN entry
        expected = {"FANs": {"32:153289": {"default_min_humidity": 40.0}}}
        assert result == expected

    def test_load_humidity_validator(self):
        """Test humidity control validator loading."""
        load_humidity_validator()
        # Should not raise any exceptions


class TestDefaultFeatureYAML:
    """Test cases for Default feature YAML validation."""

    def test_default_feature_config_schema_valid(self):
        """Test default feature config schema with valid data."""
        config = {"enabled": True, "entities": {"sensor.test": "test"}}

        result = DEFAULT_FEATURE_CONFIG_SCHEMA(config)
        assert result["enabled"] is True
        assert result["entities"] == {"sensor.test": "test"}

    def test_default_feature_config_schema_defaults(self):
        """Test default feature config schema with defaults."""
        config = {}

        result = DEFAULT_FEATURE_CONFIG_SCHEMA(config)
        assert result["enabled"] is True
        assert result["entities"] == {}

    def test_default_validator_valid(self):
        """Test default validator with valid configuration."""
        section = {"enabled": True, "entities": {}}

        errors = default_validator(section)
        assert errors == []

    def test_default_validator_invalid_type(self):
        """Test default validator with invalid section type."""
        section = "not_a_dict"

        errors = default_validator(section)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_default_validator_invalid_entities(self):
        """Test default validator with invalid entities."""
        section = {"entities": "not_a_dict"}

        errors = default_validator(section)
        assert len(errors) == 1
        assert "entities must be a dictionary" in errors[0]

    def test_export_default_to_yaml(self):
        """Test default feature export to YAML."""
        config = {"enabled": True, "entities": {"sensor.test": "test"}}

        result = export_default_to_yaml(config)
        assert result == config

    def test_export_default_to_yaml_defaults(self):
        """Test default feature export with defaults."""
        config = {}

        result = export_default_to_yaml(config)
        expected = {"enabled": True, "entities": {}}
        assert result == expected

    def test_parse_default_yaml(self):
        """Test default feature YAML parsing."""
        yaml_data = {"enabled": True, "entities": {}}

        result = parse_default_yaml(yaml_data)
        assert result == yaml_data

    def test_merge_default_config(self):
        """Test default feature config merging."""
        existing = {"entities": {"sensor.existing": "existing"}}
        imported = {"entities": {"sensor.imported": "imported"}}

        result = merge_default_config(existing, imported)
        expected = {  # noqa: E501
            "entities": {"sensor.existing": "existing", "sensor.imported": "imported"}
        }
        assert result == expected

    def test_load_default_validator(self):
        """Test default feature validator loading."""
        load_default_validator()
        # Should not raise any exceptions


class TestHelloWorldYAML:
    """Test cases for Hello World YAML validation."""

    def test_hello_world_config_schema_valid(self):
        """Test hello world config schema with valid data."""
        config = {"enabled": True, "greeting": "Hello Test"}

        result = HELLO_WORLD_CONFIG_SCHEMA(config)
        assert result["enabled"] is True
        assert result["greeting"] == "Hello Test"

    def test_hello_world_config_schema_defaults(self):
        """Test hello world config schema with defaults."""
        config = {}

        result = HELLO_WORLD_CONFIG_SCHEMA(config)
        assert result["enabled"] is False
        assert result["greeting"] == "Hello World"

    def test_hello_world_validator_valid(self):
        """Test hello world validator with valid configuration."""
        section = {"enabled": True, "greeting": "Hello Test"}

        errors = hello_world_validator(section)
        assert errors == []

    def test_hello_world_validator_invalid_type(self):
        """Test hello world validator with invalid section type."""
        section = "not_a_dict"

        errors = hello_world_validator(section)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_hello_world_validator_invalid_greeting(self):
        """Test hello world validator with invalid greeting."""
        section = {"greeting": 123}

        errors = hello_world_validator(section)
        assert len(errors) == 1
        assert "greeting must be a string" in errors[0]

    def test_export_hello_world_to_yaml(self):
        """Test hello world export to YAML."""
        config = {"enabled": True, "greeting": "Hello Test"}

        result = export_hello_world_to_yaml(config)
        assert result == config

    def test_export_hello_world_to_yaml_defaults(self):
        """Test hello world export with defaults."""
        config = {}

        result = export_hello_world_to_yaml(config)
        expected = {"enabled": False, "greeting": "Hello World"}
        assert result == expected

    def test_parse_hello_world_yaml(self):
        """Test hello world YAML parsing."""
        yaml_data = {"enabled": True, "greeting": "Hello Test"}

        result = parse_hello_world_yaml(yaml_data)
        assert result == yaml_data

    def test_merge_hello_world_config(self):
        """Test hello world config merging."""
        existing = {"enabled": True}
        imported = {"greeting": "Hello Imported"}

        result = merge_hello_world_config(existing, imported)
        expected = {"enabled": True, "greeting": "Hello Imported"}
        assert result == expected

    def test_load_hello_world_validator(self):
        """Test hello world validator loading."""
        load_hello_world_validator()
        # Should not raise any exceptions


class TestHVACFanCardYAML:
    """Test cases for HVAC Fan Card YAML validation."""

    def test_hvac_fan_card_config_schema_valid(self):
        """Test HVAC fan card config schema with valid data."""
        config = {
            "enabled": True,
            "fan_id": "32:153289",
            "card_config": {"show_humidity": True},
        }

        result = HVAC_FAN_CARD_CONFIG_SCHEMA(config)
        assert result["enabled"] is True
        assert result["fan_id"] == "32:153289"
        assert result["card_config"]["show_humidity"] is True

    def test_hvac_fan_card_config_schema_defaults(self):
        """Test HVAC fan card config schema with defaults."""
        config = {}

        result = HVAC_FAN_CARD_CONFIG_SCHEMA(config)
        assert result["enabled"] is False
        assert result["card_config"] == {}

    def test_hvac_fan_card_validator_valid(self):
        """Test HVAC fan card validator with valid configuration."""
        section = {
            "enabled": True,
            "fan_id": "32:153289",
            "card_config": {"show_humidity": True},
        }

        errors = hvac_fan_card_validator(section)
        assert errors == []

    def test_hvac_fan_card_validator_invalid_type(self):
        """Test HVAC fan card validator with invalid section type."""
        section = "not_a_dict"

        errors = hvac_fan_card_validator(section)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_hvac_fan_card_validator_invalid_card_config(self):
        """Test HVAC fan card validator with invalid card_config."""
        section = {"card_config": "not_a_dict"}

        errors = hvac_fan_card_validator(section)
        assert len(errors) == 1
        assert "card_config must be a dictionary" in errors[0]

    def test_export_hvac_fan_card_to_yaml(self):
        """Test HVAC fan card export to YAML."""
        config = {
            "enabled": True,
            "fan_id": "32:153289",
            "card_config": {"show_humidity": True},
        }

        result = export_hvac_fan_card_to_yaml(config)
        assert result == config

    def test_export_hvac_fan_card_to_yaml_defaults(self):
        """Test HVAC fan card export with defaults."""
        config = {}

        result = export_hvac_fan_card_to_yaml(config)
        expected = {"enabled": False, "fan_id": None, "card_config": {}}
        assert result == expected

    def test_parse_hvac_fan_card_yaml(self):
        """Test HVAC fan card YAML parsing."""
        yaml_data = {
            "enabled": True,
            "fan_id": "32:153289",
            "card_config": {"show_humidity": True},
        }

        result = parse_hvac_fan_card_yaml(yaml_data)
        assert result == yaml_data

    def test_merge_hvac_fan_card_config(self):
        """Test HVAC fan card config merging."""
        existing = {
            "enabled": True,
            "card_config": {"show_humidity": True},
        }
        imported = {
            "fan_id": "32:153289",
            "card_config": {"show_co2": True},
        }

        result = merge_hvac_fan_card_config(existing, imported)
        expected = {
            "enabled": True,
            "fan_id": "32:153289",
            "card_config": {"show_humidity": True, "show_co2": True},
        }
        assert result == expected

    def test_load_hvac_fan_card_validator(self):
        """Test HVAC fan card validator loading."""
        load_hvac_fan_card_validator()
        # Should not raise any exceptions


class TestRamsesDebuggerYAML:
    """Test cases for Ramses Debugger YAML validation."""

    def test_ramses_debugger_config_schema_valid(self):
        """Test ramses debugger config schema with valid data."""
        config = {
            "enabled": True,
            "debug_level": "debug",
            "log_packets": True,
        }

        result = RAMSES_DEBUGGER_CONFIG_SCHEMA(config)
        assert result["enabled"] is True
        assert result["debug_level"] == "debug"
        assert result["log_packets"] is True

    def test_ramses_debugger_config_schema_defaults(self):
        """Test ramses debugger config schema with defaults."""
        config = {}

        result = RAMSES_DEBUGGER_CONFIG_SCHEMA(config)
        assert result["enabled"] is False
        assert result["debug_level"] == "info"
        assert result["log_packets"] is False

    def test_ramses_debugger_config_schema_invalid_debug_level(self):
        """Test ramses debugger config schema with invalid debug level."""
        config = {"debug_level": "invalid"}

        with pytest.raises(vol.Invalid):  # vol.Invalid
            RAMSES_DEBUGGER_CONFIG_SCHEMA(config)

    def test_ramses_debugger_validator_valid(self):
        """Test ramses debugger validator with valid configuration."""
        section = {
            "enabled": True,
            "debug_level": "debug",
            "log_packets": True,
        }

        errors = ramses_debugger_validator(section)
        assert errors == []

    def test_ramses_debugger_validator_invalid_type(self):
        """Test ramses debugger validator with invalid section type."""
        section = "not_a_dict"

        errors = ramses_debugger_validator(section)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_ramses_debugger_validator_invalid_debug_level(self):
        """Test ramses debugger validator with invalid debug level."""
        section = {"debug_level": "invalid"}

        errors = ramses_debugger_validator(section)
        assert len(errors) == 1
        assert "debug_level must be one of: debug, info, warning, error" in errors[0]

    def test_export_ramses_debugger_to_yaml(self):
        """Test ramses debugger export to YAML."""
        config = {
            "enabled": True,
            "debug_level": "debug",
            "log_packets": True,
        }

        result = export_ramses_debugger_to_yaml(config)
        assert result == config

    def test_export_ramses_debugger_to_yaml_defaults(self):
        """Test ramses debugger export with defaults."""
        config = {}

        result = export_ramses_debugger_to_yaml(config)
        expected = {"enabled": False, "debug_level": "info", "log_packets": False}
        assert result == expected

    def test_parse_ramses_debugger_yaml(self):
        """Test ramses debugger YAML parsing."""
        yaml_data = {
            "enabled": True,
            "debug_level": "debug",
            "log_packets": True,
        }

        result = parse_ramses_debugger_yaml(yaml_data)
        assert result == yaml_data

    def test_merge_ramses_debugger_config(self):
        """Test ramses debugger config merging."""
        existing = {"enabled": True}
        imported = {"debug_level": "debug", "log_packets": True}

        result = merge_ramses_debugger_config(existing, imported)
        expected = {"enabled": True, "debug_level": "debug", "log_packets": True}
        assert result == expected

    def test_load_ramses_debugger_validator(self):
        """Test ramses debugger validator loading."""
        load_ramses_debugger_validator()
        # Should not raise any exceptions


class TestSensorControlYAML:
    """Test cases for Sensor Control YAML validation."""

    def test_area_sensor_schema_valid(self):
        """Test area sensor schema with valid data."""
        sensor_data = {
            "source_id": "bathroom",
            "area_id": "Bathroom",
            "zone_id": "bathroom",
            "enabled": True,
            "temperature_entity": "sensor.bathroom_temp",
            "humidity_entity": "sensor.bathroom_humidity",
            "co2_entity": "sensor.bathroom_co2",
            "co2_threshold": 1000,
        }

        result = AREA_SENSOR_SCHEMA(sensor_data)
        assert result["source_id"] == "bathroom"
        assert result["area_id"] == "Bathroom"
        assert result["zone_id"] == "bathroom"
        assert result["co2_threshold"] == 1000

    def test_area_sensor_schema_defaults(self):
        """Test area sensor schema with default values."""
        sensor_data = {"source_id": "bathroom"}

        result = AREA_SENSOR_SCHEMA(sensor_data)
        assert result["source_id"] == "bathroom"
        assert result["enabled"] is True
        assert result["area_co2_enabled"] is False

    def test_abs_humidity_input_schema_valid(self):
        """Test absolute humidity input schema with valid data."""
        input_data = {
            "entity_id": "sensor.outdoor_humidity",
            "temperature": {
                "kind": "external",
                "entity_id": "sensor.outdoor_temp",
            },
            "humidity": "sensor.outdoor_humidity",
            "indoor": False,
        }

        result = ABS_HUMIDITY_INPUT_SCHEMA(input_data)
        assert result["entity_id"] == "sensor.outdoor_humidity"
        assert result["indoor"] is False

    def test_source_schema_valid(self):
        """Test source schema with valid data."""
        source_data = {
            "kind": "external",
            "metric": "temperature",
            "entity_id": "sensor.outdoor_temp",
        }

        result = SOURCE_SCHEMA(source_data)
        assert result["kind"] == "external"
        assert result["entity_id"] == "sensor.outdoor_temp"

    def test_source_schema_invalid_kind(self):
        """Test source schema with invalid kind."""
        source_data = {"kind": "invalid"}

        with pytest.raises(vol.Invalid):  # vol.Invalid
            SOURCE_SCHEMA(source_data)

    def test_fan_config_schema_valid(self):
        """Test fan config schema with valid data."""
        fan_config = {
            "sources": {
                "indoor_temperature": {
                    "kind": "internal",
                    "metric": "temperature",
                }
            },
            "area_sensors": [
                {
                    "source_id": "bathroom",
                    "temperature_entity": "sensor.bathroom_temp",
                    "humidity_entity": "sensor.bathroom_humidity",
                }
            ],
            "abs_humidity_inputs": {
                "outdoor": {
                    "entity_id": "sensor.outdoor_humidity",
                }
            },
        }

        result = FAN_CONFIG_SCHEMA(fan_config)
        assert "sources" in result
        assert len(result["area_sensors"]) == 1
        assert "outdoor" in result["abs_humidity_inputs"]

    def test_sensor_control_validator_valid(self):
        """Test sensor control validator with valid configuration."""
        section = {
            "FANs": {
                "32:153289": {
                    "sources": [
                        {
                            "kind": "internal",
                            "metric": "temperature",
                        }
                    ],
                    "area_sensors": {
                        "bathroom": {
                            "source_id": "bathroom",
                            "temperature_entity": "sensor.bathroom_temp",
                        }
                    },
                    "abs_humidity_inputs": {
                        "outdoor": {
                            "entity_id": "sensor.outdoor_humidity",
                        }
                    },
                }
            }
        }

        errors = sensor_control_validator(section)
        assert errors == []

    def test_sensor_control_validator_invalid_fan_config(self):
        """Test sensor control validator with invalid fan config."""
        section = {"FANs": {"32:153289": "not_a_dict"}}

        errors = sensor_control_validator(section)
        assert len(errors) == 1
        assert "configuration must be a dictionary" in errors[0]

    def test_sensor_control_validator_invalid_area_sensors(self):
        """Test sensor control validator with invalid area_sensors."""
        section = {"FANs": {"32:153289": {"area_sensors": "not_a_dict"}}}

        errors = sensor_control_validator(section)
        assert len(errors) == 1
        assert "area_sensors must be a dictionary" in errors[0]

    def test_sensor_control_validator_invalid_sources(self):
        """Test sensor control validator with invalid sources."""
        section = {"FANs": {"32:153289": {"sources": "not_a_list"}}}

        errors = sensor_control_validator(section)
        assert len(errors) == 1
        assert "sources must be a list" in errors[0]

    def test_export_sensor_control_to_yaml(self):
        """Test sensor control export to YAML."""
        config = {
            "FANs": {
                "32:153289": {
                    "sources": {
                        "indoor_temperature": {
                            "kind": "internal",
                            "metric": "temperature",
                        }
                    }
                }
            }
        }

        result = export_sensor_control_to_yaml(config)
        assert result == config

    def test_parse_sensor_control_yaml(self):
        """Test sensor control YAML parsing."""
        yaml_data = {
            "FANs": {
                "32:153289": {
                    "sources": {
                        "indoor_temperature": {
                            "kind": "internal",
                            "metric": "temperature",
                        }
                    }
                }
            }
        }

        result = parse_sensor_control_yaml(yaml_data)
        assert result == yaml_data

    def test_merge_sensor_control_config(self):
        """Test sensor control config merging."""
        existing = {"FANs": {"32:153289": {"sources": []}}}
        imported = {"FANs": {"32:153289": {"area_sensors": {}}}}

        result = merge_sensor_control_config(existing, imported)
        # The merge replaces the entire FAN entry
        expected = {"FANs": {"32:153289": {"area_sensors": {}}}}
        assert result == expected

    def test_load_sensor_control_validator(self):
        """Test sensor control validator loading."""
        load_sensor_control_validator()
        # Should not raise any exceptions


class TestZonesYAML:
    """Test cases for Zones YAML validation."""

    def test_zone_entry_schema_valid(self):
        """Test zone entry schema with valid data."""
        zone_data = {
            "zone_id": "bathroom",
            "type": "custom_valve",
            "enabled": True,
            "open_entity": "button.bathroom_valve_open",
            "close_entity": "button.bathroom_valve_close",
            "position_entity": "sensor.bathroom_valve_position",
            "min_position": 15,
            "max_position": 90,
        }

        result = ZONE_ENTRY_SCHEMA(zone_data)
        assert result["zone_id"] == "bathroom"
        assert result["type"] == "custom_valve"
        assert result["min_position"] == 15
        assert result["max_position"] == 90

    def test_zone_entry_schema_orcon_native(self):
        """Test zone entry schema for ORCON native zone."""
        zone_data = {
            "zone_id": "living_room",
            "type": "orcon_native",
            "native_zone_id": "zone_1",
        }

        result = ZONE_ENTRY_SCHEMA(zone_data)
        assert result["zone_id"] == "living_room"
        assert result["type"] == "orcon_native"
        assert result["native_zone_id"] == "zone_1"

    def test_zone_entry_schema_invalid_type(self):
        """Test zone entry schema with invalid type."""
        zone_data = {"zone_id": "test", "type": "invalid_type"}

        with pytest.raises(vol.Invalid):  # vol.Invalid
            ZONE_ENTRY_SCHEMA(zone_data)

    def test_zone_entry_schema_invalid_position_range(self):  # noqa: E501
        """Test zone entry schema with invalid position range.

        Schema only validates individual ranges.
        """
        zone_data = {
            "zone_id": "test",
            "type": "custom_valve",
            "min_position": 150,  # Invalid - > 100
            "max_position": 15,
        }

        with pytest.raises(vol.Invalid):  # vol.Invalid for min_position > 100
            ZONE_ENTRY_SCHEMA(zone_data)

    def test_zones_config_schema_valid(self):
        """Test zones config schema with valid data."""
        config = {
            "version": 1,
            "FANs": {
                "32:153289": [
                    {
                        "zone_id": "bathroom",
                        "type": "custom_valve",
                    }
                ]
            },
        }

        result = ZONES_CONFIG_SCHEMA(config)
        assert result["version"] == 1
        assert len(result["FANs"]["32:153289"]) == 1

    def test_zones_config_schema_defaults(self):
        """Test zones config schema with default values."""
        config = {
            "FANs": {
                "32:153289": [
                    {
                        "zone_id": "bathroom",
                        "type": "custom_valve",
                    }
                ]
            }
        }

        result = ZONES_CONFIG_SCHEMA(config)
        assert result["version"] == 1

    def test_zones_validator_valid(self):
        """Test zones validator with valid configuration."""
        section = {
            "FANs": {
                "32:153289": [
                    {
                        "zone_id": "bathroom",
                        "type": "custom_valve",
                        "min_position": 15,
                        "max_position": 90,
                    }
                ]
            }
        }

        errors = zones_validator(section)
        assert errors == []

    def test_zones_validator_invalid_fans_structure(self):
        """Test zones validator with invalid FANs structure."""
        section = {"FANs": "not_a_dict"}

        errors = zones_validator(section)
        assert len(errors) == 1
        assert "FANs must be a dictionary" in errors[0]

    def test_zones_validator_invalid_zones_list(self):
        """Test zones validator with invalid zones list."""
        section = {"FANs": {"32:153289": "not_a_list"}}

        errors = zones_validator(section)
        assert len(errors) == 1
        assert "zones must be a list" in errors[0]

    def test_zones_validator_missing_zone_id(self):
        """Test zones validator with missing zone_id."""
        section = {
            "FANs": {
                "32:153289": [
                    {"type": "custom_valve"}  # Missing zone_id
                ]
            }
        }

        errors = zones_validator(section)
        assert len(errors) == 1
        assert "missing zone_id" in errors[0]

    def test_zones_validator_invalid_zone_type(self):
        """Test zones validator with invalid zone type."""
        section = {
            "FANs": {
                "32:153289": [
                    {
                        "zone_id": "test",
                        "type": "invalid_type",
                    }
                ]
            }
        }

        errors = zones_validator(section)
        assert len(errors) == 1
        assert "invalid type 'invalid_type'" in errors[0]

    def test_zones_validator_invalid_position_range(self):
        """Test zones validator with invalid position range."""
        section = {
            "FANs": {
                "32:153289": [
                    {
                        "zone_id": "test",
                        "type": "custom_valve",
                        "min_position": 90,
                        "max_position": 15,
                    }
                ]
            }
        }

        errors = zones_validator(section)
        assert len(errors) == 1
        assert "min_position (90) > max_position (15)" in errors[0]

    def test_export_zones_to_yaml(self):
        """Test zones export to YAML."""
        zones = [
            {
                "zone_id": "bathroom",
                "type": "custom_valve",
                "min_position": 15,
                "max_position": 90,
            }
        ]

        result = export_zones_to_yaml(zones, "32:153289")
        assert "version: 1" in result
        assert "fan_id: 32:153289" in result
        assert "zone_id: bathroom" in result

    def test_parse_zones_yaml_valid(self):
        """Test zones YAML parsing with valid content."""
        yaml_content = """
version: 1
FANs:
  32:153289:
    - zone_id: bathroom
      type: custom_valve
      min_position: 15
      max_position: 90
"""

        result = parse_zones_yaml(yaml_content)
        assert result["version"] == 1
        assert len(result["FANs"]["32:153289"]) == 1

    def test_parse_zones_yaml_invalid_syntax(self):
        """Test zones YAML parsing with invalid syntax."""
        yaml_content = "invalid: yaml: content: ["

        with pytest.raises(ValueError, match="Invalid YAML syntax"):
            parse_zones_yaml(yaml_content)

    def test_parse_zones_yaml_invalid_schema(self):
        """Test zones YAML parsing with invalid schema."""
        yaml_content = """
version: 1
FANs:
  32:153289:
    - zone_id: test
      type: invalid_type
"""

        with pytest.raises(ValueError, match="Schema validation failed"):
            parse_zones_yaml(yaml_content)

    def test_merge_zones_config(self):
        """Test zones config merging."""
        existing_zones = [
            {"zone_id": "bathroom", "type": "custom_valve", "fan_id": "32:153289"}
        ]
        imported_zones = [{"zone_id": "office", "type": "shelly_2pm_gen3"}]

        result = merge_zones_config(existing_zones, imported_zones, "32:153289")
        assert len(result) == 2

        # Check that new zone has fan_id set
        office_zone = next(z for z in result if z["zone_id"] == "office")
        assert office_zone["fan_id"] == "32:153289"

    def test_merge_zones_config_overwrite(self):
        """Test zones config merging with overwrite."""
        existing_zones = [
            {"zone_id": "bathroom", "type": "custom_valve", "fan_id": "32:153289"}
        ]
        imported_zones = [{"zone_id": "bathroom", "type": "shelly_2pm_gen3"}]

        # Without overwrite
        result = merge_zones_config(existing_zones, imported_zones, "32:153289")
        assert len(result) == 1
        assert result[0]["type"] == "custom_valve"

        # With overwrite
        result = merge_zones_config(
            existing_zones, imported_zones, "32:153289", overwrite_existing=True
        )
        assert len(result) == 1
        assert result[0]["type"] == "shelly_2pm_gen3"

    def test_validate_zone_references_no_hass(self):
        """Test zone entity validation without hass instance."""
        zones = [
            {
                "zone_id": "bathroom",
                "type": "custom_valve",
                "open_entity": "button.bathroom_valve_open",
            }
        ]

        errors = validate_zone_references(zones, None)
        assert errors == []  # Should skip validation without hass

    def test_validate_zone_references_with_hass(self):
        """Test zone entity validation with hass instance."""
        hass = MagicMock()
        hass.states.get.return_value = None  # Entity not found

        zones = [
            {
                "zone_id": "bathroom",
                "type": "custom_valve",
                "open_entity": "button.bathroom_valve_open",
            }
        ]

        errors = validate_zone_references(zones, hass)
        assert len(errors) == 1
        assert "open_entity 'button.bathroom_valve_open' not found" in errors[0]

    def test_validate_zone_references_orcon_native(self):
        """Test zone entity validation for ORCON native (no entities to validate)."""
        hass = MagicMock()

        zones = [
            {
                "zone_id": "living_room",
                "type": "orcon_native",
            }
        ]

        errors = validate_zone_references(zones, hass)
        assert errors == []

    def test_load_zones_validator(self):
        """Test zones validator loading."""
        load_zones_validator()
        # Should not raise any exceptions


class TestRemoteBindingYAML:
    """Test cases for Remote Binding YAML validation."""

    def test_rem_entry_schema_valid(self):
        """Test valid REM entry schema."""
        # Valid REM entry
        rem_data = {
            "rem_id": "37:123456",
            "role": "primary",
            "enabled": True,
            "source": "manual",
            "zone_id": "bathroom",
            "area_id": "bathroom",
        }

        # Should not raise any exceptions
        validated = REM_ENTRY_SCHEMA(rem_data)
        assert validated["rem_id"] == "37:123456"
        assert validated["role"] == "primary"
        assert validated["enabled"] is True
        assert validated["zone_id"] == "bathroom"
        assert validated["area_id"] == "bathroom"

    def test_rem_entry_schema_minimal(self):
        """Test REM entry schema with minimal required fields."""
        rem_data = {
            "rem_id": "37:123456",
            "role": "secondary",
        }

        validated = REM_ENTRY_SCHEMA(rem_data)
        assert validated["rem_id"] == "37:123456"
        assert validated["role"] == "secondary"
        assert validated["enabled"] is True  # Default value

    def test_rem_entry_schema_invalid_role(self):
        """Test REM entry schema with invalid role."""
        rem_data = {
            "rem_id": "37:123456",
            "role": "invalid_role",
        }

        with pytest.raises(vol.MultipleInvalid):
            REM_ENTRY_SCHEMA(rem_data)

    def test_rem_entry_schema_missing_required(self):
        """Test REM entry schema missing required fields."""
        rem_data = {
            "enabled": True,
        }

        with pytest.raises(vol.MultipleInvalid):
            REM_ENTRY_SCHEMA(rem_data)

    def test_rem_entry_schema_extra_fields(self):
        """Test REM entry schema rejects extra fields."""
        rem_data = {
            "rem_id": "37:123456",
            "role": "primary",
            "extra_field": "not_allowed",
        }

        with pytest.raises(vol.MultipleInvalid):
            REM_ENTRY_SCHEMA(rem_data)

    def test_fan_rem_config_schema_valid(self):
        """Test valid FAN REM config schema."""
        fan_config = {
            "REMs": [
                {
                    "rem_id": "37:123456",
                    "role": "primary",
                },
                {
                    "rem_id": "37:789012",
                    "role": "secondary",
                },
            ]
        }

        validated = FAN_REM_CONFIG_SCHEMA(fan_config)
        assert len(validated["REMs"]) == 2

    def test_fan_rem_config_schema_empty_rems(self):
        """Test FAN REM config with empty REMs list."""
        fan_config = {
            "REMs": [],
        }

        validated = FAN_REM_CONFIG_SCHEMA(fan_config)
        assert validated["REMs"] == []

    def test_remote_binding_config_schema_valid(self):
        """Test valid remote binding config schema."""
        config = {
            "version": 1,
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "primary",
                        }
                    ]
                },
                "32:789012": {
                    "REMs": [
                        {
                            "rem_id": "37:789012",
                            "role": "secondary",
                        }
                    ]
                },
            },
        }

        validated = REMOTE_BINDING_CONFIG_SCHEMA(config)
        assert validated["version"] == 1
        assert len(validated["FANs"]) == 2

    def test_remote_binding_config_schema_defaults(self):
        """Test remote binding config schema with defaults."""
        config = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "primary",
                        }
                    ]
                }
            },
        }

        validated = REMOTE_BINDING_CONFIG_SCHEMA(config)
        assert validated["version"] == 1  # Default value

    def test_remote_binding_validator_valid(self):
        """Test remote binding validator with valid config."""
        section = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "primary",
                        },
                        {
                            "rem_id": "37:789012",
                            "role": "secondary",
                        },
                    ]
                },
                "32:111111": {
                    "REMs": [
                        {
                            "rem_id": "37:111111",
                            "role": "boost_only",
                        }
                    ]
                },
            },
        }

        errors = remote_binding_validator(section)
        assert errors == []

    def test_remote_binding_validator_duplicate_rem(self):
        """Test remote binding validator detects duplicate REMs."""
        section = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "primary",
                        }
                    ]
                },
                "32:789012": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",  # Same REM ID
                            "role": "secondary",
                        }
                    ]
                },
            },
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "REM '37:123456' assigned to multiple FANs" in errors[0]

    def test_remote_binding_validator_invalid_structure(self):
        """Test remote binding validator with invalid structure."""
        section = "not_a_dict"

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_remote_binding_validator_invalid_fans_structure(self):
        """Test remote binding validator with invalid FANs structure."""
        section = {
            "FANs": "not_a_dict",
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "FANs must be a dictionary" in errors[0]

    def test_remote_binding_validator_invalid_fan_config(self):
        """Test remote binding validator with invalid FAN config."""
        section = {
            "FANs": {
                "32:123456": "not_a_dict",
            },
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "FAN '32:123456': configuration must be a dictionary" in errors[0]

    def test_remote_binding_validator_invalid_rems_structure(self):
        """Test remote binding validator with invalid REMs structure."""
        section = {
            "FANs": {
                "32:123456": {
                    "REMs": "not_a_list",
                },
            },
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "FAN '32:123456': REMs must be a list" in errors[0]

    def test_remote_binding_validator_missing_rem_id(self):
        """Test remote binding validator with missing rem_id."""
        section = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "role": "primary",
                        }
                    ],
                },
            },
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "FAN '32:123456': REM missing rem_id" in errors[0]

    def test_remote_binding_validator_invalid_rem_role(self):
        """Test remote binding validator with invalid REM role."""
        section = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "invalid_role",
                        }
                    ],
                },
            },
        }

        errors = remote_binding_validator(section)
        assert len(errors) == 1
        assert "invalid role 'invalid_role'" in errors[0]

    def test_export_remote_binding_to_yaml(self):
        """Test export remote binding to YAML."""
        bindings = {
            "32:123456": {
                "REMs": [
                    {
                        "rem_id": "37:123456",
                        "role": "primary",
                        "enabled": True,
                    }
                ]
            },
            "32:789012": {
                "REMs": [
                    {
                        "rem_id": "37:789012",
                        "role": "secondary",
                        "enabled": False,
                    }
                ]
            },
        }

        yaml_str = export_remote_binding_to_yaml(bindings)

        assert "version: 1" in yaml_str
        assert "FANs:" in yaml_str
        assert "32:123456:" in yaml_str
        assert "37:123456" in yaml_str
        assert "role: primary" in yaml_str

    def test_parse_remote_binding_yaml_valid(self):
        """Test parse valid remote binding YAML."""
        yaml_content = """
version: 1
FANs:
  32:123456:
    REMs:
      - rem_id: 37:123456
        role: primary
        enabled: true
      - rem_id: 37:789012
        role: secondary
"""

        parsed = parse_remote_binding_yaml(yaml_content)

        assert parsed["version"] == 1
        assert "32:123456" in parsed["FANs"]
        assert len(parsed["FANs"]["32:123456"]["REMs"]) == 2
        assert parsed["FANs"]["32:123456"]["REMs"][0]["rem_id"] == "37:123456"

    def test_parse_remote_binding_yaml_invalid_yaml(self):
        """Test parse invalid YAML syntax."""
        yaml_content = """
version: 1
FANs:
  32:123456:
    REMs:
      - rem_id: 37:123456
        role: primary
        enabled: true
      - rem_id: 37:789012  # Missing role
    invalid_yaml: [unclosed
"""

        with pytest.raises(ValueError, match="Invalid YAML syntax"):
            parse_remote_binding_yaml(yaml_content)

    def test_parse_remote_binding_yaml_not_dict(self):
        """Test parse YAML that is not a dictionary."""
        yaml_content = """
- item1
- item2
- item3
"""

        with pytest.raises(ValueError, match="YAML content must be a dictionary"):
            parse_remote_binding_yaml(yaml_content)

    def test_parse_remote_binding_yaml_schema_validation(self):
        """Test parse YAML that fails schema validation."""
        yaml_content = """
version: 1
FANs:
  32:123456:
    REMs:
      - rem_id: 37:123456
        role: invalid_role  # Invalid role
"""

        with pytest.raises(ValueError, match="Schema validation failed"):
            parse_remote_binding_yaml(yaml_content)

    def test_merge_remote_binding_config_new_fans(self):
        """Test merge remote binding config with new FANs."""
        existing = {
            "FANs": {
                "32:111111": {
                    "REMs": [
                        {
                            "rem_id": "37:111111",
                            "role": "primary",
                        }
                    ]
                }
            }
        }

        imported = {
            "FANs": {
                "32:222222": {
                    "REMs": [
                        {
                            "rem_id": "37:222222",
                            "role": "secondary",
                        }
                    ]
                }
            }
        }

        merged = merge_remote_binding_config(existing, imported)

        assert len(merged["FANs"]) == 2
        assert "32:111111" in merged["FANs"]
        assert "32:222222" in merged["FANs"]

    def test_merge_remote_binding_config_existing_fans_no_overwrite(self):
        """Test merge config without overwriting existing FANs."""
        existing = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:111111",
                            "role": "primary",
                        }
                    ]
                }
            }
        }

        imported = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:222222",
                            "role": "secondary",
                        }
                    ]
                }
            }
        }

        merged = merge_remote_binding_config(
            existing, imported, overwrite_existing=False
        )

        # Should keep existing config
        assert len(merged["FANs"]) == 1
        assert merged["FANs"]["32:123456"]["REMs"][0]["rem_id"] == "37:111111"

    def test_merge_remote_binding_config_existing_fans_overwrite(self):
        """Test merge config with overwriting existing FANs."""
        existing = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:111111",
                            "role": "primary",
                        }
                    ]
                }
            }
        }

        imported = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:222222",
                            "role": "secondary",
                        }
                    ]
                }
            }
        }

        merged = merge_remote_binding_config(
            existing, imported, overwrite_existing=True
        )

        # Should have imported config
        assert len(merged["FANs"]) == 1
        assert merged["FANs"]["32:123456"]["REMs"][0]["rem_id"] == "37:222222"

    def test_merge_remote_binding_config_no_existing_fans(self):
        """Test merge config when existing has no FANs."""
        existing = {}

        imported = {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "37:123456",
                            "role": "primary",
                        }
                    ]
                }
            }
        }

        merged = merge_remote_binding_config(existing, imported)

        assert len(merged["FANs"]) == 1
        assert "32:123456" in merged["FANs"]

    def test_load_remote_binding_validator(self):
        """Test load_validator function."""
        # Should not raise any exceptions
        load_remote_binding_validator()


class TestYAMLValidationIntegration:
    """Integration tests for YAML validation modules."""

    def test_co2_control_schema_integration(self):
        """Test CO2 control schema integration with validator."""
        valid_config = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "threshold": 1000,
                    "zones": [{"zone_id": "bathroom", "threshold": 800}],
                }
            }
        }

        # Schema validation (adds defaults)
        schema_result = CO2_CONTROL_CONFIG_SCHEMA(valid_config)
        expected_schema = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "threshold": 1000,
                    "zones": [
                        {
                            "zone_id": "bathroom",
                            "threshold": 800,
                            "activation_hysteresis": 100,
                            "deactivation_hysteresis": -100,
                        }
                    ],
                    "automation_enabled": False,
                    "activation_hysteresis": 100,
                    "cooldown_period_minutes": 15,
                    "priority_over_humidity": True,
                    "deactivation_hysteresis": -100,
                    "max_runtime_minutes": 120,
                }
            }
        }

        # Custom validation
        errors = co2_control_validator(valid_config)

        assert schema_result == expected_schema
        assert errors == []

    def test_humidity_control_schema_integration(self):
        """Test humidity control schema integration with validator."""
        valid_config = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "default_min_humidity": 40.0,
                    "default_max_humidity": 60.0,
                }
            }
        }

        # Schema validation (adds defaults)
        schema_result = HUMIDITY_CONTROL_CONFIG_SCHEMA(valid_config)
        expected_schema = {
            "FANs": {
                "32:153289": {
                    "enabled": True,
                    "default_min_humidity": 40.0,
                    "default_max_humidity": 60.0,
                    "automation_enabled": False,
                    "max_runtime_minutes": 120,
                    "cooldown_period_minutes": 15,
                }
            }
        }

        # Custom validation
        errors = humidity_control_validator(valid_config)

        assert schema_result == expected_schema
        assert errors == []

    def test_all_load_validators(self):
        """Test that all validators can be loaded without errors."""
        load_validator()
        load_humidity_validator()
        load_default_validator()
        load_hello_world_validator()
        load_humidity_validator()
        load_hvac_fan_card_validator()
        load_ramses_debugger_validator()
        load_remote_binding_validator()
        load_sensor_control_validator()
        load_zones_validator()

        # If we reach here, all validators loaded successfully
        assert True

    def test_validator_with_hass_mock(self):
        """Test validators with Home Assistant instance."""
        hass = MagicMock()

        # Test with hass instance (should not affect validation)
        section = {"enabled": True}

        errors = hello_world_validator(section, hass)
        assert errors == []

    def test_empty_config_handling(self):
        """Test validators handle empty configurations gracefully."""
        # CO2 Control
        errors = co2_control_validator({})
        assert errors == []

        # Humidity Control
        errors = humidity_control_validator({})
        assert errors == []

        # Default
        errors = default_validator({})
        assert errors == []

        # Hello World
        errors = hello_world_validator({})
        assert errors == []
