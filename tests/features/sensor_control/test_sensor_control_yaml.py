"""Tests for sensor_control/sensor_control_yaml.py"""

import pytest

from custom_components.ramses_extras.features.sensor_control.sensor_control_yaml import (  # noqa: E501
    export_sensor_control_to_yaml,
    merge_sensor_control_config,
    sensor_control_validator,
)


def test_sensor_control_validator_empty():
    """Test sensor_control_validator with empty section"""
    result = sensor_control_validator({})
    assert result == []


def test_sensor_control_validator_valid_config():
    """Test sensor_control_validator with valid config"""
    section = {
        "FANs": {
            "32:153289": {
                "area_sensors": {},
                "abs_humidity_inputs": {},
                "sources": [],
            }
        }
    }
    result = sensor_control_validator(section)
    assert result == []


def test_sensor_control_validator_invalid_fan_config():
    """Test sensor_control_validator with invalid fan config"""
    section = {"FANs": {"32:153289": "not_a_dict"}}
    result = sensor_control_validator(section)
    assert len(result) == 1
    assert "must be a dictionary" in result[0]


def test_sensor_control_validator_invalid_area_sensors():
    """Test sensor_control_validator with invalid area_sensors"""
    section = {
        "FANs": {
            "32:153289": {
                "area_sensors": "not_a_dict",
            }
        }
    }
    result = sensor_control_validator(section)
    assert len(result) == 1
    assert "area_sensors" in result[0]


def test_sensor_control_validator_invalid_abs_humidity():
    """Test sensor_control_validator with invalid abs_humidity_inputs"""
    section = {
        "FANs": {
            "32:153289": {
                "abs_humidity_inputs": "not_a_dict",
            }
        }
    }
    result = sensor_control_validator(section)
    assert len(result) == 1
    assert "abs_humidity_inputs" in result[0]


def test_sensor_control_validator_invalid_sources():
    """Test sensor_control_validator with invalid sources"""
    section = {
        "FANs": {
            "32:153289": {
                "sources": "not_a_list",
            }
        }
    }
    result = sensor_control_validator(section)
    assert len(result) == 1
    assert "sources" in result[0]


def test_export_sensor_control_to_yaml():
    """Test export_sensor_control_to_yaml"""
    config = {"FANs": {"32:153289": {"enabled": True}}}
    result = export_sensor_control_to_yaml(config)
    assert result == config


def test_export_sensor_control_to_yaml_empty():
    """Test export_sensor_control_to_yaml with empty config"""
    config = {}
    result = export_sensor_control_to_yaml(config)
    assert result == {}


def test_merge_sensor_control_config():
    """Test merge_sensor_control_config"""
    existing = {"FANs": {"32:153289": {"enabled": True}}}
    imported = {"FANs": {"32:999999": {"enabled": False}}}
    result = merge_sensor_control_config(existing, imported)
    assert "32:153289" in result["FANs"]
    assert "32:999999" in result["FANs"]


def test_merge_sensor_control_config_new_fan():
    """Test merge_sensor_control_config when FANs doesn't exist"""
    existing = {}
    imported = {"FANs": {"32:153289": {"enabled": True}}}
    result = merge_sensor_control_config(existing, imported)
    assert "FANs" in result
    assert "32:153289" in result["FANs"]


def test_merge_sensor_control_config_no_fans_in_imported():
    """Test merge_sensor_control_config when imported has no FANs"""
    existing = {"FANs": {"32:153289": {"enabled": True}}}
    imported = {}
    result = merge_sensor_control_config(existing, imported)
    assert result == existing
