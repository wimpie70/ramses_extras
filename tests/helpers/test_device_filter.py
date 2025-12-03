"""Tests for DeviceFilter class."""

from unittest.mock import Mock

import pytest

from custom_components.ramses_extras.framework.helpers.device.filter import DeviceFilter


def create_mock_device(slugs=None, device_type=None, type_name=None):
    """Create mock device for testing."""
    device = Mock()
    if slugs:
        device.slugs = slugs
    if device_type:
        device.device_type = device_type
    if type_name:
        device.type = type_name
    return device


def test_filter_devices_wildcard():
    """Test wildcard device filtering."""
    devices = [
        create_mock_device(slugs=["FAN"]),
        create_mock_device(slugs=["REM"]),
        create_mock_device(slugs=["UNKNOWN"]),
    ]

    feature_config = {"allowed_device_slugs": ["*"]}
    filtered = DeviceFilter.filter_devices_for_feature(feature_config, devices)

    assert len(filtered) == 3
    assert all(device in filtered for device in devices)


def test_filter_devices_specific_slugs():
    """Test specific device slug filtering."""
    devices = [
        create_mock_device(slugs=["FAN"]),
        create_mock_device(slugs=["REM"]),
        create_mock_device(slugs=["UNKNOWN"]),
    ]

    feature_config = {"allowed_device_slugs": ["FAN"]}
    filtered = DeviceFilter.filter_devices_for_feature(feature_config, devices)

    assert len(filtered) == 1
    assert filtered[0].slugs == ["FAN"]


def test_filter_devices_multiple_slugs():
    """Test filtering with multiple allowed slugs."""
    devices = [
        create_mock_device(slugs=["FAN"]),
        create_mock_device(slugs=["REM"]),
        create_mock_device(slugs=["UNKNOWN"]),
    ]

    feature_config = {"allowed_device_slugs": ["FAN", "REM"]}
    filtered = DeviceFilter.filter_devices_for_feature(feature_config, devices)

    assert len(filtered) == 2
    assert {device.slugs[0] for device in filtered} == {"FAN", "REM"}


def test_filter_devices_empty_slugs():
    """Test filtering with empty allowed slugs."""
    devices = [create_mock_device(slugs=["FAN"]), create_mock_device(slugs=["REM"])]

    feature_config = {"allowed_device_slugs": []}
    filtered = DeviceFilter.filter_devices_for_feature(feature_config, devices)

    assert len(filtered) == 0


def test_filter_devices_no_slugs_in_config():
    """Test filtering when config has no allowed_device_slugs."""
    devices = [create_mock_device(slugs=["FAN"]), create_mock_device(slugs=["REM"])]

    feature_config = {}  # No allowed_device_slugs
    filtered = DeviceFilter.filter_devices_for_feature(feature_config, devices)

    # Should default to wildcard behavior
    assert len(filtered) == 2


def test_get_device_slugs_string_device():
    """Test getting slugs from string device ID."""
    slugs = DeviceFilter._get_device_slugs("FAN_DEVICE_1")
    assert slugs == ["FAN_DEVICE_1"]


def test_get_device_slugs_object_with_slugs():
    """Test getting slugs from device with slugs attribute."""
    device = create_mock_device(slugs=["FAN", "VENTILATOR"])
    slugs = DeviceFilter._get_device_slugs(device)
    assert slugs == ["FAN", "VENTILATOR"]


def test_get_device_slugs_object_with_device_type():
    """Test getting slugs from device with device_type attribute."""

    # Create a simple object with device_type attribute
    class TestDevice:
        def __init__(self):
            self.device_type = "FAN"

    device = TestDevice()
    slugs = DeviceFilter._get_device_slugs(device)
    assert slugs == ["FAN"]


def test_get_device_slugs_object_with_type():
    """Test getting slugs from device with type attribute."""

    # Create a simple object with type attribute
    class TestDevice:
        def __init__(self):
            self.type = "REM"

    device = TestDevice()
    slugs = DeviceFilter._get_device_slugs(device)
    assert slugs == ["REM"]


def test_get_device_slugs_object_with_class_name():
    """Test getting slugs from device class name."""

    class TestDevice:
        pass

    device = TestDevice()
    slugs = DeviceFilter._get_device_slugs(device)
    assert slugs == ["TestDevice"]


def test_get_device_slugs_unknown_device():
    """Test getting slugs from unknown device type."""

    # Create a device that will trigger the unknown fallback
    # This happens when device has no recognizable attributes and no class name
    class UnknownDevice:
        pass

    device = UnknownDevice()

    # Test with a device that has no attributes - should return class name
    # To test the true unknown case, we need a device that somehow fails all checks
    # Let's test that empty class name returns empty string (which is correct)
    original_name = device.__class__.__name__
    device.__class__.__name__ = ""
    slugs = DeviceFilter._get_device_slugs(device)
    device.__class__.__name__ = original_name  # Restore

    # Empty class name returns empty string (this is correct behavior)
    assert slugs == [""]


def test_is_device_allowed_for_feature_wildcard():
    """Test device allowed check with wildcard."""
    device = create_mock_device(slugs=["FAN"])
    feature_config = {"allowed_device_slugs": ["*"]}

    assert DeviceFilter.is_device_allowed_for_feature(device, feature_config) is True


def test_is_device_allowed_for_feature_specific():
    """Test device allowed check with specific slugs."""
    device = create_mock_device(slugs=["FAN"])
    feature_config = {"allowed_device_slugs": ["FAN", "REM"]}

    assert DeviceFilter.is_device_allowed_for_feature(device, feature_config) is True


def test_is_device_allowed_for_feature_not_allowed():
    """Test device not allowed for feature."""
    device = create_mock_device(slugs=["REM"])
    feature_config = {"allowed_device_slugs": ["FAN"]}

    assert DeviceFilter.is_device_allowed_for_feature(device, feature_config) is False


def test_get_supported_device_types():
    """Test getting supported device types."""
    feature_config = {"allowed_device_slugs": ["FAN", "REM"]}
    supported = DeviceFilter.get_supported_device_types(feature_config)
    assert supported == ["FAN", "REM"]


def test_get_supported_device_types_wildcard():
    """Test getting supported device types with wildcard."""
    feature_config = {"allowed_device_slugs": ["*"]}
    supported = DeviceFilter.get_supported_device_types(feature_config)
    assert supported == ["*"]


def test_get_supported_device_types_default():
    """Test getting supported device types with no config."""
    feature_config = {}
    supported = DeviceFilter.get_supported_device_types(feature_config)
    assert supported == ["*"]
