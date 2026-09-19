"""Tests for transport_monitor to improve coverage."""

import asyncio
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

    def test_runtime_rename_replaces_state_subscription(self):
        """A runtime entity rename must replace the stale subscription."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        registry = MagicMock()
        old_entity = self._entity(
            "binary_sensor.pool_status_2",
            "ENTRY_pool_status_online",
        )
        new_entity = self._entity(
            "binary_sensor.pool_status",
            "ENTRY_pool_status_online",
        )
        registry.entities.values.return_value = [old_entity]
        old_unsub = MagicMock()
        new_unsub = MagicMock()

        with (
            patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=registry,
            ),
            patch(
                "homeassistant.helpers.event.async_track_state_change_event",
                side_effect=[old_unsub, new_unsub],
            ) as track_state,
        ):
            monitor._discover_pool_health_entities()
            monitor._subscribe_pool_state_changes()
            assert track_state.call_args.args[1] == ["binary_sensor.pool_status_2"]

            registry.entities.values.return_value = [new_entity]
            with patch(
                "custom_components.ramses_extras.framework.helpers."
                "transport_monitor.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=[None, asyncio.CancelledError],
            ):
                asyncio.run(monitor._monitor_loop())

        old_unsub.assert_called_once_with()
        assert track_state.call_args.args[1] == ["binary_sensor.pool_status"]
        assert monitor._pool_state_unsub is new_unsub

    def test_monitor_loop_rebinds_msg_handler_after_entry_reload(self):
        """The msg handler must follow the client across entry reloads.

        A ramses_cc entry reload replaces ``entry.runtime_data`` with a new
        coordinator and client.  The monitor must refresh its binding from
        the monitor loop — otherwise the message handler stays attached to
        the dead client and no received packet can re-online a device.
        """
        monitor = TransportMonitor()
        monitor._hass = MagicMock()

        old_client = MagicMock()
        old_unsub = MagicMock()
        old_client.add_msg_handler.return_value = old_unsub
        new_client = MagicMock()
        new_unsub = MagicMock()
        new_client.add_msg_handler.return_value = new_unsub

        entry = MagicMock()
        entry.runtime_data = MagicMock(client=old_client)
        monitor._hass.config_entries.async_entries.return_value = [entry]

        registry = MagicMock()
        registry.entities.values.return_value = []

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ):
            # Initial binding, as start_monitoring() would do.
            monitor._refresh_coordinator()
            old_client.add_msg_handler.assert_called_once_with(monitor._handle_msg)

            # Simulate an entry reload: runtime_data now exposes the
            # new coordinator/client.  The pool entity still exists, so
            # the loop's fallback path would not run — the refresh must
            # happen regardless.
            entry.runtime_data = MagicMock(client=new_client)
            monitor._pool_status_entity_id = "binary_sensor.pool_status"
            monitor._hass.states.get.return_value = MagicMock(state="on")

            with patch(
                "custom_components.ramses_extras.framework.helpers."
                "transport_monitor.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=[None, asyncio.CancelledError],
            ):
                asyncio.run(monitor._monitor_loop())

        old_unsub.assert_called_once_with()
        new_client.add_msg_handler.assert_called_once_with(monitor._handle_msg)
        assert monitor._client is new_client
        assert monitor._msg_handler_unsub is new_unsub


class TestDeviceStatusEntities:
    """Tests for ramses_cc per-device status entity consumption.

    ramses_cc issue 1210 adds ``binary_sensor.<device>_status``
    entities (unique_id ``{device_id}-device_status``).  When present
    they are the primary source of per-device liveness; the internal
    command-timer tracking is only a fallback.
    """

    @staticmethod
    def _entity(entity_id: str, unique_id: str) -> MagicMock:
        e = MagicMock()
        e.platform = "ramses_cc"
        e.entity_id = entity_id
        e.unique_id = unique_id
        return e

    @staticmethod
    def _discover(monitor: TransportMonitor, entities: list[MagicMock]) -> None:
        registry = MagicMock()
        registry.entities.values.return_value = entities
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ):
            monitor._discover_pool_health_entities()

    def test_discovers_device_status_entities_by_unique_id(self):
        """``{device_id}-device_status`` unique_ids map device -> entity."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        self._discover(
            monitor,
            [
                self._entity(
                    "binary_sensor.fan_32_153289_status",
                    "32:153289-device_status",
                ),
                self._entity(
                    "binary_sensor.rem_29_176861_status",
                    "29:176861-device_status",
                ),
            ],
        )
        assert monitor._device_status_entity_ids == {
            "32:153289": "binary_sensor.fan_32_153289_status",
            "29:176861": "binary_sensor.rem_29_176861_status",
        }

    def test_is_device_available_prefers_status_entity(self):
        """The status entity wins over the internal _device_states map."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        monitor._pool_status_entity_id = "binary_sensor.pool_status"
        monitor._device_status_entity_ids = {
            "32:153289": "binary_sensor.fan_32_153289_status"
        }

        def _state(entity_id: str) -> MagicMock:
            states = {
                "binary_sensor.pool_status": "on",
                "binary_sensor.fan_32_153289_status": "off",
            }
            return MagicMock(state=states[entity_id])

        monitor._hass.states.get.side_effect = _state

        # Internal tracking thinks the device is online, but cc says
        # it is not communicating.
        monitor._device_states["32:153289"] = True
        assert monitor.is_device_available("32:153289") is False

        # And the reverse: cc says online despite a stale internal
        # offline mark.
        def _state_flip(entity_id: str) -> MagicMock:
            states = {
                "binary_sensor.pool_status": "on",
                "binary_sensor.fan_32_153289_status": "on",
            }
            return MagicMock(state=states[entity_id])

        monitor._hass.states.get.side_effect = _state_flip
        monitor._device_states["32:153289"] = False
        assert monitor.is_device_available("32:153289") is True

    def test_is_device_available_pool_offline_overrides_entity(self):
        """An offline pool reports offline even if a status entity is on."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        monitor._pool_status_entity_id = "binary_sensor.pool_status"
        monitor._device_status_entity_ids = {
            "32:153289": "binary_sensor.fan_32_153289_status"
        }
        monitor._hass.states.get.side_effect = lambda eid: MagicMock(
            state="off" if eid == "binary_sensor.pool_status" else "on"
        )
        assert monitor.is_device_available("32:153289") is False

    def test_is_device_available_falls_back_without_entity(self):
        """No status entity -> internal _device_states is used."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        monitor._pool_status_entity_id = "binary_sensor.pool_status"
        monitor._hass.states.get.return_value = MagicMock(state="on")
        monitor._device_states["32:153289"] = False
        assert monitor.is_device_available("32:153289") is False

    def test_notify_command_sent_skips_timer_when_entity_tracked(self):
        """No 61s timer when ramses_cc tracks the device's liveness."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        monitor._device_status_entity_ids = {
            "32:153289": "binary_sensor.fan_32_153289_status"
        }
        monitor.notify_command_sent("32:153289")
        monitor._hass.async_create_task.assert_not_called()
        assert "32:153289" not in monitor._device_timeout_tasks

    def test_status_entity_change_fires_device_callback(self):
        """A status entity state change notifies registered callbacks."""
        monitor = TransportMonitor()
        monitor._hass = MagicMock()
        monitor._pool_status_entity_id = "binary_sensor.pool_status"
        monitor._device_status_entity_ids = {
            "32:153289": "binary_sensor.fan_32_153289_status"
        }

        captured: dict[str, object] = {}

        def _track(hass: object, entities: list[str], cb: object) -> MagicMock:
            captured["entities"] = entities
            captured["cb"] = cb
            return MagicMock()

        with (
            patch(
                "homeassistant.helpers.event.async_track_state_change_event",
                side_effect=_track,
            ),
            patch.object(monitor, "_discover_pool_health_entities"),
        ):
            monitor._subscribe_pool_state_changes()

        # The subscription covers the status entity too.
        assert "binary_sensor.fan_32_153289_status" in captured["entities"]

        # Simulate the entity going off.
        callback = MagicMock()
        monitor.register_callback("test", "32:153289", callback)
        event = MagicMock()
        event.data = {
            "entity_id": "binary_sensor.fan_32_153289_status",
            "new_state": MagicMock(state="off"),
        }
        captured["cb"](event)

        assert monitor._device_states["32:153289"] is False
        monitor._hass.async_create_task.assert_called_once()
