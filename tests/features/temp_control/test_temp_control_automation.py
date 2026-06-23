"""Tests for Temp Control automation decision logic.

Tests the core state machine:
- entering cooling (force bypass open)
- entering heating_retention (force bypass close)
- exiting cooling/heating_retention (return to idle)
- hysteresis behavior
- manual override (temp_control toggled off)
- safety: min_supply_temp
- min bypass mode interval (no command spam)
- humidity/CO2 speed gates
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.temp_control.config import (
    TempControlSettings,
)


def make_settings(**overrides) -> TempControlSettings:
    """Create TempControlSettings with defaults and optional overrides."""
    defaults = {
        "comfort_delta_activate": 1.0,
        "comfort_delta_deactivate": 0.5,
        "cooling_delta_activate": 1.0,
        "cooling_delta_deactivate": 0.5,
        "min_outdoor_temp": 10.0,
        "min_bypass_mode_interval_seconds": 180,
        "default_desired_speed": "high",
    }
    defaults.update(overrides)
    return TempControlSettings(**defaults)


def make_entity_states(
    temp_control=True,
    indoor_temp=22.0,
    outdoor_temp=18.0,
    supply_temp=18.0,
    comfort_temp=21.0,
    indoor_rh=50.0,
    min_rh=40.0,
    max_rh=60.0,
    dehumidifying_active=False,
    co2_active=False,
):
    """Build entity_states dict as expected by _process_automation_logic."""
    return {
        "temp_control": temp_control,
        "indoor_temp": indoor_temp,
        "outdoor_temp": outdoor_temp,
        "supply_temp": supply_temp,
        "comfort_temp": comfort_temp,
        "indoor_rh": indoor_rh,
        "min_rh": min_rh,
        "max_rh": max_rh,
        "dehumidifying_active": dehumidifying_active,
        "co2_active": co2_active,
    }


@pytest.fixture
def automation_manager():
    """Create a TempControlAutomationManager with mocked dependencies."""
    hass = MagicMock()
    hass.data = {"ramses_extras": {"enabled_features": {"temp_control": True}}}
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.states.get = MagicMock(return_value=None)

    config_entry = MagicMock()
    config_entry.options = {}
    config_entry.data = {}

    with (
        patch(
            "custom_components.ramses_extras.features.temp_control.automation.get_fan_speed_arbiter"
        ),
        patch(
            "custom_components.ramses_extras.features.temp_control.automation.RamsesCommands"
        ),
        patch(
            "custom_components.ramses_extras.features.temp_control.automation.TempControlConfig"
        ) as mock_config_cls,
    ):
        mock_config = MagicMock()
        mock_config.get_settings = MagicMock(return_value=make_settings())
        mock_config_cls.return_value = mock_config

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        mgr = TempControlAutomationManager(hass, config_entry)
        mgr._automation_active = True
        mgr.ramses_commands.send_command = AsyncMock()
        mgr.fan_speed_arbiter.async_set_demand = AsyncMock()
        mgr.fan_speed_arbiter.async_clear_demand = AsyncMock()
        mgr.fan_speed_arbiter.async_commit_state = AsyncMock()
        mgr._set_active_indicator = MagicMock()
        mgr._set_status_sensor = MagicMock()
        mgr._get_desired_speed_option = MagicMock(return_value="high")

        yield mgr


class TestTempControlDecisionLogic:
    """Test the core decision logic of _process_automation_logic."""

    @pytest.mark.asyncio
    async def test_disabled_when_switch_off(self, automation_manager):
        """When temp_control switch is off, mode should be disabled."""
        states = make_entity_states(temp_control=False)
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "disabled"
        automation_manager.ramses_commands.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_idle_when_in_comfort_band(self, automation_manager):
        """When indoor is within comfort band, mode should be idle."""
        states = make_entity_states(indoor_temp=21.0, comfort_temp=21.0)
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"

    @pytest.mark.asyncio
    async def test_enter_cooling(self, automation_manager):
        """When indoor above comfort + delta and outdoor can cool, enter cooling."""
        states = make_entity_states(
            indoor_temp=24.0,  # comfort(21) + delta_activate(1) = 22, 24 > 22
            outdoor_temp=18.0,  # indoor(24) - supply_cooler_delta(1) = 23, 18 <= 23
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "cooling"
        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_open"
        )

    @pytest.mark.asyncio
    async def test_enter_heating_retention(self, automation_manager):
        """When indoor below comfort - delta, enter heating_retention."""
        states = make_entity_states(
            indoor_temp=18.0,  # comfort(21) - delta_activate(1) = 20, 18 <= 20
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "heating_retention"
        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_close"
        )

    @pytest.mark.asyncio
    async def test_no_cooling_when_outdoor_too_warm(self, automation_manager):
        """When outdoor_temp is not cooler than indoor by required delta, stay idle."""
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=23.5,  # indoor(24) - delta(1) = 23, 23.5 > 23 → no cooling
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"

    @pytest.mark.asyncio
    async def test_no_cooling_when_outdoor_below_min(self, automation_manager):
        """When outdoor_temp is below min_supply_temp safety, stay idle."""
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=5.0,  # below min_supply_temp(10)
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"

    @pytest.mark.asyncio
    async def test_heating_retention_priority_over_cooling(self, automation_manager):
        """When indoor is below comfort-delta, heating_retention takes priority."""
        states = make_entity_states(
            indoor_temp=18.0,  # below comfort - delta
            supply_temp=5.0,  # below min_supply_temp, but heating_retention
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "heating_retention"

    @pytest.mark.asyncio
    async def test_transition_from_disabled_to_idle(self, automation_manager):
        """When previously disabled and switch turns on, go to idle (not KeyError)."""
        import time

        automation_manager._mode["32:153289"] = "disabled"
        # Set a recent bypass change time to test that the min-interval
        # guard doesn't cause desired_mode to become "disabled"
        automation_manager._last_bypass_change["32:153289"] = time.time() - 10

        states = make_entity_states(
            indoor_temp=21.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"

    @pytest.mark.asyncio
    async def test_transition_from_disabled_to_cooling(self, automation_manager):
        """When previously disabled and conditions warrant cooling, enter cooling."""
        automation_manager._mode["32:153289"] = "disabled"

        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "cooling"
        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_open"
        )


class TestTempControlHysteresis:
    """Test hysteresis behavior when transitioning between states."""

    @pytest.mark.asyncio
    async def test_cooling_hysteresis_stays_cooling(self, automation_manager):
        """When previously cooling, stay cooling until deactivate threshold."""
        automation_manager._mode["32:153289"] = "cooling"

        # indoor is now 21.6 — above comfort + deactivate(0.5) = 21.5
        # outdoor still cooler than indoor - deactivate_delta
        states = make_entity_states(
            indoor_temp=21.6,
            outdoor_temp=20.0,  # indoor(21.6) - deactivate(0.5) = 21.1, 20 <= 21.1
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "cooling"

    @pytest.mark.asyncio
    async def test_cooling_exits_when_indoor_returns(self, automation_manager):
        """When previously cooling and indoor returns to comfort band, exit to idle."""
        automation_manager._mode["32:153289"] = "cooling"
        # Set last_bypass_change to past so interval doesn't block
        import time

        automation_manager._last_bypass_change["32:153289"] = time.time() - 999

        # indoor is now 21.2 — below comfort + deactivate(0.5) = 21.5
        states = make_entity_states(
            indoor_temp=21.2,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"

    @pytest.mark.asyncio
    async def test_heating_retention_hysteresis_stays(self, automation_manager):
        """When previously heating_retention, stay until deactivate threshold."""
        automation_manager._mode["32:153289"] = "heating_retention"

        # indoor is 20.4 — below comfort - deactivate(0.5) = 20.5
        states = make_entity_states(
            indoor_temp=20.4,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "heating_retention"

    @pytest.mark.asyncio
    async def test_heating_retention_exits_when_indoor_returns(
        self, automation_manager
    ):
        """When previously heating_retention and indoor returns, exit to idle."""
        import time

        automation_manager._mode["32:153289"] = "heating_retention"
        automation_manager._last_bypass_change["32:153289"] = time.time() - 999

        # indoor is 20.6 — above comfort - deactivate(0.5) = 20.5
        states = make_entity_states(
            indoor_temp=20.6,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "idle"


class TestTempControlMinInterval:
    """Test minimum bypass mode interval prevents command spam."""

    @pytest.mark.asyncio
    async def test_min_interval_blocks_mode_change(self, automation_manager):
        """When min interval hasn't elapsed, mode change is blocked."""
        import time

        # Set previous mode to cooling and recent change time
        automation_manager._mode["32:153289"] = "cooling"
        automation_manager._last_bypass_change["32:153289"] = (
            time.time() - 10  # only 10s ago
        )

        # Conditions now say heating_retention (indoor dropped below comfort - delta)
        states = make_entity_states(
            indoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        # Should stay cooling because interval hasn't elapsed
        assert automation_manager._mode["32:153289"] == "cooling"

    @pytest.mark.asyncio
    async def test_min_interval_allows_after_elapsed(self, automation_manager):
        """When min interval has elapsed, mode change is allowed."""
        import time

        automation_manager._mode["32:153289"] = "cooling"
        automation_manager._last_bypass_change["32:153289"] = (
            time.time() - 999  # well past 180s
        )

        states = make_entity_states(
            indoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "heating_retention"


class TestTempControlSpeedDemand:
    """Test fan speed demand during cooling/idle/heating_retention.

    The arbiter resolves conflicts with humidity_control / co2_control,
    so temp_control always sets its demand during cooling and lets the
    arbiter pick the winning speed.
    """

    @pytest.mark.asyncio
    async def test_speed_demand_set_during_cooling(self, automation_manager):
        """When cooling, fan speed demand is set (arbiter resolves conflicts)."""
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.fan_speed_arbiter.async_set_demand.assert_called_once()
        automation_manager.fan_speed_arbiter.async_commit_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_speed_demand_set_during_cooling_even_if_dehumidifying(
        self, automation_manager
    ):
        """Temp_control sets its demand even when dehumidifying is active;
        the arbiter resolves the conflict."""
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
            dehumidifying_active=True,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.fan_speed_arbiter.async_set_demand.assert_called_once()

    @pytest.mark.asyncio
    async def test_speed_demand_cleared_in_idle(self, automation_manager):
        """When idle, fan speed demand is cleared."""
        states = make_entity_states(
            indoor_temp=21.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.fan_speed_arbiter.async_set_demand.assert_not_called()
        automation_manager.fan_speed_arbiter.async_clear_demand.assert_called_once()

    @pytest.mark.asyncio
    async def test_speed_demand_cleared_in_heating_retention(self, automation_manager):
        """When heating_retention, fan speed demand is cleared."""
        states = make_entity_states(
            indoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.fan_speed_arbiter.async_set_demand.assert_not_called()
        automation_manager.fan_speed_arbiter.async_clear_demand.assert_called_once()


class TestTempControlDisabled:
    """Test disabled/manual override behavior."""

    @pytest.mark.asyncio
    async def test_disabled_clears_speed_demand(self, automation_manager):
        """When temp_control switch is off, speed demand is cleared."""
        states = make_entity_states(temp_control=False)
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "disabled"
        automation_manager.fan_speed_arbiter.async_clear_demand.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_sets_active_indicator_off(self, automation_manager):
        """When disabled, active indicator is set to False."""
        states = make_entity_states(temp_control=False)
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager._set_active_indicator.assert_called_once()
        call_args = automation_manager._set_active_indicator.call_args
        assert call_args.args[1] is False  # active=False

    @pytest.mark.asyncio
    async def test_active_indicator_on_during_cooling(self, automation_manager):
        """When cooling, active indicator is set to True."""
        states = make_entity_states(
            indoor_temp=24.0,
            supply_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager._set_active_indicator.assert_called_once()
        call_args = automation_manager._set_active_indicator.call_args
        assert call_args.args[1] is True  # active=True
