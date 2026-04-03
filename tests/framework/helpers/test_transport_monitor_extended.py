"""Tests for transport_monitor to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.transport_monitor import (
    TransportMonitor,
    get_transport_monitor,
)


class TestTransportMonitor:
    """Test TransportMonitor class."""

    @pytest.fixture
    def transport_monitor(self):
        """Create transport monitor instance."""
        return TransportMonitor()

    def test_transport_monitor_init(self, transport_monitor):
        """Test transport monitor initialization."""
        assert transport_monitor.is_transport_available is False
        assert transport_monitor._device_states == {}

    def test_register_callback(self, transport_monitor):
        """Test registering transport state callback."""
        callback = MagicMock()
        transport_monitor.register_callback("test", "32:153289", callback)
        assert "test" in transport_monitor._callbacks

    def test_unregister_callback(self, transport_monitor):
        """Test unregistering callback."""
        callback = MagicMock()
        transport_monitor.register_callback("test", "32:153289", callback)
        transport_monitor.unregister_callback("test")
        assert "test" not in transport_monitor._callbacks

    def test_notify_command_sent(self, transport_monitor):
        """Test notifying command was sent."""
        transport_monitor.register_callback("test", "32:153289", MagicMock())
        transport_monitor.notify_command_sent("32:153289")
        # Should not crash

    def test_update_device_message_received(self, transport_monitor):
        """Test updating device message received."""
        transport_monitor.update_device_message_received("32:153289")
        # Should not crash

    def test_is_device_available(self, transport_monitor):
        """Test device availability check."""
        # Default should be True
        assert transport_monitor.is_device_available("32:153289") is True

    def test_is_transport_available_property(self, transport_monitor):
        """Test transport available property."""
        assert transport_monitor.is_transport_available is False

    def test_is_monitoring_property(self, transport_monitor):
        """Test is monitoring property."""
        assert transport_monitor.is_monitoring is False


class TestGetTransportMonitor:
    """Test get_transport_monitor function."""

    def test_get_transport_monitor(self):
        """Test getting transport monitor."""
        monitor = get_transport_monitor()
        assert monitor is not None
        assert isinstance(monitor, TransportMonitor)


class TestTransportMonitorCallbacks:
    """Test transport monitor callback functionality."""

    @pytest.fixture
    def transport_monitor(self):
        """Create transport monitor instance."""
        return TransportMonitor()

    def test_register_callback(self, transport_monitor):
        """Test registering transport state callback."""
        callback = MagicMock()
        transport_monitor.register_callback("test", "32:153289", callback)
        assert "test" in transport_monitor._callbacks

    def test_callback_with_command_sent(self, transport_monitor):
        """Test callback triggered by command sent."""
        callback = MagicMock()
        transport_monitor.register_callback("test", "32:153289", callback)

        transport_monitor.notify_command_sent("32:153289")
        # Should not crash

    def test_callback_with_message_received(self, transport_monitor):
        """Test callback triggered by message received."""
        callback = MagicMock()
        transport_monitor.register_callback("test", "32:153289", callback)

        transport_monitor.update_device_message_received("32:153289")
        # Should not crash
