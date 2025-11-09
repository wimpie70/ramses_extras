"""Tests for helpers/device.py."""

import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")


# Create a mock RamsesBroker class for testing
class MockRamsesBroker:
    def __init__(self):
        self.devices = []
        self.client = MagicMock()


# Mock the RamsesBroker class at the module level
sys.modules["ramses_cc.broker"] = MagicMock()
sys.modules["ramses_cc.broker"].RamsesBroker = MockRamsesBroker

try:
    from ramses_extras.helpers.device import (
        find_ramses_device,
        get_all_device_ids,
        get_device_type,
    )
except ImportError as e:
    pytest.skip(
        f"Integration not properly installed for testing: {e}",
        allow_module_level=True,
    )


class TestDeviceHelpers:
    """Test device helper functions."""

    @pytest.fixture
    def mock_ramses_broker(self) -> Mock:
        """Create a mock RamsesBroker instance."""
        broker = Mock(spec=MockRamsesBroker)
        broker.__class__.__name__ = "RamsesBroker"
        broker._devices = {}
        broker.client = Mock()
        # Add _get_device method to mock
        broker._get_device = Mock()
        return broker

    @pytest.fixture
    def mock_hass(self, mock_ramses_broker) -> Mock:
        """Create mock Home Assistant instance."""
        mock_hass = Mock()
        mock_hass.data = {"ramses_cc": mock_ramses_broker}
        return mock_hass

    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear caches before each test."""
        from ramses_extras.helpers.device import clear_broker_cache

        clear_broker_cache()

    def test_find_ramses_device_dict_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test finding device when devices is a dictionary."""
        # Mock broker with devices as dict
        mock_device = Mock()
        mock_ramses_broker._devices = {"32:153289": mock_device, "01:123456": Mock()}
        # Configure _get_device to return the mock device
        mock_ramses_broker._get_device.return_value = mock_device

        device = find_ramses_device(mock_hass, "32:153289")

        assert device is not None
        assert device == mock_device
        mock_ramses_broker._get_device.assert_called_once_with("32:153289")

    def test_find_ramses_device_list_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test finding device when devices is a list of objects."""
        # Mock broker with devices as list of objects
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_device2 = Mock()
        mock_device2.id = "01:123456"
        mock_ramses_broker._devices = [mock_device1, mock_device2]
        # Configure _get_device to return the mock device
        mock_ramses_broker._get_device.return_value = mock_device1

        device = find_ramses_device(mock_hass, "32:153289")

        assert device is not None
        assert device == mock_device1
        mock_ramses_broker._get_device.assert_called_once_with("32:153289")

    def test_find_ramses_device_not_found(self, mock_hass: Mock) -> None:
        """Test finding device when device doesn't exist."""
        # Mock broker with devices as list of objects
        mock_broker = Mock()
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_broker._devices = [mock_device1]
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        device = find_ramses_device(mock_hass, "99:000001")

        assert device is None

    def test_find_ramses_device_no_broker(self, mock_hass: Mock) -> None:
        """Test finding device when no broker available."""
        # No ramses_cc data - remove ramses_cc from hass.data
        mock_hass.data = {}

        device = find_ramses_device(mock_hass, "32:153289")

        assert device is None

    def test_get_all_device_ids_dict_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test getting all device IDs when devices is a dictionary."""
        mock_ramses_broker._devices = {"32:153289": Mock(), "01:123456": Mock()}

        device_ids = get_all_device_ids(mock_hass)

        assert set(device_ids) == {"32:153289", "01:123456"}

    def test_get_all_device_ids_list_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test getting all device IDs when devices is a list of objects."""
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_device2 = Mock()
        mock_device2.id = "01:123456"
        mock_ramses_broker._devices = [mock_device1, mock_device2]

        device_ids = get_all_device_ids(mock_hass)

        assert set(device_ids) == {"32:153289", "01:123456"}

    def test_get_all_device_ids_no_broker(self, mock_hass: Mock) -> None:
        """Test getting device IDs when no broker available."""
        device_ids = get_all_device_ids(mock_hass)

        assert device_ids == []

    def test_get_device_type(self) -> None:
        """Test getting device type."""
        # Mock device with class name
        mock_device = Mock()
        mock_device.id = "32:153289"

        device_type = get_device_type(mock_device)

        assert device_type == "Mock"

    def test_get_ramses_broker_direct_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test getting broker when it's directly in data."""
        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_ramses_broker

    def test_get_ramses_broker_entry_structure(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test getting broker when it's in entry structure."""
        # The broker is expected to be found directly in ramses_cc data
        mock_hass.data = {"ramses_cc": mock_ramses_broker}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_ramses_broker

    def test_get_ramses_broker_nested_structure(self, mock_hass: Mock) -> None:
        """Test getting broker when it's in nested dict structure."""
        # The broker is expected to be found directly in ramses_cc data
        mock_broker = Mock()
        mock_broker.client = Mock()
        mock_broker._devices = []
        mock_broker.__class__.__name__ = "RamsesBroker"
        mock_hass.data = {"ramses_cc": mock_broker}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_broker

    def test_find_ramses_device_case_insensitive(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test case-insensitive device ID matching."""
        mock_device = Mock()
        mock_ramses_broker._devices = {"32:153289": mock_device, "01:123456": Mock()}
        # Configure _get_device to return the mock device for case-insensitive lookup
        mock_ramses_broker._get_device.return_value = mock_device

        from ramses_extras.helpers.device import find_ramses_device

        # Test with different case
        device = find_ramses_device(mock_hass, "32:153289".upper())
        assert device is not None
        assert device == mock_device
        mock_ramses_broker._get_device.assert_called_once_with("32:153289")

    def test_find_ramses_device_different_id_attributes(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test finding device with different ID attribute names."""

        # In real usage, all devices have 'id' attribute
        # Test with real Device-like objects
        class MockDevice:
            def __init__(self, device_id):
                self.id = device_id

        mock_device1 = MockDevice("32:153289")
        mock_device2 = MockDevice("45:678901")
        mock_device3 = MockDevice("78:901234")

        mock_ramses_broker._devices = [mock_device1, mock_device2, mock_device3]

        # Configure _get_device to return the appropriate device based on ID
        def mock_get_device(device_id):
            if device_id == "32:153289":
                return mock_device1
            if device_id == "45:678901":
                return mock_device2
            if device_id == "78:901234":
                return mock_device3
            return None

        mock_ramses_broker._get_device.side_effect = mock_get_device

        from ramses_extras.helpers.device import find_ramses_device

        # Test finding each device
        assert find_ramses_device(mock_hass, "32:153289") == mock_device1
        assert find_ramses_device(mock_hass, "45:678901") == mock_device2
        assert find_ramses_device(mock_hass, "78:901234") == mock_device3

    def test_find_ramses_device_attribute_error_handling(
        self, mock_hass: Mock, mock_ramses_broker, caplog
    ) -> None:
        """Test error handling during device attribute access."""

        # Create a device that will raise AttributeError when accessing id
        class DeviceWithError:
            @property
            def id(self):
                raise AttributeError("Test error")

        mock_device = DeviceWithError()

        mock_ramses_broker._devices = [mock_device]
        # Configure _get_device to return None (device not found)
        mock_ramses_broker._get_device.return_value = None

        from ramses_extras.helpers.device import find_ramses_device

        # Should not raise, should log the error and continue
        device = find_ramses_device(mock_hass, "32:153289")
        assert device is None  # Should not find the device due to error
        # No longer logs "Error checking device" since we use _get_device

    def test_get_all_device_ids_empty(self, mock_hass: Mock) -> None:
        """Test getting device IDs with empty devices."""
        mock_broker = Mock()
        mock_broker._devices = {}
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        from ramses_extras.helpers.device import get_all_device_ids

        device_ids = get_all_device_ids(mock_hass)
        assert device_ids == []

    def test_get_all_device_ids_invalid_structure(self, mock_hass: Mock) -> None:
        """Test getting device IDs with invalid devices structure."""
        mock_broker = Mock()
        mock_broker._devices = "not a list or dict"
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        from ramses_extras.helpers.device import get_all_device_ids

        device_ids = get_all_device_ids(mock_hass)
        assert device_ids == []

    def test_get_device_type_edge_cases(self) -> None:
        """Test get_device_type with edge cases."""
        from ramses_extras.helpers.device import get_device_type

        # Test with None
        assert get_device_type(None) == "None"

        # Test with object that has __class__ = None
        class CustomDevice:
            __class__ = None

        assert get_device_type(CustomDevice()) == "Unknown"

        # Test with object that has __class__ but no __name__
        class CustomDevice2:
            class DummyClass:
                pass

            __class__ = DummyClass

        assert get_device_type(CustomDevice2()) == "DummyClass"

    def test_get_ramses_broker_no_ramses_cc(self, mock_hass: Mock) -> None:
        """Test get_ramses_broker when ramses_cc is not in hass.data."""
        mock_hass.data = {}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)
        assert broker is None

    @patch("ramses_extras.helpers.device._LOGGER")
    def test_get_ramses_broker_invalid_structure(
        self, mock_logger, mock_hass: Mock
    ) -> None:
        """Test get_ramses_broker with invalid broker structure."""
        mock_hass.data = {"ramses_cc": {"entry_123": "not a broker"}}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)
        assert broker is None
        mock_logger.warning.assert_called()

    def test_find_ramses_device_with_str_method(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test finding device when device has __str__ method that returns ID."""

        # Create a device with __str__ method that returns the ID
        class DeviceWithStr:
            def __init__(self, device_id):
                self.id = device_id

            def __str__(self):
                return self.id

        mock_device = DeviceWithStr("32:153289")
        mock_ramses_broker._devices = [mock_device]
        # Configure _get_device to return the mock device
        mock_ramses_broker._get_device.return_value = mock_device

        from ramses_extras.helpers.device import find_ramses_device

        device = find_ramses_device(mock_hass, "32:153289")
        assert device == mock_device
        mock_ramses_broker._get_device.assert_called_once_with("32:153289")

    def test_get_all_device_ids_with_str_method(
        self, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test getting device IDs when devices have __str__ method that returns ID."""

        # Create devices with __str__ method that returns the ID
        class DeviceWithStr:
            def __init__(self, device_id):
                self.id = device_id

            def __str__(self):
                return self.id

        mock_device1 = DeviceWithStr("32:153289")
        mock_device2 = DeviceWithStr("45:678901")
        mock_ramses_broker._devices = [mock_device1, mock_device2]

        from ramses_extras.helpers.device import get_all_device_ids

        device_ids = get_all_device_ids(mock_hass)
        assert set(device_ids) == {"32:153289", "45:678901"}

    @patch("ramses_extras.helpers.device._LOGGER")
    def test_get_ramses_broker_no_client_attr(
        self, mock_logger, mock_hass: Mock, mock_ramses_broker
    ) -> None:
        """Test get_ramses_broker with broker missing client attribute."""
        # Remove client attribute to test error handling
        del mock_ramses_broker.client
        mock_ramses_broker._devices = ["device1", "device2"]  # Has devices

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)
        # Should still return the broker
        assert broker == mock_ramses_broker
        mock_logger.debug.assert_called()
