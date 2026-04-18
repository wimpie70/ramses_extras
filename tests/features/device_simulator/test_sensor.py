# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.features.device_simulator.platforms.sensor import (
    SimulatorBaseSensor,
    SimulatorDevicesSensor,
    SimulatorMessagesSensor,
    SimulatorStatusSensor,
    async_setup_entry,
)


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self) -> None:
        """Test that async_setup_entry adds all sensor entities."""
        hass = MagicMock()
        async_add_entities = MagicMock()

        await async_setup_entry(hass, MagicMock(), async_add_entities)

        # Verify that async_add_entities was called with the three sensors
        assert async_add_entities.call_count == 1
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 3
        assert isinstance(entities[0], SimulatorStatusSensor)
        assert isinstance(entities[1], SimulatorMessagesSensor)
        assert isinstance(entities[2], SimulatorDevicesSensor)


class TestSimulatorBaseSensor:
    """Tests for SimulatorBaseSensor."""

    def test_init(self) -> None:
        """Test sensor initialization."""
        hass = MagicMock()
        sensor = SimulatorBaseSensor(hass, "Test Name", "test_unique")

        assert sensor.hass == hass
        assert sensor._attr_name == "Device Simulator Test Name"
        assert sensor._attr_unique_id == "device_simulator_test_unique"
        assert sensor._attr_should_poll is True
        assert sensor._unsub is None

    def test_available_with_engine(self) -> None:
        """Test available property when engine is initialized."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": MagicMock()}}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        assert sensor.available is True

    def test_available_without_engine(self) -> None:
        """Test available property when engine is not initialized."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        assert sensor.available is False

    def test_available_without_ramses_extras(self) -> None:
        """Test available property when ramses_extras is not in hass.data."""
        hass = MagicMock()
        hass.data = {}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        assert sensor.available is False

    def test_get_engine_with_engine(self) -> None:
        """Test _get_engine when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        result = sensor._get_engine()

        assert result == engine

    def test_get_engine_without_engine(self) -> None:
        """Test _get_engine when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        result = sensor._get_engine()

        assert result is None

    def test_get_engine_without_ramses_extras(self) -> None:
        """Test _get_engine when ramses_extras is not in hass.data."""
        hass = MagicMock()
        hass.data = {}
        sensor = SimulatorBaseSensor(hass, "Test", "test")

        result = sensor._get_engine()

        assert result is None


class TestSimulatorStatusSensor:
    """Tests for SimulatorStatusSensor."""

    def test_init(self) -> None:
        """Test status sensor initialization."""
        hass = MagicMock()
        sensor = SimulatorStatusSensor(hass)

        assert sensor._attr_name == "Device Simulator Status"
        assert sensor._attr_unique_id == "device_simulator_status"
        assert sensor._attr_native_unit_of_measurement is None

    def test_native_value_with_engine(self) -> None:
        """Test native_value when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        engine.state = "running"
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorStatusSensor(hass)

        assert sensor.native_value == "running"

    def test_native_value_without_engine(self) -> None:
        """Test native_value when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorStatusSensor(hass)

        assert sensor.native_value == "unavailable"

    def test_extra_state_attributes_with_engine(self) -> None:
        """Test extra_state_attributes when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint.is_connected = True
        engine.active_device_ids = ["37:168270", "37:168271"]
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorStatusSensor(hass)

        attrs = sensor.extra_state_attributes

        assert attrs == {
            "connected": True,
            "active_devices": 2,
        }

    def test_extra_state_attributes_without_engine(self) -> None:
        """Test extra_state_attributes when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorStatusSensor(hass)

        assert sensor.extra_state_attributes == {}


class TestSimulatorMessagesSensor:
    """Tests for SimulatorMessagesSensor."""

    def test_init(self) -> None:
        """Test messages sensor initialization."""
        hass = MagicMock()
        sensor = SimulatorMessagesSensor(hass)

        assert sensor._attr_name == "Device Simulator Messages Sent"
        assert sensor._attr_unique_id == "device_simulator_messages_sent"
        assert sensor._attr_native_unit_of_measurement == "msgs"
        assert sensor._attr_state_class == "total"

    def test_native_value_with_engine(self) -> None:
        """Test native_value when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        engine.messages_sent = 42
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorMessagesSensor(hass)

        assert sensor.native_value == 42

    def test_native_value_without_engine(self) -> None:
        """Test native_value when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorMessagesSensor(hass)

        assert sensor.native_value == 0


class TestSimulatorDevicesSensor:
    """Tests for SimulatorDevicesSensor."""

    def test_init(self) -> None:
        """Test devices sensor initialization."""
        hass = MagicMock()
        sensor = SimulatorDevicesSensor(hass)

        assert sensor._attr_name == "Device Simulator Active Devices"
        assert sensor._attr_unique_id == "device_simulator_active_devices"
        assert sensor._attr_native_unit_of_measurement == "devices"

    def test_native_value_with_engine(self) -> None:
        """Test native_value when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        engine.active_device_ids = ["37:168270", "37:168271", "37:168272"]
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorDevicesSensor(hass)

        assert sensor.native_value == 3

    def test_native_value_without_engine(self) -> None:
        """Test native_value when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorDevicesSensor(hass)

        assert sensor.native_value == 0

    def test_extra_state_attributes_with_engine(self) -> None:
        """Test extra_state_attributes when engine is available."""
        hass = MagicMock()
        engine = MagicMock()
        engine.active_device_ids = ["37:168270", "37:168271"]
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        sensor = SimulatorDevicesSensor(hass)

        attrs = sensor.extra_state_attributes

        assert attrs == {"device_ids": ["37:168270", "37:168271"]}

    def test_extra_state_attributes_without_engine(self) -> None:
        """Test extra_state_attributes when engine is not available."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}
        sensor = SimulatorDevicesSensor(hass)

        assert sensor.extra_state_attributes == {}
