"""Tests for device helper utilities in framework/helpers/device/core.py."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.ramses_extras.framework.helpers.device.core import (
    _get_broker_for_entry,
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
    """Test cases for extract_device_id_as_string function."""

    def test_extract_device_id_string(self):
        """Test extracting device ID from string."""
        device_id = "32:153289"
        result = extract_device_id_as_string(device_id)
        assert result == "32:153289"

    def test_extract_device_id_with_device_id_attr(self):
        """Test extracting device ID from object with device_id attribute."""

        class MockDevice:
            device_id = "32:153289"

        device = MockDevice()
        result = extract_device_id_as_string(device)
        assert result == "32:153289"

    def test_extract_device_id_with_id_attr(self):
        """Test extracting device ID from object with id attribute."""

        class MockDevice:
            id = "32:153289"

        device = MockDevice()
        result = extract_device_id_as_string(device)
        assert result == "32:153289"

    def test_extract_device_id_with_private_id_attr(self):
        """Test extracting device ID from object with _id attribute."""

        class MockDevice:
            _id = "32:153289"

        device = MockDevice()
        result = extract_device_id_as_string(device)
        assert result == "32:153289"

    def test_extract_device_id_with_name_attr(self):
        """Test extracting device ID from object with name attribute."""

        class MockDevice:
            name = "32:153289"

        device = MockDevice()
        result = extract_device_id_as_string(device)
        assert result == "32:153289"

    def test_extract_device_id_fallback(self):
        """Test extracting device ID fallback to object id."""
        device = object()  # Plain object with no attributes
        result = extract_device_id_as_string(device)
        assert result.startswith("device_")


class TestFindRamsesDevice:
    """Test cases for find_ramses_device function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.device_id = "32:153289"

    def test_find_ramses_device_ramses_cc_not_loaded(self):
        """Test finding device when ramses_cc is not loaded."""
        self.hass.data = {}
        self.hass.config_entries.async_entries = MagicMock(return_value=[])

        result = find_ramses_device(self.hass, self.device_id)
        assert result is None

    def test_find_ramses_device_no_entries(self):
        """Test finding device when no ramses_cc entries exist."""
        self.hass.data = {"ramses_cc": {}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[])

        result = find_ramses_device(self.hass, self.device_id)
        assert result is None

    def test_find_ramses_device_no_broker(self):
        """Test finding device when no broker is available."""
        self.hass.data = {"ramses_cc": {"entry1": None}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = find_ramses_device(self.hass, self.device_id)
        assert result is None

    def test_find_ramses_device_device_not_found(self):
        """Test finding device when device is not in broker."""
        mock_broker = MagicMock()
        mock_broker._get_device = MagicMock(return_value=None)
        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = find_ramses_device(self.hass, self.device_id)
        assert result is None

    def test_find_ramses_device_device_found(self):
        """Test finding device when device exists in broker."""
        mock_device = MagicMock()
        mock_device.__class__.__name__ = "HvacVentilator"
        mock_broker = MagicMock()
        mock_broker._get_device = MagicMock(return_value=mock_device)
        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = find_ramses_device(self.hass, self.device_id)
        assert result == mock_device


class TestGetDeviceType:
    """Test cases for get_device_type function."""

    def test_get_device_type_none_device(self):
        """Test getting device type for None device."""
        result = get_device_type(None)
        assert result == "None"

    def test_get_device_type_valid_device(self):
        """Test getting device type for valid device."""
        device = MagicMock()
        device.__class__.__name__ = "HvacVentilator"
        result = get_device_type(device)
        assert result == "HvacVentilator"

    def test_get_device_type_exception_handling(self):
        """Test getting device type with exception handling."""
        device = MagicMock()
        device.__class__.__name__ = "HvacVentilator"
        device.__class__ = MagicMock(side_effect=Exception("test error"))

        result = get_device_type(device)
        assert result == "Unknown"


class TestValidateDeviceForService:
    """Test cases for validate_device_for_service function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.device_id = "32:153289"
        self.service_name = "set_fan_speed"

    @patch(
        "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device"
    )
    def test_validate_device_for_service_device_not_found(self, mock_find_device):
        """Test validating service when device is not found."""
        mock_find_device.return_value = None

        result = validate_device_for_service(
            self.hass, self.device_id, self.service_name
        )
        assert result is False

    @patch(
        "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.device.core.get_device_type"
    )
    def test_validate_device_for_service_device_found(
        self, mock_get_type, mock_find_device
    ):
        """Test validating service when device is found."""
        mock_device = MagicMock()
        mock_find_device.return_value = mock_device
        mock_get_type.return_value = "HvacVentilator"

        result = validate_device_for_service(
            self.hass, self.device_id, self.service_name
        )
        assert result is True


class TestGetAllDeviceIds:
    """Test cases for get_all_device_ids function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()

    def test_get_all_device_ids_ramses_cc_not_loaded(self):
        """Test getting device IDs when ramses_cc is not loaded."""
        self.hass.data = {}
        self.hass.config_entries.async_entries = MagicMock(return_value=[])

        result = get_all_device_ids(self.hass)
        assert result == []

    def test_get_all_device_ids_no_entries(self):
        """Test getting device IDs when no ramses_cc entries exist."""
        self.hass.data = {"ramses_cc": {}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[])

        result = get_all_device_ids(self.hass)
        assert result == []

    def test_get_all_device_ids_no_broker(self):
        """Test getting device IDs when no broker is available."""
        self.hass.data = {"ramses_cc": {"entry1": None}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = get_all_device_ids(self.hass)
        assert result == []

    def test_get_all_device_ids_list_devices(self):
        """Test getting device IDs from list of devices."""
        mock_device1 = MagicMock()
        mock_device1.id = "32:153289"
        mock_device2 = MagicMock()
        mock_device2.id = "32:153290"

        mock_broker = MagicMock()
        mock_broker._devices = [mock_device1, mock_device2]

        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = get_all_device_ids(self.hass)
        assert result == ["32:153289", "32:153290"]

    def test_get_all_device_ids_dict_devices(self):
        """Test getting device IDs from dict of devices."""
        mock_broker = MagicMock()
        mock_broker._devices = {"32:153289": MagicMock(), "32:153290": MagicMock()}

        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = get_all_device_ids(self.hass)
        assert set(result) == {"32:153289", "32:153290"}

    def test_get_all_device_ids_unexpected_type(self):
        """Test getting device IDs with unexpected devices type."""
        mock_broker = MagicMock()
        mock_broker._devices = "unexpected_type"

        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}
        self.hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        result = get_all_device_ids(self.hass)
        assert result == []


class TestEnsureRamsesCcLoaded:
    """Test cases for ensure_ramses_cc_loaded function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()

    def test_ensure_ramses_cc_loaded_success(self):
        """Test ensuring ramses_cc is loaded when it is available."""
        self.hass.config.components = {"ramses_cc"}
        self.hass.data = {"ramses_cc": {}}

        # Should not raise exception
        ensure_ramses_cc_loaded(self.hass)

    def test_ensure_ramses_cc_loaded_not_in_components(self):
        """Test ensuring ramses_cc is loaded when not in components."""
        self.hass.config.components = set()  # Empty set instead of dict
        self.hass.data = {}

        with pytest.raises(
            HomeAssistantError, match="Ramses CC integration is not loaded"
        ):
            ensure_ramses_cc_loaded(self.hass)

    def test_ensure_ramses_cc_loaded_not_in_data(self):
        """Test ensuring ramses_cc is loaded when not in data."""
        self.hass.config.components = {"ramses_cc"}
        self.hass.data = {}

        with pytest.raises(
            HomeAssistantError, match="Ramses CC broker is not available"
        ):
            ensure_ramses_cc_loaded(self.hass)


class TestGetDeviceSupportedEntities:
    """Test cases for get_device_supported_entities function."""

    def test_get_device_supported_entities(self):
        """Test getting supported entities for device type."""
        # Function returns empty list due to circular import avoidance
        result = get_device_supported_entities("HvacVentilator")
        assert result == []


class TestValidateDeviceEntitySupport:
    """Test cases for validate_device_entity_support function."""

    def test_validate_device_entity_support(self):
        """Test validating device entity support."""
        # Since get_device_supported_entities returns empty list,
        # this will always return False
        result = validate_device_entity_support("HvacVentilator", "fan_speed")
        assert result is False


class TestGetBrokerForEntry:
    """Test cases for _get_broker_for_entry function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_no_entries(self):
        """Test getting broker when no ramses_cc entries exist."""
        self.hass.config_entries.async_entries = MagicMock(return_value=[])

        result = await _get_broker_for_entry(self.hass)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_broker_in_data_direct(self):
        """Test getting broker when stored directly in hass.data."""
        mock_broker = MagicMock()
        mock_broker.__class__.__name__ = "Broker"
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"

        self.hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        self.hass.data = {"ramses_cc": {"entry1": mock_broker}}

        result = await _get_broker_for_entry(self.hass)
        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_broker_in_data_nested(self):
        """Test getting broker when nested in hass.data."""
        mock_broker = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"

        self.hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        self.hass.data = {"ramses_cc": {"entry1": {"broker": mock_broker}}}

        result = await _get_broker_for_entry(self.hass)
        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_broker_on_entry(self):
        """Test getting broker from entry attribute."""
        mock_broker = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"
        mock_entry.broker = mock_broker

        self.hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        self.hass.data = {"ramses_cc": {}}

        result = await _get_broker_for_entry(self.hass)
        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_from_integrations(self):
        """Test getting broker from integrations registry."""
        mock_broker = MagicMock()
        mock_integration = MagicMock()
        mock_integration.broker = mock_broker
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"
        mock_entry.broker = None  # Ensure not found from entry

        self.hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        self.hass.data = {
            "ramses_cc": {},
            "integrations": {"some_integration": mock_integration},
        }

        result = await _get_broker_for_entry(self.hass)
        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_not_found(self):
        """Test getting broker when not found by any method."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"
        mock_entry.broker = None  # Ensure not found from entry

        # Mock the async_entries call to return our mock entry
        self.hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        # Ensure data doesn't have the broker
        self.hass.data = {"ramses_cc": {}}

        result = await _get_broker_for_entry(self.hass)
        assert result is None
