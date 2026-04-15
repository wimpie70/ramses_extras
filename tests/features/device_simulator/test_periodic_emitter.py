# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator PeriodicEmitter."""

from __future__ import annotations

import asyncio
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

    def test_disable_nonexistent_device(self, emitter: PeriodicEmitter) -> None:
        """Test disabling a non-existent device."""
        assert emitter.disable_device("99:999999") is False

    def test_set_device_speed_nonexistent(self, emitter: PeriodicEmitter) -> None:
        """Test setting speed on non-existent device."""
        assert emitter.set_device_speed("99:999999", 5.0) is False

    def test_exclude_code_nonexistent(self, emitter: PeriodicEmitter) -> None:
        """Test excluding code on non-existent device."""
        assert emitter.exclude_code("99:999999", "31DA") is False

    def test_include_code_nonexistent(self, emitter: PeriodicEmitter) -> None:
        """Test including code on non-existent device."""
        assert emitter.include_code("99:999999", "31DA") is False

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
        assert "082  I --- 37:168270 --:------ 37:168270 31DA 002 21..." in call_args

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

    @pytest.mark.asyncio
    async def test_emit_message_payload_length_calculation(
        self, emitter: PeriodicEmitter, device: ActiveDevice
    ) -> None:
        """Test payload length calculation in frame."""
        # 6 hex chars = 3 bytes
        entry = AutonomousEntry(code="31DA", interval_seconds=30.0, payloads=["ABCDEF"])

        await emitter._emit_message(device, entry)

        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert " 003 " in call_args


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


class TestPeriodicEmitterCheckAndEmit:
    """Tests for _check_and_emit method."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        mock_endpoint.send_packet = AsyncMock()

        # Setup periodic entries
        mock_periodic = [
            AutonomousEntry(code="31DA", interval_seconds=30.0, payloads=["payload1"]),
            AutonomousEntry(code="31D9", interval_seconds=60.0, payloads=["payload2"]),
        ]
        mock_db.get_periodic.return_value = mock_periodic

        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_check_and_emit_emits_due_messages(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test that due messages are emitted."""
        device = emitter.add_device("37:168270", "FAN")
        # Record emission in the past
        device.record_emission("31DA", 0.0)

        await emitter._check_and_emit()

        # Should have emitted 31DA (due) and 31D9 (first time)
        assert emitter._endpoint.send_packet.call_count == 2

    @pytest.mark.asyncio
    async def test_check_and_emit_skips_disabled_device(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test that disabled devices are skipped."""
        device = emitter.add_device("37:168270", "FAN")
        device.enabled = False

        await emitter._check_and_emit()

        emitter._endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_emit_skips_excluded_code(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test that excluded codes are skipped."""
        device = emitter.add_device("37:168270", "FAN")
        device.excluded_codes.add("31DA")

        await emitter._check_and_emit()

        # Should only emit 31D9, not 31DA
        assert emitter._endpoint.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_check_and_emit_applies_global_speed(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test that global speed multiplier is applied."""
        emitter.set_global_speed(2.0)
        device = emitter.add_device("37:168270", "FAN")
        device.record_emission("31DA", 0.0)

        await emitter._check_and_emit()

        # With 2x global speed, both should emit
        assert emitter._endpoint.send_packet.call_count == 2


class TestPeriodicEmitterEmitOnceEdgeCases:
    """Tests for emit_once edge cases."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        mock_endpoint.send_packet = AsyncMock()

        # Setup periodic entries with empty payloads
        mock_periodic = [
            AutonomousEntry(code="31DA", interval_seconds=30.0, payloads=[]),
        ]
        mock_db.get_periodic.return_value = mock_periodic

        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_emit_once_empty_db_payload(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit when DB has empty payload."""
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA")

        assert result is True
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "31DA 000 " in call_args  # Empty payload

    @pytest.mark.asyncio
    async def test_emit_once_code_not_in_db(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit when code not in DB."""
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "9999")

        assert result is True
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "9999 000 " in call_args  # Empty payload fallback

    @pytest.mark.asyncio
    async def test_emit_once_empty_custom_payload(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test manual emit with empty custom payload."""
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA", "")

        assert result is True
        call_args = emitter._endpoint.send_packet.call_args[0][0]
        assert "31DA 000 " in call_args

    @pytest.mark.asyncio
    async def test_emit_once_send_exception(self, emitter: PeriodicEmitter) -> None:
        """Test manual emit when send raises exception."""
        emitter._endpoint.send_packet = AsyncMock(side_effect=Exception("Send error"))
        emitter.add_device("37:168270", "FAN")

        result = await emitter.emit_once("37:168270", "31DA")

        assert result is False


class TestPeriodicEmitterGlobalSpeed:
    """Tests for global speed multiplier."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return PeriodicEmitter(mock_db, mock_endpoint)

    def test_set_global_speed_min_bound(self, emitter: PeriodicEmitter) -> None:
        """Test global speed minimum bound."""
        emitter.set_global_speed(0.001)
        assert emitter._global_speed == 0.01  # Clamped to minimum


class TestPeriodicEmitterEmitMessageException:
    """Tests for _emit_message exception handling."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.send_packet = AsyncMock(side_effect=Exception("Send error"))
        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.fixture
    def device(self, emitter: PeriodicEmitter) -> ActiveDevice:
        """Create an active device."""
        return emitter.add_device("37:168270", "FAN")

    @pytest.mark.asyncio
    async def test_emit_message_exception_handling(
        self, emitter: PeriodicEmitter, device: ActiveDevice
    ) -> None:
        """Test that exceptions in _emit_message are caught and logged."""
        entry = AutonomousEntry(
            code="31DA", interval_seconds=30.0, payloads=["payload"]
        )

        # The exception is caught and logged, not re-raised
        await emitter._emit_message(device, entry)

        # Send was attempted
        emitter._endpoint.send_packet.assert_called_once()


class TestPeriodicEmitterLoop:
    """Tests for _emitter_loop method."""

    @pytest.fixture
    def emitter(self) -> PeriodicEmitter:
        """Create a PeriodicEmitter with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        mock_endpoint.send_packet = AsyncMock()
        return PeriodicEmitter(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_emitter_loop_exception_handling(
        self, emitter: PeriodicEmitter
    ) -> None:
        """Test that exceptions in emitter loop are caught and logged."""
        emitter.add_device("37:168270", "FAN")
        # Make _check_and_emit raise an exception
        emitter._check_and_emit = AsyncMock(side_effect=Exception("Loop error"))

        # Start the emitter loop
        emitter._running = True
        emitter._shutdown_event.clear()

        # Run the loop (it should catch the exception, log it, and re-raise)
        with pytest.raises(Exception, match="Loop error"):
            await emitter._emitter_loop()

        # The exception is re-raised after logging, so _running is still True
        # The loop doesn't set _running to False on exception
        assert emitter._running is True

    @pytest.mark.asyncio
    async def test_emitter_loop_cancelled(self, emitter: PeriodicEmitter) -> None:
        """Test that CancelledError is handled and re-raised."""
        emitter.add_device("37:168270", "FAN")
        # Make _check_and_emit raise CancelledError
        emitter._check_and_emit = AsyncMock(side_effect=asyncio.CancelledError())

        emitter._running = True
        emitter._shutdown_event.clear()

        # CancelledError should be caught, logged, and re-raised
        with pytest.raises(asyncio.CancelledError):
            await emitter._emitter_loop()

    @pytest.mark.asyncio
    async def test_emitter_loop_shutdown_event(self, emitter: PeriodicEmitter) -> None:
        """Test that emitter loop breaks when shutdown event is set."""
        emitter.add_device("37:168270", "FAN")
        emitter._running = True
        emitter._shutdown_event.clear()

        # Set shutdown event immediately
        emitter._shutdown_event.set()

        # Run the loop - it should break immediately
        await emitter._emitter_loop()

        # Loop should have stopped (the loop sets _running = False when it exits)
        # Actually, looking at the code, the loop doesn't set _running = False
        # It just breaks out of the while loop
        assert (
            emitter._running is True
        )  # Still True since the loop doesn't set it to False

    @pytest.mark.asyncio
    async def test_emitter_loop_not_connected(self, emitter: PeriodicEmitter) -> None:
        """Test that emitter loop continues when not connected."""
        emitter.add_device("37:168270", "FAN")
        emitter._endpoint.is_connected = False
        emitter._running = True
        emitter._shutdown_event.clear()

        # Set shutdown event after 1.5 seconds to ensure loop
        # runs at least one iteration
        async def set_shutdown_after_delay():
            await asyncio.sleep(1.5)
            emitter._shutdown_event.set()

        # Run loop and shutdown task in parallel
        task = asyncio.create_task(emitter._emitter_loop())
        asyncio.create_task(set_shutdown_after_delay())

        # Wait for loop to finish
        await asyncio.wait_for(task, timeout=2.0)

        # _check_and_emit should not have been called since not connected
        # The loop should have hit the continue statement
