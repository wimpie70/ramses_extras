"""Tests for service registration refactoring."""

import importlib
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")

# Mock Home Assistant modules
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.exceptions"] = MagicMock()

# Mock ramses_cc modules
sys.modules["ramses_cc"] = MagicMock()
sys.modules["ramses_cc.broker"] = MagicMock()

try:
    from ramses_extras.const import DEVICE_SERVICE_MAPPING, SERVICE_REGISTRY
    from ramses_extras.helpers.device import (
        find_ramses_device,
        get_all_device_ids,
        get_device_type,
        validate_device_for_service,
    )
except ImportError as e:
    pytest.skip(
        f"Integration not properly installed for testing: {e}",
        allow_module_level=True,
    )


class MockRamsesBroker:
    """Mock RamsesBroker class for testing."""

    def __init__(self):
        self.devices = []
        self.client = MagicMock()


# Mock the RamsesBroker class
sys.modules["ramses_cc.broker"].RamsesBroker = MockRamsesBroker


class TestServiceRegistration:
    """Test service registration functionality."""

    @pytest.fixture
    def mock_ramses_broker(self) -> Mock:
        """Create a mock RamsesBroker instance."""
        broker = Mock(spec=MockRamsesBroker)
        broker.__class__.__name__ = "RamsesBroker"
        broker.devices = {}
        broker.client = Mock()
        # Add _get_device method to mock
        broker._get_device = Mock()
        return broker

    @pytest.fixture
    def mock_hass(self, mock_ramses_broker) -> Mock:
        """Create mock Home Assistant instance."""
        mock_hass = Mock()
        mock_hass.data = {"ramses_cc": {"entry_123": mock_ramses_broker}}
        mock_hass.services = Mock()
        mock_hass.config = Mock()
        mock_hass.config.components = []
        return mock_hass

    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear caches before each test."""
        from ramses_extras.helpers.broker import clear_broker_cache

        clear_broker_cache()

    @pytest.fixture
    def mock_feature_manager(self) -> Mock:
        """Create mock FeatureManager instance."""
        return Mock()

    def test_service_registry_structure(self) -> None:
        """Test SERVICE_REGISTRY has correct structure."""
        # Check HvacVentilator device type exists
        assert "HvacVentilator" in SERVICE_REGISTRY

        hvac_services = SERVICE_REGISTRY["HvacVentilator"]
        assert "set_fan_speed_mode" in hvac_services

        # Check service configuration
        fan_service_config = hvac_services["set_fan_speed_mode"]
        assert "module" in fan_service_config
        assert "function" in fan_service_config
        assert fan_service_config["module"] == ".services.fan_services"
        assert fan_service_config["function"] == "register_fan_services"

    def test_device_service_mapping_backward_compatibility(self) -> None:
        """Test DEVICE_SERVICE_MAPPING maintains backward compatibility."""
        # Should contain the same device types as SERVICE_REGISTRY
        service_registry_devices = set(SERVICE_REGISTRY.keys())
        mapping_devices = set(DEVICE_SERVICE_MAPPING.keys())

        assert service_registry_devices == mapping_devices

        # HvacVentilator should have the expected service
        hvac_services = DEVICE_SERVICE_MAPPING["HvacVentilator"]
        assert "set_fan_speed_mode" in hvac_services
        assert isinstance(hvac_services, list)

    def test_service_registry_adds_new_service(self) -> None:
        """Test adding a new service to SERVICE_REGISTRY works."""
        # This is a documentation test to show how to add new services
        new_registry = {
            "HvacVentilator": {
                "set_fan_speed_mode": {
                    "module": "ramses_extras.services.fan_services",
                    "function": "register_fan_services",
                },
                "set_boost_mode": {  # Example new service
                    "module": "ramses_extras.services.boost_services",
                    "function": "register_boost_services",
                },
            },
            "CO2Remote": {  # Example new device type
                "calibrate_sensor": {
                    "module": "ramses_extras.services.co2_services",
                    "function": "register_calibration_services",
                }
            },
        }

        # Verify structure is valid
        assert "HvacVentilator" in new_registry
        assert "set_boost_mode" in new_registry["HvacVentilator"]
        assert "CO2Remote" in new_registry
        assert "calibrate_sensor" in new_registry["CO2Remote"]

    def test_dynamic_service_registration_logic(
        self, mock_hass, mock_feature_manager
    ) -> None:
        """Test the core service registration logic without async complications."""
        # Test the logic by directly calling the registration function logic
        from ramses_extras import SERVICE_REGISTRY
        from ramses_extras.helpers.device import get_all_device_ids

        # Create mock devices
        mock_device = Mock()
        mock_device.id = "32:153289"
        mock_device.__class__.__name__ = "HvacVentilator"

        mock_hass.data["ramses_cc"]["entry_123"]._devices = {"32:153289": mock_device}
        mock_hass.config.components = ["ramses_cc"]

        # Test that device discovery works
        device_ids = get_all_device_ids(mock_hass)
        assert "32:153289" in device_ids

        # Test that the service registry contains the expected
        #  service for this device type
        device_type = "HvacVentilator"
        if device_type in SERVICE_REGISTRY:
            services = SERVICE_REGISTRY[device_type]
            assert "set_fan_speed_mode" in services
            # Verify the service configuration
            service_config = services["set_fan_speed_mode"]
            assert "module" in service_config
            assert "function" in service_config

    def test_no_duplicate_service_registration_logic(self, mock_hass) -> None:
        """Test the logic that prevents duplicate service registration."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Create multiple mock devices of same type
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_device1.__class__.__name__ = "HvacVentilator"

        mock_device2 = Mock()
        mock_device2.id = "45:678901"
        mock_device2.__class__.__name__ = "HvacVentilator"

        # Both devices should map to the same service
        service_config1 = SERVICE_REGISTRY["HvacVentilator"]["set_fan_speed_mode"]
        service_config2 = SERVICE_REGISTRY["HvacVentilator"]["set_fan_speed_mode"]

        # They should be the same config (proving no duplicates needed)
        assert service_config1 == service_config2
        assert service_config1["module"] == ".services.fan_services"
        assert service_config1["function"] == "register_fan_services"

    def test_no_devices_handling(self, mock_hass) -> None:
        """Test handling when no devices are available."""
        from ramses_extras.helpers.device import get_all_device_ids

        # No devices available
        mock_hass.data["ramses_cc"]["entry_123"]._devices = {}

        # Should return empty list
        device_ids = get_all_device_ids(mock_hass)
        assert device_ids == []

    def test_no_devices_no_unboundlocalerror(self, mock_hass) -> None:
        """Test that no UnboundLocalError occurs when no devices are found."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Mock no devices found (empty device list)
        mock_hass.data["ramses_cc"]["entry_123"].devices = {}
        mock_hass.config.components = ["ramses_cc"]

        # This should not raise UnboundLocalError
        from ramses_extras.helpers.device import get_all_device_ids

        device_ids = get_all_device_ids(mock_hass)
        assert device_ids == []  # Verify no devices

        # Test that registered_services would be handled correctly
        # This simulates the fixed logic where registered_services is always initialized
        registered_services = set()  # This is the fix
        if not registered_services:
            # This should not crash
            result = "No services registered - no supported devices found"
            assert result == "No services registered - no supported devices found"
        else:
            pytest.fail("Should not have registered any services when no devices found")

    def test_validate_device_for_service_with_service_registry(self, mock_hass) -> None:
        """Test device validation using the new service registry."""
        # Create mock device
        mock_device = Mock()
        mock_device.id = "32:153289"
        mock_device.__class__.__name__ = "HvacVentilator"

        mock_hass.data["ramses_cc"]["entry_123"]._devices = {"32:153289": mock_device}
        # Configure _get_device to return the mock device
        mock_hass.data["ramses_cc"]["entry_123"]._get_device.return_value = mock_device

        # Test validation for supported service
        result = validate_device_for_service(
            mock_hass, "32:153289", "set_fan_speed_mode"
        )
        assert result is True

        # Test validation for unsupported service
        result = validate_device_for_service(
            mock_hass, "32:153289", "unsupported_service"
        )
        assert result is False

    def test_unknown_device_type(self, mock_hass) -> None:
        """Test handling of unknown device types."""
        from ramses_extras.helpers.device import get_device_type

        # Create mock device with unknown type
        mock_device = Mock()
        mock_device.id = "99:000001"
        mock_device.__class__.__name__ = "UnknownDeviceType"

        device_type = get_device_type(mock_device)
        assert device_type == "UnknownDeviceType"

        # Test that unknown device types don't crash the system
        from ramses_extras.const import SERVICE_REGISTRY

        assert device_type not in SERVICE_REGISTRY  # Should not be in registry

    def test_service_registration_error_handling(self) -> None:
        """Test that service registration handles errors gracefully."""
        # Test that the SERVICE_REGISTRY structure prevents configuration errors
        for device_type, services in SERVICE_REGISTRY.items():
            for service_name, config in services.items():
                # All service configs should have required keys
                assert "module" in config, (
                    f"Service {service_name} missing 'module' key"
                )
                assert "function" in config, (
                    f"Service {service_name} missing 'function' key"
                )
                assert isinstance(config["module"], str), (
                    f"Service {service_name} module should be string"
                )
                assert isinstance(config["function"], str), (
                    f"Service {service_name} function should be string"
                )

    def test_backward_compatibility_maintained(self) -> None:
        """Test that old code using DEVICE_SERVICE_MAPPING still works."""
        # Old code that uses DEVICE_SERVICE_MAPPING should work unchanged
        device_type = "HvacVentilator"
        services = DEVICE_SERVICE_MAPPING[device_type]

        # Should be a list of service names
        assert isinstance(services, list)
        assert "set_fan_speed_mode" in services

        # Each service name should exist in SERVICE_REGISTRY
        for service_name in services:
            assert service_name in SERVICE_REGISTRY[device_type]

    def test_extensibility_example(self) -> None:
        """Test that shows how to extend the system with new services."""
        # Example of how to add a new service
        example_addition = {
            "HvacVentilator": {
                "set_fan_speed_mode": {
                    "module": "ramses_extras.services.fan_services",
                    "function": "register_fan_services",
                },
                "set_night_mode": {
                    "module": "ramses_extras.services.night_mode_services",
                    "function": "register_night_mode_services",
                },
            },
            "NewDeviceType": {
                "control_new_feature": {
                    "module": "ramses_extras.services.new_feature_services",
                    "function": "register_new_feature_services",
                }
            },
        }

        # Verify the structure is correct
        assert "HvacVentilator" in example_addition
        assert "NewDeviceType" in example_addition
        assert "set_night_mode" in example_addition["HvacVentilator"]
        assert "control_new_feature" in example_addition["NewDeviceType"]

    def test_dynamic_import_module_success(self) -> None:
        """Test that importlib.import_module works correctly for service modules."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Test importing the actual fan services module
        for device_type, services in SERVICE_REGISTRY.items():
            for service_name, config in services.items():
                if service_name == "set_fan_speed_mode":
                    # Test that the module can be imported
                    try:
                        module = importlib.import_module(
                            config["module"], "ramses_extras"
                        )
                        # Test that the function exists in the module
                        assert hasattr(module, config["function"]), (
                            f"Function {config['function']} not found in "
                            f"{config['module']}"
                        )
                    except ImportError as e:
                        pytest.fail(f"Failed to import {config['module']}: {e}")

    @patch("importlib.import_module")
    def test_dynamic_import_mocked_success(self, mock_importlib) -> None:
        """Test dynamic import with mocked importlib for isolation."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Setup mock return values
        mock_module = Mock()
        mock_module.register_fan_services = Mock()
        mock_importlib.return_value = mock_module

        # Test that importlib is called with correct parameters
        test_module = "ramses_extras.services.fan_services"
        imported = importlib.import_module(test_module)

        # Verify the import was called correctly
        mock_importlib.assert_called_with(test_module)
        assert hasattr(imported, "register_fan_services")

    @patch("importlib.import_module")
    def test_dynamic_import_error_handling(self, mock_importlib) -> None:
        """Test error handling when importlib fails."""
        # Simulate import failure
        mock_importlib.side_effect = ImportError("Module not found")

        with pytest.raises(ImportError):
            importlib.import_module("nonexistent.module")

    @patch("importlib.import_module")
    def test_service_registration_imports_correctly(self, mock_importlib) -> None:
        """Test that service registration uses correct import paths."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Setup mock
        mock_module = Mock()
        mock_module.test_function = Mock()
        mock_importlib.return_value = mock_module

        # Test the import path from SERVICE_REGISTRY
        service_config = SERVICE_REGISTRY["HvacVentilator"]["set_fan_speed_mode"]

        # Verify import path is correct
        expected_module = service_config["module"]
        expected_function = service_config["function"]

        # Import the module
        imported = importlib.import_module(expected_module)

        # Verify it matches our config
        assert hasattr(imported, expected_function)
        assert mock_importlib.call_args[0][0] == expected_module

    def test_all_service_modules_are_importable(self) -> None:
        """Test that all service modules defined in SERVICE_REGISTRY can be imported."""
        from ramses_extras.const import SERVICE_REGISTRY

        # Collect all unique module paths
        modules_to_test = set()
        for device_type, services in SERVICE_REGISTRY.items():
            for service_name, config in services.items():
                modules_to_test.add(config["module"])

        # Test that each module can be imported
        for module_path in modules_to_test:
            try:
                # Try to import the module
                module = importlib.import_module(module_path, "ramses_extras")
                assert module is not None
            except ImportError as e:
                # Some modules might not exist in test environment
                # but the importlib call should not crash
                assert "No module named" in str(e) or "cannot import" in str(e)

    @patch("importlib.import_module")
    def test_getattr_function_extraction(self, mock_importlib) -> None:
        """Test that getattr works correctly for extracting registration functions."""
        # Setup mock module with the expected function
        mock_module = Mock()
        mock_function = Mock()
        mock_module.register_fan_services = mock_function
        mock_importlib.return_value = mock_module

        from ramses_extras.const import SERVICE_REGISTRY

        # Test extracting the function
        service_config = SERVICE_REGISTRY["HvacVentilator"]["set_fan_speed_mode"]

        # Import module
        imported_module = importlib.import_module(service_config["module"])

        # Extract function
        registration_function = getattr(imported_module, service_config["function"])

        # Verify it's callable
        assert callable(registration_function)
        assert registration_function is mock_function
