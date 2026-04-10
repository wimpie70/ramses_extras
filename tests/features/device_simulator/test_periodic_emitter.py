# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator PeriodicEmitter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.device_db import (
    AutonomousEntry,
)
from custom_components.ramses_extras.features.device_simulator.periodic_emitter import (
    ActiveDevice,
    PeriodicEmitter,
)

if TYPE_CHECKING:
    pass


class TestActiveDevice:
    """Tests for ActiveDevice dataclass."""

    def test_default_values(self) -> None:
        """Test ActiveDevice default values."""
        device = ActiveDevice(device_id="37:168270", device_type="FAN")
        assert device.device_id == "37:168270"
        assert device.device_type == "FAN"
        assert device.variant_id is None
        assert device.enabled is True
        assert device.speed_multiplier == 1.0
        assert device.excluded_codes == set()

    def test_should_emit_basic(self) -> None:
        """Test should_emit with basic interval."""
        device = ActiveDevice(device_id="37:168270", device_type="FAN")

        # Should emit at t=0 (no previous emission)
        assert device.should_emit("31DA", 100.0, 60.0) is True

        # Record emission
        device.record_emission("31DA", 100.0)

        # Should not emit immediately after
        assert device.should_emit("31DA", 100.1, 60.0) is False

        # Should emit after interval passes
        assert device.should_emit("31DA", 161.0, 60.0) is True

    def test_should_emit_disabled(self) -> None:
        """Test should_emit when device is disabled."""
        device = ActiveDevice(device_id="37:168270", device_type="FAN", enabled=False)

        assert device.should_emit("31DA", 100.0, 60.0) is False

    def test_should_emit_excluded_code(self) -> None:
        """Test should_emit with excluded code."""
        device = ActiveDevice(device_id="37:168270", device_type="FAN")
        device.excluded_codes.add("31DA")

        assert device.should_emit("31DA", 100.0, 60.0) is False

    def test_should_emit_speed_multiplier(self) -> None:
        """Test should_emit with speed multiplier."""
        device = ActiveDevice(
            device_id="37:168270", device_type="FAN", speed_multiplier=2.0
        )

        # Record emission at t=100
        device.record_emission("31DA", 100.0)

        # With 2x speed, 60s interval becomes 30s effective
        # Should emit at t=130 (30s later)
        assert device.should_emit("31DA", 129.0, 60.0) is False
        assert device.should_emit("31DA", 130.0, 60.0) is True

    def test_record_emission(self) -> None:
        """Test recording emissions."""
        device = ActiveDevice(device_id="37:168270", device_type="FAN")

        device.record_emission("31DA", 100.0)
        assert device._last_emission["31DA"] == 100.0

        device.record_emission("31DA", 200.0)
        assert device._last_emission["31DA"] == 200.0


class TestPeriodicEmitterInit:
    """Tests for PeriodicEmitter initialization."""

    def test_init(self) -> None:
        """Test PeriodicEmitter initialization."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()

        emitter = PeriodicEmitter(mock_db, mock_endpoint)

        assert emitter._db == mock_db
        assert emitter._endpoint == mock_endpoint
        assert emitter._active_devices == {}
        assert emitter._running is False
        assert emitter._global_speed == 1.0
        assert emitter._default_src == "18:001234"


class TestPeriodicEmitterDeviceManagement:
    """Tests for device management."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return PeriodicEmitter(mock_db, mock_endpoint)

    def test_add_device(self, emitter: PeriodicEmitter) -> None:
        """Test adding a device."""
        device = emitter.add_device("37:168270", "FAN", "itho_cve_rf", 2.0)

        assert device.device_id == "37:168270"
        assert device.device_type == "FAN"
        assert device.variant_id == "itho_cve_rf"
        assert device.speed_multiplier == 2.0
        assert "37:168270" in emitter._active_devices

    def test_remove_device(self, emitter: PeriodicEmitter) -> None:
        """Test removing a device."""
        emitter.add_device("37:168270", "FAN")

        result = emitter.remove_device("37:168270")
        assert result is True
        assert "37:168270" not in emitter._active_devices

    def test_remove_nonexistent_device(self, emitter: PeriodicEmitter) -> None:
        """Test removing a non-existent device."""
        result = emitter.remove_device("99:999999")
        assert result is False

    def test_enable_disable_device(self, emitter: PeriodicEmitter) -> None:
        """Test enabling and disabling a device."""
        device = emitter.add_device("37:168270", "FAN")
        device.enabled = False

        assert emitter.enable_device("37:168270") is True
        assert device.enabled is True

        assert emitter.disable_device("37:168270") is True
        assert device.enabled is False

    def test_enable_nonexistent_device(self, emitter: PeriodicEmitter) -> None:
        """Test enabling a non-existent device."""
        assert emitter.enable_device("99:999999") is False

    def test_set_device_speed(self, emitter: PeriodicEmitter) -> None:
        """Test setting device speed."""
        device = emitter.add_device("37:168270", "FAN")

        assert emitter.set_device_speed("37:168270", 5.0) is True
        assert device.speed_multiplier == 5.0

    def test_set_device_speed_min_bound(self, emitter: PeriodicEmitter) -> None:
        """Test speed multiplier minimum bound."""
        device = emitter.add_device("37:168270", "FAN")

        emitter.set_device_speed("37:168270", 0.001)
        assert device.speed_multiplier == 0.01  # Clamped to minimum

    def test_set_global_speed(self, emitter: PeriodicEmitter) -> None:
        """Test setting global speed."""
        emitter.set_global_speed(10.0)
        assert emitter._global_speed == 10.0

    def test_exclude_include_code(self, emitter: PeriodicEmitter) -> None:
        """Test excluding and including codes."""
        device = emitter.add_device("37:168270", "FAN")

        assert emitter.exclude_code("37:168270", "31DA") is True
        assert "31DA" in device.excluded_codes

        assert emitter.include_code("37:168270", "31DA") is True
        assert "31DA" not in device.excluded_codes

    def test_list_devices(self, emitter: PeriodicEmitter) -> None:
        """Test listing devices."""
        emitter.add_device("37:168270", "FAN")
        emitter.add_device("37:168271", "FAN")

        devices = emitter.list_devices()
        assert len(devices) == 2
        assert "37:168270" in devices
        assert "37:168271" in devices


class TestPeriodicEmitterGetStatus:
    """Tests for get_device_status."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_periodic = [
            AutonomousEntry(code="31DA", interval_seconds=30.0),
            AutonomousEntry(code="31D9", interval_seconds=60.0),
        ]
        mock_db.get_periodic.return_value = mock_periodic
        return PeriodicEmitter(mock_db, MagicMock())

    def test_get_device_status(self, emitter: PeriodicEmitter) -> None:
        """Test getting device status."""
        emitter.add_device("37:168270", "FAN", "itho_cve_rf", 2.0)

        status = emitter.get_device_status("37:168270")
        assert status is not None
        assert status["device_id"] == "37:168270"
        assert status["device_type"] == "FAN"
        assert status["variant_id"] == "itho_cve_rf"
        assert status["speed_multiplier"] == 2.0
        assert status["periodic_codes"] == ["31DA", "31D9"]

    def test_get_nonexistent_device_status(self, emitter: PeriodicEmitter) -> None:
        """Test getting status for non-existent device."""
        status = emitter.get_device_status("99:999999")
        assert status is None


class TestPeriodicEmitterEmitMessage:
    """Tests for _emit_message method."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.send_packet = AsyncMock()
        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.fixture
    def device(self, emitter: PeriodicEmitter) -> ActiveDevice:
        """Create an active device."""
        return emitter.add_device("37:168270", "FAN")

    @pytest.mark.asyncio
    async def test_emit_message_with_payload(
        self, emitter: PeriodicEmitter, device: ActiveDevice
    ) -> None:
        """Test emitting message with payload."""
        entry = AutonomousEntry(code="31DA", interval_seconds=30.0, payloads=["21..."])

        await emitter._emit_message(device, entry)

        emitter._endpoint.send_packet.assert_called_once()
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "I 052 37:168270 --:------ 31DA 002 21..." in call_args

    @pytest.mark.asyncio
    async def test_emit_message_empty_payload(
        self, emitter: PeriodicEmitter, device: ActiveDevice
    ) -> None:
        """Test emitting message with empty payload."""
        entry = AutonomousEntry(code="31DA", interval_seconds=30.0, payloads=[])

        await emitter._emit_message(device, entry)

        emitter._endpoint.send_packet.assert_called_once()
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "31DA 000 " in call_args


class TestPeriodicEmitterEmitOnce:
    """Tests for emit_once method."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        mock_endpoint.send_packet = AsyncMock()

        # Setup periodic entries
        mock_periodic = [
            AutonomousEntry(
                code="31DA", interval_seconds=30.0, payloads=["db_payload"]
            ),
        ]
        mock_db.get_periodic.return_value = mock_periodic

        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_emit_once_with_db_payload(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit using DB payload."""
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA")

        assert result is True
        emitter._endpoint.send_packet.assert_called_once()
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "db_payload" in call_args

    @pytest.mark.asyncio
    async def test_emit_once_with_custom_payload(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test manual emit with custom payload."""
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA", "custom_payload")

        assert result is True
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "custom_payload" in call_args

    @pytest.mark.asyncio
    async def test_emit_once_not_connected(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit when not connected."""
        emitter._endpoint.is_connected = False
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA")

        assert result is False

    @pytest.mark.asyncio
    async def test_emit_once_nonexistent_device(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit for non-existent device."""
        result = await emitter.emit_once("99:999999", "31DA")
        assert result is False


class TestPeriodicEmitterStartStop:
    """Tests for start/stop lifecycle."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_start_creates_task(self, emitter: PeriodicEmitter) -> None:
        """Test that start creates the emitter task."""
        await emitter.start()

        assert emitter._running is True
        assert emitter._emitter_task is not None

        await emitter.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, emitter: PeriodicEmitter) -> None:
        """Test that stop cancels the emitter task."""
        await emitter.start()
        await emitter.stop()

        assert emitter._running is False
        assert emitter._emitter_task is None

    @pytest.mark.asyncio
    async def test_double_start_warning(self, emitter: PeriodicEmitter) -> None:
        """Test that double start logs warning."""
        await emitter.start()

        with patch(
            "custom_components.ramses_extras.features.device_simulator.periodic_emitter.LOGGER"
        ) as mock_logger:
            await emitter.start()
            mock_logger.warning.assert_called_once_with(
                "PeriodicEmitter: already running"
            )

        await emitter.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, emitter: PeriodicEmitter) -> None:
        """Test stop when not running."""
        # Should not raise
        await emitter.stop()

        assert emitter._running is False
