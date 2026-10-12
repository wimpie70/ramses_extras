"""Tests for the timed manual-override release helper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.helpers.override_release import (
    REVERT_EXTRAS_AUTO,
    REVERT_FAN_AUTO,
    OverrideReleaseManager,
    async_resume_feature_control,
    boost_release_delay,
    clear_source_zone_demands,
    get_override_release_manager,
)
from custom_components.ramses_extras.framework.helpers.zone_demand import (
    DemandSource,
)


@pytest.fixture
def hass():
    """Mock Home Assistant with event loop support."""
    hass = MagicMock()
    hass.data = {}
    hass.loop = MagicMock()

    handles: list = []

    def _call_later(delay, callback, *args):
        handle = MagicMock()
        handle.cancelled.return_value = False
        handles.append(handle)
        return handle

    hass.loop.call_later = MagicMock(side_effect=_call_later)
    hass._call_later_handles = handles

    pending_coros: list = []

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


class TestBoostReleaseDelay:
    """Duration is encoded in the fan_timer_* command itself."""

    def test_known_durations(self):
        # Arrange / Act / Assert
        assert boost_release_delay("fan_timer_15min") == 15 * 60 + 30
        assert boost_release_delay("fan_timer_30min") == 30 * 60 + 30
        assert boost_release_delay("fan_timer_60min") == 60 * 60 + 30

    def test_unknown_command_returns_none(self):
        assert boost_release_delay("fan_high") is None
        assert boost_release_delay("fan_away") is None

    def test_arbitrary_durations_parse(self):
        """Non-standard remote timer values still get a release delay."""
        assert boost_release_delay("fan_timer_5min") == 5 * 60 + 30
        assert boost_release_delay("fan_timer_120min") == 120 * 60 + 30


class TestScheduleAndCancel:
    """schedule_release arms call_later; re-pressing resets the timer."""

    def test_schedule_release_arms_timer(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)

        # Act
        mgr.schedule_release("32:123456", 900.0)

        # Assert
        hass.loop.call_later.assert_called_once()
        assert hass.loop.call_later.call_args.args[0] == 900.0

    def test_repeat_schedule_replaces_pending_timer(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)
        mgr.schedule_release("32:123456", 900.0)

        # Act
        mgr.schedule_release("32:123456", 1800.0)

        # Assert: first handle cancelled, new timer armed
        hass._call_later_handles[0].cancel.assert_called_once()
        second_call = hass.loop.call_later.call_args_list[1]
        assert second_call.args[0] == 1800.0
        assert hass.loop.call_later.call_count == 2

    def test_cancel_release_cancels_handle(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)
        mgr.schedule_release("32:123456", 900.0)

        # Act
        mgr.cancel_release("32:123456")

        # Assert
        handle = hass._call_later_handles[-1]
        handle.cancel.assert_called_once()
        assert "32:123456" not in mgr._handles

    def test_device_id_normalized(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)

        # Act
        mgr.schedule_release("32_123456", 60.0)

        # Assert: stored under colon-normalized id
        assert "32:123456" in mgr._handles


class TestAsyncRelease:
    """Release clears the override and applies the revert mode."""

    @pytest.mark.asyncio
    async def test_release_extras_auto_resumes_features(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)
        automation = MagicMock()
        automation._reconcile_startup_states = AsyncMock()
        hass.data[DOMAIN] = {"features": {"temp_control": {"automation": automation}}}

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "zone_coordinator.get_zone_coordinator"
            ) as mock_coord,
        ):
            arbiter = MagicMock()
            arbiter.async_commit_state = AsyncMock()
            mock_arb.return_value = arbiter
            mock_demand.return_value.get_all_demands_for_fan.return_value = {}
            coordinator = MagicMock()
            coordinator.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = coordinator

            # Act
            await mgr.async_release("32:123456", revert_mode=REVERT_EXTRAS_AUTO)

            # Assert
            arbiter.clear_manual_override_state.assert_called_once_with("32:123456")
            arbiter.set_extras_control_enabled.assert_called_once_with(
                "32:123456", True
            )
            arbiter.async_commit_state.assert_awaited_once_with(
                "32:123456", apply=False
            )
            coordinator.async_run_zone_actuation_cycle.assert_awaited_once()
            automation._reconcile_startup_states.assert_awaited_once_with("32:123456")

    @pytest.mark.asyncio
    async def test_release_fan_auto_disables_extras(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)
        automation = MagicMock()
        automation._reconcile_startup_states = AsyncMock()
        hass.data[DOMAIN] = {"features": {"temp_control": {"automation": automation}}}

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "zone_coordinator.get_zone_coordinator"
            ) as mock_coord,
        ):
            arbiter = MagicMock()
            arbiter.async_commit_state = AsyncMock()
            mock_arb.return_value = arbiter
            mock_demand.return_value.get_all_demands_for_fan.return_value = {}
            coordinator = MagicMock()
            coordinator.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = coordinator

            # Act
            await mgr.async_release("32:123456", revert_mode=REVERT_FAN_AUTO)

            # Assert: extras disabled, features NOT resumed
            arbiter.set_extras_control_enabled.assert_called_once_with(
                "32:123456", False
            )
            automation._reconcile_startup_states.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_scheduled_release_fires_via_call_later(self, hass):
        # Arrange
        mgr = OverrideReleaseManager(hass)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_fan_speed_arbiter"
            ) as mock_arb,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "override_release.get_zone_demand_registry"
            ) as mock_demand,
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "zone_coordinator.get_zone_coordinator"
            ) as mock_coord,
        ):
            arbiter = MagicMock()
            arbiter.async_commit_state = AsyncMock()
            mock_arb.return_value = arbiter
            mock_demand.return_value.get_all_demands_for_fan.return_value = {}
            coordinator = MagicMock()
            coordinator.async_run_zone_actuation_cycle = AsyncMock()
            mock_coord.return_value = coordinator

            mgr.schedule_release("32:123456", 900.0, revert_mode=REVERT_FAN_AUTO)

            # Act: fire the call_later callback
            callback = hass.loop.call_later.call_args.args[1]
            callback()
            await _drain_pending(hass)

            # Assert
            arbiter.clear_manual_override_state.assert_called_once_with("32:123456")
            arbiter.set_extras_control_enabled.assert_called_once_with(
                "32:123456", False
            )


class TestClearSourceZoneDemands:
    """Only demands of the given source are cleared."""

    def test_clears_only_matching_source(self, hass):
        # Arrange
        demand_registry = MagicMock()
        demand_registry.get_all_demands_for_fan.return_value = {
            "zone1": {DemandSource.REM: True, DemandSource.HUMIDITY: True},
            "zone2": {DemandSource.HUMIDITY: True},
        }

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "override_release.get_zone_demand_registry",
            return_value=demand_registry,
        ):
            # Act
            clear_source_zone_demands(hass, "32:123456", DemandSource.REM)

        # Assert: only the REM demand of zone1 cleared
        demand_registry.clear_demand.assert_called_once_with(
            "32:123456", "zone1", DemandSource.REM
        )


class TestResumeFeatureControl:
    """Feature automations are re-evaluated on release."""

    @pytest.mark.asyncio
    async def test_resumes_all_present_features(self, hass):
        # Arrange
        humidity = MagicMock()
        humidity._reconcile_startup_states = AsyncMock()
        co2 = MagicMock()
        co2._evaluate_co2_control = AsyncMock()
        temp = MagicMock()
        temp._reconcile_startup_states = AsyncMock()
        hass.data[DOMAIN] = {
            "features": {
                "humidity_control": {"automation": humidity},
                "co2_control": {"automation": co2},
                "temp_control": {"automation": temp},
            }
        }

        # Act
        await async_resume_feature_control(hass, "32:123456")

        # Assert
        humidity._reconcile_startup_states.assert_awaited_once_with()
        co2._evaluate_co2_control.assert_awaited_once_with("32:123456")
        temp._reconcile_startup_states.assert_awaited_once_with("32:123456")

    @pytest.mark.asyncio
    async def test_noop_without_features(self, hass):
        # Arrange / Act / Assert: must not raise
        await async_resume_feature_control(hass, "32:123456")


class TestManagerSingleton:
    def test_get_override_release_manager_caches(self, hass):
        # Arrange / Act
        mgr1 = get_override_release_manager(hass)
        mgr2 = get_override_release_manager(hass)

        # Assert
        assert mgr1 is mgr2
        assert isinstance(mgr1, OverrideReleaseManager)
