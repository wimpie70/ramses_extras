"""Tests for Transport Monitor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.transport_monitor import (
    TransportMonitor,
    get_transport_monitor,
)


class TestTransportMonitor:
    """Test cases for TransportMonitor."""

    def test_get_transport_monitor_singleton(self):
        """Test that get_transport_monitor returns the same instance."""
        monitor1 = get_transport_monitor()
        monitor2 = get_transport_monitor()
        assert monitor1 is monitor2
        assert isinstance(monitor1, TransportMonitor)

    def test_register_callback(self):
        """Test registering callbacks."""
        monitor = TransportMonitor()
        callback = MagicMock()

        monitor.register_callback("test", callback, "32:153289")
        assert "test" in monitor._callbacks
        assert monitor._callbacks["test"] == ("32:153289", callback)

    def test_unregister_callback(self):
        """Test unregistering callbacks."""
        monitor = TransportMonitor()
        callback = MagicMock()

        monitor.register_callback("test", callback)
        monitor.unregister_callback("test")
        assert "test" not in monitor._callbacks

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        monitor = TransportMonitor()
        coordinator = MagicMock()
        coordinator.client = MagicMock()
        coordinator.client.add_msg_handler = MagicMock(return_value=MagicMock())
        hass = MagicMock()

        # Start monitoring
        await monitor.start_monitoring(coordinator, hass)
        assert monitor._monitor_task is not None
        assert not monitor._monitor_task.done()
        assert monitor._coordinator == coordinator
        coordinator.client.add_msg_handler.assert_called_once_with(monitor._handle_msg)

        # Stop monitoring
        await monitor.stop_monitoring()
        assert monitor._monitor_task.cancelled()

    @pytest.mark.asyncio
    async def test_device_availability(self):
        """Test device availability tracking."""
        monitor = TransportMonitor()

        # Device should default to available (True) when no commands sent
        assert monitor.is_device_available("32:153289") is True

        # After marking offline, should be unavailable
        monitor._device_states["32:153289"] = False
        assert monitor.is_device_available("32:153289") is False

        # After marking online, should be available
        monitor._device_states["32:153289"] = True
        assert monitor.is_device_available("32:153289") is True

    @pytest.mark.asyncio
    async def test_callback_notification(self):
        """Test that callbacks are notified on state change."""
        monitor = TransportMonitor()
        callback1 = MagicMock()
        callback2 = MagicMock()

        monitor.register_callback("test1", callback1, "32:153289")
        monitor.register_callback("test2", callback2, "32:153290")

        # Simulate device state change
        await monitor._notify_device_state_changed("32:153289", True)

        # Only callback1 should be called (for device 32:153289)
        callback1.assert_called_once_with(True)
        callback2.assert_not_called()

    def test_is_transport_available_property(self):
        """Test the transport availability property."""
        monitor = TransportMonitor()
        assert isinstance(monitor.is_transport_available, bool)
        assert not monitor.is_transport_available  # Default state

    @pytest.mark.asyncio
    async def test_monitor_loop_handles_cancellation(self):
        """Test that monitor loop handles cancellation gracefully."""
        monitor = TransportMonitor()
        coordinator = MagicMock()
        coordinator.client = MagicMock()
        hass = MagicMock()

        await monitor.start_monitoring(coordinator, hass)

        # Give the loop a moment to start
        await asyncio.sleep(0.01)

        # Stop monitoring should cancel the loop without errors
        await monitor.stop_monitoring()

        # The task should be cancelled or done
        assert monitor._monitor_task.done() or monitor._monitor_task.cancelled()

    @pytest.mark.asyncio
    async def test_notify_command_sent(self):
        """Test that notify_command_sent starts a timeout timer."""
        monitor = TransportMonitor()
        hass = MagicMock()
        hass.async_create_task = MagicMock(
            side_effect=lambda coro: asyncio.create_task(coro)
        )
        monitor._hass = hass

        # Send command to device
        monitor.notify_command_sent("32:153289")

        # Should have created a timeout task
        assert "32:153289" in monitor._device_timeout_tasks
        assert monitor._device_timeout_tasks["32:153289"] is not None
        assert not monitor._device_timeout_tasks["32:153289"].done()

        # Clean up
        monitor._device_timeout_tasks["32:153289"].cancel()
        try:
            await monitor._device_timeout_tasks["32:153289"]
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_notify_command_sent_does_not_restart_timer(self):
        """Test that sending multiple commands doesn't restart the timer."""
        monitor = TransportMonitor()
        hass = MagicMock()
        hass.async_create_task = MagicMock(
            side_effect=lambda coro: asyncio.create_task(coro)
        )
        monitor._hass = hass

        # Send first command
        monitor.notify_command_sent("32:153289")
        first_task = monitor._device_timeout_tasks["32:153289"]

        # Send second command
        monitor.notify_command_sent("32:153289")
        second_task = monitor._device_timeout_tasks["32:153289"]

        # Should be the same task (not restarted)
        assert first_task is second_task

        # Clean up
        first_task.cancel()
        try:
            await first_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_device_timeout_marks_offline(self):
        """Test that device is marked offline after timeout."""
        monitor = TransportMonitor()
        hass = MagicMock()
        hass.async_create_task = MagicMock(
            side_effect=lambda coro: asyncio.create_task(coro)
        )
        monitor._hass = hass
        monitor._command_timeout = 0.05  # Short timeout for testing

        callback = MagicMock()
        monitor.register_callback("test", callback, "32:153289")

        # Send command
        monitor.notify_command_sent("32:153289")

        # Wait for timeout
        await asyncio.sleep(0.1)

        # Device should be marked offline
        assert monitor._device_states.get("32:153289") is False
        callback.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_update_device_message_received_cancels_timeout(self):
        """Test that receiving a message cancels the timeout timer."""
        monitor = TransportMonitor()
        hass = MagicMock()
        hass.loop = asyncio.get_event_loop()
        hass.async_create_task = MagicMock(
            side_effect=lambda coro: asyncio.create_task(coro)
        )
        hass.data = {"ramses_cc": {"mock_coordinator": MagicMock(client=MagicMock())}}
        monitor._hass = hass

        callback = MagicMock()
        monitor.register_callback("test", callback, "32:153289")

        # Send command to start timer
        monitor.notify_command_sent("32:153289")
        task = monitor._device_timeout_tasks["32:153289"]

        # Simulate device reply
        monitor.update_device_message_received("32:153289")

        # Give async operations time to complete
        await asyncio.sleep(0.01)

        # Timer should be cancelled
        assert task.cancelled() or task.done()

        # Device should be marked online
        await asyncio.sleep(0.01)  # Wait for async callback
        assert monitor._device_states.get("32:153289") is True

    @pytest.mark.asyncio
    async def test_handle_msg_marks_device_online(self):
        """Test that live client messages mark a device online."""
        monitor = TransportMonitor()
        hass = MagicMock()
        hass.loop = asyncio.get_event_loop()
        hass.async_create_task = MagicMock(
            side_effect=lambda coro: asyncio.create_task(coro)
        )
        hass.data = {"ramses_cc": {"mock_coordinator": MagicMock(client=MagicMock())}}
        monitor._hass = hass

        callback = MagicMock()
        monitor.register_callback("test", callback, "32:153289")
        monitor.notify_command_sent("32:153289")

        msg = MagicMock()
        msg.src.id = "32:153289"
        msg.dst.id = "37:168270"

        monitor._handle_msg(msg)

        await asyncio.sleep(0.01)

        assert monitor._device_states.get("32:153289") is True
        callback.assert_called_with(True)

    def test_device_id_normalization(self):
        """Test that device IDs with underscores are normalized to colons."""
        monitor = TransportMonitor()
        callback = MagicMock()

        # Register with underscores
        monitor.register_callback("test", callback, "32_153289")

        # Should be stored with colons
        assert monitor._callbacks["test"] == ("32:153289", callback)

        # Check availability with underscores
        monitor._device_states["32:153289"] = False
        assert monitor.is_device_available("32_153289") is False
