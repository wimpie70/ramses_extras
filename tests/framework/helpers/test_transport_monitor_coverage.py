"""Tests for transport_monitor to improve coverage."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.transport_monitor import (
    TransportMonitor,
    get_transport_monitor,
)


@pytest.fixture
def monitor():
    """Create a fresh TransportMonitor instance."""
    # Reset the global instance
    from custom_components.ramses_extras.framework.helpers import transport_monitor

    transport_monitor._transport_monitor = None
    return TransportMonitor()


class TestTransportMonitorCoverage:
    """Additional tests for TransportMonitor."""

    def test_init(self, monitor):
        """Test monitor initialization."""
        assert monitor._transport_available is False
        assert monitor._callbacks == {}
        assert monitor._coordinator is None
        assert monitor._hass is None

    def test_register_callback_no_device(self, monitor):
        """Test registering callback without device_id."""
        callback = MagicMock()
        monitor.register_callback("test_callback", callback)

        assert "test_callback" in monitor._callbacks
        assert monitor._callbacks["test_callback"] == (None, callback)

    def test_register_callback_with_device(self, monitor):
        """Test registering callback with device_id."""
        callback = MagicMock()
        monitor.register_callback("test_callback", callback, "32_123456")

        # Device ID should be normalized
        assert monitor._callbacks["test_callback"] == ("32:123456", callback)

    def test_unregister_callback(self, monitor):
        """Test unregistering callback."""
        callback = MagicMock()
        monitor.register_callback("test_callback", callback)
        monitor.unregister_callback("test_callback")

        assert "test_callback" not in monitor._callbacks

    def test_notify_command_sent_starts_timer(self, monitor):
        """Test notify_command_sent starts a timeout timer."""
        hass = MagicMock()
        hass.async_create_task = MagicMock(return_value=MagicMock())
        monitor._hass = hass

        monitor.notify_command_sent("32_123456")

        assert "32:123456" in monitor._last_command_sent_times
        hass.async_create_task.assert_called_once()

    def test_notify_command_sent_existing_timer(self, monitor):
        """Test notify_command_sent doesn't start new timer if one exists."""
        hass = MagicMock()
        existing_task = MagicMock()
        existing_task.done.return_value = False
        monitor._device_timeout_tasks["32:123456"] = existing_task
        monitor._hass = hass

        monitor.notify_command_sent("32_123456")

        # Should not create new task
        hass.async_create_task.assert_not_called()

    def test_update_device_message_received_cancels_timer(self, monitor):
        """Test update_device_message_received cancels timeout timer."""
        hass = MagicMock()
        hass.loop = MagicMock()
        existing_task = MagicMock()
        existing_task.done.return_value = False
        monitor._device_timeout_tasks["32:123456"] = existing_task
        monitor._hass = hass

        monitor.update_device_message_received("32_123456")

        existing_task.cancel.assert_called_once()
        hass.loop.call_soon_threadsafe.assert_called_once()

    def test_update_device_message_received_no_timer(self, monitor):
        """Test update_device_message_received when no timer exists."""
        hass = MagicMock()
        hass.loop = MagicMock()
        monitor._hass = hass

        # Should not crash
        monitor.update_device_message_received("32_123456")

    def test_is_device_available_default_true(self, monitor):
        """Test is_device_available returns True by default."""
        result = monitor.is_device_available("32_123456")
        assert result is True  # Default when no state known

    def test_is_device_available_known_state(self, monitor):
        """Test is_device_available returns known state."""
        monitor._device_states["32:123456"] = False
        result = monitor.is_device_available("32_123456")
        assert result is False

    def test_is_transport_available_property(self, monitor):
        """Test is_transport_available property."""
        monitor._transport_available = True
        assert monitor.is_transport_available is True

        monitor._transport_available = False
        assert monitor.is_transport_available is False

    def test_is_monitoring_property(self, monitor):
        """Test is_monitoring property."""
        # No task running
        assert monitor.is_monitoring is False

        # Task running
        monitor._monitor_task = MagicMock()
        monitor._monitor_task.done.return_value = False
        assert monitor.is_monitoring is True

        # Task done
        monitor._monitor_task.done.return_value = True
        assert monitor.is_monitoring is False

    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self, monitor):
        """Test start_monitoring when already running."""
        monitor._monitor_task = MagicMock()
        monitor._monitor_task.done.return_value = False

        hass = MagicMock()
        coordinator = MagicMock()

        # Should not start new task
        await monitor.start_monitoring(coordinator, hass)
        assert monitor._hass is None  # Not set because already running

    @pytest.mark.asyncio
    async def test_start_monitoring_with_msg_handler(self, monitor):
        """Test start_monitoring with message handler."""
        hass = MagicMock()
        hass.bus.async_listen.return_value = MagicMock()

        coordinator = MagicMock()
        coordinator.client.add_msg_handler.return_value = MagicMock()

        await monitor.start_monitoring(coordinator, hass)

        assert monitor._hass is hass
        assert monitor._coordinator is coordinator
        coordinator.client.add_msg_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_monitoring_not_running(self, monitor):
        """Test stop_monitoring when not running."""
        # Should not crash
        await monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test__device_timeout_handler_cancelled(self, monitor):
        """Test _device_timeout_handler when cancelled."""
        # Simulate cancellation
        with patch.object(asyncio, "sleep", side_effect=asyncio.CancelledError()):
            await monitor._device_timeout_handler("32:123456")
            # Should not mark offline when cancelled
            assert "32:123456" not in monitor._device_states

    @pytest.mark.asyncio
    async def test__device_timeout_handler_times_out(self, monitor):
        """Test _device_timeout_handler marks device offline on timeout."""
        with patch.object(asyncio, "sleep", return_value=None):
            await monitor._device_timeout_handler("32:123456")
            assert monitor._device_states.get("32:123456") is False

    @pytest.mark.asyncio
    async def test__mark_device_offline_already_offline(self, monitor):
        """Test _mark_device_offline when already offline."""
        monitor._device_states["32:123456"] = False

        # Should not notify if already offline
        with patch.object(monitor, "_notify_device_state_changed") as mock_notify:
            await monitor._mark_device_offline("32:123456")
            mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test__mark_device_online_already_online(self, monitor):
        """Test _mark_device_online when already online."""
        monitor._device_states["32:123456"] = True

        # Should still notify
        with patch.object(monitor, "_notify_device_state_changed") as mock_notify:
            await monitor._mark_device_online("32:123456")
            mock_notify.assert_called_once_with("32:123456", True)

    @pytest.mark.asyncio
    async def test__notify_device_state_changed_callback_error(self, monitor):
        """Test _notify_device_state_changed handles callback errors."""
        error_callback = MagicMock(side_effect=Exception("Callback error"))
        monitor.register_callback("error_cb", error_callback, "32:123456")

        # Should not crash
        await monitor._notify_device_state_changed("32:123456", True)
        error_callback.assert_called_once_with(True)

    def test__handle_ramses_cc_message_no_src(self, monitor):
        """Test _handle_ramses_cc_message with no src."""
        event = MagicMock()
        event.data = {"dst": "32:123456"}  # No src

        monitor._handle_ramses_cc_message(event)
        # Should not crash

    def test__handle_ramses_cc_message_no_colon_in_src(self, monitor):
        """Test _handle_ramses_cc_message when src has no colon."""
        event = MagicMock()
        event.data = {"src": "invalid", "dst": "32:123456"}

        monitor._handle_ramses_cc_message(event)
        # Should not crash

    def test__handle_ramses_cc_message_no_timer_for_device(self, monitor):
        """Test _handle_ramses_cc_message when no timer for device."""
        event = MagicMock()
        event.data = {"src": "29:123456", "dst": "32:123456"}

        # No timer for this device
        monitor._handle_ramses_cc_message(event)
        # Should not crash

    def test__handle_msg_exception(self, monitor):
        """Test _handle_msg handles exceptions."""
        msg = MagicMock()
        msg.src = None  # This will cause an error

        # Should not crash
        monitor._handle_msg(msg)

    def test__is_transport_active_no_coordinator(self, monitor):
        """Test _is_transport_active with no coordinator."""
        result = monitor._is_transport_active()
        assert result is False

    def test__is_transport_active_no_client(self, monitor):
        """Test _is_transport_active with no client."""
        monitor._coordinator = MagicMock()
        monitor._coordinator.client = None

        result = monitor._is_transport_active()
        assert result is False

    def test__is_transport_active_exception(self, monitor):
        """Test _is_transport_active handles exceptions."""
        monitor._coordinator = MagicMock()
        monitor._coordinator.client.transport = None  # Will cause AttributeError

        result = monitor._is_transport_active()
        assert result is False

    @pytest.mark.asyncio
    async def test_force_check_callback_error(self, monitor):
        """Test force_check handles callback errors."""
        error_callback = MagicMock(side_effect=Exception("Callback error"))
        monitor.register_callback("error_cb", error_callback)

        # Should not crash
        await monitor.force_check()
        error_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_check_with_device_id(self, monitor):
        """Test force_check with device-specific callback."""
        callback = MagicMock()
        monitor.register_callback("device_cb", callback, "32:123456")
        monitor._device_states["32:123456"] = True

        await monitor.force_check()
        callback.assert_called_once_with(True)


class TestGetTransportMonitor:
    """Test get_transport_monitor factory."""

    def test_creates_singleton(self):
        """Test get_transport_monitor returns singleton."""
        from custom_components.ramses_extras.framework.helpers import transport_monitor

        # Reset global
        transport_monitor._transport_monitor = None

        monitor1 = get_transport_monitor()
        monitor2 = get_transport_monitor()

        assert monitor1 is monitor2
        assert isinstance(monitor1, TransportMonitor)
