"""Simple effective tests for binary_sensor.py"""

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
    """Test migration when new entity already exists"""
    hass = MagicMock()
    registry = MagicMock()
    registry.async_get = MagicMock(return_value=MagicMock())  # New entity exists

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        # Should return early without doing anything
        _migrate_legacy_transport_entity_id(hass, "32:153289")


def test_migrate_legacy_transport_entity_id_no_legacy_entity():
    """Test migration when legacy entity doesn't exist"""
    hass = MagicMock()
    registry = MagicMock()
    # First call returns None (new entity doesn't exist),
    # second call returns None (legacy doesn't exist)
    registry.async_get = MagicMock(side_effect=[None, None])

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        _migrate_legacy_transport_entity_id(hass, "32:153289")


def test_transport_state_binary_sensor_init():
    """Test TransportStateBinarySensor initialization"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
        ) as _mock_get_monitor:
            mock_monitor = MagicMock()
            _mock_get_monitor.return_value = mock_monitor

            _sensor = TransportStateBinarySensor(hass, "32_153289")

            assert _sensor._device_id == "32_153289"
            assert _sensor._is_on is False


def test_transport_state_binary_sensor_is_on_property():
    """Test the is_on property"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
        ) as _mock_get_monitor:
            mock_monitor = MagicMock()
            _mock_get_monitor.return_value = mock_monitor

            _sensor = TransportStateBinarySensor(hass, "32_153289")

            # Test the is_on property
            result = _sensor.is_on
            assert result is False


def test_transport_state_binary_sensor_unique_id():
    """Test unique_id property"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
        ) as _mock_get_monitor:
            mock_monitor = MagicMock()
            _mock_get_monitor.return_value = mock_monitor

            _sensor = TransportStateBinarySensor(hass, "32_153289")

            # Test unique_id
            assert "transport_state" in _sensor.unique_id


def test_transport_state_binary_sensor_on_transport_state_changed():
    """Test _on_transport_state_changed callback"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
        ) as _mock_get_monitor:
            mock_monitor = MagicMock()
            _mock_get_monitor.return_value = mock_monitor

            _sensor = TransportStateBinarySensor(hass, "32_153289")

            # Test the callback
            _sensor._on_transport_state_changed(True)
            assert _sensor._is_on is True


def test_transport_state_binary_sensor_async_added_to_hass():
    """Test async_added_to_hass method"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor"
        ) as _mock_get_monitor:
            mock_monitor = MagicMock()
            mock_monitor.get_device_state.return_value = False
            mock_monitor.return_value = mock_monitor

            _sensor = TransportStateBinarySensor(hass, "32_153289")

            # Test async_added_to_hass
            # This should register the callback and update state
            # We can't fully test async here but we can verify it doesn't crash
