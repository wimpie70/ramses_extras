"""Tests for binary_sensor.py utility functions"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.platforms.binary_sensor import (
    TransportStateBinarySensor,
    _legacy_transport_entity_id,
    _migrate_legacy_transport_entity_id,
    _transport_entity_id,
)


def test_legacy_transport_entity_id():
    """Test _legacy_transport_entity_id function"""
    result = _legacy_transport_entity_id("32:153289")
    assert result == "binary_sensor.32_153289_transport_state"


def test_transport_entity_id():
    """Test _transport_entity_id function"""
    result = _transport_entity_id("32:153289")
    assert result == "binary_sensor.transport_state_32_153289"


def test_migrate_legacy_transport_entity_id_no_new_entity():
    """Test _migrate_legacy_transport_entity_id when new entity exists"""
    hass = MagicMock()
    registry = MagicMock()
    registry.async_get = MagicMock(return_value=MagicMock())  # New entity exists

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        # Should return early without doing anything
        _migrate_legacy_transport_entity_id(hass, "32:153289")


def test_migrate_legacy_transport_entity_id_no_legacy():
    """Test _migrate_legacy_transport_entity_id when legacy doesn't exist"""
    hass = MagicMock()
    registry = MagicMock()
    # First call (new) returns None, second call (legacy) returns None
    registry.async_get = MagicMock(side_effect=[None, None])

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        _migrate_legacy_transport_entity_id(hass, "32:153289")
        # Should return early since legacy doesn't exist


def test_migrate_legacy_transport_entity_id_success():
    """Test _migrate_legacy_transport_entity_id successful migration"""
    hass = MagicMock()
    registry = MagicMock()
    # New entity doesn't exist, legacy exists
    registry.async_get = MagicMock(side_effect=[None, MagicMock()])
    registry.async_update_entity = MagicMock()

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        _migrate_legacy_transport_entity_id(hass, "32:153289")
        # Should call async_update_entity
        assert registry.async_update_entity.called


class TestTransportStateBinarySensor:
    """Tests for TransportStateBinarySensor class"""

    def test_sensor_init_with_device(self):
        """Test sensor initialization when device is found"""
        hass = MagicMock()

        mock_device = MagicMock()
        mock_device.friendly_name = "Test Device"

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=mock_device,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
            ) as mock_get_monitor:
                mock_monitor = MagicMock()
                mock_get_monitor.return_value = mock_monitor

                sensor = TransportStateBinarySensor(hass, "32_153289")

                assert sensor._device_id == "32_153289"
                assert sensor._is_on is False
                assert mock_monitor.register_callback.called

    def test_sensor_init_no_device(self):
        """Test sensor initialization when no device found"""
        hass = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=None,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
            ) as mock_get_monitor:
                mock_monitor = MagicMock()
                mock_get_monitor.return_value = mock_monitor

                sensor = TransportStateBinarySensor(hass, "32_153289")

                assert sensor._device_id == "32_153289"
                assert sensor._attr_device_info is not None

    def test_on_transport_state_changed(self):
        """Test _on_transport_state_changed callback"""
        hass = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=None,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
            ) as mock_get_monitor:
                mock_monitor = MagicMock()
                mock_get_monitor.return_value = mock_monitor

                sensor = TransportStateBinarySensor(hass, "32_153289")

                # Test state change to online
                sensor._on_transport_state_changed(True)
                assert sensor._is_on is True

                # Test state change to offline
                sensor._on_transport_state_changed(False)
                assert sensor._is_on is False

    def test_icon_property(self):
        """Test icon property returns correct icon"""
        hass = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=None,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
            ) as mock_get_monitor:
                mock_monitor = MagicMock()
                mock_get_monitor.return_value = mock_monitor

                sensor = TransportStateBinarySensor(hass, "32_153289")

                # Test online icon
                sensor._is_on = True
                assert "network-strength" in sensor.icon

                # Test offline icon
                sensor._is_on = False
                assert "network-strength-off" in sensor.icon

    def test_available_property(self):
        """Test available property"""
        hass = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=None,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
            ) as mock_get_monitor:
                mock_monitor = MagicMock()
                mock_get_monitor.return_value = mock_monitor

                sensor = TransportStateBinarySensor(hass, "32_153289")

                assert sensor.available is True
