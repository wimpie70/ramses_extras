"""Tests for device_simulator entity_helpers."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.entity_helpers import (
    get_device_entities,
    normalize_ramses_id,
)


class TestNormalizeRamsesId:
    """Tests for normalize_ramses_id."""

    def test_none_input(self):
        assert normalize_ramses_id(None) is None

    def test_empty_string(self):
        assert normalize_ramses_id("") is None

    def test_non_string_input(self):
        assert normalize_ramses_id(123) is None

    def test_simple_id_no_colon(self):
        assert normalize_ramses_id("BDR91") == "BDR91"

    def test_id_with_colon_no_underscore(self):
        assert normalize_ramses_id("01:123456") == "01:123456"

    def test_id_with_colon_uppercase(self):
        assert normalize_ramses_id("01:abcdef") == "01:ABCDEF"

    def test_id_with_suffix_stripped(self):
        assert normalize_ramses_id("01:123456_03") == "01:123456"

    def test_id_with_suffix_uppercase(self):
        assert normalize_ramses_id("01:abcdef_03") == "01:ABCDEF"

    def test_id_with_whitespace_stripped(self):
        assert normalize_ramses_id("  01:123456  ") == "01:123456"

    def test_underscore_without_colon_kept(self):
        assert normalize_ramses_id("sensor_test") == "SENSOR_TEST"

    def test_multiple_underscores_only_first_split(self):
        result = normalize_ramses_id("01:123456_03_extra")
        assert result == "01:123456"


class TestGetDeviceEntities:
    """Tests for get_device_entities."""

    def test_empty_device_id(self):
        hass = MagicMock()
        assert get_device_entities(hass, "") == []

    def test_none_device_id(self):
        hass = MagicMock()
        assert get_device_entities(hass, None) == []

    def test_no_matching_devices(self):
        hass = MagicMock()
        device_reg = MagicMock()
        device_reg.async_get_devices.return_value = []
        hass.data = {}

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = MagicMock(entities={})
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert result == []

    def test_matching_device_with_entities(self):
        hass = MagicMock()

        # Set up a matching device
        mock_device = MagicMock()
        mock_device.id = "dev-1"
        mock_device.identifiers = [("ramses_cc", "01:123456")]

        # Set up device registry
        device_reg = MagicMock()
        device_reg.async_get_devices.return_value = [mock_device]

        # Set up entity registry with entities for this device
        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test_entity"
        mock_entity.domain = "sensor"
        mock_entity.name = "Test Entity"
        mock_entity.device_id = "dev-1"

        entity_reg = MagicMock()
        entity_reg.entities = {"sensor.test_entity": mock_entity}

        # Set up HA state
        mock_state = MagicMock()
        mock_state.state = "23.5"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert len(result) == 1
        assert result[0]["entity_id"] == "sensor.test_entity"
        assert result[0]["domain"] == "sensor"
        assert result[0]["name"] == "Test Entity"
        assert result[0]["available"] is True
        assert result[0]["state"] == "23.5"

    def test_matching_device_unavailable_state(self):
        hass = MagicMock()

        mock_device = MagicMock()
        mock_device.id = "dev-1"
        mock_device.identifiers = [("ramses_cc", "01:123456")]

        device_reg = MagicMock()
        device_reg.async_get_devices.return_value = [mock_device]

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity.domain = "sensor"
        mock_entity.name = None
        mock_entity.device_id = "dev-1"

        entity_reg = MagicMock()
        entity_reg.entities = {"sensor.test": mock_entity}

        mock_state = MagicMock()
        mock_state.state = "unavailable"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert len(result) == 1
        assert result[0]["available"] is False
        assert result[0]["state"] == "unavailable"
        # Name falls back to entity_id suffix
        assert result[0]["name"] == "test"

    def test_matching_device_no_state(self):
        hass = MagicMock()

        mock_device = MagicMock()
        mock_device.id = "dev-1"
        mock_device.identifiers = [("ramses_cc", "01:123456")]

        device_reg = MagicMock()
        device_reg.async_get_devices.return_value = [mock_device]

        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test"
        mock_entity.domain = "sensor"
        mock_entity.name = "Test"
        mock_entity.device_id = "dev-1"

        entity_reg = MagicMock()
        entity_reg.entities = {"sensor.test": mock_entity}

        hass.states.get.return_value = None

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert len(result) == 1
        assert result[0]["available"] is False
        assert result[0]["state"] == "unavailable"

    def test_device_with_non_ramses_identifier_skipped(self):
        hass = MagicMock()

        mock_device = MagicMock()
        mock_device.id = "dev-1"
        mock_device.identifiers = [("other_integration", "01:123456")]

        device_reg = MagicMock()
        device_reg.async_get_devices.return_value = [mock_device]

        entity_reg = MagicMock()
        entity_reg.entities = {}

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert result == []

    def test_devices_fallback_to_devices_attr(self):
        """Test fallback when async_get_devices is not available."""
        hass = MagicMock()

        mock_device = MagicMock()
        mock_device.id = "dev-1"
        mock_device.identifiers = [("ramses_cc", "01:123456")]

        device_reg = MagicMock()
        # Remove async_get_devices, use .devices dict instead
        del device_reg.async_get_devices
        device_reg.devices = {"dev-1": mock_device}

        entity_reg = MagicMock()
        entity_reg.entities = {}

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        # Found device but no entities
        assert result == []

    def test_no_device_registry_api(self):
        """Test when device registry has neither async_get_devices nor devices."""
        hass = MagicMock()

        device_reg = MagicMock()
        del device_reg.async_get_devices
        del device_reg.devices

        entity_reg = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.er"
            ) as mock_er,
            patch(
                "custom_components.ramses_extras.features.device_simulator.entity_helpers.dr"
            ) as mock_dr,
        ):
            mock_er.async_get.return_value = entity_reg
            mock_dr.async_get.return_value = device_reg

            result = get_device_entities(hass, "01:123456")

        assert result == []
