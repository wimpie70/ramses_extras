"""Tests for YAML configuration import functionality.

Tests the full configuration import system including:
- YAML parsing and validation
- Feature-level validation (zones, remote_binding, sensor_control)
- Framework-level validation
- Error handling and edge cases
"""

from __future__ import annotations

from typing import Any

import pytest
import voluptuous as vol

from custom_components.ramses_extras.framework.helpers.config.import_full import (
    RAMSES_EXTRAS_CONFIG_SCHEMA,
    parse_full_config_yaml,
    validate_full_config_import,
    validate_full_config_import_detailed,
)
from custom_components.ramses_extras.framework.helpers.config.import_validation import (
    format_validation_errors,
    get_registered_validators,
    register_config_validator,
    unregister_config_validator,
    validate_import_config,
)
from custom_components.ramses_extras.framework.helpers.config.model import (
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
)

# =============================================================================
# YAML Parsing Tests
# =============================================================================


def test_parse_full_config_yaml_valid_minimal() -> None:
    """Test parsing minimal valid YAML config."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
"""
    result = parse_full_config_yaml(yaml_content)
    assert "ramses_extras" in result
    assert result["ramses_extras"]["schema_version"] == 1
    assert "features" in result["ramses_extras"]


def test_parse_full_config_yaml_multiple_features() -> None:
    """Test parsing YAML with multiple features."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: primary
    sensor_control:
      devices:
        "32:153289":
          sources:
            indoor_temperature:
              kind: internal
"""
    result = parse_full_config_yaml(yaml_content)
    features = result["ramses_extras"]["features"]
    assert FEATURE_ZONES in features
    assert FEATURE_REMOTE_BINDING in features
    assert FEATURE_SENSOR_CONTROL in features


def test_parse_full_config_yaml_invalid_syntax() -> None:
    """Test parsing YAML with syntax errors."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        invalid: yaml: here:
"""
    with pytest.raises(ValueError, match="Invalid YAML"):
        parse_full_config_yaml(yaml_content)


def test_parse_full_config_yaml_not_dict() -> None:
    """Test parsing YAML that is not a dictionary."""
    yaml_content = "- just\n- a\n- list"
    with pytest.raises(ValueError, match="dictionary"):
        parse_full_config_yaml(yaml_content)


def test_parse_full_config_yaml_missing_root() -> None:
    """Test parsing YAML missing ramses_extras root."""
    yaml_content = """
other_key:
  something: value
"""
    with pytest.raises(ValueError, match="Schema validation"):
        parse_full_config_yaml(yaml_content)


# =============================================================================
# Schema Validation Tests
# =============================================================================


def test_schema_validation_valid_zone_types() -> None:
    """Test schema accepts all valid zone types."""
    for zone_type in ["orcon_native", "custom_valve", "shelly_2pm_gen3"]:
        config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    FEATURE_ZONES: {
                        "FANs": {"32:153289": [{"zone_id": "test", "type": zone_type}]}
                    }
                },
            }
        }
        result = RAMSES_EXTRAS_CONFIG_SCHEMA(config)
        assert result is not None


def test_schema_validation_invalid_zone_type() -> None:
    """Test schema rejects invalid zone types."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_ZONES: {
                    "FANs": {"32:153289": [{"zone_id": "test", "type": "invalid_type"}]}
                }
            },
        }
    }
    with pytest.raises(vol.MultipleInvalid):
        RAMSES_EXTRAS_CONFIG_SCHEMA(config)


def test_schema_validation_remote_binding_roles() -> None:
    """Test schema accepts all valid REM roles."""
    for role in ["primary", "secondary", "boost_only"]:
        config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    FEATURE_REMOTE_BINDING: {
                        "FANs": {
                            "32:153289": {
                                "REMs": [{"rem_id": "37:169161", "role": role}]
                            }
                        }
                    }
                },
            }
        }
        result = RAMSES_EXTRAS_CONFIG_SCHEMA(config)
        assert result is not None


def test_schema_validation_invalid_schema_version() -> None:
    """Test schema rejects unsupported schema versions."""
    config = {
        "ramses_extras": {
            "schema_version": 99,
            "features": {},
        }
    }
    with pytest.raises(vol.MultipleInvalid):
        RAMSES_EXTRAS_CONFIG_SCHEMA(config)


# =============================================================================
# Zones Feature Validation Tests
# =============================================================================


def test_validate_zones_valid() -> None:
    """Test zones validation with valid config."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
          - zone_id: bedroom
            type: custom_valve
            min_position: 10
            max_position: 90
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) == 0


def test_validate_zones_invalid_position_range() -> None:
    """Test zones validation catches invalid position ranges."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: custom_valve
            min_position: 150
            max_position: 200
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("positions must be between 0-100" in e for e in errors)


def test_validate_zones_min_greater_than_max() -> None:
    """Test zones validation catches min > max position."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: custom_valve
            min_position: 80
            max_position: 20
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("min_position" in e and "max_position" in e for e in errors)


def test_validate_zones_invalid_type() -> None:
    """Test zones validation catches invalid zone types."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: not_a_valid_type
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("invalid type" in e.lower() for e in errors)


def test_validate_zones_missing_zone_id() -> None:
    """Test zones validation catches missing zone_id."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - type: orcon_native
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("missing zone_id" in e.lower() for e in errors)


# =============================================================================
# Remote Binding Feature Validation Tests
# =============================================================================


def test_validate_remote_binding_valid() -> None:
    """Test remote_binding validation with valid config."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: primary
            - rem_id: "37:169162"
              role: secondary
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) == 0


def test_validate_remote_binding_duplicate_rem() -> None:
    """Test remote_binding validation catches duplicate REM assignments."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: primary
        "32:153290":
          REMs:
            - rem_id: "37:169161"
              role: primary
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("REM '37:169161' assigned to multiple FANs" in e for e in errors)


def test_validate_remote_binding_invalid_role() -> None:
    """Test remote_binding validation catches invalid REM roles."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: invalid_role
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("invalid role" in e.lower() for e in errors)


def test_validate_remote_binding_missing_rem_id() -> None:
    """Test remote_binding validation catches missing rem_id."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - role: primary
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("REM missing rem_id" in e for e in errors)


# =============================================================================
# Sensor Control Feature Validation Tests
# =============================================================================


def test_validate_sensor_control_valid() -> None:
    """Test sensor_control validation with valid config."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    sensor_control:
      abs_humidity_inputs:
        input1:
          temperature:
            kind: internal
          humidity:
            kind: external
            entity_id: sensor.humidity
      area_sensors:
        "32:153289":
          - source_id: bathroom_sensor
            temperature_entity: sensor.bathroom_temp
            humidity_entity: sensor.bathroom_hum
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) == 0


def test_validate_sensor_control_invalid_humidity_kind() -> None:
    """Test sensor_control validation catches invalid kind values."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    sensor_control:
      abs_humidity_inputs:
        input1:
          temperature:
            kind: invalid_kind
          humidity:
            kind: internal
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("invalid kind" in e.lower() for e in errors)


def test_validate_sensor_control_missing_source_id() -> None:
    """Test sensor_control validation catches missing source_id."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    sensor_control:
      area_sensors:
        "32:153289":
          - temperature_entity: sensor.temp
"""
    config = parse_full_config_yaml(yaml_content)
    errors = validate_full_config_import(config)
    assert len(errors) > 0
    assert any("missing source_id" in e.lower() for e in errors)


# =============================================================================
# Framework-Level Validation Tests
# =============================================================================


def test_validate_framework_invalid_root() -> None:
    """Test framework validation catches missing root key."""
    config: dict[str, Any] = {}
    result = validate_import_config(config)
    assert not result["valid"]
    assert len(result["framework_errors"]) > 0


def test_validate_framework_invalid_features_type() -> None:
    """Test framework validation catches invalid features type."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": "not_a_dict",
        }
    }
    result = validate_import_config(config)
    assert not result["valid"]


def test_validate_framework_unsupported_schema_version() -> None:
    """Test framework validation catches unsupported schema version."""
    config = {
        "ramses_extras": {
            "schema_version": 99,
            "features": {},
        }
    }
    result = validate_import_config(config)
    assert not result["valid"]
    assert any("Unsupported schema version" in e for e in result["framework_errors"])


# =============================================================================
# Detailed Validation Results Tests
# =============================================================================


def test_validate_detailed_structure() -> None:
    """Test detailed validation returns expected structure."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
"""
    config = parse_full_config_yaml(yaml_content)
    result = validate_full_config_import_detailed(config)
    assert "valid" in result
    assert "framework_errors" in result
    assert "feature_errors" in result
    assert "total_errors" in result
    assert result["valid"] is True
    assert result["total_errors"] == 0


def test_validate_detailed_with_errors() -> None:
    """Test detailed validation with feature errors."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: invalid_type
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: invalid_role
"""
    # Note: Schema validation will fail, so we test at framework level
    with pytest.raises(ValueError, match="Schema validation"):
        parse_full_config_yaml(yaml_content)


def test_format_validation_errors() -> None:
    """Test error formatting function."""
    result = {
        "valid": False,
        "framework_errors": ["Error 1", "Error 2"],
        "feature_errors": {
            "zones": ["Zone error"],
            "remote_binding": ["Binding error"],
        },
        "total_errors": 4,
    }
    formatted = format_validation_errors(result)
    assert len(formatted) == 4
    assert any("[Framework]" in e for e in formatted)
    assert any("[zones]" in e for e in formatted)
    assert any("[remote_binding]" in e for e in formatted)


# =============================================================================
# Validation Registry Tests
# =============================================================================


def test_register_and_unregister_validator() -> None:
    """Test registering and unregistering validators."""
    test_feature = "test_feature"

    def test_validator(section: dict[str, Any], hass: Any) -> list[str]:
        return ["test error"]

    # Register validator
    register_config_validator(test_feature, test_validator)
    assert test_feature in get_registered_validators()

    # Unregister validator
    unregister_config_validator(test_feature)
    assert test_feature not in get_registered_validators()


def test_registered_validators_for_known_features() -> None:
    """Test that known features have registered validators."""
    validators = get_registered_validators()
    assert FEATURE_ZONES in validators
    assert FEATURE_REMOTE_BINDING in validators
    assert FEATURE_SENSOR_CONTROL in validators


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


def test_empty_yaml() -> None:
    """Test parsing empty YAML."""
    with pytest.raises(ValueError):
        parse_full_config_yaml("")


def test_whitespace_only_yaml() -> None:
    """Test parsing whitespace-only YAML."""
    with pytest.raises(ValueError):
        parse_full_config_yaml("   \n\n   ")


def test_yaml_with_comments() -> None:
    """Test parsing YAML with comments."""
    yaml_content = """
# This is a comment
ramses_extras:
  schema_version: 1
  # Another comment
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
"""
    result = parse_full_config_yaml(yaml_content)
    assert "ramses_extras" in result


def test_complex_zone_configuration() -> None:
    """Test parsing complex zone config with all options."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: custom_valve
            min_position: 15
            max_position: 85
            open_entity: switch.bathroom_open
            close_entity: switch.bathroom_close
            position_entity: number.bathroom_position
          - zone_id: bedroom
            type: shelly_2pm_gen3
            min_position: 10
            max_position: 90
"""
    config = parse_full_config_yaml(yaml_content)
    features = config["ramses_extras"]["features"]
    zones = features[FEATURE_ZONES]["FANs"]["32:153289"]
    assert len(zones) == 2
    assert zones[0]["zone_id"] == "bathroom"
    assert zones[0]["min_position"] == 15
    assert zones[1]["zone_id"] == "bedroom"


def test_multiple_fans_with_zones() -> None:
    """Test zones configuration for multiple FANs."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: orcon_native
        "32:153290":
          - zone_id: living_room
            type: custom_valve
            min_position: 20
            max_position: 80
"""
    config = parse_full_config_yaml(yaml_content)
    fans = config["ramses_extras"]["features"][FEATURE_ZONES]["FANs"]
    assert len(fans) == 2
    assert "32:153289" in fans
    assert "32:153290" in fans


def test_complete_real_world_config() -> None:
    """Test parsing a complete real-world configuration."""
    yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    sensor_control:
      devices:
        "32:153289":
          sources:
            indoor_temperature:
              kind: internal
            indoor_humidity:
              kind: internal
          abs_humidity_inputs:
            outdoor:
              temperature:
                kind: external
                entity_id: sensor.outdoor_temp
              humidity:
                kind: external
                entity_id: sensor.outdoor_hum
      area_sensors:
        "32:153289":
          - source_id: bathroom
            label: Bathroom
            zone_id: bathroom
            temperature_entity: sensor.bathroom_temp
            humidity_entity: sensor.bathroom_hum
            area_co2_enabled: true
            co2_entity: sensor.bathroom_co2
            co2_threshold: 1000
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: primary
              enabled: true
              source: manual_config
            - rem_id: "37:169162"
              role: secondary
              enabled: false
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: custom_valve
            min_position: 15
            max_position: 90
            open_entity: switch.bathroom_open
            close_entity: switch.bathroom_close
            position_entity: number.bathroom_position
"""
    config = parse_full_config_yaml(yaml_content)
    features = config["ramses_extras"]["features"]

    # Verify all features present
    assert FEATURE_SENSOR_CONTROL in features
    assert FEATURE_REMOTE_BINDING in features
    assert FEATURE_ZONES in features

    # Verify sensor_control structure
    sc = features[FEATURE_SENSOR_CONTROL]
    assert "32:153289" in sc["devices"]
    assert "outdoor" in sc.get("abs_humidity_inputs", {})
    assert "bathroom" in [
        a["source_id"] for a in sc["area_sensors"].get("32:153289", [])
    ]

    # Verify remote_binding structure
    rb = features[FEATURE_REMOTE_BINDING]
    assert len(rb["FANs"]["32:153289"]["REMs"]) == 2

    # Verify zones structure
    zones = features[FEATURE_ZONES]
    assert len(zones["FANs"]["32:153289"]) == 1
    assert zones["FANs"]["32:153289"][0]["zone_id"] == "bathroom"

    # Validate the config
    errors = validate_full_config_import(config)
    assert len(errors) == 0


# =============================================================================
# Export/Import Roundtrip Tests
# =============================================================================


def test_export_import_roundtrip() -> None:
    """Test that exported config can be imported back."""
    from custom_components.ramses_extras.framework.helpers.config.export import (
        build_exportable_config,
        export_config_to_yaml,
    )

    # Build a config
    raw_config = {
        FEATURE_ZONES: {
            "fans": {
                "32_153289": [
                    {
                        "zone_id": "bathroom",
                        "actuator": {
                            "min_position": 15,
                            "max_position": 90,
                        },
                    }
                ]
            }
        }
    }

    # Export to YAML
    canonical = build_exportable_config(raw_config)
    yaml_output = export_config_to_yaml(canonical)

    # Parse the YAML
    imported = parse_full_config_yaml(yaml_output)

    # Verify structure preserved
    assert "ramses_extras" in imported
    features = imported["ramses_extras"]["features"]
    assert FEATURE_ZONES in features
    zones = features[FEATURE_ZONES]["FANs"]["32:153289"]
    assert zones[0]["zone_id"] == "bathroom"


# =============================================================================
# Main Test Runner
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
