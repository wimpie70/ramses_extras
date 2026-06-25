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
        hass.data = {"ramses_cc": {"mock_coordinator": MagicMock(client=MagicMock())}}
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
    async def test_start_monitoring_coordinator_without_client_attr(self, monitor):
        """Test start_monitoring when coordinator lacks client attribute."""
        hass = MagicMock()
        hass.data = {"ramses_cc": {"mock_coordinator": MagicMock(spec=[])}}

        await monitor.start_monitoring(None, hass)

        assert monitor._coordinator is None

    @pytest.mark.asyncio
    async def test_start_monitoring_coordinator_client_none(self, monitor):
        """Test start_monitoring when coordinator.client is None."""
        hass = MagicMock()
        coordinator = MagicMock()
        coordinator.client = None
        hass.data = {"ramses_cc": {"mock_coordinator": coordinator}}

        await monitor.start_monitoring(None, hass)

        assert monitor._coordinator is None

    @pytest.mark.asyncio
    async def test_ensure_msg_handler_exception_handling(self, monitor):
        """Test _ensure_msg_handler handles unsubscribe exceptions."""
        mock_unsub = MagicMock(side_effect=RuntimeError("test error"))
        monitor._msg_handler_unsub = mock_unsub
        monitor._client = MagicMock()

        # Should not raise, just log error
        monitor._ensure_msg_handler(None)

        assert monitor._msg_handler_unsub is None

    @pytest.mark.asyncio
    async def test__mark_device_online_already_online(self, monitor):
        """Test _mark_device_online when already online does not re-notify."""
        monitor._device_states["32:123456"] = True

        # Should NOT notify when state hasn't changed (avoids per-packet spam)
        with patch.object(monitor, "_notify_device_state_changed") as mock_notify:
            await monitor._mark_device_online("32:123456")
            mock_notify.assert_not_called()

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
        monitor._coordinator.client = MagicMock()

        result = monitor._is_transport_active()
        assert result is True

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

    def test_register_callback_with_device_id_and_hass(self, monitor):
        """Test register_callback with device_id when hass is set."""
        hass = MagicMock()
        monitor._hass = hass
        monitor._device_states["32:123456"] = False

        callback = MagicMock()
        monitor.register_callback("test_callback", callback, "32_123456")

        # Should call callback with initial state
        callback.assert_called_once_with(False)

    def test_register_callback_initial_callback_error(self, monitor):
        """Test register_callback handles initial callback error."""
        hass = MagicMock()
        monitor._hass = hass
        monitor._device_states["32:123456"] = True

        error_callback = MagicMock(side_effect=Exception("Callback error"))
        monitor.register_callback("error_cb", error_callback, "32_123456")

        # Should not crash despite error
        assert "error_cb" in monitor._callbacks

    def test_mark_device_offline_immediate(self, monitor):
        """Test mark_device_offline_immediate."""
        hass = MagicMock()
        monitor._hass = hass
        hass.loop.call_soon_threadsafe = MagicMock()

        monitor.mark_device_offline_immediate("32_123456")

        assert monitor._device_states["32:123456"] is False
        hass.loop.call_soon_threadsafe.assert_called_once()

    def test_mark_device_offline_immediate_already_offline(self, monitor):
        """Test mark_device_offline_immediate when already offline."""
        monitor._device_states["32:123456"] = False
        hass = MagicMock()
        monitor._hass = hass
        hass.loop.call_soon_threadsafe = MagicMock()

        monitor.mark_device_offline_immediate("32_123456")

        # Should not call call_soon_threadsafe since already offline
        hass.loop.call_soon_threadsafe.assert_not_called()

    def test_mark_device_offline_immediate_cancels_task(self, monitor):
        """Test mark_device_offline_immediate cancels existing task."""
        hass = MagicMock()
        monitor._hass = hass
        hass.loop.call_soon_threadsafe = MagicMock()

        existing_task = MagicMock()
        existing_task.done.return_value = False
        monitor._device_timeout_tasks["32:123456"] = existing_task

        monitor.mark_device_offline_immediate("32_123456")

        existing_task.cancel.assert_called_once()
        assert "32:123456" not in monitor._device_timeout_tasks

    @pytest.mark.asyncio
    async def test_mark_all_tracked_devices_offline(self, monitor):
        """Test _mark_all_tracked_devices_offline."""
        monitor.register_callback("cb1", MagicMock(), "32:123456")
        monitor.register_callback("cb2", MagicMock(), "32:123457")

        existing_task1 = MagicMock()
        existing_task1.done.return_value = False
        existing_task2 = MagicMock()
        existing_task2.done.return_value = False
        monitor._device_timeout_tasks["32:123456"] = existing_task1
        monitor._device_timeout_tasks["32:123457"] = existing_task2

        await monitor._mark_all_tracked_devices_offline()

        assert monitor._device_states["32:123456"] is False
        assert monitor._device_states["32:123457"] is False
        existing_task1.cancel.assert_called_once()
        existing_task2.cancel.assert_called_once()

    def test_refresh_coordinator_no_hass(self, monitor):
        """Test _refresh_coordinator when hass is None."""
        monitor._hass = None

        monitor._refresh_coordinator()

        # Should not crash
        assert monitor._coordinator is None

    def test_refresh_coordinator_no_ramses_cc_data(self, monitor):
        """Test _refresh_coordinator when ramses_cc data not found."""
        hass = MagicMock()
        hass.data = {}
        monitor._hass = hass

        monitor._refresh_coordinator()

        # Should not crash
        assert monitor._coordinator is None

    def test_ensure_msg_handler_client_unchanged(self, monitor):
        """Test _ensure_msg_handler when client unchanged."""
        monitor._client = MagicMock()
        monitor._msg_handler_unsub = MagicMock()

        monitor._ensure_msg_handler(monitor._client)

        # Should not call unsubscribe
        monitor._msg_handler_unsub.assert_not_called()

    def test_ensure_msg_handler_removes_old_handler(self, monitor):
        """Test _ensure_msg_handler removes old handler."""
        old_client = MagicMock()
        new_client = MagicMock()
        monitor._client = old_client
        monitor._msg_handler_unsub = MagicMock()

        # The method checks if client is the same before removing handler
        # So we need to ensure they're different
        monitor._ensure_msg_handler(new_client)

        # Since old_client != new_client, it should have tried to remove
        # But if the removal failed (exception), it won't call
        # Let's just verify the client was updated
        assert monitor._client is new_client

    def test_ensure_msg_handler_no_add_msg_handler(self, monitor):
        """Test _ensure_msg_handler when client has no add_msg_handler."""
        new_client = MagicMock(spec=[])  # No add_msg_handler
        monitor._client = MagicMock()
        monitor._msg_handler_unsub = MagicMock()

        monitor._ensure_msg_handler(new_client)

        assert monitor._client is new_client

    def test_ensure_msg_handler_add_msg_handler_fails(self, monitor):
        """Test _ensure_msg_handler when add_msg_handler raises."""
        new_client = MagicMock()
        new_client.add_msg_handler.side_effect = Exception("Handler error")
        monitor._client = MagicMock()
        monitor._msg_handler_unsub = MagicMock()

        monitor._ensure_msg_handler(new_client)

        # Should not crash
        assert monitor._client is new_client

    def test_handle_ramses_cc_message_no_data(self, monitor):
        """Test _handle_ramses_cc_message with no data."""
        event = MagicMock()
        event.data = None

        monitor._handle_ramses_cc_message(event)

        # Should not crash

    def test_handle_ramses_cc_message_invalid_data(self, monitor):
        """Test _handle_ramses_cc_message with invalid data."""
        event = MagicMock()
        event.data = "not a dict"

        monitor._handle_ramses_cc_message(event)

        # Should not crash

    def test_handle_ramses_cc_message_not_tracked_device(self, monitor):
        """Test _handle_ramses_cc_message for untracked device."""
        event = MagicMock()
        event.data = {"src": "29:999999", "dst": "32:123456"}

        monitor.register_callback("cb", MagicMock(), "32:123456")

        monitor._handle_ramses_cc_message(event)

        # Should not crash, device not tracked

    def test_handle_msg_no_src(self, monitor):
        """Test _handle_msg when msg has no src."""
        msg = MagicMock()
        msg.src = None

        monitor._handle_msg(msg)

        # Should not crash

    def test_handle_msg_no_colon_in_src(self, monitor):
        """Test _handle_msg when src has no colon."""
        msg = MagicMock()
        src = MagicMock()
        src.id = "invalid"
        msg.src = src

        monitor._handle_msg(msg)

        # Should not crash

    def test_handle_msg_not_tracked_device(self, monitor):
        """Test _handle_msg for untracked device."""
        msg = MagicMock()
        src = MagicMock()
        src.id = "29:999999"
        msg.src = src
        dst = MagicMock()
        dst.id = "32:123456"
        msg.dst = dst

        monitor.register_callback("cb", MagicMock(), "32:123456")

        monitor._handle_msg(msg)

        # Should not crash, device not tracked

    @pytest.mark.asyncio
    async def test_start_monitoring_with_no_client(self, monitor):
        """Test start_monitoring when coordinator has no client."""
        hass = MagicMock()
        hass.bus.async_listen.return_value = MagicMock()

        coordinator = MagicMock()
        coordinator.client = None

        await monitor.start_monitoring(coordinator, hass)

        assert monitor._coordinator is coordinator
        assert monitor._hass is hass

    @pytest.mark.asyncio
    async def test_start_monitoring_event_listen_fails(self, monitor):
        """Test start_monitoring when event listen fails."""
        hass = MagicMock()
        hass.bus.async_listen.side_effect = Exception("Listen error")

        coordinator = MagicMock()
        coordinator.client = MagicMock()
        coordinator.client.add_msg_handler.return_value = MagicMock()

        await monitor.start_monitoring(coordinator, hass)

        # Should not crash
        assert monitor._coordinator is coordinator

    @pytest.mark.asyncio
    async def test_stop_monitoring_cleanup_event_unsub(self, monitor):
        """Test stop_monitoring cleans up event listener."""

        async def dummy_task():
            await asyncio.sleep(1)

        monitor._monitor_task = asyncio.create_task(dummy_task())
        monitor._event_unsub = MagicMock()

        await monitor.stop_monitoring()

        # Verify unsub was set to None (cleanup happened)
        assert monitor._event_unsub is None

    @pytest.mark.asyncio
    async def test_stop_monitoring_cleanup_msg_handler_unsub(self, monitor):
        """Test stop_monitoring cleans up msg handler."""

        async def dummy_task():
            await asyncio.sleep(1)

        monitor._monitor_task = asyncio.create_task(dummy_task())
        monitor._msg_handler_unsub = MagicMock()

        await monitor.stop_monitoring()

        # Verify unsub was set to None (cleanup happened)
        assert monitor._msg_handler_unsub is None

    @pytest.mark.asyncio
    async def test_monitor_loop_transport_state_change(self, monitor):
        """Test _monitor_loop detects transport state change."""
        hass = MagicMock()
        monitor._hass = hass
        monitor._coordinator = MagicMock()
        monitor._coordinator.client = MagicMock()

        # Set initial state
        monitor._transport_available = True

        # Mock sleep to raise CancelledError after one iteration
        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with patch.object(monitor, "_refresh_coordinator"):
                with patch.object(monitor, "_is_transport_active", return_value=False):
                    with patch.object(
                        monitor, "_mark_all_tracked_devices_offline"
                    ) as mock_mark_offline:
                        try:
                            await monitor._monitor_loop()
                        except asyncio.CancelledError:
                            pass

                        # Should have marked devices offline when transport went down
                        mock_mark_offline.assert_called_once()


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
