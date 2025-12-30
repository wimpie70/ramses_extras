"""Tests for Device Filter Helper."""

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.device.filter import DeviceFilter


class TestDeviceFilter:
    """Test DeviceFilter class."""

    def test_filter_devices_for_feature_wildcard(self):
        """Test wildcard filtering returns all devices."""
        feature_config = {"allowed_device_slugs": ["*"]}
        devices = ["dev1", "dev2"]
        result = DeviceFilter.filter_devices_for_feature(feature_config, devices)
        assert result == devices

    def test_filter_devices_for_feature_string_fallback(self):
        """Test that plain strings are always included."""
        feature_config = {"allowed_device_slugs": ["FAN"], "name": "test"}
        devices = ["32:123456"]
        result = DeviceFilter.filter_devices_for_feature(feature_config, devices)
        assert result == ["32:123456"]

    def test_filter_devices_for_feature_match(self):
        """Test filtering with matching slugs."""
        feature_config = {"allowed_device_slugs": ["FAN"]}

        class FanDevice:
            _SLUG = "FAN"

            def __str__(self):
                return "FAN_DEVICE"

        class Co2Device:
            _SLUG = "CO2"

            def __str__(self):
                return "CO2_DEVICE"

        mock_fan = FanDevice()
        mock_co2 = Co2Device()

        devices = [mock_fan, mock_co2]
        result = DeviceFilter.filter_devices_for_feature(feature_config, devices)
        assert result == [mock_fan]

    def test_get_device_slugs_string(self):
        """Test getting slugs from string."""
        assert DeviceFilter._get_device_slugs("32:1") == ["32:1"]

    def test_get_device_slugs_attribute(self):
        """Test getting slugs from 'slugs' attribute."""

        class SlugsDevice:
            def __init__(self, slugs):
                self.slugs = slugs

            def __str__(self):
                return "device_with_slugs"

        device = SlugsDevice(["FAN", "VENT"])
        assert DeviceFilter._get_device_slugs(device) == ["FAN", "VENT"]

        # Use a separate instance for single slug
        device2 = SlugsDevice("SINGLE")
        assert DeviceFilter._get_device_slugs(device2) == ["SINGLE"]

    def test_get_device_slugs_underscore_slug(self):
        """Test getting slugs from '_SLUG' attribute."""

        class SlugAttrDevice:
            def __init__(self, slug):
                self._SLUG = slug

            def __str__(self):
                return "slug_attr_device"

        device = SlugAttrDevice("CO2")
        assert DeviceFilter._get_device_slugs(device) == ["CO2"]

        class NamedSlug:
            def __init__(self, name):
                self.name = name

            def __str__(self):
                return self.name

        device2 = SlugAttrDevice(NamedSlug("HUM"))
        assert DeviceFilter._get_device_slugs(device2) == ["HUM"]

    def test_get_device_slugs_generic_attributes(self):
        """Test getting slugs from generic attributes."""

        class SlugDevice:
            def __init__(self, slug=None, device_type=None, dtype=None):
                if slug:
                    self.slug = slug
                if device_type:
                    self.device_type = device_type
                if dtype:
                    self.type = dtype

            def __str__(self):
                return "generic_device"

        device1 = SlugDevice(slug="slug_val")
        assert DeviceFilter._get_device_slugs(device1) == ["slug_val"]

        device2 = SlugDevice(device_type="type_val")
        assert DeviceFilter._get_device_slugs(device2) == ["type_val"]

        device3 = SlugDevice(dtype="type_attr")
        assert DeviceFilter._get_device_slugs(device3) == ["type_attr"]

    def test_get_device_slugs_fallback_class(self):
        """Test fallback to class name."""

        class HvacVentilator:
            def __str__(self):
                return "vent"

        assert DeviceFilter._get_device_slugs(HvacVentilator()) == ["FAN"]

        class SomeOtherDevice:
            def __str__(self):
                return "other"

        assert DeviceFilter._get_device_slugs(SomeOtherDevice()) == ["SomeOtherDevice"]

    def test_get_device_slugs_empty_fallback(self):
        """Test fallback when no info found."""
        assert DeviceFilter._get_device_slugs(object()) == ["object"]

    def test_is_device_allowed_for_feature(self):
        """Test is_device_allowed_for_feature method."""
        feature_config = {"allowed_device_slugs": ["FAN"]}

        class FanDevice:
            _SLUG = "FAN"

            def __str__(self):
                return "fan"

        class Co2Device:
            _SLUG = "CO2"

            def __str__(self):
                return "co2"

        mock_fan = FanDevice()
        assert (
            DeviceFilter.is_device_allowed_for_feature(mock_fan, feature_config) is True
        )

        mock_co2 = Co2Device()
        assert (
            DeviceFilter.is_device_allowed_for_feature(mock_co2, feature_config)
            is False
        )

        # Wildcard
        assert (
            DeviceFilter.is_device_allowed_for_feature(
                mock_co2, {"allowed_device_slugs": ["*"]}
            )
            is True
        )

    def test_get_supported_device_types(self):
        """Test get_supported_device_types method."""
        assert DeviceFilter.get_supported_device_types(
            {"allowed_device_slugs": ["FAN"]}
        ) == ["FAN"]
        assert DeviceFilter.get_supported_device_types({}) == ["*"]
