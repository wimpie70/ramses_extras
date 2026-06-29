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
from custom_components.ramses_extras.framework.helpers.zone_demand import DemandSource


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
        "dewpoint_guard_enabled": False,
        "dewpoint_margin_c": 1.0,
        "supply_cooler_delta_activate": 1.0,
        "supply_cooler_delta_deactivate": 0.5,
        "min_supply_temp": 10.0,
    }
    defaults.update(overrides)
    return TempControlSettings(**defaults)


def make_entity_states(
    temp_control=True,
    indoor_temp=22.0,
    outdoor_temp=18.0,
    supply_temp=25.0,
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
            "custom_components.ramses_extras.features.temp_control.automation.get_zone_demand_registry"
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
        mgr.fan_speed_arbiter.is_manual_override_active = MagicMock(return_value=False)
        mgr.fan_speed_arbiter.is_extras_control_enabled = MagicMock(return_value=True)
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
            outdoor_temp=18.0,  # indoor(24) - cooling_delta(1) = 23, 18 <= 23
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "cooling"
        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_open"
        )

    @pytest.mark.asyncio
    async def test_cooling_via_supply_air(self, automation_manager):
        """Cooling via supply air when outdoor is warmer than indoor.

        Supply temp (18) is cooler than indoor (24) by the required delta,
        so cooling should activate even though outdoor (28) is hotter.
        """
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=28.0,  # hotter than indoor → outdoor can't cool
            supply_temp=18.0,  # indoor(24) - supply_delta(1) = 23, 18 <= 23
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


class TestTempControlManualOverride:
    """Test manual override / extras control checks."""

    @pytest.mark.asyncio
    async def test_skipped_when_manual_override_active(self, automation_manager):
        """When manual override is active (remote/card), temp_control skips
        processing and does not send any commands."""
        automation_manager.fan_speed_arbiter.is_manual_override_active = MagicMock(
            return_value=True
        )
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.ramses_commands.send_command.assert_not_called()
        automation_manager.fan_speed_arbiter.async_set_demand.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_when_extras_control_disabled(self, automation_manager):
        """When extras control is disabled (away/timer mode), temp_control
        skips processing."""
        automation_manager.fan_speed_arbiter.is_extras_control_enabled = MagicMock(
            return_value=False
        )
        states = make_entity_states(
            indoor_temp=24.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        automation_manager.ramses_commands.send_command.assert_not_called()
        automation_manager.fan_speed_arbiter.async_set_demand.assert_not_called()


class TestTempControlBypassSafetyNet:
    """Test the state-based manual override safety net."""

    @pytest.mark.asyncio
    async def test_external_bypass_change_turns_off_temp_control(
        self, automation_manager
    ):
        """When bypass position changes externally (no recent command from us),
        temp_control switch is turned off."""
        import time

        hass = automation_manager.hass
        # Simulate temp_control switch is on
        switch_state = MagicMock()
        switch_state.state = "on"
        hass.states.get = MagicMock(return_value=switch_state)
        hass.services.async_call = AsyncMock()

        # No recent bypass command from temp_control (old timestamp)
        automation_manager._last_bypass_command_time["32:153289"] = time.time() - 60
        # Safety net only fires when temp_control is actively forcing a
        # bypass state (cooling/heating_retention), not in idle.
        automation_manager._mode["32:153289"] = "cooling"

        old_state = MagicMock()
        new_state = MagicMock()

        await automation_manager._async_handle_state_change(
            "binary_sensor.32_153289_bypass_position",
            old_state,
            new_state,
        )

        hass.services.async_call.assert_called_once_with(
            "switch",
            "turn_off",
            {"entity_id": "switch.temp_control_32_153289"},
        )

    @pytest.mark.asyncio
    async def test_own_bypass_change_does_not_turn_off(self, automation_manager):
        """When bypass position changes shortly after we sent a command,
        temp_control is NOT turned off (it was our command)."""
        import time

        hass = automation_manager.hass
        switch_state = MagicMock()
        switch_state.state = "on"
        hass.states.get = MagicMock(return_value=switch_state)
        hass.services.async_call = AsyncMock()

        # Recent bypass command from temp_control (within 10s window)
        automation_manager._last_bypass_command_time["32:153289"] = time.time() - 2

        old_state = MagicMock()
        new_state = MagicMock()

        # Mock super()._async_handle_state_change to avoid full processing
        with patch.object(
            type(automation_manager).__mro__[1],
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ):
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                old_state,
                new_state,
            )

        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_bypass_change_ignored_when_temp_control_off(
        self, automation_manager
    ):
        """When temp_control switch is already off, bypass changes are ignored."""
        hass = automation_manager.hass
        switch_state = MagicMock()
        switch_state.state = "off"
        hass.states.get = MagicMock(return_value=switch_state)
        hass.services.async_call = AsyncMock()

        old_state = MagicMock()
        new_state = MagicMock()

        with patch.object(
            type(automation_manager).__mro__[1],
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ):
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                old_state,
                new_state,
            )

        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_bypass_entity_passes_through(self, automation_manager):
        """Non-bypass entity changes pass through to normal processing."""
        old_state = MagicMock()
        new_state = MagicMock()

        with patch.object(
            type(automation_manager).__mro__[1],
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "sensor.32_153289_indoor_temp",
                old_state,
                new_state,
            )

        mock_super.assert_called_once()


class TestTempControlPerAreaEvaluation:
    """Test per-area temperature evaluation and zone demand publishing."""

    @pytest.mark.asyncio
    async def test_evaluate_areas_returns_empty_when_no_sensor_control(
        self, automation_manager
    ):
        """When sensor_control is not enabled, _evaluate_areas returns []."""
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)
        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_evaluate_areas_returns_empty_when_no_areas(self, automation_manager):
        """When sensor_control has no area_sensors, returns []."""
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": []}
        )
        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_evaluate_areas_cooling_demand(self, automation_manager):
        """An area above comfort + delta with cool outdoor air → cooling."""
        area = {
            "area_id": "living_room",
            "zone_id": "zone_1",
            "enabled": True,
            "temperature_entity": "sensor.living_room_temp",
            "comfort_temperature_entity": "input_number.lr_comfort",
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )

        def mock_get(entity_id):
            if entity_id == "sensor.living_room_temp":
                return MagicMock(state="24.0")
            if entity_id == "input_number.lr_comfort":
                return MagicMock(state="21.0")
            return None

        automation_manager.hass.states.get = mock_get

        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )

        assert len(result) == 1
        assert result[0]["decision"] == "cooling"
        assert result[0]["area_id"] == "living_room"
        assert result[0]["zone_id"] == "zone_1"
        assert result[0]["area_temp"] == 24.0
        assert result[0]["area_comfort"] == 21.0

    @pytest.mark.asyncio
    async def test_evaluate_areas_heating_retention_demand(self, automation_manager):
        """An area below comfort - delta → heating_retention."""
        area = {
            "area_id": "bedroom",
            "zone_id": "zone_2",
            "enabled": True,
            "temperature_entity": "sensor.bedroom_temp",
            "comfort_temperature_entity": "input_number.br_comfort",
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )

        def mock_get(entity_id):
            if entity_id == "sensor.bedroom_temp":
                return MagicMock(state="18.0")
            if entity_id == "input_number.br_comfort":
                return MagicMock(state="21.0")
            return None

        automation_manager.hass.states.get = mock_get

        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )

        assert len(result) == 1
        assert result[0]["decision"] == "heating_retention"

    @pytest.mark.asyncio
    async def test_evaluate_areas_idle_area_skipped(self, automation_manager):
        """An area within comfort band → idle, not included in results."""
        area = {
            "area_id": "office",
            "enabled": True,
            "temperature_entity": "sensor.office_temp",
            "comfort_temperature_entity": "input_number.office_comfort",
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )

        def mock_get(entity_id):
            if entity_id == "sensor.office_temp":
                return MagicMock(state="21.5")
            if entity_id == "input_number.office_comfort":
                return MagicMock(state="21.0")
            return None

        automation_manager.hass.states.get = mock_get

        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_evaluate_areas_falls_back_to_global_comfort(
        self, automation_manager
    ):
        """When area has no comfort_temperature_entity, use FAN global comfort."""
        area = {
            "area_id": "kitchen",
            "enabled": True,
            "temperature_entity": "sensor.kitchen_temp",
            # No comfort_temperature_entity
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )

        def mock_get(entity_id):
            if entity_id == "sensor.kitchen_temp":
                return MagicMock(state="24.0")
            if entity_id == "number.32_153289_param_75":
                return MagicMock(state="21.0")
            return None

        automation_manager.hass.states.get = mock_get

        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )

        assert len(result) == 1
        assert result[0]["decision"] == "cooling"
        assert result[0]["area_comfort"] == 21.0

    @pytest.mark.asyncio
    async def test_evaluate_areas_skips_disabled_areas(self, automation_manager):
        """Disabled areas are skipped."""
        area = {
            "area_id": "garage",
            "enabled": False,
            "temperature_entity": "sensor.garage_temp",
            "comfort_temperature_entity": "input_number.garage_comfort",
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )
        automation_manager.hass.states.get = MagicMock(return_value=None)

        settings = make_settings()
        result = await automation_manager._evaluate_areas(
            "32:153289", settings, outdoor_temp=18.0
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_evaluate_areas_cooling_blocked_by_min_outdoor_temp(
        self, automation_manager
    ):
        """Cooling is blocked when outdoor_temp < min_outdoor_temp."""
        area = {
            "area_id": "living_room",
            "enabled": True,
            "temperature_entity": "sensor.lr_temp",
            "comfort_temperature_entity": "input_number.lr_comfort",
        }
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": [area]}
        )

        def mock_get(entity_id):
            if entity_id == "sensor.lr_temp":
                return MagicMock(state="24.0")
            if entity_id == "input_number.lr_comfort":
                return MagicMock(state="21.0")
            return None

        automation_manager.hass.states.get = mock_get

        settings = make_settings(min_outdoor_temp=15.0)
        result = await automation_manager._evaluate_areas(
            "32:153289",
            settings,
            outdoor_temp=10.0,  # Below min_outdoor_temp
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_publish_zone_demands_sets_demand_for_cooling(
        self, automation_manager
    ):
        """Zone demands are set for areas with zone_id during cooling."""
        automation_manager._zone_demand_registry = MagicMock()
        automation_manager._zone_demand_registry.set_demand = MagicMock()
        automation_manager._zone_demand_registry.clear_demand = MagicMock()

        area_results = [
            {
                "area_id": "living_room",
                "zone_id": "zone_1",
                "area_temp": 24.0,
                "area_comfort": 21.0,
                "decision": "cooling",
                "reason": "too warm",
            }
        ]

        await automation_manager._publish_zone_demands(
            "32:153289", area_results, "cooling"
        )

        automation_manager._zone_demand_registry.set_demand.assert_called_once()
        call_args = automation_manager._zone_demand_registry.set_demand.call_args
        assert call_args.args[0] == "32:153289"
        assert call_args.args[1] == "zone_1"
        assert call_args.args[2] == DemandSource.OTHER
        assert call_args.args[3] is True

    @pytest.mark.asyncio
    async def test_publish_zone_demands_clears_stale_demands(self, automation_manager):
        """Zones that no longer need action have their demands cleared."""
        automation_manager._zone_demand_registry = MagicMock()
        automation_manager._zone_demand_registry.set_demand = MagicMock()
        automation_manager._zone_demand_registry.clear_demand = MagicMock()

        # Simulate that zone_1 previously had a demand
        automation_manager._temp_demand_zones["32:153289"] = {"zone_1"}

        # Now no areas need action
        await automation_manager._publish_zone_demands("32:153289", [], "idle")

        automation_manager._zone_demand_registry.clear_demand.assert_called_once_with(
            "32:153289", "zone_1", DemandSource.OTHER
        )

    @pytest.mark.asyncio
    async def test_publish_zone_demands_skips_areas_without_zone_id(
        self, automation_manager
    ):
        """Areas without a zone_id don't get zone demands."""
        automation_manager._zone_demand_registry = MagicMock()
        automation_manager._zone_demand_registry.set_demand = MagicMock()

        area_results = [
            {
                "area_id": "loft",
                "zone_id": None,
                "area_temp": 24.0,
                "area_comfort": 21.0,
                "decision": "cooling",
                "reason": "too warm",
            }
        ]

        await automation_manager._publish_zone_demands(
            "32:153289", area_results, "cooling"
        )

        automation_manager._zone_demand_registry.set_demand.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_all_zone_demands(self, automation_manager):
        """_clear_all_zone_demands clears all tracked zone demands."""
        automation_manager._zone_demand_registry = MagicMock()
        automation_manager._zone_demand_registry.clear_demand = MagicMock()

        automation_manager._temp_demand_zones["32:153289"] = {"zone_1", "zone_2"}

        await automation_manager._clear_all_zone_demands("32:153289")

        assert automation_manager._zone_demand_registry.clear_demand.call_count == 2
        assert "32:153289" not in automation_manager._temp_demand_zones

    @pytest.mark.asyncio
    async def test_aggregate_cooling_has_priority_over_heating(
        self, automation_manager
    ):
        """When one area needs cooling and another needs heating, cooling wins."""
        automation_manager._zone_demand_registry = MagicMock()
        automation_manager._zone_demand_registry.set_demand = MagicMock()
        automation_manager._zone_demand_registry.clear_demand = MagicMock()

        area_results = [
            {
                "area_id": "living_room",
                "zone_id": "zone_1",
                "area_temp": 24.0,
                "area_comfort": 21.0,
                "decision": "cooling",
                "reason": "too warm",
            },
            {
                "area_id": "bedroom",
                "zone_id": "zone_2",
                "area_temp": 18.0,
                "area_comfort": 21.0,
                "decision": "heating_retention",
                "reason": "too cold",
            },
        ]

        # Mock _evaluate_areas to return our mixed results
        automation_manager._evaluate_areas = AsyncMock(return_value=area_results)
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": []}
        )
        automation_manager._publish_zone_demands = AsyncMock()

        states = make_entity_states(
            indoor_temp=22.0,
            outdoor_temp=18.0,
            comfort_temp=21.0,
        )
        await automation_manager._process_automation_logic("32:153289", states)

        # Cooling should win
        assert automation_manager._mode["32:153289"] == "cooling"


class TestTempControlBypassFlowProdScenario:
    """End-to-end flow tests simulating the prod HA scenario.

    Reproduces: temp_control in idle → humidity_control veto forces fan_low
    via the arbiter → FAN device repositions the bypass damper → the bypass
    position entity changes → the safety net must NOT turn temp_control off.

    Also covers: temp_control disabled while forcing bypass → fan_bypass_auto
    is sent so the device resumes autonomous bypass control.
    """

    @pytest.mark.asyncio
    async def test_idle_bypass_change_from_humidity_veto_does_not_disable(
        self, automation_manager
    ):
        """Prod scenario: idle mode + humidity veto → bypass moves → no disable.

        1. temp_control evaluates to idle (indoor near comfort, no cooling/
           heating needed) and sends fan_bypass_auto.
        2. humidity_control sets a veto (fan_low) via the arbiter because
           outside is wetter than inside.
        3. The FAN device, now running at low speed with bypass in auto,
           repositions the damper → binary_sensor.*_bypass_position changes.
        4. The safety net must NOT turn temp_control off, because in idle
           mode the bypass is in the device's hands.
        """
        import time

        hass = automation_manager.hass

        # Step 1: temp_control is on and in idle mode (sent fan_bypass_auto)
        switch_state = MagicMock()
        switch_state.state = "on"
        hass.states.get = MagicMock(return_value=switch_state)
        hass.services.async_call = AsyncMock()
        automation_manager._mode["32:153289"] = "idle"
        # Timestamp is stale — simulates steady state where no bypass
        # command was sent for a while (the original false-positive trigger)
        automation_manager._last_bypass_command_time["32:153289"] = time.time() - 120

        # Step 3: bypass position entity changes (device repositioned damper)
        old_state = MagicMock(state="open")
        new_state = MagicMock(state="closed")

        with patch.object(
            type(automation_manager).__mro__[1],
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                old_state,
                new_state,
            )

        # Safety net must NOT turn off the switch
        hass.services.async_call.assert_not_called()
        # Mode must remain idle (not changed to disabled)
        assert automation_manager._mode["32:153289"] == "idle"
        # State change passes through to normal handler
        mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_cooling_bypass_external_change_disables_temp_control(
        self, automation_manager
    ):
        """Contrast: in cooling mode (forcing bypass open), an external bypass
        change IS a real manual override → temp_control is disabled.
        """
        import time

        hass = automation_manager.hass
        switch_state = MagicMock()
        switch_state.state = "on"
        hass.states.get = MagicMock(return_value=switch_state)
        hass.services.async_call = AsyncMock()
        automation_manager._mode["32:153289"] = "cooling"
        automation_manager._last_bypass_command_time["32:153289"] = time.time() - 120

        old_state = MagicMock(state="open")
        new_state = MagicMock(state="closed")

        await automation_manager._async_handle_state_change(
            "binary_sensor.32_153289_bypass_position",
            old_state,
            new_state,
        )

        hass.services.async_call.assert_called_once_with(
            "switch",
            "turn_off",
            {"entity_id": "switch.temp_control_32_153289"},
        )

    @pytest.mark.asyncio
    async def test_handle_disabled_releases_bypass_when_forcing(
        self, automation_manager
    ):
        """_handle_disabled sends fan_bypass_auto when previously forcing bypass.

        When temp_control was in cooling/heating_retention (forcing a bypass
        state) and gets disabled, the bypass must be released back to the
        device's autonomous control.  Without this the damper stays stuck.
        """
        automation_manager._mode["32:153289"] = "cooling"
        automation_manager.ramses_commands.send_command = AsyncMock()

        await automation_manager._handle_disabled("32:153289", reason="disabled")

        # fan_bypass_auto sent to release the damper
        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_auto"
        )
        assert automation_manager._mode["32:153289"] == "disabled"

    @pytest.mark.asyncio
    async def test_handle_disabled_does_not_release_bypass_in_idle(
        self, automation_manager
    ):
        """_handle_disabled does NOT send fan_bypass_auto when already idle.

        In idle we already sent fan_bypass_auto, so no need to resend on
        disable (avoids a spurious command).
        """
        automation_manager._mode["32:153289"] = "idle"
        automation_manager.ramses_commands.send_command = AsyncMock()

        await automation_manager._handle_disabled("32:153289", reason="disabled")

        automation_manager.ramses_commands.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_releases_bypass_when_forcing(self, automation_manager):
        """stop() sends fan_bypass_auto for devices that were forcing bypass."""
        automation_manager._mode["32:153289"] = "heating_retention"
        automation_manager.ramses_commands.send_command = AsyncMock()
        automation_manager._clear_speed_demand = AsyncMock()
        automation_manager._clear_all_zone_demands = AsyncMock()

        with patch.object(
            type(automation_manager).__mro__[1], "stop", new_callable=AsyncMock
        ):
            await automation_manager.stop()

        automation_manager.ramses_commands.send_command.assert_called_once_with(
            "32:153289", "fan_bypass_auto"
        )

    @pytest.mark.asyncio
    async def test_stop_does_not_release_bypass_in_idle(self, automation_manager):
        """stop() does NOT send fan_bypass_auto for idle devices."""
        automation_manager._mode["32:153289"] = "idle"
        automation_manager.ramses_commands.send_command = AsyncMock()
        automation_manager._clear_speed_demand = AsyncMock()
        automation_manager._clear_all_zone_demands = AsyncMock()

        with patch.object(
            type(automation_manager).__mro__[1], "stop", new_callable=AsyncMock
        ):
            await automation_manager.stop()

        automation_manager.ramses_commands.send_command.assert_not_called()
