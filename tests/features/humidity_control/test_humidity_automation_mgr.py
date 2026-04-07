"""Tests for Humidity Control Automation Manager."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.humidity_control.automation import (
    HumidityAutomationManager,
    create_humidity_control_automation,
)


class TestHumidityAutomationManager:
    """Test cases for HumidityAutomationManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        # Use MagicMock for data to allow side_effect/return_value on get()
        self.hass.data = MagicMock()
        self.hass.data.get.return_value = {
            "enabled_features": {"humidity_control": True}
        }
        self.hass.config = MagicMock()
        self.hass.states = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.fan_speed_arbiter = MagicMock()
        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
        self.fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)
        self.fan_speed_arbiter.is_manual_override_active.return_value = False

        # Patch dependencies
        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.RamsesCommands"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.HumidityConfig"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.HumidityServices"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.get_fan_speed_arbiter",
                return_value=self.fan_speed_arbiter,
            ),
        ):
            self.manager = HumidityAutomationManager(self.hass, self.config_entry)
            self.manager._automation_active = True

    def test_init(self):
        """Test initialization."""
        assert self.manager.feature_id == "humidity_control"
        assert self.manager._automation_active is True

    def test_is_feature_enabled(self):
        """Test feature enabled check."""
        # 1. Enabled (from setup_method)
        assert self.manager._is_feature_enabled() is True

        # 2. Disabled
        self.hass.data.get.return_value = {
            "enabled_features": {"humidity_control": False}
        }
        assert self.manager._is_feature_enabled() is False

        # Reset for other tests
        self.hass.data.get.return_value = {
            "enabled_features": {"humidity_control": True}
        }

    @patch.object(HumidityAutomationManager, "_evaluate_humidity_conditions")
    @patch.object(HumidityAutomationManager, "_activate_dehumidification")
    @patch.object(HumidityAutomationManager, "_set_fan_low_and_binary_off")
    @patch.object(HumidityAutomationManager, "_update_automation_status")
    async def test_process_automation_logic_dehumidify(
        self, mock_update, mock_stop, mock_activate, mock_evaluate
    ):
        """Test processing automation logic when dehumidification is needed."""
        device_id = "32_123456"
        entity_states = {
            "indoor_rh": 65.0,
            "indoor_abs": 12.0,
            "outdoor_abs": 8.0,
            "min_humidity": 40.0,
            "max_humidity": 60.0,
            "offset": 0.0,
            "dehumidify": True,
        }

        decision = {"action": "dehumidify", "reasoning": ["Test"], "confidence": 1.0}
        mock_evaluate.return_value = decision

        await self.manager._process_automation_logic(device_id, entity_states)

        mock_activate.assert_called_once_with(device_id, decision)
        mock_update.assert_called_once_with(device_id, decision)

    @patch.object(HumidityAutomationManager, "_evaluate_humidity_conditions")
    @patch.object(HumidityAutomationManager, "_activate_dehumidification")
    @patch.object(HumidityAutomationManager, "_set_fan_low_and_binary_off")
    @patch.object(HumidityAutomationManager, "_update_automation_status")
    async def test_process_automation_logic_stop(
        self, mock_update, mock_stop, mock_activate, mock_evaluate
    ):
        """Test processing automation logic when dehumidification should stop."""
        device_id = "32_123456"
        entity_states = {
            "indoor_rh": 50.0,
            "indoor_abs": 10.0,
            "outdoor_abs": 10.0,
            "min_humidity": 40.0,
            "max_humidity": 60.0,
            "offset": 0.0,
            "dehumidify": True,
        }

        decision = {"action": "stop", "reasoning": ["Test"], "confidence": 1.0}
        mock_evaluate.return_value = decision

        await self.manager._process_automation_logic(device_id, entity_states)

        mock_stop.assert_called_once_with(device_id, decision)
        mock_update.assert_called_once_with(device_id, decision)

    @patch.object(HumidityAutomationManager, "_evaluate_humidity_conditions")
    @patch.object(HumidityAutomationManager, "_activate_dehumidification")
    @patch.object(HumidityAutomationManager, "_set_fan_low_and_binary_off")
    @patch.object(HumidityAutomationManager, "_update_automation_status")
    async def test_process_automation_logic_skips_when_manual_override_active(
        self, mock_update, mock_stop, mock_activate, mock_evaluate
    ):
        """Sticky manual override should short-circuit humidity automation."""
        device_id = "32_123456"
        entity_states = {"dehumidify": True}
        self.fan_speed_arbiter.is_manual_override_active.return_value = True

        await self.manager._process_automation_logic(device_id, entity_states)

        mock_evaluate.assert_not_called()
        mock_activate.assert_not_called()
        mock_stop.assert_not_called()
        mock_update.assert_not_called()

    @patch.object(HumidityAutomationManager, "_evaluate_humidity_conditions")
    @patch.object(HumidityAutomationManager, "_activate_dehumidification")
    @patch.object(HumidityAutomationManager, "_set_fan_low_and_binary_off")
    @patch.object(HumidityAutomationManager, "_update_automation_status")
    async def test_process_automation_logic_stop_uses_low_balance_demand(
        self, mock_update, mock_stop, mock_activate, mock_evaluate
    ):
        """Stop decisions should keep humidity's low-speed demand active."""
        device_id = "32_123456"
        entity_states = {
            "indoor_rh": 50.0,
            "indoor_abs": 10.0,
            "outdoor_abs": 10.0,
            "min_humidity": 40.0,
            "max_humidity": 60.0,
            "offset": 0.0,
            "dehumidify": True,
        }

        decision = {
            "action": "stop",
            "reasoning": ["Humidity in range for balance mode"],
            "confidence": 1.0,
            "control_mode": "balance",
        }
        mock_evaluate.return_value = decision

        await self.manager._process_automation_logic(device_id, entity_states)

        mock_stop.assert_called_once_with(device_id, decision)
        mock_activate.assert_not_called()
        mock_update.assert_called_once_with(device_id, decision)
        assert self.manager._dehumidify_active is False

    async def test_process_automation_logic_switch_off(self):
        """Test processing automation logic when switch is off."""
        device_id = "32_123456"
        entity_states = {"dehumidify": False}

        with patch.object(self.manager, "_set_indicator_off") as mock_off:
            await self.manager._process_automation_logic(device_id, entity_states)
            mock_off.assert_called_once_with(device_id)

    async def test_reconcile_startup_states_switch_off(self):
        """Test startup reconciliation enforces restored OFF switch state."""
        mock_switch = MagicMock()
        mock_switch.entity_id = "switch.dehumidify_32_123456"
        self.hass.states.async_all.return_value = [mock_switch]

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.is_supported_humidity_device",
                return_value=True,
            ),
            patch.object(
                self.manager,
                "_get_device_entity_states",
                new=AsyncMock(return_value={"dehumidify": False}),
            ),
            patch.object(
                self.manager, "_enforce_switch_off_state", new=AsyncMock()
            ) as mock_enforce,
            patch.object(
                self.manager, "_set_indicator_off", new=AsyncMock()
            ) as mock_indicator,
            patch.object(
                self.manager, "_process_automation_logic", new=AsyncMock()
            ) as mock_process,
        ):
            await self.manager._reconcile_startup_states()

        mock_enforce.assert_called_once_with("32_123456")
        mock_indicator.assert_called_once_with("32_123456")
        mock_process.assert_not_called()

    async def test_reconcile_startup_states_switch_on(self):
        """Test startup reconciliation evaluates restored ON switch state."""
        mock_switch = MagicMock()
        mock_switch.entity_id = "switch.dehumidify_32_123456"
        self.hass.states.async_all.return_value = [mock_switch]
        entity_states = {"dehumidify": True, "indoor_rh": 55.0}

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.is_supported_humidity_device",
                return_value=True,
            ),
            patch.object(
                self.manager,
                "_get_device_entity_states",
                new=AsyncMock(return_value=entity_states),
            ),
            patch.object(
                self.manager, "_process_automation_logic", new=AsyncMock()
            ) as mock_process,
            patch.object(
                self.manager, "_enforce_switch_off_state", new=AsyncMock()
            ) as mock_enforce,
        ):
            await self.manager._reconcile_startup_states()

        mock_process.assert_called_once_with("32_123456", entity_states)
        mock_enforce.assert_not_called()

    async def test_resume_from_co2_triggers_reconcile(self):
        """CO2 state changes should trigger a humidity re-evaluation."""
        self.manager._paused_for_co2 = False

        with patch.object(
            self.manager,
            "_reconcile_startup_states",
            new=AsyncMock(),
        ) as mock_reconcile:
            await self.manager.resume_from_co2()

        assert self.manager._paused_for_co2 is False
        mock_reconcile.assert_awaited_once()

    async def test_pause_for_co2_keeps_humidity_arbiter_managed(self):
        """CO2 activation should no longer suppress humidity demand generation."""
        self.manager._paused_for_co2 = True

        await self.manager.pause_for_co2()

        assert self.manager._paused_for_co2 is False
        assert self.manager.check_priority() is True

    async def test_resume_from_co2_skips_reconcile_when_inactive(self):
        """CO2 resume should not reconcile when humidity automation is inactive."""
        self.manager._paused_for_co2 = True
        self.manager._automation_active = False

        with patch.object(
            self.manager,
            "_reconcile_startup_states",
            new=AsyncMock(),
        ) as mock_reconcile:
            await self.manager.resume_from_co2()

        assert self.manager._paused_for_co2 is False
        mock_reconcile.assert_not_awaited()

    @patch(
        "custom_components.ramses_extras.features.humidity_control.automation.entity_registry"
    )
    async def test_validate_device_entities(self, mock_registry):
        """Test validating device entities."""
        device_id = "32_123456"
        mock_reg = MagicMock()
        mock_registry.async_get.return_value = mock_reg

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.core.get_feature_entity_mappings",
                new=AsyncMock(
                    return_value={
                        "indoor_abs": "sensor.indoor_absolute_humidity_32_123456",
                    }
                ),
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.core.get_required_entity_ids_for_feature_device",
                new=AsyncMock(
                    return_value=[
                        "switch.dehumidify_32_123456",
                    ]
                ),
            ),
        ):
            # All entities exist
            mock_reg.async_get.return_value = True
            assert await self.manager._validate_device_entities(device_id) is True

            # Some missing
            mock_reg.async_get.return_value = None
            assert await self.manager._validate_device_entities(device_id) is False

    async def test_evaluate_humidity_conditions_high(self):
        """Test evaluation logic for high humidity."""
        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=80.0,
            indoor_abs=15.0,
            outdoor_abs=10.0,
            min_humidity=40.0,
            max_humidity=75.0,
            offset=0.0,
        )
        assert decision["action"] == "dehumidify"
        assert "High indoor RH" in decision["reasoning"][0]

    async def test_evaluate_humidity_conditions_low(self):
        """Test evaluation logic for low humidity."""
        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=30.0,
            indoor_abs=5.0,
            outdoor_abs=10.0,
            min_humidity=40.0,
            max_humidity=75.0,
            offset=0.0,
        )
        assert decision["action"] == "dehumidify"
        assert "Low indoor RH" in decision["reasoning"][0]

    async def test_evaluate_humidity_conditions_normal(self):
        """Test evaluation logic for normal humidity."""
        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=50.0,
            indoor_abs=10.0,
            outdoor_abs=10.0,
            min_humidity=40.0,
            max_humidity=75.0,
            offset=0.0,
        )
        assert decision["action"] == "stop"
        assert "acceptable range" in decision["reasoning"][0]

    async def test_evaluate_humidity_conditions_area_spike_detected(self):
        """Area spike should trigger spike_boost dehumidification."""
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": [
                {
                    "area_id": "bathroom",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_humidity",
                    "spike_rise_percent": 15.0,
                    "spike_window_minutes": 3,
                    "check_interval_minutes": 1,
                    "enabled": True,
                }
            ]
        }

        temp_state = MagicMock(state="22.0")
        humidity_state = MagicMock(state="65.0")
        self.hass.states.get.side_effect = lambda entity_id: {
            "sensor.bath_temp": temp_state,
            "sensor.bath_humidity": humidity_state,
        }.get(entity_id)

        self.manager._area_history["test"] = {
            "bathroom": [
                {"ts": time.time() - 60, "abs": 9.0},
                {"ts": time.time() - 10, "abs": 9.2},
            ]
        }

        with patch.object(
            self.manager,
            "_schedule_area_spike_recheck",
        ) as mock_schedule:
            decision = await self.manager._evaluate_humidity_conditions(
                device_id="test",
                indoor_rh=50.0,
                indoor_abs=10.0,
                outdoor_abs=8.0,
                min_humidity=40.0,
                max_humidity=60.0,
                offset=0.0,
            )

        assert decision["action"] == "dehumidify"
        assert decision["control_mode"] == "spike_boost"
        assert decision["active_trigger"]["area_id"] == "bathroom"
        mock_schedule.assert_called_once_with("test", 1)

    async def test_evaluate_active_area_spike_clears_when_recovered(self):
        """Active spike should stop once the area humidity recovers."""
        self.manager._active_area_spikes["test"] = {
            "area_id": "bathroom",
            "label": "Bathroom",
            "baseline_abs": 10.0,
            "check_interval_minutes": 1,
        }
        area_sensor_states = [
            {"area_id": "bathroom", "current_abs": 9.5, "current_rh": 60.0}
        ]

        decision = self.manager._evaluate_active_area_spike(
            device_id="test",
            indoor_abs=10.0,
            outdoor_abs=8.0,
            offset=0.0,
            area_sensor_states=area_sensor_states,
        )

        assert decision is None

    async def test_evaluate_active_area_spike_keeps_boost_active(self):
        """Active spike should stay active while still above target."""
        self.manager._active_area_spikes["test"] = {
            "area_id": "bathroom",
            "label": "Bathroom",
            "baseline_abs": 10.0,
            "check_interval_minutes": 1,
        }
        area_sensor_states = [
            {"area_id": "bathroom", "current_abs": 12.0, "current_rh": 75.0}
        ]

        decision = self.manager._evaluate_active_area_spike(
            device_id="test",
            indoor_abs=10.5,
            outdoor_abs=8.0,
            offset=0.0,
            area_sensor_states=area_sensor_states,
        )

        assert decision is not None
        assert decision["action"] == "dehumidify"
        assert decision["control_mode"] == "spike_boost"

    def test_build_indicator_attributes_with_active_trigger(self):
        """Indicator attributes should include active trigger metadata."""
        decision = {
            "control_mode": "spike_boost",
            "active_trigger": {
                "area_id": "bathroom",
                "label": "Bathroom",
                "current_abs": 12.0,
                "current_rh": 68.0,
                "baseline_abs": 10.0,
                "rise_percent": 20.0,
                "check_interval_minutes": 1,
            },
            "active_triggers": [
                {
                    "area_id": "bathroom",
                    "label": "Bathroom",
                    "current_abs": 12.0,
                    "current_rh": 68.0,
                    "baseline_abs": 10.0,
                    "rise_percent": 20.0,
                    "check_interval_minutes": 1,
                },
                {
                    "area_id": "ensuite",
                    "label": "Ensuite",
                    "current_abs": 11.8,
                    "current_rh": 64.0,
                    "baseline_abs": 10.1,
                    "rise_percent": 16.8,
                    "check_interval_minutes": 2,
                },
            ],
        }

        attrs = self.manager._build_indicator_attributes("32_123456", decision)

        assert attrs["control_mode"] == "spike_boost"
        assert attrs["active_trigger_area_id"] == "bathroom"
        assert attrs["active_trigger_label"] == "Bathroom"
        assert attrs["active_trigger_rise_percent"] == 20.0
        assert attrs["active_trigger_labels"] == [
            "Bathroom (68%)",
            "Ensuite (64%)",
        ]
        assert attrs["active_trigger_labels_text"] == ("Bathroom (68%), Ensuite (64%)")
        assert attrs["next_check_interval_minutes"] == 1

    def test_build_indicator_attributes_with_active_spike_fallback(self):
        """Active spike cache should populate indicator metadata when needed."""
        self.manager._active_area_spikes["32_123456"] = [
            {
                "area_id": "bathroom",
                "label": "Bathroom",
                "current_abs": 12.0,
                "current_rh": 68.0,
                "baseline_abs": 10.0,
                "rise_percent": 20.0,
                "check_interval_minutes": 1,
            },
            {
                "area_id": "ensuite",
                "label": "Ensuite",
                "current_abs": 11.8,
                "current_rh": 64.0,
                "baseline_abs": 10.1,
                "rise_percent": 16.8,
                "check_interval_minutes": 2,
            },
        ]

        attrs = self.manager._build_indicator_attributes(
            "32_123456",
            {"control_mode": "dehumidify", "active_trigger": None},
        )

        assert attrs["control_mode"] == "spike_boost"
        assert attrs["active_trigger_area_id"] == "bathroom"
        assert attrs["active_trigger_labels_text"] == ("Bathroom (68%), Ensuite (64%)")
        assert attrs["next_check_interval_minutes"] == 1

    def test_detect_area_spike_guard_paths(self):
        """
        Spike detection should ignore disabled, incomplete, and below-threshold data.
        """
        now = time.time()
        self.manager._area_history["test"] = {
            "bathroom": [{"ts": now - 10, "abs": 9.0}],
            "zero": [{"ts": now - 10, "abs": 0.0}],
            "lowrise": [{"ts": now - 10, "abs": 10.0}],
            "outdoorbad": [{"ts": now - 10, "abs": 9.0}],
        }

        area_sensor_states = [
            {"area_id": "", "enabled": True, "current_abs": 12.0},
            {"area_id": "disabled", "enabled": False, "current_abs": 12.0},
            {"area_id": "missing_abs", "enabled": True, "current_abs": None},
            {
                "area_id": "zero",
                "enabled": True,
                "current_abs": 12.0,
            },
        ]

        decision = self.manager._detect_area_spike(
            device_id="test",
            indoor_abs=10.0,
            outdoor_abs=9.5,
            offset=0.0,
            area_sensor_states=area_sensor_states,
        )

        assert decision is None

    def test_detect_area_spike_skips_missing_history_window(self):
        """Spike detection should ignore sources with no usable history window."""
        now = time.time()
        self.manager._area_history["test"] = {
            "expired": [{"ts": now - 600, "abs": 9.0}],
        }

        assert (
            self.manager._detect_area_spike(
                device_id="test",
                indoor_abs=10.0,
                outdoor_abs=8.0,
                offset=0.0,
                area_sensor_states=[
                    {
                        "area_id": "nohistory",
                        "enabled": True,
                        "current_abs": 12.0,
                        "spike_window_minutes": 3,
                        "spike_rise_percent": 10.0,
                    },
                    {
                        "area_id": "expired",
                        "enabled": True,
                        "current_abs": 12.0,
                        "spike_window_minutes": 1,
                        "spike_rise_percent": 10.0,
                    },
                ],
            )
            is None
        )

    def test_schedule_and_cancel_area_spike_recheck(self):
        """Scheduling should replace old handles and cancellation should call them."""
        old_handle = MagicMock()
        self.manager._area_spike_check_handles["32_123456"] = old_handle

        new_handle = MagicMock()
        with patch(
            "custom_components.ramses_extras.features.humidity_control.automation.async_track_time_interval",
            return_value=new_handle,
        ) as mock_track:
            self.manager._schedule_area_spike_recheck("32_123456", 0)

        old_handle.assert_called_once()
        assert self.manager._area_spike_check_handles["32_123456"] is new_handle
        assert mock_track.call_args.args[2].total_seconds() == 60

        self.manager._cancel_area_spike_recheck("32_123456")
        new_handle.assert_called_once()
        assert "32_123456" not in self.manager._area_spike_check_handles

    async def test_async_recheck_area_spike_paths(self):
        """Recheck should guard on disabled state and process valid states."""
        device_id = "32_123456"

        self.manager._automation_active = False
        self.manager._get_device_entity_states = AsyncMock()
        self.manager._process_automation_logic = AsyncMock()
        await self.manager._async_recheck_area_spike(device_id)
        self.manager._get_device_entity_states.assert_not_called()

        self.manager._automation_active = True
        with patch.object(self.manager, "_is_feature_enabled", return_value=False):
            await self.manager._async_recheck_area_spike(device_id)
        self.manager._get_device_entity_states.assert_not_called()

        with patch.object(self.manager, "_is_feature_enabled", return_value=True):
            self.manager._get_device_entity_states = AsyncMock(
                side_effect=ValueError("missing")
            )
            await self.manager._async_recheck_area_spike(device_id)

            entity_states = {"dehumidify": True}
            self.manager._get_device_entity_states = AsyncMock(
                return_value=entity_states
            )
            self.manager._process_automation_logic = AsyncMock()
            await self.manager._async_recheck_area_spike(device_id)

        self.manager._process_automation_logic.assert_awaited_once_with(
            device_id, entity_states
        )

    async def test_reconcile_startup_states_skips_non_humidity_device(self):
        """Test startup reconciliation ignores stale dehumidify states."""
        mock_switch = MagicMock()
        mock_switch.entity_id = "switch.dehumidify_18_130236"
        self.hass.states.async_all.return_value = [mock_switch]

        self.manager._get_device_entity_states = AsyncMock()
        self.manager._enforce_switch_off_state = AsyncMock()
        self.manager._set_indicator_off = AsyncMock()
        self.manager._process_automation_logic = AsyncMock()

        with patch(
            "custom_components.ramses_extras.features.humidity_control.automation.is_supported_humidity_device",
            return_value=False,
        ):
            await self.manager._reconcile_startup_states()

        self.manager._get_device_entity_states.assert_not_awaited()
        self.manager._enforce_switch_off_state.assert_not_awaited()
        self.manager._set_indicator_off.assert_not_awaited()
        self.manager._process_automation_logic.assert_not_awaited()

    def test_evaluate_active_area_spike_guard_paths(self):
        """
        Active spike evaluation should return None for unmatched or invalid states.
        """
        assert (
            self.manager._evaluate_active_area_spike(
                device_id="missing",
                indoor_abs=10.0,
                outdoor_abs=8.0,
                offset=0.0,
                area_sensor_states=[],
            )
            is None
        )

        self.manager._active_area_spikes["test"] = {
            "area_id": "bathroom",
            "label": "Bathroom",
            "baseline_abs": 10.0,
            "check_interval_minutes": 1,
        }
        assert (
            self.manager._evaluate_active_area_spike(
                device_id="test",
                indoor_abs=10.0,
                outdoor_abs=8.0,
                offset=0.0,
                area_sensor_states=[{"source_id": "other", "current_abs": 12.0}],
            )
            is None
        )
        assert (
            self.manager._evaluate_active_area_spike(
                device_id="test",
                indoor_abs=10.0,
                outdoor_abs=10.0,
                offset=1.0,
                area_sensor_states=[
                    {
                        "area_id": "bathroom",
                        "current_abs": 10.5,
                        "current_rh": 70.0,
                    }
                ],
            )
            is None
        )

    def test_get_decision_history_statistics_and_factory(self):
        """Helpers should return recent decisions, statistics, and factory instances."""
        self.manager._decision_history = [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ]
        self.manager._decision_count = 7
        self.manager._active_cycles = 2
        self.manager._automation_active = True
        self.manager._dehumidify_active = False
        self.fan_speed_arbiter.get_debug_state.return_value = {
            "devices": {"32_123456": {"last_applied_command": "fan_low"}}
        }

        assert self.manager.get_decision_history(2) == [{"id": 2}, {"id": 3}]

        stats = self.manager.get_automation_statistics()
        assert stats["decisions_made"] == 7
        assert stats["active_cycles"] == 2
        assert stats["recent_decisions"] == 3
        assert (
            stats["fan_arbiter"]["devices"]["32_123456"]["last_applied_command"]
            == "fan_low"
        )

        created = create_humidity_control_automation(self.hass, self.config_entry)
        assert isinstance(created, HumidityAutomationManager)

    def test_generate_entity_patterns(self):
        """Test generating entity patterns."""
        patterns = self.manager._generate_entity_patterns()
        assert "sensor.indoor_absolute_humidity_*" in patterns
        assert "switch.dehumidify_*" in patterns
        assert "sensor.*_indoor_humidity" in patterns

    def test_generate_entity_patterns_reads_canonical_sensor_control(self):
        """Canonical sensor_control config should contribute external area sensors."""
        self.config_entry.options = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "sensor_control": {
                        "devices": {
                            "32:123456": {
                                "area_sensors": [
                                    {
                                        "temperature_entity": "sensor.bath_temp",
                                        "humidity_entity": "sensor.bath_humidity",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        }

        patterns = self.manager._generate_entity_patterns()

        assert "sensor.bath_temp" in patterns
        assert "sensor.bath_humidity" in patterns

    def test_extract_device_id_reads_canonical_sensor_control(self):
        """Canonical sensor_control config should map area entities back to a device."""
        self.config_entry.options = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "sensor_control": {
                        "devices": {
                            "32:123456": {
                                "area_sensors": [
                                    {
                                        "temperature_entity": "sensor.bath_temp",
                                        "humidity_entity": "sensor.bath_humidity",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        }

        result = self.manager._extract_device_id("sensor.bath_humidity")

        assert result == "32_123456"

    async def test_start_stop(self):
        """Test start and stop methods."""
        with (
            patch.object(
                self.manager.config, "async_load", new_callable=AsyncMock
            ) as mock_load,
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_automation.ExtrasBaseAutomation.start",
                new_callable=AsyncMock,
            ) as mock_super_start,
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_automation.ExtrasBaseAutomation.stop",
                new_callable=AsyncMock,
            ) as mock_super_stop,
        ):
            # Test start
            await self.manager.start()
            assert self.manager._automation_active is True
            mock_load.assert_called_once()
            mock_super_start.assert_called_once()

            # Test stop
            await self.manager.stop()
            assert self.manager._automation_active is False
            mock_super_stop.assert_called_once()

    async def test_on_homeassistant_started_reconciles_states(self):
        """Test startup handler reconciles restored device states."""
        with (
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_automation.ExtrasBaseAutomation._on_homeassistant_started",
                new=AsyncMock(),
            ) as mock_super_started,
            patch.object(
                self.manager, "_reconcile_startup_states", new=AsyncMock()
            ) as mock_reconcile,
        ):
            self.manager._automation_active = True
            await self.manager._on_homeassistant_started(None)

        mock_super_started.assert_called_once_with(None)
        mock_reconcile.assert_called_once()

    async def test_check_any_device_ready(self):
        """Test checking if any device is ready."""
        # Feature disabled
        self.hass.data[DOMAIN]["enabled_features"]["humidity_control"] = False
        assert await self.manager._check_any_device_ready() is False

        # Feature enabled
        self.hass.data[DOMAIN]["enabled_features"]["humidity_control"] = True

        # Mock patterns and states
        mock_state = MagicMock()
        mock_state.entity_id = "sensor.indoor_absolute_humidity_32_123456"
        self.hass.states.async_all.return_value = [mock_state]

        with (
            patch.object(
                self.manager,
                "_generate_entity_patterns",
                return_value=["sensor.indoor_absolute_humidity_*"],
            ),
            patch.object(
                self.manager, "_validate_device_entities", new_callable=AsyncMock
            ) as mock_validate,
        ):
            mock_validate.return_value = True
            # Clear the cached property if any
            self.manager._entity_patterns = None
            assert await self.manager._check_any_device_ready() is True
            mock_validate.assert_called_with("32_123456")

    async def test_get_device_entity_states(self):
        """Test getting device entity states."""
        device_id = "32_123456"

        # Mock states
        mock_rh = MagicMock(state="55.0")
        mock_indoor_abs = MagicMock(state="8.5")
        mock_outdoor_abs = MagicMock(state="7.0")
        mock_min = MagicMock(state="40.0")
        mock_max = MagicMock(state="60.0")
        mock_offset = MagicMock(state="0.0")
        mock_switch = MagicMock(state="on")

        state_map = {
            "sensor.32_123456_indoor_humidity": mock_rh,
            "sensor.indoor_absolute_humidity_32_123456": mock_indoor_abs,
            "sensor.outdoor_absolute_humidity_32_123456": mock_outdoor_abs,
            "number.relative_humidity_minimum_32_123456": mock_min,
            "number.relative_humidity_maximum_32_123456": mock_max,
            "number.absolute_humidity_offset_32_123456": mock_offset,
            "switch.dehumidify_32_123456": mock_switch,
        }

        self.hass.states.get.side_effect = lambda eid: state_map.get(eid)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.core.get_feature_entity_mappings",
                new=AsyncMock(
                    return_value={
                        "indoor_rh": "sensor.32_123456_indoor_humidity",
                        "indoor_abs": "sensor.indoor_absolute_humidity_32_123456",
                        "outdoor_abs": "sensor.outdoor_absolute_humidity_32_123456",
                        "min_humidity": "number.relative_humidity_minimum_32_123456",
                        "max_humidity": "number.relative_humidity_maximum_32_123456",
                        "offset": "number.absolute_humidity_offset_32_123456",
                        "dehumidify": "switch.dehumidify_32_123456",
                    }
                ),
            ),
            patch.object(
                self.manager, "_get_sensor_control_context", new_callable=AsyncMock
            ) as mock_ctx,
        ):
            mock_ctx.return_value = None

            states = await self.manager._get_device_entity_states(device_id)
            assert states["indoor_rh"] == 55.0
            assert states["indoor_abs"] == 8.5
            assert states["dehumidify"] is True

    async def test_get_sensor_control_context(self):
        """Test getting sensor control context."""
        device_id = "32_123456"

        # Sensor control disabled
        with patch.object(
            self.manager, "_is_sensor_control_enabled", return_value=False
        ):
            assert await self.manager._get_sensor_control_context(device_id) is None

        # Sensor control enabled
        with patch.object(
            self.manager, "_is_sensor_control_enabled", return_value=True
        ):
            with patch(
                "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand"
            ) as mock_cmd_class:
                mock_cmd = MagicMock()
                mock_cmd_class.return_value = mock_cmd

                # Mock successful execution
                async def mock_execute(conn, msg):
                    conn.result = {
                        "success": True,
                        "mappings": {"indoor_humidity": "sensor.other_rh"},
                    }

                mock_cmd.execute.side_effect = mock_execute

                result = await self.manager._get_sensor_control_context(device_id)
                assert result["success"] is True
                assert result["mappings"]["indoor_humidity"] == "sensor.other_rh"

    async def test_get_sensor_control_overlay(self):
        """Test sensor_control overlay merges area sensor metadata."""
        device_id = "32_123456"
        self.hass.data = {
            DOMAIN: {
                "devices": [
                    {
                        "device_id": "32:123456",
                        "type": "FAN",
                    }
                ]
            }
        }

        with patch(
            "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver.resolve_entity_mappings",
            new=AsyncMock(
                return_value={
                    "mappings": {"indoor_humidity": "sensor.bathroom_humidity"},
                    "sources": {"indoor_humidity": {"kind": "external"}},
                    "raw_internal": {
                        "indoor_humidity": "sensor.fan_32_123456_indoor_humidity"
                    },
                    "abs_humidity_inputs": {
                        "indoor_abs_humidity": {"kind": "area_sensor"}
                    },
                    "area_sensors": [{"area_id": "bathroom", "label": "Bathroom"}],
                }
            ),
        ):
            result = await self.manager._get_sensor_control_overlay(
                device_id,
                {"indoor_abs": "sensor.indoor_absolute_humidity_32_123456"},
            )

        assert (
            result["mappings"]["indoor_abs"]
            == "sensor.indoor_absolute_humidity_32_123456"
        )
        assert result["mappings"]["indoor_humidity"] == "sensor.bathroom_humidity"
        assert result["area_sensors"] == [{"area_id": "bathroom", "label": "Bathroom"}]

    def test_is_sensor_control_enabled(self):
        """Test sensor control enabled check."""
        # No config entry
        self.hass.data = {}
        assert self.manager._is_sensor_control_enabled() is False

        # Enabled in config entry
        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"sensor_control": True}}
        self.hass.data = {DOMAIN: {"config_entry": mock_entry}}
        assert self.manager._is_sensor_control_enabled() is True

    async def test_set_indicator_off(self):
        """Test setting indicator OFF."""
        device_id = "32_123456"
        mock_entity = MagicMock()
        self.hass.data = {
            "ramses_extras": {
                "entities": {
                    f"binary_sensor.dehumidifying_active_{device_id}": mock_entity
                }
            }
        }

        await self.manager._set_indicator_off(device_id)
        mock_entity.set_state.assert_called_once()
        assert mock_entity.set_state.call_args[0][0] is False

    async def test_activate_dehumidification(self):
        """Test activating dehumidification."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}

        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
        self.manager.services.async_activate_dehumidification = AsyncMock(
            return_value=True
        )

        await self.manager._activate_dehumidification(device_id, decision)
        assert self.manager._dehumidify_active is True
        self.manager.services.async_activate_dehumidification.assert_called_once_with(
            device_id
        )

    async def test_deactivate_dehumidification(self):
        """Test deactivating dehumidification."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}
        self.manager._dehumidify_active = True

        self.fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)
        self.manager.services.async_deactivate_dehumidification = AsyncMock(
            return_value=True
        )

        await self.manager._deactivate_dehumidification(device_id, decision)
        assert self.manager._dehumidify_active is False
        self.manager.services.async_deactivate_dehumidification.assert_called_once_with(
            device_id
        )

    async def test_public_api_methods(self):
        """Test public API methods."""
        device_id = "32_123456"

        # Thresholds
        self.manager.services.async_set_min_humidity = AsyncMock(return_value=True)
        assert await self.manager.async_set_min_humidity(device_id, 45.0) is True

        self.manager.services.async_set_max_humidity = AsyncMock(return_value=True)
        assert await self.manager.async_set_max_humidity(device_id, 65.0) is True

        # Offset
        self.manager.services.async_set_offset = AsyncMock(return_value=True)
        assert await self.manager.async_set_offset(device_id, 0.5) is True

        # State checks
        self.manager._automation_active = True
        assert self.manager.is_automation_active() is True

        self.manager._dehumidify_active = True
        assert self.manager.is_dehumidifying() is True

    async def test_is_feature_enabled_exception(self):
        """Test is_feature_enabled exception path."""
        self.hass.data.get.side_effect = Exception("Test error")
        assert self.manager._is_feature_enabled() is False

    async def test_validate_device_entities_missing(self):
        """Test _validate_device_entities with missing entities."""
        device_id = "32_123456"
        mock_reg = MagicMock()
        # Note: we need to patch async_get where it is USED in automation.py
        with patch(
            "custom_components.ramses_extras.features.humidity_control.automation.entity_registry.async_get",
            return_value=mock_reg,
        ):
            # 1. First required entity missing
            mock_reg.async_get.return_value = None
            if hasattr(self.manager, "_logged_missing_entities"):
                self.manager._logged_missing_entities = {}
            assert await self.manager._validate_device_entities(device_id) is False

            # 2. Entity mappings missing
            # Reset mock and provide truthy values for required entities,
            #  but None for some mappings
            def side_effect(entity_id):
                if "outdoor_absolute_humidity" in entity_id:
                    return None
                return MagicMock()

            mock_reg.async_get.side_effect = side_effect
            self.manager._logged_missing_entities = {}
            assert await self.manager._validate_device_entities(device_id) is False

    async def test_get_device_entity_states_errors(self):
        """Test _get_device_entity_states error paths."""
        device_id = "32_123456"

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core.get_feature_entity_mappings",
            new=AsyncMock(
                return_value={
                    "indoor_rh": "sensor.32_123456_indoor_humidity",
                }
            ),
        ):
            # Entity not found
            self.hass.states.get.return_value = None
            with pytest.raises(ValueError, match="Entity .* not found"):
                await self.manager._get_device_entity_states(device_id)

            # Entity unavailable
            mock_state = MagicMock(state="unavailable")
            self.hass.states.get.return_value = mock_state
            with pytest.raises(ValueError, match="Entity .* state unavailable"):
                await self.manager._get_device_entity_states(device_id)

    async def test_get_sensor_control_context_failure(self):
        """Test _get_sensor_control_context failure paths."""
        device_id = "32_123456"

        with patch.object(
            self.manager, "_is_sensor_control_enabled", return_value=True
        ):
            with patch(
                "custom_components.ramses_extras.framework.helpers.websocket_base.GetEntityMappingsCommand"
            ) as mock_cmd_class:
                mock_cmd = MagicMock()
                mock_cmd_class.return_value = mock_cmd

                # Success False
                async def mock_execute_fail(conn, msg):
                    conn.result = {"success": False}

                mock_cmd.execute.side_effect = mock_execute_fail
                assert await self.manager._get_sensor_control_context(device_id) is None

                # Exception path
                mock_cmd.execute.side_effect = Exception("Test error")
                assert await self.manager._get_sensor_control_context(device_id) is None

    async def test_activate_dehumidification_failure(self):
        """Test _activate_dehumidification failure paths."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}

        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=False)
        self.manager.services.async_deactivate_dehumidification = AsyncMock()

        await self.manager._activate_dehumidification(device_id, decision)
        assert self.manager._dehumidify_active is False
        self.manager.services.async_deactivate_dehumidification.assert_called_once_with(
            device_id
        )

        # Exception path
        self.fan_speed_arbiter.async_set_demand.side_effect = Exception("Test error")
        await self.manager._activate_dehumidification(device_id, decision)
        # Should log and continue

    async def test_set_fan_low_and_binary_off(self):
        """Test _set_fan_low_and_binary_off."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}

        # Success
        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
        await self.manager._set_fan_low_and_binary_off(device_id, decision)
        assert self.manager._dehumidify_active is False

        # Failure
        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=False)
        await self.manager._set_fan_low_and_binary_off(device_id, decision)
        # Should log and continue

        # Exception
        self.fan_speed_arbiter.async_set_demand.side_effect = Exception("Test error")
        await self.manager._set_fan_low_and_binary_off(device_id, decision)

    async def test_stop_dehumidification_without_switch_change(self):
        """Test _stop_dehumidification_without_switch_change."""
        device_id = "32_123456"

        # Already inactive
        self.manager._dehumidify_active = False
        await self.manager._stop_dehumidification_without_switch_change(device_id)

        # Active -> Stop
        self.manager._dehumidify_active = True
        self.manager.services.async_deactivate_dehumidification = AsyncMock()
        self.fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)

        await self.manager._stop_dehumidification_without_switch_change(device_id)
        assert self.manager._dehumidify_active is False
        self.manager.services.async_deactivate_dehumidification.assert_not_called()

    async def test_update_automation_status_missing_entity(self):
        """Test _update_automation_status with missing entity."""
        device_id = "32_123456"
        decision = {"action": "dehumidify"}

        self.hass.data = {"ramses_extras": {"entities": {}}}
        await self.manager._update_automation_status(device_id, decision)
        # Should log warning

    async def test_public_api_exceptions(self):
        """Test public API methods exception paths."""
        device_id = "32_123456"

        self.manager.services.async_set_min_humidity = AsyncMock(
            side_effect=Exception("Test error")
        )
        assert await self.manager.async_set_min_humidity(device_id, 45.0) is False

        self.manager.services.async_set_max_humidity = AsyncMock(
            side_effect=Exception("Test error")
        )
        assert await self.manager.async_set_max_humidity(device_id, 65.0) is False

        self.manager.services.async_set_offset = AsyncMock(
            side_effect=Exception("Test error")
        )
        assert await self.manager.async_set_offset(device_id, 0.5) is False

    def test_generate_entity_patterns_with_slug_prefixes(self):
        """Test entity pattern generation includes both old and new naming."""
        patterns = self.manager._generate_entity_patterns()

        # Should include both old and new ramses_cc naming patterns
        assert "sensor.*_indoor_humidity" in patterns
        assert "sensor.fan_*_indoor_humidity" in patterns

        # Should include other expected patterns
        assert "sensor.indoor_absolute_humidity_*" in patterns
        assert "sensor.outdoor_absolute_humidity_*" in patterns
        assert "number.relative_humidity_minimum_*" in patterns
        assert "switch.dehumidify_*" in patterns

    def test_wildcard_pattern_matches_old_naming(self):
        """Test that wildcard pattern matches old ramses_cc naming."""
        patterns = self.manager._generate_entity_patterns()
        old_entity_id = "sensor.32_153289_indoor_humidity"

        # The pattern sensor.*_indoor_humidity should match
        pattern = "sensor.*_indoor_humidity"
        assert pattern in patterns

        # Verify the entity ID ends with the expected suffix
        assert old_entity_id.endswith("_indoor_humidity")

    def test_wildcard_pattern_matches_new_naming(self):
        """Test that wildcard pattern matches new ramses_cc naming."""
        patterns = self.manager._generate_entity_patterns()
        new_entity_id = "sensor.fan_32_153289_indoor_humidity"

        # The pattern sensor.fan_*_indoor_humidity should match
        pattern = "sensor.fan_*_indoor_humidity"
        assert pattern in patterns

        # Verify the entity ID starts with the expected prefix
        assert new_entity_id.startswith("sensor.fan_")
        assert new_entity_id.endswith("_indoor_humidity")

    async def test_evaluate_humidity_conditions_indoor_spike_detected(self):
        """Indoor humidity spike should trigger spike_boost dehumidification."""
        # Set up sensor control context with indoor humidity spike config
        self.manager._latest_sensor_control_context["test"] = {
            "sources": {
                "indoor_humidity": {
                    "spike_enabled": True,
                    "spike_rise_percent": 10.0,
                    "spike_window_minutes": 5,
                }
            }
        }

        # Set up indoor humidity history to simulate a spike
        now = time.time()
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},  # Baseline 4 minutes ago
            {"ts": now - 120, "abs": 10.2},  # 2 minutes ago
        ]

        with patch.object(
            self.manager,
            "_schedule_indoor_spike_recheck",
        ) as mock_schedule:
            decision = await self.manager._evaluate_humidity_conditions(
                device_id="test",
                indoor_rh=65.0,  # Above max_humidity
                indoor_abs=11.5,  # 15% rise from baseline of 10.0
                outdoor_abs=8.0,
                min_humidity=40.0,
                max_humidity=60.0,
                offset=0.0,
            )

        assert decision["action"] == "dehumidify"
        assert decision["control_mode"] == "spike_boost"
        assert decision["active_trigger"]["area_id"] == "indoor_humidity"
        assert decision["active_trigger"]["rise_percent"] > 10.0
        assert decision["values"]["active_indoor_spike"] is True
        mock_schedule.assert_called_once()

    async def test_evaluate_humidity_conditions_indoor_spike_disabled(self):
        """Indoor spike detection should be skipped when disabled."""
        self.manager._latest_sensor_control_context["test"] = {
            "sources": {
                "indoor_humidity": {
                    "spike_enabled": False,
                    "spike_rise_percent": 10.0,
                    "spike_window_minutes": 5,
                }
            }
        }

        now = time.time()
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},
        ]

        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=65.0,
            indoor_abs=11.5,  # Would be a spike if enabled
            outdoor_abs=8.0,
            min_humidity=40.0,
            max_humidity=60.0,
            offset=0.0,
        )

        # Should be normal dehumidify, not spike_boost
        assert decision["action"] == "dehumidify"
        assert decision["control_mode"] == "balance"
        assert "active_indoor_spike" not in decision.get("values", {})

    def test_detect_indoor_spike_with_valid_spike(self):
        """Detect indoor spike when conditions are met."""
        now = time.time()
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},
            {"ts": now - 120, "abs": 10.1},
        ]

        spike_config = {
            "enabled": True,
            "spike_rise_percent": 10.0,
            "spike_window_minutes": 5,
        }

        result = self.manager._detect_indoor_spike(
            device_id="test",
            indoor_abs=11.5,  # 15% rise
            indoor_rh=65.0,
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
            spike_config=spike_config,
        )

        assert result is not None
        assert result["area_id"] == "indoor_humidity"
        assert result["label"] == "Indoor Humidity"
        assert result["baseline_abs"] == 10.0
        assert result["current_abs"] == 11.5
        assert result["rise_percent"] == 15.0
        assert result["check_interval_minutes"] == 5

    def test_detect_indoor_spike_disabled(self):
        """No spike when detection is disabled."""
        spike_config = {
            "enabled": False,
            "spike_rise_percent": 10.0,
            "spike_window_minutes": 5,
        }

        result = self.manager._detect_indoor_spike(
            device_id="test",
            indoor_abs=15.0,
            indoor_rh=80.0,
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
            spike_config=spike_config,
        )

        assert result is None

    def test_detect_indoor_spike_below_threshold(self):
        """No spike when rise is below threshold."""
        now = time.time()
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},
        ]

        spike_config = {
            "enabled": True,
            "spike_rise_percent": 20.0,  # High threshold
            "spike_window_minutes": 5,
        }

        result = self.manager._detect_indoor_spike(
            device_id="test",
            indoor_abs=11.5,  # Only 15% rise
            indoor_rh=65.0,
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
            spike_config=spike_config,
        )

        assert result is None

    def test_detect_indoor_spike_rh_too_low(self):
        """No spike when RH is at or below max_humidity."""
        now = time.time()
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},
        ]

        spike_config = {
            "enabled": True,
            "spike_rise_percent": 10.0,
            "spike_window_minutes": 5,
        }

        # RH exactly at max_humidity - should not trigger
        result = self.manager._detect_indoor_spike(
            device_id="test",
            indoor_abs=11.5,
            indoor_rh=60.0,  # Equal to max_humidity
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
            spike_config=spike_config,
        )

        assert result is None

    def test_evaluate_active_indoor_spike_keeps_active(self):
        """Active indoor spike should be retained when conditions persist."""
        self.manager._active_indoor_spikes["test"] = {
            "area_id": "indoor_humidity",
            "label": "Indoor Humidity",
            "baseline_abs": 10.0,
            "current_abs": 11.5,
            "current_rh": 65.0,
            "rise_percent": 15.0,
        }

        result = self.manager._evaluate_active_indoor_spike(
            device_id="test",
            indoor_abs=11.2,  # Still high
            indoor_rh=64.0,  # Still above max
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
        )

        assert result is not None
        assert result["area_id"] == "indoor_humidity"
        assert result["current_abs"] == 11.2  # Updated value
        assert result["current_rh"] == 64.0  # Updated value

    def test_evaluate_active_indoor_spike_clears_when_recovered(self):
        """Active indoor spike should clear when conditions normalize."""
        self.manager._active_indoor_spikes["test"] = {
            "area_id": "indoor_humidity",
            "label": "Indoor Humidity",
            "baseline_abs": 10.0,
            "current_abs": 11.5,
            "current_rh": 65.0,
            "rise_percent": 15.0,
        }

        # RH drops below threshold
        result = self.manager._evaluate_active_indoor_spike(
            device_id="test",
            indoor_abs=10.5,
            indoor_rh=55.0,  # Below max_humidity
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
        )

        assert result is None
        assert "test" not in self.manager._active_indoor_spikes

    def test_evaluate_active_indoor_spike_clears_when_no_spike(self):
        """Evaluate should return None when no active spike exists."""
        result = self.manager._evaluate_active_indoor_spike(
            device_id="test",
            indoor_abs=11.5,
            indoor_rh=65.0,
            outdoor_abs=8.0,
            offset=0.0,
            max_humidity=60.0,
        )

        assert result is None

    def test_clear_active_indoor_spike(self):
        """Test clearing active indoor spike and canceling recheck."""
        mock_handle = MagicMock()
        self.manager._active_indoor_spikes["test"] = {
            "area_id": "indoor_humidity",
            "rise_percent": 15.0,
        }
        self.manager._indoor_spike_check_handles["test"] = mock_handle

        self.manager._clear_active_indoor_spike("test")

        assert "test" not in self.manager._active_indoor_spikes
        assert "test" not in self.manager._indoor_spike_check_handles
        mock_handle.assert_called_once()

    def test_schedule_indoor_spike_recheck(self):
        """Test scheduling indoor spike recheck."""
        old_handle = MagicMock()
        self.manager._indoor_spike_check_handles["test"] = old_handle

        new_handle = MagicMock()
        with patch(
            "custom_components.ramses_extras.features.humidity_control.automation.async_track_time_interval",
            return_value=new_handle,
        ) as mock_track:
            self.manager._schedule_indoor_spike_recheck("test", 3)

        old_handle.assert_called_once()  # Old handle should be cancelled
        assert self.manager._indoor_spike_check_handles["test"] is new_handle
        assert mock_track.call_args.args[2].total_seconds() == 180  # 3 minutes

    async def test_async_recheck_indoor_spike(self):
        """Test indoor spike recheck guards and execution."""
        device_id = "test"

        # When automation inactive
        self.manager._automation_active = False
        self.manager._get_device_entity_states = AsyncMock()
        await self.manager._async_recheck_indoor_spike(device_id)
        self.manager._get_device_entity_states.assert_not_called()

        # When feature disabled
        self.manager._automation_active = True
        with patch.object(self.manager, "_is_feature_enabled", return_value=False):
            await self.manager._async_recheck_indoor_spike(device_id)
        self.manager._get_device_entity_states.assert_not_called()

        # When entity states unavailable
        with patch.object(self.manager, "_is_feature_enabled", return_value=True):
            self.manager._get_device_entity_states = AsyncMock(
                side_effect=ValueError("missing")
            )
            await self.manager._async_recheck_indoor_spike(device_id)
            # Should log and return without error

        # Successful recheck
        with patch.object(self.manager, "_is_feature_enabled", return_value=True):
            entity_states = {"dehumidify": True}
            self.manager._get_device_entity_states = AsyncMock(
                return_value=entity_states
            )
            self.manager._process_automation_logic = AsyncMock()
            await self.manager._async_recheck_indoor_spike(device_id)

        self.manager._process_automation_logic.assert_awaited_once_with(
            device_id, entity_states
        )

    def test_build_indicator_attributes_with_indoor_spike(self):
        """Indicator attributes should include indoor spike metadata."""
        self.manager._active_indoor_spikes["32_123456"] = {
            "area_id": "indoor_humidity",
            "label": "Indoor Humidity",
            "current_abs": 12.0,
            "current_rh": 68.0,
            "baseline_abs": 10.0,
            "rise_percent": 20.0,
            "check_interval_minutes": 5,
        }

        # Test with no decision but active indoor spike
        attrs = self.manager._build_indicator_attributes(
            "32_123456",
            {"control_mode": "dehumidify", "active_trigger": None},
        )

        assert attrs["control_mode"] == "spike_boost"
        assert attrs["active_trigger_area_id"] == "indoor_humidity"
        assert attrs["active_trigger_label"] == "Indoor Humidity"
        assert attrs["active_trigger_rise_percent"] == 20.0
        assert attrs["next_check_interval_minutes"] == 5

    async def test_indoor_spike_takes_priority_over_area_spike(self):
        """Indoor spike should take priority when both are active."""
        self.manager._latest_sensor_control_context["test"] = {
            "sources": {
                "indoor_humidity": {
                    "spike_enabled": True,
                    "spike_rise_percent": 10.0,
                    "spike_window_minutes": 5,
                }
            },
            "area_sensors": [
                {
                    "area_id": "bathroom",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_humidity",
                    "spike_rise_percent": 15.0,
                    "spike_window_minutes": 3,
                    "check_interval_minutes": 1,
                    "enabled": True,
                }
            ],
        }

        temp_state = MagicMock(state="22.0")
        humidity_state = MagicMock(state="70.0")  # High RH for area spike
        self.hass.states.get.side_effect = lambda entity_id: {
            "sensor.bath_temp": temp_state,
            "sensor.bath_humidity": humidity_state,
        }.get(entity_id)

        now = time.time()
        # Set up both indoor and area history for spikes
        self.manager._indoor_history["test"] = [
            {"ts": now - 240, "abs": 10.0},
        ]
        self.manager._area_history["test"] = {
            "bathroom": [
                {"ts": now - 120, "abs": 9.0},
            ]
        }

        with patch.object(self.manager, "_schedule_indoor_spike_recheck"):
            decision = await self.manager._evaluate_humidity_conditions(
                device_id="test",
                indoor_rh=65.0,
                indoor_abs=11.5,  # 15% rise - indoor spike
                outdoor_abs=8.0,
                min_humidity=40.0,
                max_humidity=60.0,
                offset=0.0,
            )

        # Indoor spike should take priority
        assert decision["action"] == "dehumidify"
        assert decision["control_mode"] == "spike_boost"
        assert decision["active_trigger"]["area_id"] == "indoor_humidity"
        assert "active_indoor_spike" in decision["values"]

    def test_set_fan_low_clears_indoor_spike(self):
        """Setting fan low should clear indoor spike when not in spike mode."""
        self.manager._active_indoor_spikes["test"] = {
            "area_id": "indoor_humidity",
            "rise_percent": 15.0,
        }
        mock_handle = MagicMock()
        self.manager._indoor_spike_check_handles["test"] = mock_handle

        # Mock the _clear_active_indoor_spike to track it was called
        with patch.object(self.manager, "_clear_active_indoor_spike") as mock_clear:
            decision = {"reasoning": ["Test"], "control_mode": "balance"}
            # Run async method
            import asyncio

            asyncio.run(self.manager._set_fan_low_and_binary_off("test", decision))

        mock_clear.assert_called_once_with("test")

    def test_update_indoor_humidity_history(self):
        """Test indoor humidity history tracking."""
        # Add multiple readings
        self.manager._update_indoor_humidity_history("test", 10.0, 5)
        self.manager._update_indoor_humidity_history("test", 10.5, 5)
        self.manager._update_indoor_humidity_history("test", 11.0, 5)

        history = self.manager._indoor_history["test"]
        assert len(history) == 3
        assert history[0]["abs"] == 10.0
        assert history[1]["abs"] == 10.5
        assert history[2]["abs"] == 11.0

    def test_update_indoor_humidity_history_trims_old_entries(self):
        """Old history entries should be trimmed."""
        now = time.time()

        # Add old entries
        self.manager._indoor_history["test"] = [
            {"ts": now - 400, "abs": 9.0},  # Too old (> 5 min window + 60s buffer)
            {"ts": now - 200, "abs": 9.5},  # Within window
        ]

        self.manager._update_indoor_humidity_history("test", 10.0, 5)

        history = self.manager._indoor_history["test"]
        # Old entry should be removed, new one added
        assert len(history) == 2
        assert all(entry["ts"] >= now - 360 for entry in history)

    @pytest.mark.asyncio
    async def test_automation_skips_when_device_offline(self):
        """Test that automation skips processing when device is offline."""
        device_id = "32:153289"

        # Mock transport monitor to report device offline
        with patch.object(
            self.manager, "is_device_transport_available", return_value=False
        ):
            # Mock entity states
            entity_states = {
                "indoor_humidity": 75.0,
                "outdoor_humidity": 60.0,
                "dehumidify": True,
            }

            # Process automation logic
            await self.manager._process_automation_logic(device_id, entity_states)

            # Verify no fan speed demand was set (automation was skipped)
            self.fan_speed_arbiter.async_set_demand.assert_not_called()
            self.fan_speed_arbiter.async_clear_demand.assert_not_called()

    @pytest.mark.asyncio
    async def test_automation_resumes_when_device_online(self):
        """Test that automation resumes when device comes back online."""
        device_id = "32:153289"

        # Mock transport monitor to report device online
        with patch.object(
            self.manager, "is_device_transport_available", return_value=True
        ):
            # Mock entity states that should trigger dehumidify
            entity_states = {
                "indoor_humidity": 75.0,
                "outdoor_humidity": 60.0,
                "dehumidify": True,
                "indoor_absolute_humidity": 15.0,
                "outdoor_absolute_humidity": 10.0,
            }

            # Mock config to allow processing
            self.manager.config.get_min_humidity = MagicMock(return_value=50.0)
            self.manager.config.get_max_humidity = MagicMock(return_value=70.0)
            self.manager.config.get_offset = MagicMock(return_value=5.0)

            # Process automation logic
            await self.manager._process_automation_logic(device_id, entity_states)

            # Verify fan speed demand was processed (automation ran)
            # Note: actual call depends on humidity logic, but it should not be skipped
            assert (
                self.fan_speed_arbiter.async_set_demand.called
                or self.fan_speed_arbiter.async_clear_demand.called
            )
