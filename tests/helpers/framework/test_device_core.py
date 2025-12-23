# tests/helpers/framework/test_device_core.py
"""Test device core helper functions."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.device.core import (
    ensure_ramses_cc_loaded,
    extract_device_id_as_string,
    find_ramses_device,
    get_all_device_ids,
    get_device_supported_entities,
    get_device_type,
    validate_device_entity_support,
    validate_device_for_service,
)


class TestExtractDeviceIdAsString:
    """Test extract_device_id_as_string function."""

    def test_extract_device_id_string_input(self):
        """Test extracting device ID from string input."""
        result = extract_device_id_as_string("32:153289")
        assert result == "32:153289"

    def test_extract_device_id_object_with_device_id_attr(self):
        """Test extracting device ID from object with device_id attribute."""
        mock_device = MagicMock()
        mock_device.device_id = "32:153289"
        result = extract_device_id_as_string(mock_device)
        assert result == "32:153289"

    def test_extract_device_id_object_with_id_attr(self):
        """Test extracting device ID from object with id attribute."""
        mock_device = MagicMock()
        del mock_device.device_id  # Remove device_id to test fallback
        mock_device.id = "32:153289"
        result = extract_device_id_as_string(mock_device)
        assert result == "32:153289"

    def test_extract_device_id_object_with_private_id_attr(self):
        """Test extracting device ID from object with _id attribute."""

        class MockDevice:
            _id = "32:153289"

        result = extract_device_id_as_string(MockDevice())
        assert result == "32:153289"

    def test_extract_device_id_object_with_name_attr(self):
        """Test extracting device ID from object with name attribute."""

        class MockDevice:
            name = "32:153289"

        result = extract_device_id_as_string(MockDevice())
        assert result == "32:153289"

    def test_extract_device_id_object_with_str_method(self):
        """Test extracting device ID from object with __str__ method."""

        class MockDevice:
            def __str__(self):
                return "32:153289"

        result = extract_device_id_as_string(MockDevice())
        assert result == "32:153289"

    def test_extract_device_id_fallback(self):
        """Test fallback device ID extraction."""
        # The function uses str() for objects that have __str__, which all objects do
        device_obj = object()
        result = extract_device_id_as_string(device_obj)
        # Should return the string representation of the object
        assert result.startswith("<object object at 0x")  # Default object str


class TestFindRamsesDevice:
    """Test find_ramses_device function."""

    def test_find_ramses_device_success(self, hass):
        """Test successful device finding."""
        mock_device = MagicMock()
        mock_broker = MagicMock()
        mock_broker._get_device.return_value = mock_device

        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": mock_broker}

            result = find_ramses_device(hass, "32:153289")

            assert result == mock_device
            mock_broker._get_device.assert_called_once_with("32:153289")

    def test_find_ramses_device_no_ramses_cc(self, hass):
        """Test when Ramses CC is not loaded."""
        hass.data = {}  # No ramses_cc

        result = find_ramses_device(hass, "32:153289")

        assert result is None

    def test_find_ramses_device_no_entries(self, hass):
        """Test when no Ramses CC entries exist."""
        hass.data["ramses_cc"] = {}

        with patch.object(hass.config_entries, "async_entries", return_value=[]):
            result = find_ramses_device(hass, "32:153289")

            assert result is None

    def test_find_ramses_device_no_broker(self, hass):
        """Test when broker is not available."""
        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": None}

            result = find_ramses_device(hass, "32:153289")

            assert result is None

    def test_find_ramses_device_not_found(self, hass):
        """Test when device is not found by broker."""
        mock_broker = MagicMock()
        mock_broker._get_device.return_value = None

        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": mock_broker}

            result = find_ramses_device(hass, "32:153289")

            assert result is None


class TestGetDeviceType:
    """Test get_device_type function."""

    def test_get_device_type_valid_device(self):
        """Test getting device type from valid device."""
        mock_device = MagicMock()
        mock_device.__class__.__name__ = "HvacVentilator"

        result = get_device_type(mock_device)

        assert result == "HvacVentilator"

    def test_get_device_type_none_device(self):
        """Test getting device type from None device."""
        result = get_device_type(None)

        assert result == "None"

    def test_get_device_type_exception(self):
        """Test getting device type when exception occurs."""

        class ProblematicDevice:
            def __getattribute__(self, name):
                if name == "__class__":
                    raise Exception("Simulated exception")
                return super().__getattribute__(name)

        result = get_device_type(ProblematicDevice())

        assert result == "Unknown"


class TestValidateDeviceForService:
    """Test validate_device_for_service function."""

    def test_validate_device_for_service_success(self, hass):
        """Test successful device validation for service."""
        mock_device = MagicMock()

        with patch(
            "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device",
            return_value=mock_device,
        ):
            result = validate_device_for_service(hass, "32:153289", "test_service")

            assert result is True

    def test_validate_device_for_service_device_not_found(self, hass):
        """Test validation when device is not found."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device",
            return_value=None,
        ):
            result = validate_device_for_service(hass, "32:153289", "test_service")

            assert result is False


class TestGetAllDeviceIds:
    """Test get_all_device_ids function."""

    def test_get_all_device_ids_success_dict(self, hass):
        """Test getting all device IDs when devices is a dict."""
        mock_broker = MagicMock()
        # Simulate devices as dict with device IDs as keys
        mock_broker._devices = {"32:153289": MagicMock(), "32:153290": MagicMock()}

        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": mock_broker}

            result = get_all_device_ids(hass)

            assert set(result) == {"32:153289", "32:153290"}

    def test_get_all_device_ids_success_list(self, hass):
        """Test getting all device IDs when devices is a list."""
        mock_device1 = MagicMock()
        mock_device1.id = "32:153289"
        mock_device2 = MagicMock()
        mock_device2.id = "32:153290"

        mock_broker = MagicMock()
        mock_broker._devices = [mock_device1, mock_device2]

        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": mock_broker}

            result = get_all_device_ids(hass)

            assert set(result) == {"32:153289", "32:153290"}

    def test_get_all_device_ids_no_ramses_cc(self, hass):
        """Test when Ramses CC is not loaded."""
        hass.data = {}

        result = get_all_device_ids(hass)

        assert result == []

    def test_get_all_device_ids_no_entries(self, hass):
        """Test when no Ramses CC entries exist."""
        hass.data["ramses_cc"] = {}

        with patch.object(hass.config_entries, "async_entries", return_value=[]):
            result = get_all_device_ids(hass)

            assert result == []

    def test_get_all_device_ids_no_broker(self, hass):
        """Test when broker is not available."""
        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": None}

            result = get_all_device_ids(hass)

            assert result == []

    def test_get_all_device_ids_device_without_id(self, hass):
        """Test handling device without id attribute."""
        mock_device = MagicMock()
        del mock_device.id  # Remove id attribute

        mock_broker = MagicMock()
        mock_broker._devices = [mock_device]

        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            hass.data["ramses_cc"] = {"entry1": mock_broker}

            result = get_all_device_ids(hass)

            assert result == []  # Device without id should be skipped


class TestEnsureRamsesCcLoaded:
    """Test ensure_ramses_cc_loaded function."""

    def test_ensure_ramses_cc_loaded_success(self, hass):
        """Test successful Ramses CC loaded check."""
        hass.data["ramses_cc"] = {}
        hass.config.components.add("ramses_cc")

        # Should not raise
        ensure_ramses_cc_loaded(hass)

    def test_ensure_ramses_cc_loaded_no_component(self, hass):
        """Test when Ramses CC component is not loaded."""
        hass.config.components.clear()

        with pytest.raises(Exception) as exc_info:
            ensure_ramses_cc_loaded(hass)

        assert "Ramses CC integration is not loaded" in str(exc_info.value)

    def test_ensure_ramses_cc_loaded_no_broker(self, hass):
        """Test when Ramses CC broker is not available."""
        hass.config.components.add("ramses_cc")
        hass.data.clear()  # No ramses_cc in data

        with pytest.raises(Exception) as exc_info:
            ensure_ramses_cc_loaded(hass)

        assert "Ramses CC broker is not available" in str(exc_info.value)


class TestGetDeviceSupportedEntities:
    """Test get_device_supported_entities function."""

    def test_get_device_supported_entities(self):
        """Test getting supported entities for device type."""
        # Function currently returns empty list to avoid circular import
        result = get_device_supported_entities("HvacVentilator")

        assert result == []


class TestValidateDeviceEntitySupport:
    """Test validate_device_entity_support function."""

    def test_validate_device_entity_support(self):
        """Test validating device entity support."""
        # Function currently returns False to avoid circular import
        result = validate_device_entity_support("HvacVentilator", "fan_speed")

        assert result is False
