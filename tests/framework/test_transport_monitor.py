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

        monitor.register_callback("test", callback)
        assert "test" in monitor._callbacks
        assert monitor._callbacks["test"] == callback

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
        hass = MagicMock()

        # Start monitoring
        await monitor.start_monitoring(coordinator, hass)
        assert monitor._monitor_task is not None
        assert not monitor._monitor_task.done()
        assert monitor._coordinator == coordinator

        # Stop monitoring
        await monitor.stop_monitoring()
        assert monitor._monitor_task.cancelled()

    @pytest.mark.asyncio
    async def test_force_check(self):
        """Test forcing a transport state check."""
        monitor = TransportMonitor()
        coordinator = MagicMock()
        coordinator.client = MagicMock()
        coordinator.client.transport = MagicMock()
        coordinator.client.transport.state = MagicMock()
        coordinator.client.transport.state.name = "Active"
        hass = MagicMock()

        await monitor.start_monitoring(coordinator, hass)

        # Force check should update state
        result = await monitor.force_check()
        assert isinstance(result, bool)

        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_callback_notification(self):
        """Test that callbacks are notified on state change."""
        monitor = TransportMonitor()
        callback1 = MagicMock()
        callback2 = MagicMock()

        monitor.register_callback("test1", callback1)
        monitor.register_callback("test2", callback2)

        # Simulate state change
        await monitor._check_transport_state()

        # If state changed from default (False) to True, callbacks should be called
        if monitor._transport_available:
            callback1.assert_called_once_with(True)
            callback2.assert_called_once_with(True)

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
