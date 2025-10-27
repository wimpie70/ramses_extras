"""Tests for helpers/device.py."""

import sys
from unittest.mock import Mock

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")

try:
    from ramses_extras.helpers.device import (
        find_ramses_device,
        get_all_device_ids,
        get_device_type,
    )
except ImportError:
    pytest.skip(
        "Integration not properly installed for testing",
        allow_module_level=True,
    )


class TestDeviceHelpers:
    """Test device helper functions."""

    @pytest.fixture
    def mock_hass(self) -> Mock:
        """Create mock Home Assistant instance."""
        mock_hass = Mock()
        mock_hass.data = {}
        return mock_hass

    def test_find_ramses_device_dict_structure(self, mock_hass: Mock) -> None:
        """Test finding device when devices is a dictionary."""
        # Mock broker with devices as dict
        mock_broker = Mock()
        mock_broker.devices = {"32:153289": Mock(), "01:123456": Mock()}
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        device = find_ramses_device(mock_hass, "32:153289")

        assert device is not None
        assert device == mock_broker.devices["32:153289"]

    def test_find_ramses_device_list_structure(self, mock_hass: Mock) -> None:
        """Test finding device when devices is a list of objects."""
        # Mock broker with devices as list of objects
        mock_broker = Mock()
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_device2 = Mock()
        mock_device2.id = "01:123456"
        mock_broker.devices = [mock_device1, mock_device2]
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        device = find_ramses_device(mock_hass, "32:153289")

        assert device is not None
        assert device == mock_device1

    def test_find_ramses_device_not_found(self, mock_hass: Mock) -> None:
        """Test finding device when device doesn't exist."""
        # Mock broker with devices as list of objects
        mock_broker = Mock()
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_broker.devices = [mock_device1]
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        device = find_ramses_device(mock_hass, "99:000001")

        assert device is None

    def test_find_ramses_device_no_broker(self, mock_hass: Mock) -> None:
        """Test finding device when no broker available."""
        # No ramses_cc data
        device = find_ramses_device(mock_hass, "32:153289")

        assert device is None

    def test_get_all_device_ids_dict_structure(self, mock_hass: Mock) -> None:
        """Test getting all device IDs when devices is a dictionary."""
        mock_broker = Mock()
        mock_broker.devices = {"32:153289": Mock(), "01:123456": Mock()}
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        device_ids = get_all_device_ids(mock_hass)

        assert set(device_ids) == {"32:153289", "01:123456"}

    def test_get_all_device_ids_list_structure(self, mock_hass: Mock) -> None:
        """Test getting all device IDs when devices is a list of objects."""
        mock_broker = Mock()
        mock_device1 = Mock()
        mock_device1.id = "32:153289"
        mock_device2 = Mock()
        mock_device2.id = "01:123456"
        mock_broker.devices = [mock_device1, mock_device2]
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

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

    def test_get_ramses_broker_direct_structure(self, mock_hass: Mock) -> None:
        """Test getting broker when it's directly in data."""
        mock_broker = Mock()
        mock_broker.client = Mock()
        mock_broker.devices = []
        mock_hass.data = {"ramses_cc": mock_broker}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_broker

    def test_get_ramses_broker_entry_structure(self, mock_hass: Mock) -> None:
        """Test getting broker when it's in entry structure."""
        mock_broker = Mock()
        mock_broker.client = Mock()
        mock_broker.devices = []
        mock_hass.data = {"ramses_cc": {"entry_123": mock_broker}}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_broker

    def test_get_ramses_broker_nested_structure(self, mock_hass: Mock) -> None:
        """Test getting broker when it's in nested dict structure."""
        mock_broker = Mock()
        mock_broker.client = Mock()
        mock_broker.devices = []
        mock_hass.data = {"ramses_cc": {"entry_123": {"broker": mock_broker}}}

        from ramses_extras.helpers.device import get_ramses_broker

        broker = get_ramses_broker(mock_hass)

        assert broker == mock_broker
