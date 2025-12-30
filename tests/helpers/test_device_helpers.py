"""Tests for framework/helpers/device/core.py and filter.py."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ramses_extras.framework.helpers.device.core import (
    ensure_ramses_cc_loaded,
    extract_device_id_as_string,
    find_ramses_device,
    get_all_device_ids,
    get_device_type,
    validate_device_for_service,
)
from custom_components.ramses_extras.framework.helpers.device.filter import DeviceFilter


def test_extract_device_id_as_string():
    """Test extract_device_id_as_string."""
    assert extract_device_id_as_string("32:111") == "32:111"
    obj = MagicMock()
    obj.device_id = "32:222"
    assert extract_device_id_as_string(obj) == "32:222"
    obj = MagicMock(spec=[])
    obj.id = "32:333"
    assert extract_device_id_as_string(obj) == "32:333"
    obj = MagicMock(spec=[])
    obj._id = "32:444"
    assert extract_device_id_as_string(obj) == "32:444"
    obj = MagicMock(spec=[])
    obj.name = "32:555"
    assert extract_device_id_as_string(obj) == "32:555"
    obj = object()
    assert extract_device_id_as_string(obj).startswith("device_")


def test_find_ramses_device(hass):
    """Test find_ramses_device."""
    device_id = "32:111"
    hass.data = {}
    assert find_ramses_device(hass, device_id) is None
    hass.data = {"ramses_cc": {}}
    with MagicMock() as mock_entries:
        mock_entries.return_value = []
        with MagicMock() as mock_async_entries:
            mock_async_entries.return_value = []
            hass.config_entries.async_entries = mock_async_entries
            assert find_ramses_device(hass, device_id) is None
    mock_broker = MagicMock()
    mock_device = MagicMock()
    mock_broker._get_device.return_value = mock_device
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}
    hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])
    assert find_ramses_device(hass, device_id) == mock_device
    mock_broker._get_device.assert_called_with(device_id)
    mock_broker._get_device.return_value = None
    assert find_ramses_device(hass, device_id) is None


def test_get_device_type():
    """Test get_device_type."""
    assert get_device_type(None) == "None"

    class HvacVentilator:
        pass

    assert get_device_type(HvacVentilator()) == "HvacVentilator"
    mock_device = MagicMock()
    assert get_device_type(mock_device) == "MagicMock"


def test_validate_device_for_service(hass):
    """Test validate_device_for_service."""
    device_id = "32:111"
    mock_broker = MagicMock()
    mock_device = MagicMock()
    mock_broker._get_device.return_value = mock_device
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}
    hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])
    assert validate_device_for_service(hass, device_id, "test_service") is True


def test_get_all_device_ids(hass):
    """Test get_all_device_ids."""
    hass.data = {}
    assert get_all_device_ids(hass) == []
    mock_broker = MagicMock()
    dev1 = MagicMock()
    dev1.id = "32:1"
    dev2 = MagicMock()
    dev2.id = "32:2"
    mock_broker._devices = [dev1, dev2]
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}
    hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])
    assert get_all_device_ids(hass) == ["32:1", "32:2"]
    mock_broker._devices = {"32:3": {}, "32:4": {}}
    assert set(get_all_device_ids(hass)) == {"32:3", "32:4"}


def test_ensure_ramses_cc_loaded(hass):
    """Test ensure_ramses_cc_loaded."""
    hass.config.components = set()
    with pytest.raises(HomeAssistantError, match="integration is not loaded"):
        ensure_ramses_cc_loaded(hass)
    hass.config.components.add("ramses_cc")
    hass.data = {}
    with pytest.raises(HomeAssistantError, match="broker is not available"):
        ensure_ramses_cc_loaded(hass)
    hass.data = {"ramses_cc": {"entry_id": MagicMock()}}
    ensure_ramses_cc_loaded(hass)  # Should not raise


def test_device_filter():
    """Test DeviceFilter."""
    config = {"allowed_device_slugs": ["*"]}
    devices = [MagicMock(), MagicMock()]
    assert DeviceFilter.filter_devices_for_feature(config, devices) == devices
    config = {"allowed_device_slugs": ["FAN"]}
    fan_device = MagicMock()
    fan_device._SLUG = "FAN"
    hum_device = MagicMock()
    hum_device._SLUG = "HUM"
    devices = [fan_device, hum_device]
    filtered = DeviceFilter.filter_devices_for_feature(config, devices)
    assert len(filtered) == 1
    assert filtered[0] == fan_device
    devices = ["32:111"]
    assert DeviceFilter.filter_devices_for_feature(config, devices) == devices

    class HvacVentilator:
        pass

    fan_obj = HvacVentilator()
    assert "FAN" in DeviceFilter._get_device_slugs(fan_obj)


def test_get_device_slugs_variations():
    """Test _get_device_slugs with different attributes."""
    dev = MagicMock()
    dev.slugs = ["S1", "S2"]
    assert DeviceFilter._get_device_slugs(dev) == ["S1", "S2"]

    # 2) _SLUG attribute (not mock)
    dev = MagicMock(spec=[])
    dev._SLUG = "TEST"
    assert DeviceFilter._get_device_slugs(dev) == ["TEST"]

    # 3) slug attribute
    dev = MagicMock(spec=[])
    dev.slug = "S3"
    assert DeviceFilter._get_device_slugs(dev) == ["S3"]

    # 4) device_type attribute
    dev = MagicMock(spec=[])
    dev.device_type = "T1"
    assert DeviceFilter._get_device_slugs(dev) == ["T1"]

    # 5) unknown
    dev = MagicMock(spec=[])
    # No attributes, no class name that matches
    assert DeviceFilter._get_device_slugs(dev) == ["MagicMock"]  # From class name
