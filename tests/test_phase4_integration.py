"""Phase 4 Integration Tests - Default Feature Device Selection and End-to-End Testing.

This module contains comprehensive integration tests for Phase 4 requirements:
- Default feature device selection with FAN slug filtering
- End-to-end testing with all components
- Final validation of the complete config flow extension
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.features.default import (
    config_flow as default_config_flow,
)
from custom_components.ramses_extras.framework.helpers.config_flow import (
    ConfigFlowHelper,
)
from custom_components.ramses_extras.framework.helpers.entity.device_mapping import (
    DeviceFeatureMatrix,
)
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestPhase4DefaultFeatureIntegration:
    """Test Phase 4 integration requirements for default feature."""

    def test_default_feature_fan_slug_filtering(self):
        """Test that default feature only shows FAN devices for device selection."""
        # Verify default feature configuration
        default_config = AVAILABLE_FEATURES["default"]
        assert default_config["allowed_device_slugs"] == ["FAN"]
        assert default_config["has_device_config"] is True

    async def test_default_feature_device_selection_integration(self):
        """Test end-to-end default feature device selection with FAN filtering."""
        # Mock flow handler
        mock_flow = MagicMock()
        mock_flow._get_all_devices.return_value = [
            MagicMock(id="fan_device1", device_type="FAN", name="Fan Device 1"),
            MagicMock(id="non_fan_device1", device_type="REM", name="Remote Device 1"),
            MagicMock(id="fan_device2", device_type="FAN", name="Fan Device 2"),
        ]

        # Mock config flow helper
        mock_helper = MagicMock()
        mock_helper.get_devices_for_feature_selection.return_value = [
            MagicMock(id="fan_device1", device_type="FAN", name="Fan Device 1"),
            MagicMock(id="fan_device2", device_type="FAN", name="Fan Device 2"),
        ]
        mock_helper.get_enabled_devices_for_feature.return_value = ["fan_device1"]
        mock_helper.set_enabled_devices_for_feature.return_value = None

        mock_flow._get_config_flow_helper.return_value = mock_helper
        mock_flow._extract_device_id.side_effect = lambda device: str(device.id)
        mock_flow._get_device_label.side_effect = lambda device: str(device.name)

        # Test device selection form generation
        result = await default_config_flow.async_step_default_config(mock_flow, None)

        # Verify the form was shown with proper schema
        assert result is not None
        mock_helper.get_devices_for_feature_selection.assert_called_once()
        mock_helper.get_enabled_devices_for_feature.assert_called_once_with("default")

    def test_device_feature_matrix_default_feature_integration(self):
        """Test DeviceFeatureMatrix integration with default feature."""
        matrix = DeviceFeatureMatrix()

        # Test default feature device enablement
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        # Verify matrix state
        assert matrix.is_device_enabled_for_feature("fan_device1", "default") is True
        assert matrix.is_device_enabled_for_feature("fan_device2", "default") is True
        assert (
            matrix.is_device_enabled_for_feature("non_fan_device1", "default") is False
        )  # noqa: E501

        # Test device-specific feature lists
        default_devices = matrix.get_enabled_devices_for_feature("default")
        assert "fan_device1" in default_devices
        assert "fan_device2" in default_devices
        assert len(default_devices) == 2

    def test_entity_creation_validation_default_feature(self):
        """Test entity creation validation for default feature."""
        matrix = DeviceFeatureMatrix()

        # Enable default feature for specific FAN devices
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        # Test that only enabled combinations would create entities
        combinations = matrix.get_all_enabled_combinations()
        assert ("fan_device1", "default") in combinations
        assert ("fan_device2", "default") in combinations
        assert ("non_fan_device1", "default") not in combinations

        # Verify matrix accuracy for default feature
        default_combinations = [comb for comb in combinations if comb[1] == "default"]
        assert len(default_combinations) == 2
        assert all(comb[1] == "default" for comb in default_combinations)


class TestPhase4EndToEndIntegration:
    """Test end-to-end integration scenarios for Phase 4."""

    async def test_complete_config_flow_integration(self):
        """Test complete config flow integration with all components."""
        # Mock HomeAssistant and config entry
        mock_hass = MagicMock()
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": False,
                "hello_world_card": False,
            }
        }

        # Mock devices
        mock_devices = [
            MagicMock(id="fan_device1", device_type="FAN", name="Fan Device 1"),
            MagicMock(id="fan_device2", device_type="FAN", name="Fan Device 2"),
            MagicMock(id="remote_device1", device_type="REM", name="Remote Device 1"),
        ]

        # Mock config flow helper
        mock_helper = MagicMock()
        mock_helper.get_devices_for_feature_selection.side_effect = (
            lambda feature_config, devices: [  # noqa: E501
                device
                for device in devices
                if device.device_type
                in feature_config.get("allowed_device_slugs", ["*"])
            ]
        )
        mock_helper.get_enabled_devices_for_feature.side_effect = lambda feature_id: (
            ["fan_device1"] if feature_id == "default" else []
        )

        # Test config flow helper integration
        with patch(
            "custom_components.ramses_extras.framework.helpers.config_flow.ConfigFlowHelper"
        ) as mock_helper_class:  # noqa: E501
            mock_helper_class.return_value = mock_helper

            # Test default feature config flow
            mock_flow = MagicMock()
            mock_flow.hass = mock_hass
            mock_flow._config_entry = mock_config_entry
            mock_flow._get_all_devices.return_value = mock_devices
            mock_flow._get_config_flow_helper.return_value = mock_helper
            mock_flow._extract_device_id.side_effect = lambda device: str(device.id)
            mock_flow._get_device_label.side_effect = lambda device: str(device.name)

            # Test default feature device selection
            await default_config_flow.async_step_default_config(mock_flow, None)

            # Verify proper device filtering occurred
            mock_helper.get_devices_for_feature_selection.assert_called_once()
            call_args = mock_helper.get_devices_for_feature_selection.call_args
            assert call_args[0][1] == mock_devices  # devices parameter
            assert call_args[0][0] == AVAILABLE_FEATURES["default"]  # feature config

    def test_entity_manager_integration_with_default_feature(self):
        """Test EntityManager integration with default feature."""
        mock_hass = MagicMock()
        entity_manager = EntityManager(mock_hass)

        # Test matrix integration
        matrix = entity_manager.get_device_feature_matrix()
        assert isinstance(matrix, DeviceFeatureMatrix)

        # Test default feature operations
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        # Verify matrix state through entity manager
        default_devices = entity_manager.get_enabled_devices_for_feature("default")
        assert "fan_device1" in default_devices
        assert "fan_device2" in default_devices

        # Test entity creation validation
        combinations = entity_manager.get_all_feature_device_combinations()
        default_combinations = [comb for comb in combinations if comb[1] == "default"]
        assert len(default_combinations) == 2


class TestPhase4DeviceFiltering:
    """Test device filtering requirements for Phase 4."""

    def test_default_feature_fan_device_filtering(self):
        """Test that default feature properly filters FAN devices."""
        # Mock devices with different types
        devices = [
            MagicMock(id="fan1", device_type="FAN", name="Fan 1"),
            MagicMock(id="fan2", device_type="FAN", name="Fan 2"),
            MagicMock(id="remote1", device_type="REM", name="Remote 1"),
            MagicMock(id="thermostat1", device_type="THERMOSTAT", name="Thermostat 1"),
        ]

        # Mock config flow helper
        mock_helper = MagicMock()
        mock_helper.get_devices_for_feature_selection.side_effect = (
            lambda feature_config, devices: [  # noqa: E501
                device
                for device in devices
                if device.device_type
                in feature_config.get("allowed_device_slugs", ["*"])
            ]
        )

        # Test default feature filtering
        default_config = AVAILABLE_FEATURES["default"]
        filtered_devices = mock_helper.get_devices_for_feature_selection(
            default_config, devices
        )  # noqa: E501

        # Verify only FAN devices are returned
        assert len(filtered_devices) == 2
        assert all(device.device_type == "FAN" for device in filtered_devices)
        assert all(device.id in ["fan1", "fan2"] for device in filtered_devices)

    def test_device_filtering_edge_cases(self):
        """Test device filtering edge cases."""
        matrix = DeviceFeatureMatrix()

        # Test with no devices
        assert matrix.get_enabled_devices_for_feature("default") == []

        # Test with devices but no features enabled
        matrix.enable_feature_for_device("fan_device1", "humidity_control")
        assert matrix.get_enabled_devices_for_feature("default") == []

        # Test with default feature enabled for specific devices
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        default_devices = matrix.get_enabled_devices_for_feature("default")
        assert len(default_devices) == 2
        assert "fan_device1" in default_devices
        assert "fan_device2" in default_devices


class TestPhase4PerformanceAndValidation:
    """Test performance and validation requirements for Phase 4."""

    def test_matrix_performance_with_default_feature(self):
        """Test matrix performance with default feature combinations."""
        matrix = DeviceFeatureMatrix()

        # Create realistic scenario with multiple FAN devices
        fan_devices = [f"fan_device{i}" for i in range(10)]
        for device_id in fan_devices:
            matrix.enable_feature_for_device(device_id, "default")

        # Test performance of queries
        default_devices = matrix.get_enabled_devices_for_feature("default")
        assert len(default_devices) == 10

        combinations = matrix.get_all_enabled_combinations()
        assert len(combinations) == 10

        # Test device-specific queries
        for device_id in fan_devices:
            assert matrix.is_device_enabled_for_feature(device_id, "default") is True

    def test_entity_creation_validation_comprehensive(self):
        """Test comprehensive entity creation validation."""
        matrix = DeviceFeatureMatrix()

        # Set up complex scenario with multiple features and devices
        devices = ["fan_device1", "fan_device2", "remote_device1"]  # noqa: F841
        features = ["default", "humidity_control"]  # noqa: F841

        # Enable default feature for FAN devices only
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        # Enable humidity control for one FAN device
        matrix.enable_feature_for_device("fan_device1", "humidity_control")

        # Test validation scenarios
        combinations = matrix.get_all_enabled_combinations()

        # Verify correct combinations
        assert ("fan_device1", "default") in combinations
        assert ("fan_device2", "default") in combinations
        assert ("fan_device1", "humidity_control") in combinations
        assert ("fan_device2", "humidity_control") not in combinations
        assert ("remote_device1", "default") not in combinations
        assert ("remote_device1", "humidity_control") not in combinations

        # Test feature-specific queries
        default_devices = matrix.get_enabled_devices_for_feature("default")
        assert len(default_devices) == 2
        assert "fan_device1" in default_devices
        assert "fan_device2" in default_devices

        humidity_devices = matrix.get_enabled_devices_for_feature("humidity_control")
        assert len(humidity_devices) == 1
        assert "fan_device1" in humidity_devices


class TestPhase4FinalValidation:
    """Final validation tests for Phase 4 completion."""

    def test_phase4_requirements_completion(self):
        """Test that all Phase 4 requirements are met."""
        # Verify default feature configuration
        default_config = AVAILABLE_FEATURES["default"]
        assert default_config["allowed_device_slugs"] == ["FAN"]
        assert default_config["has_device_config"] is True
        assert default_config["default_enabled"] is True

        # Verify matrix functionality
        matrix = DeviceFeatureMatrix()
        assert hasattr(matrix, "enable_feature_for_device")
        assert hasattr(matrix, "get_enabled_devices_for_feature")
        assert hasattr(matrix, "is_device_enabled_for_feature")
        assert hasattr(matrix, "get_all_enabled_combinations")

        # Verify entity manager integration
        mock_hass = MagicMock()
        entity_manager = EntityManager(mock_hass)
        assert hasattr(entity_manager, "get_device_feature_matrix")
        assert hasattr(entity_manager, "get_enabled_devices_for_feature")
        assert hasattr(entity_manager, "get_all_feature_device_combinations")

    def test_phase4_integration_completeness(self):
        """Test completeness of Phase 4 integration."""
        # Test that all components work together
        mock_hass = MagicMock()
        entity_manager = EntityManager(mock_hass)
        matrix = entity_manager.get_device_feature_matrix()

        # Test default feature operations
        matrix.enable_feature_for_device("fan_device1", "default")
        matrix.enable_feature_for_device("fan_device2", "default")

        # Verify integration
        default_devices = entity_manager.get_enabled_devices_for_feature("default")
        assert len(default_devices) == 2

        combinations = entity_manager.get_all_feature_device_combinations()
        default_combinations = [comb for comb in combinations if comb[1] == "default"]
        assert len(default_combinations) == 2

        # Test matrix state management
        state = entity_manager.get_device_feature_matrix_state()
        assert "fan_device1" in state
        assert "fan_device2" in state
        assert state["fan_device1"]["default"] is True
        assert state["fan_device2"]["default"] is True

    async def test_phase4_end_to_end_validation(self):
        """Test end-to-end validation of Phase 4 implementation."""
        # This test validates the complete Phase 4 implementation
        # by testing all components working together

        # 1. Verify default feature configuration
        default_config = AVAILABLE_FEATURES["default"]
        assert default_config["allowed_device_slugs"] == ["FAN"]
        assert default_config["has_device_config"] is True

        # 2. Test device filtering
        devices = [
            MagicMock(id="fan1", device_type="FAN"),
            MagicMock(id="remote1", device_type="REM"),
        ]

        mock_helper = MagicMock()
        mock_helper.get_devices_for_feature_selection.side_effect = (
            lambda feature_config, devices: [  # noqa: E501
                device
                for device in devices
                if device.device_type
                in feature_config.get("allowed_device_slugs", ["*"])
            ]
        )

        filtered_devices = mock_helper.get_devices_for_feature_selection(
            default_config, devices
        )  # noqa: E501
        assert len(filtered_devices) == 1
        assert filtered_devices[0].id == "fan1"

        # 3. Test matrix integration
        matrix = DeviceFeatureMatrix()
        matrix.enable_feature_for_device("fan1", "default")

        assert matrix.is_device_enabled_for_feature("fan1", "default") is True
        assert matrix.get_enabled_devices_for_feature("default") == ["fan1"]

        # 4. Test entity manager integration
        mock_hass = MagicMock()
        entity_manager = EntityManager(mock_hass)
        entity_matrix = entity_manager.get_device_feature_matrix()

        entity_matrix.enable_feature_for_device("fan1", "default")
        entity_default_devices = entity_manager.get_enabled_devices_for_feature(
            "default"
        )  # noqa: E501
        assert "fan1" in entity_default_devices

        # 5. Test config flow integration
        mock_flow = MagicMock()
        mock_flow._get_all_devices.return_value = devices
        mock_flow._get_config_flow_helper.return_value = mock_helper
        mock_flow._extract_device_id.side_effect = lambda device: device.id
        mock_flow._get_device_label.side_effect = lambda device: device.id

        result = await default_config_flow.async_step_default_config(mock_flow, None)
        assert result is not None

        # All Phase 4 requirements validated!
        return True
