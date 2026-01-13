"""Tests for framework/helpers/config/core.py and validation.py."""

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
)
from custom_components.ramses_extras.framework.helpers.config.validation import (
    ConfigValidator,
)


@pytest.fixture
def mock_entry():
    """Return a mock ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {}
    entry.options = {}
    return entry


@pytest.fixture
def config_manager(hass, mock_entry):
    """Return an ExtrasConfigManager instance."""
    default_config = {"enabled": True, "min_value": 10, "max_value": 20}
    return ExtrasConfigManager(hass, mock_entry, "test_feature", default_config)


@pytest.mark.asyncio
async def test_config_manager_load(config_manager, mock_entry):
    """Test loading configuration."""
    mock_entry.data = {"min_value": 15}
    mock_entry.options = {"max_value": 25}

    await config_manager.async_load()
    assert config_manager.get("enabled") is True
    assert config_manager.get("min_value") == 15
    assert config_manager.get("max_value") == 25


@pytest.mark.asyncio
async def test_config_manager_load_error(config_manager, mock_entry):
    """Test load error fallback to defaults."""
    # Trigger exception by making data something that causes update() to fail
    # but still evaluates to True
    mock_entry.data = "not a dict"

    await config_manager.async_load()
    # Should fall back to defaults
    assert config_manager.get("enabled") is True
    assert config_manager.get("min_value") == 10


@pytest.mark.asyncio
async def test_config_manager_save(config_manager):
    """Test async_save."""
    assert await config_manager.async_save() is True

    # Save failure (validation fail)
    config_manager._config["enabled"] = "not a bool"
    assert await config_manager.async_save() is False


def test_config_manager_validate(config_manager):
    """Test base validation logic."""
    # Valid config
    config_manager._config = {"enabled": True, "min_value": 10, "max_value": 20}
    assert config_manager.validate_config() is True

    # Invalid enabled type
    config_manager._config["enabled"] = "yes"
    assert config_manager.validate_config() is False

    # Invalid numeric types
    config_manager._config["enabled"] = True
    config_manager._config["min_value"] = "ten"  # type: ignore[assignment]
    assert config_manager.validate_config() is False

    # Invalid range
    config_manager._config["min_value"] = 20
    config_manager._config["max_value"] = 10
    assert config_manager.validate_config() is False


def test_config_manager_get_set(config_manager):
    """Test get and set methods."""
    config_manager.set("new_key", "val")
    assert config_manager.get("new_key") == "val"
    assert config_manager.get("missing", "default") == "default"


def test_config_manager_update(config_manager):
    """Test update method."""
    config_manager.update({"k1": 1, "k2": 2})
    assert config_manager.get("k1") == 1
    assert config_manager.get("k2") == 2

    # Update with non-dict
    config_manager.update("not a dict")
    assert config_manager.get("k1") == 1


def test_config_manager_helpers(config_manager):
    """Test helper methods."""
    config_manager._config = {"enabled": True, "automation_enabled": True}
    assert config_manager.is_enabled() is True
    assert config_manager.is_automation_enabled() is True

    config_manager.reset_to_defaults()
    assert config_manager.get("enabled") == config_manager._default_config["enabled"]


def test_config_manager_numeric_validation(config_manager):
    """Test get_numeric_validation."""
    config_manager._config = {"val": 50}
    assert config_manager.get_numeric_validation("val", 0, 100) is True
    assert config_manager.get_numeric_validation("val", 60, 100) is False

    config_manager._config["val"] = "abc"  # type: ignore[assignment]
    assert config_manager.get_numeric_validation("val", 0, 100) is False


def test_config_manager_string_validation(config_manager):
    """Test get_string_validation."""
    config_manager._config = {"val": "test"}
    assert (
        config_manager.get_string_validation("val", min_length=2, max_length=10) is True
    )
    assert (
        config_manager.get_string_validation("val", choices=["test", "other"]) is True
    )

    assert config_manager.get_string_validation("val", min_length=5) is False
    assert config_manager.get_string_validation("val", max_length=2) is False
    assert config_manager.get_string_validation("val", choices=["other"]) is False

    config_manager._config["val"] = 123  # type: ignore[assignment]
    assert config_manager.get_string_validation("val") is False


def test_config_validator():
    """Test ConfigValidator utility class."""
    validator = ConfigValidator("test_feature")
    config = {"num": 10, "bool": True, "str": "abc", "list": [1, 2]}

    # Numeric range
    assert validator.validate_numeric_range(config, "num", 0, 20)[0] is True
    assert validator.validate_numeric_range(config, "num", 20, 30)[0] is False
    assert (
        validator.validate_numeric_range(config, "missing", 0, 10, required=True)[0]
        is False
    )
    assert validator.validate_numeric_range(config, "str", 0, 10)[0] is False

    # Boolean
    assert validator.validate_boolean(config, "bool")[0] is True
    assert validator.validate_boolean(config, "num")[0] is False

    # String
    assert validator.validate_string(config, "str", min_length=2)[0] is True
    assert validator.validate_string(config, "str", choices=["abc", "def"])[0] is True
    assert validator.validate_string(config, "num")[0] is False

    # List
    assert (
        validator.validate_list(config, "list", item_type=int, min_items=1)[0] is True
    )
    assert validator.validate_list(config, "list", item_type=str)[0] is False
    assert validator.validate_list(config, "num")[0] is False

    # Dependency
    assert validator.validate_dependency(config, "num", "bool", True)[0] is True
    assert validator.validate_dependency(config, "num", "bool", False)[0] is False

    # Range relationship
    config_range = {"min": 10, "max": 20}
    assert validator.validate_range_relationship(config_range, "min", "max")[0] is True
    assert (
        validator.validate_range_relationship({"min": 20, "max": 10}, "min", "max")[0]
        is False
    )


def test_config_validator_complex(config_manager):
    """Test ConfigValidator with all validation types."""
    validator = ConfigValidator("test_feature")
    config = {
        "bool_val": True,
        "str_val": "test",
        "list_val": [1, 2, 3],
        "list_choices": ["a", "b"],
    }

    # Boolean
    assert validator.validate_boolean(config, "bool_val", required=True)[0] is True
    assert validator.validate_boolean(config, "missing", required=True)[0] is False
    assert validator.validate_boolean(config, "str_val")[0] is False

    # String
    assert (
        validator.validate_string(config, "str_val", min_length=2, max_length=10)[0]
        is True
    )
    assert (
        validator.validate_string(config, "str_val", choices=["test", "other"])[0]
        is True
    )
    assert validator.validate_string(config, "str_val", min_length=10)[0] is False
    assert validator.validate_string(config, "str_val", max_length=2)[0] is False
    assert validator.validate_string(config, "str_val", choices=["other"])[0] is False
    assert validator.validate_string(config, "missing", required=True)[0] is False

    # List
    assert (
        validator.validate_list(
            config, "list_val", item_type=int, min_items=1, max_items=5
        )[0]
        is True
    )
    assert (
        validator.validate_list(
            config, "list_choices", item_type=str, choices=["a", "b", "c"]
        )[0]
        is True
    )
    assert validator.validate_list(config, "list_val", item_type=str)[0] is False
    assert validator.validate_list(config, "list_choices", choices=["a"])[0] is False
    assert validator.validate_list(config, "list_val", min_items=5)[0] is False
    assert validator.validate_list(config, "list_val", max_items=2)[0] is False
    assert validator.validate_list(config, "missing", required=True)[0] is False
    assert validator.validate_list(config, "str_val")[0] is False


def test_validate_all_comprehensive():
    """Test validate_all with all rule types."""
    validator = ConfigValidator("test")
    rules = {
        "num": {"type": "numeric", "min": 0, "max": 100, "required": True},
        "bool": {"type": "boolean", "required": True},
        "str": {"type": "string", "min_length": 2, "choices": ["abc", "def"]},
        "list": {"type": "list", "item_type": int, "min_items": 1},
        "dependent": {"type": "string", "dependency": {"key": "bool", "value": True}},
        "range_min": {
            "type": "numeric",
            "range_relationship": {"other_key": "range_max", "allow_equal": False},
        },
        "range_max": {"type": "numeric"},
    }

    # Valid config
    config = {
        "num": 50,
        "bool": True,
        "str": "abc",
        "list": [1],
        "dependent": "val",
        "range_min": 10,
        "range_max": 20,
    }
    success, errors = validator.validate_all(config, rules)
    assert success is True
    assert not errors

    # Invalid config (multiple errors)
    config = {
        "num": 150,
        "bool": "not_bool",
        "str": "a",
        "list": [],
        "range_min": 20,
        "range_max": 10,
    }
    success, errors = validator.validate_all(config, rules)
    assert success is False
    assert len(errors) >= 5
