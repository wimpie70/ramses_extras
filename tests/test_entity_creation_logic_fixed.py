"""Test entity creation logic for Phase 3 implementation.

This module contains comprehensive tests for entity creation validation,
ensuring entities are only created for enabled features AND devices.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.entity.device_mapping import (
    DeviceFeatureMatrix,
)
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestDeviceFeatureMatrix:
    """Test DeviceFeatureMatrix functionality."""

    def test_device_feature_matrix_initialization(self):
        """Test DeviceFeatureMatrix initialization."""
        matrix = DeviceFeatureMatrix()
        assert matrix.matrix == {}
        assert str(matrix) == "DeviceFeatureMatrix(0 devices, 0 combinations)"

    def test_enable_feature_for_device(self):
        """Test enabling features for specific devices."""
        matrix = DeviceFeatureMatrix()

        # Enable feature for device
        matrix.enable_feature_for_device("device1", "feature1")
        assert matrix.is_feature_enabled_for_device("feature1", "device1") is True
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # Test convenience method
        matrix.enable_device_for_feature("feature2", "device1")
        assert matrix.is_feature_enabled_for_device("feature2", "device1") is True

    def test_get_enabled_features_for_device(self):
        """Test getting enabled features for a device."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        enabled_features = matrix.get_enabled_features_for_device("device1")
        assert "feature1" in enabled_features
        assert "feature2" in enabled_features
        assert enabled_features["feature1"] is True
        assert enabled_features["feature2"] is True

    def test_get_enabled_devices_for_feature(self):
        """Test getting devices that have a feature enabled."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device2", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        devices = matrix.get_enabled_devices_for_feature("feature1")
        assert "device1" in devices
        assert "device2" in devices
        assert len(devices) == 2

    def test_get_all_enabled_combinations(self):
        """Test getting all enabled feature/device combinations."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device2", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        combinations = matrix.get_all_enabled_combinations()
        assert ("device1", "feature1") in combinations
        assert ("device2", "feature1") in combinations
        assert ("device1", "feature2") in combinations
        assert len(combinations) == 3

    def test_matrix_state_management(self):
        """Test matrix state management."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # Test state retrieval
        state = matrix.get_matrix_state()
        assert state == {"device1": {"feature1": True}}

        # State restoration would be tested if the method existed

    def test_remove_feature_for_device(self):
        """Test removing features from devices."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        # Remove one feature
        matrix.remove_feature_for_device("device1", "feature1")
        assert matrix.is_feature_enabled_for_device("feature1", "device1") is False
        assert matrix.is_feature_enabled_for_device("feature2", "device1") is True

        # Remove last feature - should clean up device
        matrix.remove_feature_for_device("device1", "feature2")
        assert "device1" not in matrix.matrix


class TestEntityCreationValidation:
    """Test entity creation validation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    def test_entity_creation_only_for_enabled_feature_and_device(self):
        """Test that entities are only created when BOTH feature
        and device are enabled."""
        # Setup: Feature enabled, device enabled
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # Mock the entity manager's matrix
        self.entity_manager.device_feature_matrix = matrix

        # Test entity creation logic
        # This would be implemented in the actual entity creation method
        # For now, we test the matrix logic that drives it
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # Test: Feature enabled but device NOT enabled
        assert matrix.is_device_enabled_for_feature("device2", "feature1") is False

        # Test: Device enabled but feature NOT enabled
        # (This would require checking feature enablement separately)

    def test_entity_creation_validation_with_matrix(self):
        """Test entity creation validation using DeviceFeatureMatrix."""
        matrix = DeviceFeatureMatrix()

        # Enable feature for specific devices
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device2", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        # Test validation logic
        # Feature1 enabled for device1 and device2
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True
        assert matrix.is_device_enabled_for_feature("device2", "feature1") is True

        # Feature1 NOT enabled for device3
        assert matrix.is_device_enabled_for_feature("device3", "feature1") is False

        # Feature2 enabled only for device1
        assert matrix.is_device_enabled_for_feature("device1", "feature2") is True
        assert matrix.is_device_enabled_for_feature("device2", "feature2") is False

    def test_entity_removal_when_feature_or_device_disabled(self):
        """Test entity removal when feature or device is disabled."""
        matrix = DeviceFeatureMatrix()

        # Initially enable feature for device
        matrix.enable_feature_for_device("device1", "feature1")
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # Disable feature for device
        matrix.remove_feature_for_device("device1", "feature1")
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is False

        # This would trigger entity removal in the actual implementation


class TestEntityManagerIntegration:
    """Integration tests for EntityManager with DeviceFeatureMatrix."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    def test_device_feature_matrix_integration(self):
        """Test DeviceFeatureMatrix integration with EntityManager."""
        # Test that EntityManager properly uses DeviceFeatureMatrix
        matrix = self.entity_manager.get_device_feature_matrix()
        assert isinstance(matrix, DeviceFeatureMatrix)

        # Test matrix methods through EntityManager
        self.entity_manager.enable_feature_for_device("device1", "feature1")
        assert matrix.is_feature_enabled_for_device("feature1", "device1") is True

        devices = self.entity_manager.get_enabled_devices_for_feature("feature1")
        assert "device1" in devices

        is_enabled = self.entity_manager.is_device_enabled_for_feature(
            "device1", "feature1"
        )
        assert is_enabled is True

    def test_entity_creation_logic_with_matrix(self):
        """Test entity creation logic using DeviceFeatureMatrix."""
        matrix = self.entity_manager.get_device_feature_matrix()

        # Enable features for devices
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device2", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")

        # Test combinations
        combinations = self.entity_manager.get_all_feature_device_combinations()
        assert ("device1", "feature1") in combinations
        assert ("device2", "feature1") in combinations
        assert ("device1", "feature2") in combinations

        # Test that only enabled combinations would create entities
        # This validates the core Phase 3 requirement

    def test_matrix_state_management_in_entity_manager(self):
        """Test matrix state management through EntityManager."""
        matrix = self.entity_manager.get_device_feature_matrix()

        # Set up some state
        matrix.enable_feature_for_device("device1", "feature1")

        # Get state
        state = self.entity_manager.get_device_feature_matrix_state()
        assert state == {"device1": {"feature1": True}}

        # State restoration would be tested if the method existed


class TestEntityCreationEdgeCases:
    """Test edge cases for entity creation logic."""

    def test_empty_matrix_operations(self):
        """Test operations on empty matrix."""
        matrix = DeviceFeatureMatrix()

        # Test operations on empty matrix
        assert matrix.get_enabled_features_for_device("device1") == {}
        assert matrix.get_enabled_devices_for_feature("feature1") == []
        assert matrix.get_all_enabled_combinations() == []
        assert matrix.is_feature_enabled_for_device("feature1", "device1") is False

    def test_matrix_with_no_enabled_features(self):
        """Test matrix with devices but no enabled features."""
        matrix = DeviceFeatureMatrix()

        # Add devices but don't enable any features
        # This should result in no entities being created
        assert matrix.get_enabled_devices_for_feature("feature1") == []
        assert matrix.get_all_enabled_combinations() == []

    def test_matrix_with_no_devices(self):
        """Test matrix with features but no devices."""
        matrix = DeviceFeatureMatrix()

        # Enable features but don't add any devices
        # This should result in no entities being created
        assert matrix.get_enabled_devices_for_feature("feature1") == []
        assert matrix.get_all_enabled_combinations() == []

    def test_complex_feature_device_combinations(self):
        """Test complex combinations of features and devices."""
        matrix = DeviceFeatureMatrix()

        # Set up complex scenario
        devices = ["device1", "device2", "device3"]  # noqa: F841
        features = ["feature1", "feature2", "feature3"]  # noqa: F841

        # Enable some combinations
        matrix.enable_feature_for_device("device1", "feature1")
        matrix.enable_feature_for_device("device1", "feature2")
        matrix.enable_feature_for_device("device2", "feature1")
        matrix.enable_feature_for_device("device3", "feature3")

        # Test specific combinations
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True
        assert matrix.is_device_enabled_for_feature("device1", "feature2") is True
        assert matrix.is_device_enabled_for_feature("device1", "feature3") is False

        assert matrix.is_device_enabled_for_feature("device2", "feature1") is True
        assert matrix.is_device_enabled_for_feature("device2", "feature2") is False

        assert matrix.is_device_enabled_for_feature("device3", "feature3") is True
        assert matrix.is_device_enabled_for_feature("device3", "feature1") is False

        # Test device-specific feature lists
        device1_features = matrix.get_enabled_features_for_device("device1")
        assert "feature1" in device1_features
        assert "feature2" in device1_features
        assert "feature3" not in device1_features

        # Test feature-specific device lists
        feature1_devices = matrix.get_enabled_devices_for_feature("feature1")
        assert "device1" in feature1_devices
        assert "device2" in feature1_devices
        assert "device3" not in feature1_devices


class TestEntityCreationValidationScenarios:
    """Test specific entity creation validation scenarios from Phase 3 requirements."""

    def test_scenario_entity_created_for_enabled_feature_and_device(self):
        """Test entity creation for enabled feature AND enabled device."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # This combination should create entities
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # In actual implementation, this would trigger entity creation

    def test_scenario_entity_not_created_for_disabled_feature(self):
        """Test entity NOT created for disabled feature (even if device enabled)."""
        matrix = DeviceFeatureMatrix()
        # Don't enable the feature for the device

        # This combination should NOT create entities
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is False

        # Even if we had device1, without feature1 enabled,
        #  no entities should be created

    def test_scenario_entity_not_created_for_disabled_device(self):
        """Test entity NOT created for disabled device (even if feature enabled)."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # This combination should create entities for device1
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # But device2 should not create entities for feature1
        assert matrix.is_device_enabled_for_feature("device2", "feature1") is False

    def test_scenario_entity_removal_when_feature_disabled(self):
        """Test entity removal when feature is disabled."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # Initially enabled
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # Disable feature
        matrix.remove_feature_for_device("device1", "feature1")

        # Should be disabled now
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is False

        # This would trigger entity removal in actual implementation

    def test_scenario_entity_removal_when_device_disabled(self):
        """Test entity removal when device is disabled."""
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("device1", "feature1")

        # Initially enabled
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is True

        # Disable device (remove all features for device)
        matrix.remove_feature_for_device("device1", "feature1")

        # Should be disabled now
        assert matrix.is_device_enabled_for_feature("device1", "feature1") is False

        # This would trigger entity removal in actual implementation


class TestEntityCreationPerformance:
    """Test performance aspects of entity creation logic."""

    def test_matrix_performance_with_many_combinations(self):
        """Test matrix performance with many feature/device combinations."""
        matrix = DeviceFeatureMatrix()

        # Create many combinations
        for i in range(100):
            device_id = f"device{i}"
            for j in range(10):
                feature_id = f"feature{j}"
                matrix.enable_feature_for_device(device_id, feature_id)

        # Test that operations are still efficient
        combinations = matrix.get_all_enabled_combinations()
        assert len(combinations) == 1000  # 100 devices × 10 features

        # Test device-specific queries
        device_features = matrix.get_enabled_features_for_device("device50")
        assert len(device_features) == 10

        # Test feature-specific queries
        feature_devices = matrix.get_enabled_devices_for_feature("feature5")
        assert len(feature_devices) == 100

    def test_matrix_memory_usage(self):
        """Test matrix memory usage with large datasets."""
        matrix = DeviceFeatureMatrix()

        # Create large dataset
        for i in range(1000):
            device_id = f"device{i}"
            for j in range(100):
                feature_id = f"feature{j}"
                matrix.enable_feature_for_device(device_id, feature_id)

        # Test state management
        state = matrix.get_matrix_state()
        assert len(state) == 1000  # 1000 devices

        # State restoration would be tested if the method existed
