"""Tests for ConfigValidator in framework/helpers/config/validation.py."""

import pytest

from custom_components.ramses_extras.features.humidity_control.const import (
    HUMIDITY_CONTROL_VALIDATION_RULES,
)
from custom_components.ramses_extras.framework.helpers.config.validation import (
    ConfigValidator,
)


class TestConfigValidator:
    """Test cases for ConfigValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ConfigValidator("test_feature")
        self.config = {
            "enabled": True,
            "min_value": 10,
            "max_value": 20,
            "string_value": "test",
            "list_value": [1, 2, 3],
        }

    def test_init(self):
        """Test initialization of ConfigValidator."""
        assert self.validator.feature_id == "test_feature"

    def test_validate_numeric_range_valid(self):
        """Test numeric range validation with valid values."""
        is_valid, error = self.validator.validate_numeric_range(
            self.config, "min_value", 0, 100, required=False
        )

        assert is_valid is True
        assert error is None

    def test_validate_numeric_range_required_missing(self):
        """Test numeric range validation with required field missing."""
        is_valid, error = self.validator.validate_numeric_range(
            {}, "missing_key", 0, 100, required=True
        )

        assert is_valid is False
        assert error == "'missing_key' is required"

    def test_validate_numeric_range_invalid_type(self):
        """Test numeric range validation with invalid type."""
        config = {"invalid_value": "not_a_number"}
        is_valid, error = self.validator.validate_numeric_range(
            config, "invalid_value", 0, 100
        )

        assert is_valid is False
        assert "must be numeric" in error

    def test_validate_numeric_range_out_of_range(self):
        """Test numeric range validation with out of range value."""
        config = {"out_of_range": 150}
        is_valid, error = self.validator.validate_numeric_range(
            config, "out_of_range", 0, 100
        )

        assert is_valid is False
        assert "must be between 0 and 100" in error

    def test_validate_boolean_valid(self):
        """Test boolean validation with valid value."""
        is_valid, error = self.validator.validate_boolean(
            self.config, "enabled", required=False
        )

        assert is_valid is True
        assert error is None

    def test_validate_boolean_required_missing(self):
        """Test boolean validation with required field missing."""
        is_valid, error = self.validator.validate_boolean(
            {}, "missing_key", required=True
        )

        assert is_valid is False
        assert error == "'missing_key' is required"

    def test_validate_boolean_invalid_type(self):
        """Test boolean validation with invalid type."""
        config = {"invalid_bool": "not_boolean"}
        is_valid, error = self.validator.validate_boolean(config, "invalid_bool")

        assert is_valid is False
        assert "must be boolean" in error

    def test_validate_string_valid(self):
        """Test string validation with valid value."""
        is_valid, error = self.validator.validate_string(
            self.config, "string_value", choices=None, required=False
        )

        assert is_valid is True
        assert error is None

    def test_validate_string_with_choices_valid(self):
        """Test string validation with valid choice."""
        config = {"choice_value": "option1"}
        is_valid, error = self.validator.validate_string(
            config, "choice_value", choices=["option1", "option2"]
        )

        assert is_valid is True
        assert error is None

    def test_validate_string_required_missing(self):
        """Test string validation with required field missing."""
        is_valid, error = self.validator.validate_string(
            {}, "missing_key", required=True
        )

        assert is_valid is False
        assert error == "'missing_key' is required"

    def test_validate_string_invalid_type(self):
        """Test string validation with invalid type."""
        config = {"invalid_string": 123}
        is_valid, error = self.validator.validate_string(config, "invalid_string")

        assert is_valid is False
        assert "must be string" in error

    def test_validate_string_invalid_choice(self):
        """Test string validation with invalid choice."""
        config = {"choice_value": "invalid_option"}
        is_valid, error = self.validator.validate_string(
            config, "choice_value", choices=["option1", "option2"]
        )

        assert is_valid is False
        assert "must be one of" in error

    def test_validate_string_min_length(self):
        """Test string validation with minimum length."""
        config = {"short_string": "x"}
        is_valid, error = self.validator.validate_string(
            config, "short_string", min_length=3
        )

        assert is_valid is False
        assert "must be at least 3 characters long" in error

    def test_validate_string_max_length(self):
        """Test string validation with maximum length."""
        config = {"long_string": "this_is_too_long"}
        is_valid, error = self.validator.validate_string(
            config, "long_string", max_length=10
        )

        assert is_valid is False
        assert "must be at most 10 characters long" in error

    def test_validate_list_valid(self):
        """Test list validation with valid list."""
        is_valid, error = self.validator.validate_list(
            self.config, "list_value", item_type=int, required=False
        )

        assert is_valid is True
        assert error is None

    def test_validate_list_with_choices_valid(self):
        """Test list validation with valid choices."""
        config = {"choice_list": ["a", "b"]}
        is_valid, error = self.validator.validate_list(
            config, "choice_list", choices=["a", "b", "c"]
        )

        assert is_valid is True
        assert error is None

    def test_validate_list_required_missing(self):
        """Test list validation with required field missing."""
        is_valid, error = self.validator.validate_list({}, "missing_key", required=True)

        assert is_valid is False
        assert error == "'missing_key' is required"

    def test_validate_list_invalid_type(self):
        """Test list validation with invalid type."""
        config = {"invalid_list": "not_a_list"}
        is_valid, error = self.validator.validate_list(config, "invalid_list")

        assert is_valid is False
        assert "must be list" in error

    def test_validate_list_invalid_item_type(self):
        """Test list validation with invalid item type."""
        config = {"mixed_list": [1, "string", 3]}
        is_valid, error = self.validator.validate_list(
            config, "mixed_list", item_type=int
        )

        assert is_valid is False
        assert "must be int" in error

    def test_validate_list_invalid_choice(self):
        """Test list validation with invalid choice."""
        config = {"choice_list": ["valid", "invalid"]}
        is_valid, error = self.validator.validate_list(
            config, "choice_list", choices=["valid", "other"]
        )

        assert is_valid is False
        assert "must be one of" in error

    def test_validate_list_min_items(self):
        """Test list validation with minimum items."""
        config = {"small_list": [1]}
        is_valid, error = self.validator.validate_list(
            config, "small_list", min_items=3
        )

        assert is_valid is False
        assert "must have at least 3 items" in error

    def test_validate_list_max_items(self):
        """Test list validation with maximum items."""
        config = {"large_list": [1, 2, 3, 4, 5]}
        is_valid, error = self.validator.validate_list(
            config, "large_list", max_items=3
        )

        assert is_valid is False
        assert "must have at most 3 items" in error

    def test_validate_dependency_valid(self):
        """Test dependency validation with valid dependency."""
        config = {"enabled": True, "setting": "value"}
        is_valid, error = self.validator.validate_dependency(
            config, "setting", "enabled", True
        )

        assert is_valid is True
        assert error is None

    def test_validate_dependency_invalid(self):
        """Test dependency validation with invalid dependency."""
        config = {"enabled": False, "setting": "value"}
        is_valid, error = self.validator.validate_dependency(
            config, "setting", "enabled", True
        )

        assert is_valid is False
        assert "requires 'enabled' to be True" in error

    def test_validate_dependency_missing_dependent(self):
        """Test dependency validation when dependent key is missing."""
        config = {"enabled": True}
        is_valid, error = self.validator.validate_dependency(
            config, "missing_key", "enabled", True
        )

        assert is_valid is True
        assert error is None

    def test_validate_range_relationship_valid(self):
        """Test range relationship validation with valid ranges."""
        config = {"min_val": 10, "max_val": 20}
        is_valid, error = self.validator.validate_range_relationship(
            config, "min_val", "max_val", allow_equal=False
        )

        assert is_valid is True
        assert error is None

    def test_validate_range_relationship_equal_allowed(self):
        """Test range relationship validation allowing equal values."""
        config = {"min_val": 10, "max_val": 10}
        is_valid, error = self.validator.validate_range_relationship(
            config, "min_val", "max_val", allow_equal=True
        )

        assert is_valid is True
        assert error is None

    def test_validate_range_relationship_invalid(self):
        """Test range relationship validation with invalid range."""
        config = {"min_val": 20, "max_val": 10}
        is_valid, error = self.validator.validate_range_relationship(
            config, "min_val", "max_val", allow_equal=False
        )

        assert is_valid is False
        assert "must be <" in error

    def test_validate_range_relationship_invalid_types(self):
        """Test range relationship validation with invalid types."""
        config = {"min_val": "not_number", "max_val": 10}
        is_valid, error = self.validator.validate_range_relationship(
            config, "min_val", "max_val"
        )

        assert is_valid is False
        assert "must both be numeric" in error

    def test_validate_range_relationship_missing_keys(self):
        """Test range relationship validation with missing keys."""
        config = {"min_val": 10}
        is_valid, error = self.validator.validate_range_relationship(
            config, "min_val", "max_val"
        )

        assert is_valid is True
        assert error is None

    def test_validate_all_valid(self):
        """Test validate_all with valid configuration."""
        validation_rules = {
            "enabled": {"type": "boolean"},
            "min_value": {"type": "numeric", "min": 0, "max": 100},
            "string_value": {"type": "string", "choices": ["test", "other"]},
        }

        is_valid, errors = self.validator.validate_all(self.config, validation_rules)

        assert is_valid is True
        assert errors == []

    def test_validate_all_invalid(self):
        """Test validate_all with invalid configuration."""
        config = {
            "enabled": "not_boolean",
            "min_value": 150,  # Out of range
            "string_value": "invalid_choice",
        }
        validation_rules = {
            "enabled": {"type": "boolean"},
            "min_value": {"type": "numeric", "min": 0, "max": 100},
            "string_value": {"type": "string", "choices": ["test", "other"]},
        }

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 3

    def test_validate_all_with_dependency(self):
        """Test validate_all with dependency validation."""
        config = {"enabled": False, "setting": "value"}
        validation_rules = {
            "enabled": {"type": "boolean"},
            "setting": {"dependency": {"key": "enabled", "value": True}},
        }

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "requires 'enabled' to be True" in errors[0]

    def test_validate_all_with_range_relationship(self):
        """Test validate_all with range relationship validation."""
        config = {"min_val": 20, "max_val": 10}
        validation_rules = {
            "min_val": {
                "type": "numeric",
                "min": 0,
                "max": 100,
                "range_relationship": {"other_key": "max_val", "allow_equal": False},
            },
            "max_val": {"type": "numeric", "min": 0, "max": 100},
        }

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) >= 1

    def test_validate_all_with_invalid_numeric_type(self):
        """Test validate_all with invalid numeric type (string instead of number)."""
        config = {"temperature": "invalid"}
        validation_rules = {"temperature": {"type": "numeric", "min": 0, "max": 100}}

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "must be numeric" in errors[0]  # type: ignore[operator]

    def test_validate_all_with_missing_required_field(self):
        """Test validate_all with missing required field."""
        config = {}  # Missing required field
        validation_rules = {"enabled": {"type": "boolean", "required": True}}

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "'enabled' is required" in errors[0]

    def test_validate_all_with_malformed_dependency(self):
        """Test validate_all with malformed dependency configuration."""
        config = {"setting": True}  # Missing 'enabled'
        validation_rules = {
            "setting": {"dependency": {"key": "enabled"}}  # defaults to True
        }

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False  # 'enabled' not in config, dependency fails
        assert len(errors) == 1
        assert "requires 'enabled' to be True" in errors[0]

    def test_validate_all_with_invalid_string_choice(self):
        """Test validate_all with invalid string choice."""
        config = {"mode": "invalid_mode"}
        validation_rules = {
            "mode": {"type": "string", "choices": ["auto", "manual", "eco"]}
        }

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "must be one of ['auto', 'manual', 'eco']" in errors[0]

    def test_validate_all_with_invalid_list_item_type(self):
        """Test validate_all with invalid list item type."""
        config = {"sensors": ["sensor1", 123, "sensor3"]}  # Mixed types
        validation_rules = {"sensors": {"type": "list", "item_type": str}}

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "must be str" in errors[0]

    def test_validate_all_with_out_of_range_numeric(self):
        """Test validate_all with numeric value out of range."""
        config = {"humidity": 150}  # Above max 100
        validation_rules = {"humidity": {"type": "numeric", "min": 0, "max": 100}}

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "must be between 0 and 100" in errors[0]  # type: ignore[operator]

    def test_validate_all_with_empty_string_when_min_length_required(self):
        """Test validate_all with empty string when min_length is set."""
        config = {"name": ""}
        validation_rules = {"name": {"type": "string", "min_length": 1}}

        is_valid, errors = self.validator.validate_all(config, validation_rules)

        assert is_valid is False
        assert len(errors) == 1
        assert "must be at least 1 characters long" in errors[0]


class TestValidationRules:
    """Test cases for predefined validation rules."""

    def test_humidity_control_validation_rules_structure(self):
        """Test that humidity control validation rules have expected structure."""
        assert isinstance(HUMIDITY_CONTROL_VALIDATION_RULES, dict)
        assert "enabled" in HUMIDITY_CONTROL_VALIDATION_RULES
        assert "default_min_humidity" in HUMIDITY_CONTROL_VALIDATION_RULES
        assert "default_max_humidity" in HUMIDITY_CONTROL_VALIDATION_RULES
