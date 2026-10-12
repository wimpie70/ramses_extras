"""Tests for switch/contact demand inputs (issue 289)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.helpers.demand_inputs import (
    async_apply_demand_input,
    async_attach_demand_input_listeners,
    input_id_for_binding,
    is_demand_input_binding,
    role_of_binding,
)
from custom_components.ramses_extras.framework.helpers.zone_demand import (
    DemandSource,
)

_MOD = "custom_components.ramses_extras.framework.helpers.demand_inputs"


@pytest.fixture
def hass():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.loop = MagicMock()
    hass.loop.call_later = MagicMock(return_value=MagicMock())

    pending_coros: list = []

    def mock_create_task(coro):
        if asyncio.iscoroutine(coro):
            pending_coros.append(coro)
        return MagicMock()

    hass.async_create_task = mock_create_task
    hass._pending_coros = pending_coros
    return hass


async def _drain_pending(hass):
    coros = hass._pending_coros[:]
    hass._pending_coros.clear()
    for coro in coros:
        await coro


@pytest.fixture
def mocks():
    """Patch the helper's collaborators and yield them."""
    arbiter = MagicMock()
    arbiter.async_commit_state = AsyncMock()
    release_mgr = MagicMock()
    demand_registry = MagicMock()
    coordinator = MagicMock()
    coordinator.async_run_zone_actuation_cycle = AsyncMock()
    resume = AsyncMock()

    with (
        patch(f"{_MOD}.get_fan_speed_arbiter", return_value=arbiter),
        patch(f"{_MOD}.get_override_release_manager", return_value=release_mgr),
        patch(f"{_MOD}.get_zone_demand_registry", return_value=demand_registry),
        patch(f"{_MOD}.get_zone_coordinator", return_value=coordinator),
        patch(f"{_MOD}.async_resume_feature_control", resume),
        patch(
            "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry"
        ) as mock_zones,
    ):
        mock_zones.return_value.get_zone.return_value = None
        yield {
            "arbiter": arbiter,
            "release_mgr": release_mgr,
            "demand_registry": demand_registry,
            "coordinator": coordinator,
            "resume": resume,
        }


class TestBindingRoles:
    def test_role_defaults_to_remote(self):
        assert role_of_binding({}) == "remote"
        assert role_of_binding({"role": "remote"}) == "remote"
        assert not is_demand_input_binding({"role": "remote"})

    def test_demand_input_roles(self):
        assert is_demand_input_binding({"role": "switch"})
        assert is_demand_input_binding({"role": "contact"})

    def test_input_id_prefers_entity_id(self):
        binding = {"rem_id": "29_123456", "entity_id": "binary_sensor.window"}
        assert input_id_for_binding(binding) == "binary_sensor.window"
        assert input_id_for_binding({"rem_id": "29_123456"}) == "29:123456"


class TestFanTarget:
    @pytest.mark.asyncio
    async def test_momentary_switch_sets_override_and_release(self, hass, mocks):
        binding = {
            "role": "switch",
            "entity_id": "switch.toilet",
            "demand_speed": "fan_high",
            "manual_timeout": 300,
        }
        await async_apply_demand_input(hass, "32:153289", binding)

        arbiter = mocks["arbiter"]
        arbiter.set_extras_control_enabled.assert_called_once_with("32:153289", True)
        arbiter.set_manual_override_state.assert_called_once()
        kwargs = arbiter.set_manual_override_state.call_args.kwargs
        assert kwargs["source_id"] == "switch.toilet"
        assert kwargs["requested_speed"] == "fan_high"
        arbiter.async_commit_state.assert_awaited_once()
        mocks["release_mgr"].schedule_release.assert_called_once()
        assert mocks["release_mgr"].schedule_release.call_args.args == (
            "32:153289",
            300,
        )

    @pytest.mark.asyncio
    async def test_repress_rearms_release(self, hass, mocks):
        binding = {
            "role": "switch",
            "rem_id": "29:176861",
            "manual_timeout": 60,
        }
        await async_apply_demand_input(hass, "32:153289", binding, timed=True)
        await async_apply_demand_input(hass, "32:153289", binding, timed=True)
        # Two activations -> two schedules (manager replaces pending handle)
        assert mocks["release_mgr"].schedule_release.call_count == 2

    @pytest.mark.asyncio
    async def test_momentary_ignores_deactivation(self, hass, mocks):
        binding = {"role": "switch", "entity_id": "switch.toilet"}
        await async_apply_demand_input(hass, "32:153289", binding, active=False)
        mocks["arbiter"].set_manual_override_state.assert_not_called()
        mocks["arbiter"].clear_demand_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_latching_contact_clear(self, hass, mocks):
        binding = {
            "role": "contact",
            "entity_id": "binary_sensor.window",
            "demand_speed": "fan_low",
        }
        # Activate: latching -> no release scheduled
        await async_apply_demand_input(hass, "32:153289", binding, active=True)
        mocks["release_mgr"].schedule_release.assert_not_called()
        assert (
            mocks["arbiter"].set_manual_override_state.call_args.kwargs[
                "requested_speed"
            ]
            == "fan_low"
        )

        # Deactivate: only this source's demand is cleared
        await async_apply_demand_input(hass, "32:153289", binding, active=False)
        mocks["arbiter"].clear_demand_state.assert_called_once_with(
            "32:153289",
            feature_id="manual_override",
            source_id="binary_sensor.window",
        )
        mocks["resume"].assert_awaited_once_with(hass, "32:153289")


class TestZoneTarget:
    @pytest.mark.asyncio
    async def test_zone_target_sets_zone_demand_only(self, hass, mocks):
        binding = {
            "role": "contact",
            "entity_id": "binary_sensor.window",
            "demand_target": "zone",
            "zone_id": "zone 2 + 3",
        }
        await async_apply_demand_input(hass, "32:153289", binding)

        mocks["arbiter"].set_manual_override_state.assert_not_called()
        mocks["demand_registry"].set_demand.assert_called_once()
        args = mocks["demand_registry"].set_demand.call_args.args
        assert args[:3] == ("32:153289", "zone 2 + 3", DemandSource.CONTACT)
        assert args[3] is True
        mocks["coordinator"].async_run_zone_actuation_cycle.assert_awaited()

    @pytest.mark.asyncio
    async def test_both_targets(self, hass, mocks):
        binding = {
            "role": "switch",
            "entity_id": "switch.bathroom",
            "demand_target": "both",
            "zone_id": "bathroom",
            "manual_timeout": 120,
        }
        await async_apply_demand_input(hass, "32:153289", binding)

        mocks["arbiter"].set_manual_override_state.assert_called_once()
        mocks["demand_registry"].set_demand.assert_called_once()
        assert (
            mocks["demand_registry"].set_demand.call_args.args[2] == DemandSource.SWITCH
        )
        mocks["release_mgr"].schedule_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_zone_target_without_zone_id_warns(self, hass, mocks):
        binding = {
            "role": "contact",
            "entity_id": "binary_sensor.window",
            "demand_target": "zone",
        }
        await async_apply_demand_input(hass, "32:153289", binding)
        mocks["demand_registry"].set_demand.assert_not_called()

    @pytest.mark.asyncio
    async def test_contact_release_clears_zone_demand(self, hass, mocks):
        binding = {
            "role": "contact",
            "entity_id": "binary_sensor.window",
            "demand_target": "both",
            "zone_id": "zone 2 + 3",
        }
        await async_apply_demand_input(hass, "32:153289", binding, active=False)
        mocks["demand_registry"].clear_demand.assert_called_once_with(
            "32:153289", "zone 2 + 3", DemandSource.CONTACT
        )


class TestTimedRamsesSemantics:
    @pytest.mark.asyncio
    async def test_contact_over_rf_is_timed(self, hass, mocks):
        """A RAMSES contact has no 'released' edge -> timed demand."""
        binding = {
            "role": "contact",
            "rem_id": "29:176861",
            "manual_timeout": 900,
        }
        await async_apply_demand_input(
            hass, "32:153289", binding, active=True, timed=True
        )
        mocks["release_mgr"].schedule_release.assert_called_once()
        assert mocks["release_mgr"].schedule_release.call_args.args == (
            "32:153289",
            900,
        )

    @pytest.mark.asyncio
    async def test_timed_zone_only_release_still_scheduled(self, hass, mocks):
        """Zone-target timed inputs still get a release (was nested bug)."""
        binding = {
            "role": "switch",
            "rem_id": "29:176861",
            "demand_target": "zone",
            "zone_id": "zone 2 + 3",
            "manual_timeout": 300,
        }
        await async_apply_demand_input(
            hass, "32:153289", binding, active=True, timed=True
        )
        mocks["release_mgr"].schedule_release.assert_called_once()
        assert (
            mocks["release_mgr"].schedule_release.call_args.kwargs["clear_zone_source"]
            == DemandSource.SWITCH
        )


class TestEntityListeners:
    def test_no_bindings_no_listeners(self, hass):
        with patch(f"{_MOD}.iter_demand_input_bindings", return_value=[]):
            unsubs = async_attach_demand_input_listeners(hass, hass.data[DOMAIN])
        assert unsubs == []

    @pytest.mark.asyncio
    async def test_entity_state_change_applies_input(self, hass, mocks):
        binding = {
            "role": "switch",
            "entity_id": "switch.toilet",
            "manual_timeout": 60,
        }
        bindings = [("32:153289", binding)]

        captured: dict = {}

        def _track(hass_, entities, callback):
            captured["entities"] = entities
            captured["callback"] = callback
            return MagicMock()

        with (
            patch(f"{_MOD}.iter_demand_input_bindings", return_value=bindings),
            patch(
                "homeassistant.helpers.event.async_track_state_change_event",
                _track,
            ),
        ):
            unsubs = async_attach_demand_input_listeners(hass, hass.data[DOMAIN])

        assert len(unsubs) == 1
        assert captured["entities"] == ["switch.toilet"]

        # Simulate the entity turning on
        event = MagicMock()
        event.data = {"new_state": MagicMock(state="on")}
        captured["callback"](event)
        await _drain_pending(hass)

        mocks["arbiter"].set_manual_override_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_contact_entity_off_clears_demand(self, hass, mocks):
        binding = {
            "role": "contact",
            "entity_id": "binary_sensor.window",
        }
        bindings = [("32:153289", binding)]

        captured: dict = {}

        def _track(hass_, entities, callback):
            captured["callback"] = callback
            return MagicMock()

        with (
            patch(f"{_MOD}.iter_demand_input_bindings", return_value=bindings),
            patch(
                "homeassistant.helpers.event.async_track_state_change_event",
                _track,
            ),
        ):
            async_attach_demand_input_listeners(hass, hass.data[DOMAIN])

        event = MagicMock()
        event.data = {"new_state": MagicMock(state="off")}
        captured["callback"](event)
        await _drain_pending(hass)

        mocks["arbiter"].clear_demand_state.assert_called_once()
