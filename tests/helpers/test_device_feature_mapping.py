"""Tests for DeviceFeatureMatrix class."""

import pytest

from custom_components.ramses_extras.framework.helpers.entity.device_feature_matrix import (  # noqa: E501
    DeviceFeatureMatrix,
)


def test_initialization():
    """Test DeviceFeatureMatrix initialization."""
    matrix = DeviceFeatureMatrix()
    assert matrix.matrix == {}
    assert len(matrix.get_all_enabled_combinations()) == 0


def test_enable_feature_for_device():
    """Test enabling features for devices."""
    matrix = DeviceFeatureMatrix()

    # Enable feature for device
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    matrix.enable_feature_for_device("fan_device_2", "humidity_control")
    matrix.enable_feature_for_device("fan_device_1", "hvac_fan_card")

    # Verify matrix state
    assert matrix.get_enabled_features_for_device("fan_device_1") == {
        "humidity_control": True,
        "hvac_fan_card": True,
    }
    assert matrix.get_enabled_features_for_device("fan_device_2") == {
        "humidity_control": True
    }


def test_enable_device_for_feature():
    """Test convenience method for enabling devices."""
    matrix = DeviceFeatureMatrix()

    # Use convenience method
    matrix.enable_device_for_feature("humidity_control", "fan_device_1")
    matrix.enable_device_for_feature("humidity_control", "fan_device_2")

    # Should be same as enable_feature_for_device
    assert matrix.is_feature_enabled_for_device("humidity_control", "fan_device_1")
    assert matrix.is_feature_enabled_for_device("humidity_control", "fan_device_2")


def test_get_enabled_devices_for_feature():
    """Test getting devices for a specific feature."""
    matrix = DeviceFeatureMatrix()

    # Set up test data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    matrix.enable_feature_for_device("fan_device_2", "humidity_control")
    matrix.enable_feature_for_device("fan_device_1", "hvac_fan_card")

    # Test getting devices for humidity_control
    devices = matrix.get_enabled_devices_for_feature("humidity_control")
    assert len(devices) == 2
    assert "fan_device_1" in devices
    assert "fan_device_2" in devices

    # Test getting devices for hvac_fan_card
    devices = matrix.get_enabled_devices_for_feature("hvac_fan_card")
    assert len(devices) == 1
    assert "fan_device_1" in devices


def test_is_feature_enabled_for_device():
    """Test checking if feature is enabled for device."""
    matrix = DeviceFeatureMatrix()

    # Set up test data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")

    # Test enabled combination
    assert (
        matrix.is_feature_enabled_for_device("humidity_control", "fan_device_1") is True
    )
    assert (
        matrix.is_device_enabled_for_feature("fan_device_1", "humidity_control") is True
    )

    # Test disabled combination
    assert (
        matrix.is_feature_enabled_for_device("humidity_control", "fan_device_2")
        is False
    )
    assert (
        matrix.is_feature_enabled_for_device("hvac_fan_card", "fan_device_1") is False
    )


def test_get_all_enabled_combinations():
    """Test getting all enabled combinations."""
    matrix = DeviceFeatureMatrix()

    # Set up test data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    matrix.enable_feature_for_device("fan_device_2", "humidity_control")
    matrix.enable_feature_for_device("fan_device_1", "hvac_fan_card")

    # Test getting all combinations
    combinations = matrix.get_all_enabled_combinations()
    assert len(combinations) == 3
    assert ("fan_device_1", "humidity_control") in combinations
    assert ("fan_device_2", "humidity_control") in combinations
    assert ("fan_device_1", "hvac_fan_card") in combinations


def test_clear_matrix():
    """Test clearing the matrix."""
    matrix = DeviceFeatureMatrix()

    # Add some data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    assert len(matrix.get_all_enabled_combinations()) == 1

    # Clear matrix
    matrix.clear_matrix()
    assert matrix.get_all_enabled_combinations() == []
    assert matrix.matrix == {}


def test_remove_feature_for_device():
    """Test removing feature from device."""
    matrix = DeviceFeatureMatrix()

    # Add test data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    matrix.enable_feature_for_device("fan_device_1", "hvac_fan_card")
    assert len(matrix.get_enabled_features_for_device("fan_device_1")) == 2

    # Remove one feature
    matrix.remove_feature_for_device("fan_device_1", "humidity_control")
    features = matrix.get_enabled_features_for_device("fan_device_1")
    assert len(features) == 1
    assert "humidity_control" not in features
    assert "hvac_fan_card" in features

    # Remove last feature - should clean up device entry
    matrix.remove_feature_for_device("fan_device_1", "hvac_fan_card")
    assert matrix.get_enabled_features_for_device("fan_device_1") == {}


def test_get_matrix_state():
    """Test getting matrix state."""
    matrix = DeviceFeatureMatrix()

    # Add test data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")

    # Get state
    state = matrix.get_matrix_state()
    assert state == {"fan_device_1": {"humidity_control": True}}

    # Verify it's a copy (not reference)
    state["fan_device_1"]["humidity_control"] = False
    assert (
        matrix.is_feature_enabled_for_device("humidity_control", "fan_device_1") is True
    )


def test_string_representation():
    """Test string representation."""
    matrix = DeviceFeatureMatrix()

    # Empty matrix
    assert str(matrix) == "DeviceFeatureMatrix(0 devices, 0 combinations)"

    # Matrix with data
    matrix.enable_feature_for_device("fan_device_1", "humidity_control")
    matrix.enable_feature_for_device("fan_device_2", "humidity_control")
    assert str(matrix) == "DeviceFeatureMatrix(2 devices, 2 combinations)"
