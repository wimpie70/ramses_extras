"""Unit tests for DeviceFeatureMatrix."""

import pytest

from custom_components.ramses_extras.framework.helpers.entity.device_feature_matrix import (  # noqa: E501
    DeviceFeatureMatrix,
)


class TestDeviceFeatureMatrix:
    """Unit tests for DeviceFeatureMatrix"""

    def test_initialization(self):
        """Test matrix initialization."""
        matrix = DeviceFeatureMatrix()
        assert matrix.matrix == {}
        assert hasattr(matrix, "enable_feature_for_device")
        assert hasattr(matrix, "get_enabled_features_for_device")

    def test_enable_feature_for_device(self):
        """Test enabling features for devices."""
        matrix = DeviceFeatureMatrix()

        # Enable feature for device
        matrix.enable_feature_for_device("32:153289", "default")
        matrix.enable_feature_for_device("32:153289", "humidity_control")

        # Verify matrix structure
        assert "32:153289" in matrix.matrix
        assert matrix.matrix["32:153289"]["default"] is True
        assert matrix.matrix["32:153289"]["humidity_control"] is True

    def test_get_enabled_features_for_device(self):
        """Test getting enabled features for a device."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("32:153289", "default")
        matrix.enable_feature_for_device("32:153289", "humidity_control")

        features = matrix.get_enabled_features_for_device("32:153289")
        assert features == {"default": True, "humidity_control": True}

        # Test non-existent device
        empty_features = matrix.get_enabled_features_for_device("nonexistent")
        assert empty_features == {}

    def test_get_devices_for_feature(self):
        """Test getting devices for a feature."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("32:153289", "humidity_control")
        matrix.enable_feature_for_device("32:153290", "humidity_control")
        matrix.enable_feature_for_device("32:153291", "default")

        devices = matrix.get_enabled_devices_for_feature("humidity_control")
        assert devices == ["32:153289", "32:153290"]

        default_devices = matrix.get_enabled_devices_for_feature("default")
        assert default_devices == ["32:153291"]

    def test_matrix_serialization(self):
        """Test matrix serialization/deserialization."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("32:153289", "default")

        # Test serialization
        state = matrix.get_matrix_state()
        assert state == {"32:153289": {"default": True}}

        # Test deserialization
        new_matrix = DeviceFeatureMatrix()
        new_matrix.restore_matrix_state(state)
        assert new_matrix.matrix == state
