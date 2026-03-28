"""Tests for configuration import validation framework.

Tests the validation registry system and framework-level validation logic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

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
# Registry Tests
# =============================================================================


def test_register_validator_adds_to_registry() -> None:
    """Test that registering a validator adds it to the registry."""
    test_feature = "test_feature_1"

    def test_validator(section: dict[str, Any], hass: Any) -> list[str]:
        return []

    # Ensure not already registered
    unregister_config_validator(test_feature)

    # Register
    register_config_validator(test_feature, test_validator)

    # Verify
    validators = get_registered_validators()
    assert test_feature in validators
    assert validators[test_feature] is test_validator

    # Cleanup
    unregister_config_validator(test_feature)


def test_unregister_validator_removes_from_registry() -> None:
    """Test that unregistering a validator removes it from the registry."""
    test_feature = "test_feature_2"

    def test_validator(section: dict[str, Any], hass: Any) -> list[str]:
        return []

    # Register then unregister
    register_config_validator(test_feature, test_validator)
    unregister_config_validator(test_feature)

    # Verify removed
    validators = get_registered_validators()
    assert test_feature not in validators


def test_unregister_nonexistent_validator_is_safe() -> None:
    """Test that unregistering a non-existent validator doesn't raise."""
    # Should not raise
    unregister_config_validator("definitely_not_registered")


def test_register_overwrites_existing_validator() -> None:
    """Test that registering overwrites existing validator."""
    test_feature = "test_feature_3"

    def validator1(section: dict[str, Any], hass: Any) -> list[str]:
        return ["error1"]

    def validator2(section: dict[str, Any], hass: Any) -> list[str]:
        return ["error2"]

    # Register first validator
    register_config_validator(test_feature, validator1)

    # Register second validator (should overwrite)
    register_config_validator(test_feature, validator2)

    # Verify
    validators = get_registered_validators()
    assert validators[test_feature] is validator2

    # Cleanup
    unregister_config_validator(test_feature)


def test_get_registered_validators_returns_copy() -> None:
    """Test that get_registered_validators returns a copy."""
    original = get_registered_validators()

    # Modify returned dict
    original["new_feature"] = lambda s, h: []

    # Should not affect actual registry
    validators = get_registered_validators()
    assert "new_feature" not in validators


# =============================================================================
# Framework Validation Tests
# =============================================================================


def test_validate_import_config_valid() -> None:
    """Test validation with valid config."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {},
        }
    }

    result = validate_import_config(config)

    assert result["valid"] is True
    assert result["total_errors"] == 0
    assert len(result["framework_errors"]) == 0
    assert len(result["feature_errors"]) == 0


def test_validate_import_config_missing_root() -> None:
    """Test validation with missing root key."""
    config: dict[str, Any] = {}

    result = validate_import_config(config)

    assert result["valid"] is False
    assert len(result["framework_errors"]) > 0
    assert "Missing or invalid" in result["framework_errors"][0]


def test_validate_import_config_invalid_features_type() -> None:
    """Test validation with invalid features type."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": "not_a_dict",
        }
    }

    result = validate_import_config(config)

    assert result["valid"] is False
    assert len(result["framework_errors"]) > 0
    assert "Invalid 'features' section" in result["framework_errors"][0]


def test_validate_import_config_unsupported_schema_version() -> None:
    """Test validation with unsupported schema version."""
    config = {
        "ramses_extras": {
            "schema_version": 99,
            "features": {},
        }
    }

    result = validate_import_config(config)

    assert result["valid"] is False
    assert len(result["framework_errors"]) > 0
    assert "Unsupported schema version" in result["framework_errors"][0]


def test_validate_import_config_runs_feature_validators() -> None:
    """Test that feature validators are run."""
    test_feature = "test_feature_4"
    errors_list = ["test error"]

    def test_validator(section: dict[str, Any], hass: Any) -> list[str]:
        return errors_list

    register_config_validator(test_feature, test_validator)

    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                test_feature: {"some": "data"},
            },
        }
    }

    result = validate_import_config(config)

    assert result["valid"] is False
    assert test_feature in result["feature_errors"]
    assert result["feature_errors"][test_feature] == errors_list

    # Cleanup
    unregister_config_validator(test_feature)


def test_validate_import_config_unknown_feature_no_error() -> None:
    """Test that unknown features don't cause errors (extensibility)."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                "unknown_future_feature": {"some": "data"},
            },
        }
    }

    result = validate_import_config(config)

    # Should be valid (unknown features allowed for forward compatibility)
    assert result["valid"] is True
    assert "unknown_future_feature" not in result["feature_errors"]


def test_validate_import_config_multiple_feature_errors() -> None:
    """Test validation with errors from multiple features."""

    def make_validator(errors: list[str]):
        def validator(section: dict[str, Any], hass: Any) -> list[str]:
            return errors

        return validator

    feature1 = "test_feature_a"
    feature2 = "test_feature_b"

    register_config_validator(feature1, make_validator(["error1", "error2"]))
    register_config_validator(feature2, make_validator(["error3"]))

    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                feature1: {},
                feature2: {},
            },
        }
    }

    result = validate_import_config(config)

    assert result["valid"] is False
    assert result["total_errors"] == 3
    assert len(result["feature_errors"][feature1]) == 2
    assert len(result["feature_errors"][feature2]) == 1

    # Cleanup
    unregister_config_validator(feature1)
    unregister_config_validator(feature2)


def test_validate_import_config_with_hass() -> None:
    """Test validation with Home Assistant instance."""
    mock_hass = MagicMock()
    mock_hass.states.get.return_value = None  # Simulate entity not found

    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_ZONES: {
                    "FANs": {
                        "32:153289": [
                            {
                                "zone_id": "test",
                                "type": "custom_valve",
                                "open_entity": "switch.nonexistent",
                            }
                        ]
                    }
                }
            },
        }
    }

    result = validate_import_config(config, hass=mock_hass)

    # Should have errors about nonexistent entity
    assert FEATURE_ZONES in result["feature_errors"]
    assert any("not found" in e for e in result["feature_errors"][FEATURE_ZONES])


# =============================================================================
# Error Formatting Tests
# =============================================================================


def test_format_validation_errors_empty() -> None:
    """Test formatting with no errors."""
    result = {
        "valid": True,
        "framework_errors": [],
        "feature_errors": {},
        "total_errors": 0,
    }

    formatted = format_validation_errors(result)
    assert formatted == []


def test_format_validation_errors_framework_only() -> None:
    """Test formatting with only framework errors."""
    result = {
        "valid": False,
        "framework_errors": ["Error 1", "Error 2"],
        "feature_errors": {},
        "total_errors": 2,
    }

    formatted = format_validation_errors(result)
    assert len(formatted) == 2
    assert all("[Framework]" in e for e in formatted)


def test_format_validation_errors_features_only() -> None:
    """Test formatting with only feature errors."""
    result = {
        "valid": False,
        "framework_errors": [],
        "feature_errors": {
            "zones": ["Zone error"],
            "remote_binding": ["Binding error"],
        },
        "total_errors": 2,
    }

    formatted = format_validation_errors(result)
    assert len(formatted) == 2
    assert any("[zones]" in e for e in formatted)
    assert any("[remote_binding]" in e for e in formatted)


def test_format_validation_errors_mixed() -> None:
    """Test formatting with both framework and feature errors."""
    result = {
        "valid": False,
        "framework_errors": ["Framework error"],
        "feature_errors": {
            "zones": ["Zone error 1", "Zone error 2"],
        },
        "total_errors": 3,
    }

    formatted = format_validation_errors(result)
    assert len(formatted) == 3
    assert any("[Framework]" in e for e in formatted)
    assert any("[zones]" in e for e in formatted)


# =============================================================================
# Built-in Feature Validators Tests
# =============================================================================


def test_built_in_validators_registered() -> None:
    """Test that built-in feature validators are registered."""
    validators = get_registered_validators()

    assert FEATURE_ZONES in validators
    assert FEATURE_REMOTE_BINDING in validators
    assert FEATURE_SENSOR_CONTROL in validators


# =============================================================================
# Edge Cases
# =============================================================================


def test_validate_import_config_none_features() -> None:
    """Test validation with None features."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": None,
        }
    }

    result = validate_import_config(config)
    # Should handle gracefully
    assert isinstance(result["valid"], bool)


def test_validate_import_config_empty_features() -> None:
    """Test validation with empty features dict."""
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {},
        }
    }

    result = validate_import_config(config)
    assert result["valid"] is True


def test_validator_receives_correct_section() -> None:
    """Test that validators receive the correct feature section."""
    received_section: dict[str, Any] = {}

    def capturing_validator(section: dict[str, Any], hass: Any) -> list[str]:
        received_section.update(section)
        return []

    test_feature = "test_feature_5"
    register_config_validator(test_feature, capturing_validator)

    feature_data = {"FANs": {"32:153289": []}}
    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                test_feature: feature_data,
            },
        }
    }

    validate_import_config(config)

    assert received_section == feature_data

    # Cleanup
    unregister_config_validator(test_feature)


def test_validator_error_does_not_stop_others() -> None:
    """Test that one validator error doesn't prevent others from running."""

    def error_validator(section: dict[str, Any], hass: Any) -> list[str]:
        raise RuntimeError("Unexpected error")

    def normal_validator(section: dict[str, Any], hass: Any) -> list[str]:
        return ["normal error"]

    feature1 = "test_feature_6"
    feature2 = "test_feature_7"

    register_config_validator(feature1, error_validator)
    register_config_validator(feature2, normal_validator)

    config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                feature1: {},
                feature2: {},
            },
        }
    }

    # Should not raise, but may not get results from error validator
    result = validate_import_config(config)

    # At minimum, the normal validator should have run
    assert feature2 in result["feature_errors"]

    # Cleanup
    unregister_config_validator(feature1)
    unregister_config_validator(feature2)


# =============================================================================
# Main Test Runner
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
