"""Tests for CO2 Control YAML validation."""

from custom_components.ramses_extras.features.co2_control.co2_control_yaml import (
    co2_control_validator,
    export_co2_control_to_yaml,
    merge_co2_control_config,
    parse_co2_control_yaml,
)


def test_co2_control_validator_threshold_not_numeric():
    """Test validator with non-numeric threshold (covers line 87)."""
    section = {
        "FANs": {
            "32:123456": {
                "threshold": "not_a_number",
            }
        }
    }

    errors = co2_control_validator(section)

    assert any("threshold must be numeric" in error for error in errors)


def test_co2_control_validator_activation_hysteresis_not_numeric():
    """Test validator with non-numeric activation_hysteresis (covers line 96)."""
    section = {
        "FANs": {
            "32:123456": {
                "activation_hysteresis": "not_a_number",
            }
        }
    }

    errors = co2_control_validator(section)

    assert any("activation_hysteresis must be numeric" in error for error in errors)


def test_co2_control_validator_deactivation_hysteresis_not_numeric():
    """Test validator with non-numeric deactivation_hysteresis (covers line 105)."""
    section = {
        "FANs": {
            "32:123456": {
                "deactivation_hysteresis": "not_a_number",
            }
        }
    }

    errors = co2_control_validator(section)

    assert any("deactivation_hysteresis must be numeric" in error for error in errors)


def test_merge_co2_control_config_no_existing_fans():
    """Test merge when existing config has no FANs (covers line 149)."""
    existing = {}
    imported = {
        "FANs": {
            "32:123456": {"enabled": True},
        }
    }

    merged = merge_co2_control_config(existing, imported)

    assert "FANs" in merged
    assert "32:123456" in merged["FANs"]


def test_export_co2_control_to_yaml():
    """Test export to YAML."""
    config = {
        "FANs": {
            "32:123456": {"enabled": True},
        }
    }

    result = export_co2_control_to_yaml(config)

    assert result == config


def test_parse_co2_control_yaml():
    """Test parse from YAML."""
    yaml_data = {
        "FANs": {
            "32:123456": {"enabled": True},
        }
    }

    result = parse_co2_control_yaml(yaml_data)

    # Schema adds defaults
    assert "FANs" in result
    assert "32:123456" in result["FANs"]
    assert result["FANs"]["32:123456"]["enabled"] is True


def test_co2_control_validator_valid_config():
    """Test validator with valid configuration."""
    section = {
        "FANs": {
            "32:123456": {
                "threshold": 1000,
                "activation_hysteresis": 100,
                "deactivation_hysteresis": -100,
            }
        }
    }

    errors = co2_control_validator(section)

    assert len(errors) == 0


def test_co2_control_validator_invalid_fan_config():
    """Test validator with non-dict fan config."""
    section = {
        "FANs": {
            "32:123456": "not_a_dict",
        }
    }

    errors = co2_control_validator(section)

    assert any("configuration must be a dictionary" in error for error in errors)
