"""Tests for default_yaml.py functions"""

from unittest.mock import patch

import pytest

from custom_components.ramses_extras.features.default.default_yaml import (
    default_validator,
    export_default_to_yaml,
    load_validator,
    merge_default_config,
    parse_default_yaml,
)


def test_default_validator_valid_dict():
    """Test default_validator with valid dict"""
    result = default_validator({"enabled": True, "entities": {}})
    assert result == []


def test_default_validator_empty_dict():
    """Test default_validator with empty dict"""
    result = default_validator({})
    assert result == []


def test_default_validator_invalid_entities():
    """Test default_validator with invalid entities"""
    result = default_validator({"entities": "not_a_dict"})
    assert len(result) == 1
    assert "dictionary" in result[0]


def test_export_default_to_yaml():
    """Test export_default_to_yaml"""
    config = {"enabled": True, "entities": {"sensor1": "config1"}}
    result = export_default_to_yaml(config)
    assert result["enabled"] is True
    assert result["entities"] == {"sensor1": "config1"}


def test_export_default_to_yaml_defaults():
    """Test export_default_to_yaml with defaults"""
    config = {}
    result = export_default_to_yaml(config)
    assert result["enabled"] is True
    assert result["entities"] == {}


def test_parse_default_yaml():
    """Test parse_default_yaml"""
    yaml_data = {"enabled": True, "entities": {}}
    result = parse_default_yaml(yaml_data)
    assert result["enabled"] is True
    assert "entities" in result


def test_merge_default_config():
    """Test merge_default_config"""
    existing = {"enabled": True, "entities": {"sensor1": "old"}}
    imported = {"entities": {"sensor2": "new"}}
    result = merge_default_config(existing, imported)
    assert result["enabled"] is True
    assert "sensor1" in result["entities"]
    assert "sensor2" in result["entities"]


def test_merge_default_config_no_entities_in_existing():
    """Test merge when existing has no entities"""
    existing = {"enabled": True}
    imported = {"entities": {"sensor1": "new"}}
    result = merge_default_config(existing, imported)
    assert "entities" in result
    assert "sensor1" in result["entities"]


def test_merge_default_config_no_entities_in_imported():
    """Test merge when imported has no entities"""
    existing = {"enabled": True, "entities": {"sensor1": "old"}}
    imported = {"enabled": False}
    result = merge_default_config(existing, imported)
    # Should keep existing entities
    assert "sensor1" in result["entities"]


def test_default_validator_non_dict():
    """Test default_validator with non-dict input"""
    result = default_validator("not_a_dict")
    assert len(result) == 1
    assert "dictionary" in result[0]


def test_default_validator_list():
    """Test default_validator with list input"""
    result = default_validator([1, 2, 3])
    assert len(result) == 1
    assert "dictionary" in result[0]


def test_load_validator():
    """Test load_validator registers the validator"""
    with patch(
        "custom_components.ramses_extras.features.default.default_yaml.register_config_validator"
    ) as mock_register:
        load_validator()
        mock_register.assert_called_once()
