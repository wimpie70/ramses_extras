"""Tests for binary_sensor.py utility functions"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.platforms.binary_sensor import (
    TransportStateBinarySensor,
    _device_has_fan,
    _get_ramses_cc_coordinator,
    _legacy_transport_entity_id,
    _migrate_legacy_transport_entity_id,
    _start_transport_monitoring,
    _transport_entity_id,
    async_setup_entry,
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
    registry.async_update_entity = MagicMock(side_effect=ValueError("test error"))

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        # Should handle ValueError gracefully (lines 66-67)
        _migrate_legacy_transport_entity_id(hass, "32:153289")


def test_migrate_legacy_transport_entity_id_actual_success():
    """Test _migrate_legacy_transport_entity_id actual success (line 61)"""
    hass = MagicMock()
    registry = MagicMock()
    # New entity doesn't exist, legacy exists
    registry.async_get = MagicMock(side_effect=[None, MagicMock()])
    registry.async_update_entity = MagicMock()  # No exception

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ):
        # Should succeed and log info (line 61)
        _migrate_legacy_transport_entity_id(hass, "32:153289")
        assert registry.async_update_entity.called


@pytest.mark.asyncio
async def test_get_ramses_cc_coordinator_with_coordinator():
    """Test _get_ramses_cc_coordinator when coordinator exists (lines 76-84)"""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.client = MagicMock()
    hass.data = {"ramses_cc": {"entry_id": mock_coordinator}}

    result = await _get_ramses_cc_coordinator(hass)
    assert result == mock_coordinator


@pytest.mark.asyncio
async def test_get_ramses_cc_coordinator_no_data():
    """Test _get_ramses_cc_coordinator when no ramses_cc data"""
    hass = MagicMock()
    hass.data = {}

    result = await _get_ramses_cc_coordinator(hass)
    assert result is None


@pytest.mark.asyncio
async def test_get_ramses_cc_coordinator_exception():
    """Test _get_ramses_cc_coordinator when exception occurs"""
    hass = MagicMock()
    hass.data = {"ramses_cc": MagicMock()}
    hass.data["ramses_cc"].values = MagicMock(side_effect=Exception("test error"))

    result = await _get_ramses_cc_coordinator(hass)
    assert result is None


@pytest.mark.asyncio
async def test_start_transport_monitoring_no_coordinator():
    """Test _start_transport_monitoring when no coordinator (lines 88-95)"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._get_ramses_cc_coordinator",
        return_value=None,
    ):
        await _start_transport_monitoring(hass)
        # Should return early without error


@pytest.mark.asyncio
async def test_start_transport_monitoring_success():
    """Test _start_transport_monitoring successful start"""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.client = MagicMock()
    mock_monitor = MagicMock()
    mock_monitor.start_monitoring = AsyncMock()
    mock_monitor.force_check = AsyncMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._get_ramses_cc_coordinator",
        return_value=mock_coordinator,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor",
            return_value=mock_monitor,
        ):
            await _start_transport_monitoring(hass)
            mock_monitor.start_monitoring.assert_called_once()
            mock_monitor.force_check.assert_called_once()


@pytest.mark.asyncio
async def test_device_has_fan_with_fan():
    """Test _device_has_fan when device has fan (lines 235-248)"""
    hass = MagicMock()
    mock_device = MagicMock()
    mock_device.device_type = "HvacVentilator"

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=mock_device,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_device_type",
            return_value="HvacVentilator",
        ):
            result = await _device_has_fan(hass, "32:123456")
            assert result is True


@pytest.mark.asyncio
async def test_device_has_fan_no_device():
    """Test _device_has_fan when device not found"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=None,
    ):
        result = await _device_has_fan(hass, "32:123456")
        assert result is False


@pytest.mark.asyncio
async def test_device_has_fan_not_ventilator():
    """Test _device_has_fan when device is not a ventilator"""
    hass = MagicMock()
    mock_device = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        return_value=mock_device,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_device_type",
            return_value="Thermostat",
        ):
            result = await _device_has_fan(hass, "32:123456")
            assert result is False


@pytest.mark.asyncio
async def test_device_has_fan_exception():
    """Test _device_has_fan when exception occurs"""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
        side_effect=Exception("test error"),
    ):
        result = await _device_has_fan(hass, "32:123456")
        assert result is False


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

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self):
        """Test async_will_remove_from_hass (lines 176-178)"""
        hass = MagicMock()
        mock_monitor = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor.find_ramses_device",
            return_value=None,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor.get_transport_monitor",
                return_value=mock_monitor,
            ):
                sensor = TransportStateBinarySensor(hass, "32_153289")
                await sensor.async_will_remove_from_hass()
                mock_monitor.unregister_callback.assert_called_once_with(
                    "transport_sensor_32_153289"
                )


@pytest.mark.asyncio
async def test_async_setup_entry_no_devices():
    """Test async_setup_entry when no devices found (lines 187-230)"""
    hass = MagicMock()
    hass.data = {"ramses_extras": {"devices": []}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, config_entry, async_add_entities)
    # Should return early without adding entities


@pytest.mark.asyncio
async def test_async_setup_entry_with_devices():
    """Test async_setup_entry with fan devices"""
    hass = MagicMock()
    mock_device = MagicMock()
    mock_device.device_type = "HvacVentilator"
    hass.data = {"ramses_extras": {"devices": [mock_device]}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._device_has_fan",
        return_value=True,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor._start_transport_monitoring",
            new_callable=AsyncMock,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor._migrate_legacy_transport_entity_id",
            ):
                await async_setup_entry(hass, config_entry, async_add_entities)
                async_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_no_fan_devices():
    """Test async_setup_entry with devices that don't have fan (line 204)"""
    hass = MagicMock()
    mock_device = MagicMock()
    hass.data = {"ramses_extras": {"devices": [mock_device]}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._device_has_fan",
        return_value=False,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor._start_transport_monitoring",
            new_callable=AsyncMock,
        ):
            await async_setup_entry(hass, config_entry, async_add_entities)
            # Should not add any entities since no devices have fan


@pytest.mark.asyncio
async def test_async_setup_entry_async_generator():
    """Test async_setup_entry with async generator (lines 191, 193)"""
    hass = MagicMock()
    mock_device = MagicMock()
    mock_device.device_type = "HvacVentilator"

    async def async_gen():
        yield mock_device

    hass.data = {"ramses_extras": {"devices": async_gen()}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._device_has_fan",
        return_value=True,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor._start_transport_monitoring",
            new_callable=AsyncMock,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor._migrate_legacy_transport_entity_id",
            ):
                await async_setup_entry(hass, config_entry, async_add_entities)
                async_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_device_not_list():
    """Test async_setup_entry when devices is not a list (line 193)"""
    hass = MagicMock()
    mock_device = MagicMock()
    mock_device.device_type = "HvacVentilator"
    hass.data = {"ramses_extras": {"devices": iter([mock_device])}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor._device_has_fan",
        return_value=True,
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor._start_transport_monitoring",
            new_callable=AsyncMock,
        ):
            with patch(
                "custom_components.ramses_extras.features.default.platforms.binary_sensor._migrate_legacy_transport_entity_id",
            ):
                await async_setup_entry(hass, config_entry, async_add_entities)
                async_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_device_exception():
    """Test async_setup_entry when device check fails (lines 204-209)"""
    hass = MagicMock()
    mock_device = MagicMock()
    hass.data = {"ramses_extras": {"devices": [mock_device]}}
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.default.platforms.binary_sensor.extract_device_id_as_string",
        side_effect=Exception("test error"),
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.binary_sensor._start_transport_monitoring",
            new_callable=AsyncMock,
        ):
            await async_setup_entry(hass, config_entry, async_add_entities)
            # Should handle exception and continue


@pytest.mark.asyncio
async def test_async_setup_entry_exception():
    """Test async_setup_entry when exception occurs"""
    hass = MagicMock()
    hass.data = {"ramses_extras": MagicMock()}
    hass.data["ramses_extras"].get = MagicMock(side_effect=Exception("test error"))
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, config_entry, async_add_entities)
    # Should handle exception gracefully
