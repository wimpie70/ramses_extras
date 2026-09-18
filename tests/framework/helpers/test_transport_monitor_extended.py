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


class TestPoolHealthEntityDiscovery:
    """Regression tests for _discover_pool_health_entities.

    The aggregate pool_status entity must be found by unique_id — the
    entity_id may be ``binary_sensor.pool_status`` or carry a ``_N``
    registry-collision suffix (``binary_sensor.pool_status_2``).
    """

    @staticmethod
    def _make_monitor_with_registry(entities: list[MagicMock]) -> TransportMonitor:
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        registry = MagicMock()
        registry.entities.values.return_value = entities
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ):
            monitor._discover_pool_health_entities()
        return monitor

    @staticmethod
    def _entity(entity_id: str, unique_id: str) -> MagicMock:
        e = MagicMock()
        e.platform = "ramses_cc"
        e.entity_id = entity_id
        e.unique_id = unique_id
        return e

    def test_discovers_clean_pool_status_entity_id(self):
        """binary_sensor.pool_status (no _N suffix) must be discovered."""
        monitor = self._make_monitor_with_registry(
            [
                self._entity(
                    "binary_sensor.pool_status",
                    "ENTRY_pool_status_online",
                )
            ]
        )
        assert monitor._pool_status_entity_id == "binary_sensor.pool_status"

    def test_discovers_suffixed_pool_status_entity_id(self):
        """binary_sensor.pool_status_2 (collision suffix) must be discovered."""
        monitor = self._make_monitor_with_registry(
            [
                self._entity(
                    "binary_sensor.pool_status_2",
                    "ENTRY_pool_status_online",
                )
            ]
        )
        assert monitor._pool_status_entity_id == "binary_sensor.pool_status_2"

    def test_discovers_hgi_online_entities_by_unique_id(self):
        """Per-HGI online entities resolve hgi_id from the unique_id."""
        monitor = self._make_monitor_with_registry(
            [
                self._entity(
                    "binary_sensor.hgi_18_130236_online",
                    "ENTRY_pool_child_18:130236_online",
                )
            ]
        )
        assert monitor._hgi_online_entity_ids == {
            "18:130236": "binary_sensor.hgi_18_130236_online"
        }
