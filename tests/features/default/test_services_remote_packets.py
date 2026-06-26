"""Tests for default services remote packet handling and zone ventilation.

These tests exercise the inner closure functions of async_setup_services
that are not directly accessible:
- _observed_command_from_packet (packet parsing)
- _async_apply_observed_remote_command (REM command application)
- _async_handle_observed_remote_packet (event handler chain)
- _handle_remote_event / _handle_remote_msg (event/message callbacks)
- _async_force_zone_ventilation (direct valve control service)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.services import (
    SVC_FORCE_ZONE_VENTILATION,
    async_setup_services,
)
from custom_components.ramses_extras.framework.helpers.zone_demand import DemandSource


@pytest.fixture
def hass():
    """Mock Home Assistant with event loop support."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.bus.fire = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.services = MagicMock()
    hass.data = {}
    hass.loop = MagicMock()
    hass.loop.call_later = MagicMock(return_value=MagicMock())
    hass.states = MagicMock()

    # Collect coroutines created by async_create_task for later draining
    pending_coros: list = []

    # call_soon_threadsafe should execute the callback synchronously
    def mock_call_soon_threadsafe(callback, *args, **kwargs):
        callback(*args, **kwargs)

    hass.loop.call_soon_threadsafe = mock_call_soon_threadsafe

    # async_create_task is called from sync context (_create_task),
    # so it must be sync. Collect coroutines for later awaiting.
    def mock_create_task(coro):
        if asyncio.iscoroutine(coro):
            pending_coros.append(coro)
        return MagicMock()

    hass.async_create_task = mock_create_task
    hass._pending_coros = pending_coros

    return hass


async def _drain_pending(hass):
    """Await all pending coroutines collected by async_create_task."""
    coros = hass._pending_coros[:]
    hass._pending_coros.clear()
    for coro in coros:
        await coro


def _get_service_func(hass, service_name):
    """Extract a registered service function by name."""
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == service_name:
            return call.args[2]
    return None


def _get_event_listener(hass):
    """Get the ramses_cc_message event listener callback."""
    hass.bus.async_listen.assert_called_once()
    return hass.bus.async_listen.call_args[0][1]


class TestObservedCommandFromPacket:
    """Test _observed_command_from_packet via the event handling chain.

    The function is a closure inside async_setup_services. We trigger it
    by firing the ramses_cc_message event listener with various payloads.
    """

    @pytest.mark.asyncio
    async def test_string_payload_22f1_fan_low(self, hass):
        """Test 22F1 hex payload -> fan_low."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000107",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            # record_remote_activity should have been called with command="fan_low"
            mock_bind.return_value.record_remote_activity.assert_called_once()
            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_low"

    @pytest.mark.asyncio
    async def test_string_payload_22f1_fan_medium(self, hass):
        """Test 22F1 hex payload -> fan_medium."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000207",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_medium"

    @pytest.mark.asyncio
    async def test_string_payload_22f1_fan_high(self, hass):
        """Test 22F1 hex payload -> fan_high."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000307",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_high"

    @pytest.mark.asyncio
    async def test_string_payload_22f1_fan_auto(self, hass):
        """Test 22F1 hex payload -> fan_auto."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000407",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_auto"

    @pytest.mark.asyncio
    async def test_string_payload_22f1_fan_away(self, hass):
        """Test 22F1 hex payload -> fan_away."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000007",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_away"

    @pytest.mark.asyncio
    async def test_string_payload_22f1_speed_byte_extraction(self, hass):
        """Test 22F1 with 6+ char payload extracts speed byte at [3:5]."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            # Payload "000104" -> speed_byte = "01" -> fan_low
            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000104",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_low"

    @pytest.mark.asyncio
    async def test_string_payload_22f3_timer_15min(self, hass):
        """Test 22F3 hex payload -> fan_timer_15min."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F3",
                "payload": "00120F03040404",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_timer_15min"

    @pytest.mark.asyncio
    async def test_string_payload_22f3_timer_30min(self, hass):
        """Test 22F3 hex payload -> fan_timer_30min."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F3",
                "payload": "00121E03040404",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_timer_30min"

    @pytest.mark.asyncio
    async def test_string_payload_22f3_timer_60min(self, hass):
        """Test 22F3 hex payload -> fan_timer_60min."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F3",
                "payload": "00123C03040404",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_timer_60min"

    @pytest.mark.asyncio
    async def test_dict_payload_fan_mode_by_name(self, hass):
        """Test dict payload with fan_mode name."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"fan_mode": "medium"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_medium"

    @pytest.mark.asyncio
    async def test_dict_payload_fan_mode_mid_alias(self, hass):
        """Test dict payload with 'mid' alias for medium."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"fan_mode": "mid"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_medium"

    @pytest.mark.asyncio
    async def test_dict_payload_fan_mode_by_idx(self, hass):
        """Test dict payload with fan_mode as numeric index."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"fan_mode": "03"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_high"

    @pytest.mark.asyncio
    async def test_dict_payload_mode_idx(self, hass):
        """Test dict payload with _mode_idx key."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"_mode_idx": "04"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_auto"

    @pytest.mark.asyncio
    async def test_dict_payload_speed_key(self, hass):
        """Test dict payload with speed key."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"speed": "high"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_high"

    @pytest.mark.asyncio
    async def test_dict_payload_fan_speed_key(self, hass):
        """Test dict payload with fan_speed key."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": {"fan_speed": "low"},
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_low"

    @pytest.mark.asyncio
    async def test_list_payload_with_dict(self, hass):
        """Test list payload containing a dict."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": [{"fan_mode": "away"}],
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_away"

    @pytest.mark.asyncio
    async def test_string_dict_payload_literal_eval(self, hass):
        """Test string payload that looks like a dict (ast.literal_eval)."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "{'fan_mode': 'low'}",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_low"

    @pytest.mark.asyncio
    async def test_unknown_code_returns_none(self, hass):
        """Test that unknown code returns None command."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "9999",
                "payload": "some_payload",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            # record_remote_activity should NOT be called since command is None
            mock_bind.return_value.record_remote_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_string_code_returns_none(self, hass):
        """Test that non-string code returns None."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": None,
                "payload": "000107",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            mock_bind.return_value.record_remote_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_verb_rq_returns_early(self, hass):
        """Test that RQ verb is ignored."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with patch(
            "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
        ) as mock_bind:
            mock_bind.return_value.record_remote_activity = MagicMock()

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000107",
                "verb": "RQ",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            # Should not record activity for RQ
            mock_bind.return_value.record_remote_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_dict_data_ignored(self, hass):
        """Test that non-dict event data is ignored."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        event = MagicMock()
        event.data = "not a dict"

        # Should not raise
        listener(event)
        await _drain_pending(hass)

        await _drain_pending(hass)

    @pytest.mark.asyncio
    async def test_matched_rem_applies_command(self, hass):
        """Test that a matched REM triggers command application."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_coord,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = ["18:123456"]
            mock_bind.return_value.get_bindings_for_fan.return_value = [
                {"rem_id": "18_123456", "zone_id": "01"}
            ]
            mock_bind.return_value.record_remote_activity = MagicMock()

            mock_arb_inst = MagicMock()
            mock_arb_inst.set_extras_control_enabled = MagicMock()
            mock_arb_inst.set_manual_override_state = MagicMock()
            mock_arb_inst.clear_manual_override_state = MagicMock()
            mock_arb_inst.async_commit_state = AsyncMock()
            mock_arb.return_value = mock_arb_inst

            mock_demand.return_value.get_all_demands_for_fan.return_value = {}

            mock_coord_inst = MagicMock()
            mock_coord_inst.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = mock_coord_inst

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000207",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            # Arbiter should have been called to set manual override
            mock_arb_inst.set_manual_override_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_matched_rem_fan_auto_command(self, hass):
        """Test matched REM with fan_auto command."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_coord,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = ["18:123456"]
            mock_bind.return_value.get_bindings_for_fan.return_value = [
                {"rem_id": "18_123456", "zone_id": "01"}
            ]
            mock_bind.return_value.record_remote_activity = MagicMock()

            mock_arb_inst = MagicMock()
            mock_arb_inst.set_extras_control_enabled = MagicMock()
            mock_arb_inst.clear_manual_override_state = MagicMock()
            mock_arb_inst.async_commit_state = AsyncMock()
            mock_arb.return_value = mock_arb_inst

            mock_demand.return_value.get_all_demands_for_fan.return_value = {}

            mock_coord_inst = MagicMock()
            mock_coord_inst.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = mock_coord_inst

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000407",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            # fan_auto should set extras control enabled and clear override
            mock_arb_inst.set_extras_control_enabled.assert_called_once_with(
                "32:123456", True
            )
            mock_arb_inst.clear_manual_override_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_matched_rem_fan_away_command(self, hass):
        """Test matched REM with fan_away command."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_coord,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = ["18:123456"]
            mock_bind.return_value.get_bindings_for_fan.return_value = [
                {"rem_id": "18_123456", "zone_id": "01"}
            ]
            mock_bind.return_value.record_remote_activity = MagicMock()

            mock_arb_inst = MagicMock()
            mock_arb_inst.set_extras_control_enabled = MagicMock()
            mock_arb_inst.clear_manual_override_state = MagicMock()
            mock_arb_inst.async_commit_state = AsyncMock()
            mock_arb.return_value = mock_arb_inst

            mock_demand.return_value.get_all_demands_for_fan.return_value = {}

            mock_coord_inst = MagicMock()
            mock_coord_inst.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = mock_coord_inst

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000007",
                "verb": "I",
            }
            listener(event)
            await _drain_pending(hass)

            await _drain_pending(hass)

            # fan_away should disable extras control
            mock_arb_inst.set_extras_control_enabled.assert_called_once_with(
                "32:123456", False
            )

    @pytest.mark.asyncio
    async def test_dedup_within_15_seconds(self, hass):
        """Test that duplicate packets within 1.5s are deduplicated."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        listener = _get_event_listener(hass)

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_coord,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = ["18:123456"]
            mock_bind.return_value.get_bindings_for_fan.return_value = [
                {"rem_id": "18_123456", "zone_id": "01"}
            ]
            mock_bind.return_value.record_remote_activity = MagicMock()

            mock_arb_inst = MagicMock()
            mock_arb_inst.set_extras_control_enabled = MagicMock()
            mock_arb_inst.set_manual_override_state = MagicMock()
            mock_arb_inst.clear_manual_override_state = MagicMock()
            mock_arb_inst.async_commit_state = AsyncMock()
            mock_arb.return_value = mock_arb_inst

            mock_demand.return_value.get_all_demands_for_fan.return_value = {}

            mock_coord_inst = MagicMock()
            mock_coord_inst.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = mock_coord_inst

            event = MagicMock()
            event.data = {
                "src": "18_123456",
                "dst": "32_123456",
                "code": "22F1",
                "payload": "000207",
                "verb": "I",
            }

            # First call should process
            listener(event)
            await _drain_pending(hass)
            # set_manual_override_state should be called once
            assert mock_arb_inst.set_manual_override_state.call_count == 1

            # Second call within 1.5s should be deduplicated
            listener(event)
            await _drain_pending(hass)
            # set_manual_override_state should still only be called once
            assert mock_arb_inst.set_manual_override_state.call_count == 1


class TestHandleRemoteMsg:
    """Test _handle_remote_msg callback (from ramses_cc add_msg_handler)."""

    @pytest.mark.asyncio
    async def test_msg_handler_with_addr_attributes(self, hass):
        """Test message handler with addr1/addr2 attributes (PacketDTO)."""
        hass.services.has_service.return_value = False

        mock_coordinator = MagicMock()
        mock_client = MagicMock()
        mock_client.add_msg_handler = MagicMock(return_value=MagicMock())
        mock_coordinator.client = mock_client

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=mock_coordinator
            )
            await async_setup_services(hass)

        # Get the msg handler callback
        msg_handler = mock_client.add_msg_handler.call_args[0][0]

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            msg = MagicMock()
            msg.addr1 = "18_123456"
            msg.addr2 = "32_123456"
            msg.code = "22F1"
            msg.payload = "000107"
            msg.verb = "I"

            msg_handler(msg)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_low"

    @pytest.mark.asyncio
    async def test_msg_handler_with_src_dst_attributes(self, hass):
        """Test message handler with src/dst attributes (Message object)."""
        hass.services.has_service.return_value = False

        mock_coordinator = MagicMock()
        mock_client = MagicMock()
        mock_client.add_msg_handler = MagicMock(return_value=MagicMock())
        mock_coordinator.client = mock_client

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=mock_coordinator
            )
            await async_setup_services(hass)

        msg_handler = mock_client.add_msg_handler.call_args[0][0]

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
            ),
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_demand_registry"
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
            ) as mock_bind,
        ):
            mock_bind.return_value.get_all_rem_ids_for_fan.return_value = []
            mock_bind.return_value.record_remote_activity = MagicMock()

            msg = MagicMock()
            del msg.addr1
            del msg.addr2
            msg.src = MagicMock()
            msg.src.id = "18_123456"
            msg.dst = MagicMock()
            msg.dst.id = "32_123456"
            msg.code = "22F1"
            msg.payload = "000207"
            msg.verb = "I"

            msg_handler(msg)
            await _drain_pending(hass)

            await _drain_pending(hass)

            call_kwargs = mock_bind.return_value.record_remote_activity.call_args
            assert call_kwargs.kwargs["command"] == "fan_medium"


class TestForceZoneVentilation:
    """Test _async_force_zone_ventilation service."""

    @pytest.mark.asyncio
    async def test_force_ventilation_on(self, hass):
        """Test forcing ventilation ON."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "on",
        }

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = "cover.outlet_01"
            mock_zone_config.max_position = 100
            mock_zone_config.min_position = 0

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            await func(call)

            hass.bus.fire.assert_called()
            fire_args = hass.bus.fire.call_args
            assert fire_args.args[0] == "ramses_extras_zone_ventilation_forced"
            assert fire_args.args[1]["state"] == "on"
            assert fire_args.args[1]["position"] == 100

    @pytest.mark.asyncio
    async def test_force_ventilation_off(self, hass):
        """Test forcing ventilation OFF."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "off",
        }

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = "cover.outlet_01"
            mock_zone_config.max_position = 100
            mock_zone_config.min_position = 0

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            await func(call)

            fire_args = hass.bus.fire.call_args
            assert fire_args.args[1]["state"] == "off"
            assert fire_args.args[1]["position"] == 0

    @pytest.mark.asyncio
    async def test_force_ventilation_zone_not_found(self, hass, caplog):
        """Test forcing ventilation when zone doesn't exist."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "99",
            "state": "on",
        }

        with patch(
            "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
        ) as mock_get_coord:
            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = None
            mock_get_coord.return_value = mock_coord

            await func(call)

            assert "Zone 32:123456:99 not found" in caplog.text

    @pytest.mark.asyncio
    async def test_force_ventilation_zone_not_controllable(self, hass, caplog):
        """Test forcing ventilation when zone is not controllable."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "on",
        }

        with patch(
            "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
        ) as mock_get_coord:
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = False

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            await func(call)

            assert "not controllable" in caplog.text

    @pytest.mark.asyncio
    async def test_force_ventilation_open_alias(self, hass):
        """Test 'open' as alias for 'on'."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "open",
        }

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_zone_config.max_position = 80
            mock_zone_config.min_position = 10

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            await func(call)

            fire_args = hass.bus.fire.call_args
            assert fire_args.args[1]["state"] == "on"
            assert fire_args.args[1]["position"] == 80

    @pytest.mark.asyncio
    async def test_force_ventilation_inlet_failure(self, hass, caplog):
        """Test that inlet valve failure is handled gracefully."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "on",
        }

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_async_call,
        ):
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_zone_config.max_position = 100
            mock_zone_config.min_position = 0

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_async_call.side_effect = Exception("Service call failed")

            await func(call)

            assert "Failed to set inlet" in caplog.text
            # Should still fire event
            hass.bus.fire.assert_called()

    @pytest.mark.asyncio
    async def test_force_ventilation_no_valve_entities(self, hass):
        """Test forcing ventilation with no valve entities configured."""
        hass.services.has_service.return_value = False

        with patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_cmds:
            mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(
                return_value=None
            )
            await async_setup_services(hass)

        func = _get_service_func(hass, SVC_FORCE_ZONE_VENTILATION)
        assert func is not None

        call = MagicMock()
        call.data = {
            "device_id": "32:123456",
            "zone_id": "01",
            "state": "on",
        }

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = None
            mock_zone_config.outlet_valve_entity = None
            mock_zone_config.max_position = 100
            mock_zone_config.min_position = 0

            mock_coord = MagicMock()
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            await func(call)

            # Should still fire event
            hass.bus.fire.assert_called()
            fire_args = hass.bus.fire.call_args
            assert fire_args.args[1]["results"] == {}
