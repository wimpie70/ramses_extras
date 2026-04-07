"""Tests for features/default/platforms/sensor.py"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.platforms.sensor import (
    _get_area_sensors_config,
)


def test_get_area_sensors_config_no_entry():
    """Test _get_area_sensors_config when no config entry"""
    hass = MagicMock()
    hass.data = {}
    result = _get_area_sensors_config(hass, "32:153289")
    assert result == []


def test_get_area_sensors_config_no_sensor_control():
    """Test _get_area_sensors_config when no sensor_control section"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert result == []


def test_get_area_sensors_config_with_area_sensors():
    """Test _get_area_sensors_config with valid area_sensors"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {
        "sensor_control": {
            "FANs": {"32_153289": {"area_sensors": [{"area_id": "living_room"}]}}
        }
    }
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={
            "FANs": {"32_153289": {"area_sensors": [{"area_id": "living_room"}]}}
        },
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={"area_sensors": [{"area_id": "living_room"}]},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["area_id"] == "living_room"


def test_get_area_sensors_config_with_config_entry_param():
    """Test _get_area_sensors_config with config_entry parameter"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {}  # No entry in hass.data

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={},
        ):
            result = _get_area_sensors_config(
                hass, "32:153289", config_entry=mock_entry
            )
            assert result == []


def test_get_area_sensors_config_invalid_area_sensors_type():
    """Test _get_area_sensors_config when area_sensors is not a list"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={"area_sensors": "not_a_list"},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert result == []


def test_get_area_sensors_config_filters_non_dict_items():
    """Test _get_area_sensors_config filters non-dict items"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={
                "area_sensors": [{"area_id": "valid"}, "invalid_string", 123, None]
            },
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert len(result) == 1
            assert result[0]["area_id"] == "valid"
