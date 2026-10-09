"""Tests for multi-sensor aggregation and static high-humidity area triggers.

Covers issue https://github.com/wimpie70/ramses_extras/issues/276:
- `_aggregate_indoor_values` effective-value layer (first_valid/max/avg/weighted)
- `_detect_area_high_humidity` static trigger_on_high_humidity path
- end-to-end wiring in `_evaluate_humidity_conditions`
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control.automation import (
    HumidityAutomationManager,
)


def _area_state(
    area_id: str,
    rh: float,
    absh: float,
    **extra: object,
) -> dict:
    """Build a resolved area sensor state entry."""
    return {
        "area_id": area_id,
        "label": area_id.title(),
        "enabled": True,
        "valid": True,
        "current_rh": rh,
        "current_abs": absh,
        **extra,
    }


class TestAggregateIndoorValues:
    """Tests for _aggregate_indoor_values effective-value layer."""

    def setup_method(self):
        self.hass = MagicMock(spec=HomeAssistant)
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

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.get_ramses_commands"
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

    def _aggregate(
        self,
        indoor_rh: float = 50.0,
        indoor_abs: float = 10.0,
        states: list[dict] | None = None,
        strategy: str | None = None,
    ) -> tuple[float, float, str]:
        if strategy is not None:
            self.manager._latest_sensor_control_context["dev"] = {
                "aggregation": strategy
            }
        return self.manager._aggregate_indoor_values(
            "dev", indoor_rh, indoor_abs, states or []
        )

    def test_first_valid_default_ignores_area_sensors(self):
        rh, absh, source = self._aggregate(states=[_area_state("bath", 80.0, 14.0)])
        assert (rh, absh, source) == (50.0, 10.0, "internal")

    def test_first_valid_explicit_strategy(self):
        rh, absh, source = self._aggregate(
            states=[_area_state("bath", 80.0, 14.0)], strategy="first_valid"
        )
        assert (rh, absh, source) == (50.0, 10.0, "internal")

    def test_max_picks_highest_rh_source(self):
        rh, absh, source = self._aggregate(
            states=[
                _area_state("bath", 80.0, 14.0),
                _area_state("kitchen", 60.0, 12.0),
            ],
            strategy="max",
        )
        assert rh == 80.0
        assert absh == 14.0  # winner's abs comes along
        assert source == "Bath"

    def test_max_keeps_internal_when_highest(self):
        rh, absh, source = self._aggregate(
            states=[_area_state("bath", 40.0, 8.0)], strategy="max"
        )
        assert (rh, absh, source) == (50.0, 10.0, "internal")

    def test_avg_averages_all_sources(self):
        rh, absh, source = self._aggregate(
            states=[
                _area_state("bath", 80.0, 14.0),
                _area_state("kitchen", 60.0, 12.0),
            ],
            strategy="avg",
        )
        assert rh == pytest.approx((50.0 + 80.0 + 60.0) / 3)
        assert absh == pytest.approx((10.0 + 14.0 + 12.0) / 3)
        assert source == "avg of 3 sources"

    def test_weighted_applies_weights(self):
        rh, absh, source = self._aggregate(
            states=[
                _area_state("bath", 80.0, 14.0, weight=3.0),
                _area_state("kitchen", 60.0, 12.0),  # default weight 1.0
            ],
            strategy="weighted",
        )
        # weights: internal 1.0, bath 3.0, kitchen 1.0 → total 5.0
        assert rh == pytest.approx((50.0 + 3 * 80.0 + 60.0) / 5.0)
        assert absh == pytest.approx((10.0 + 3 * 14.0 + 12.0) / 5.0)
        assert source == "weighted avg of 3 sources"

    def test_weighted_falls_back_when_all_weights_invalid(self):
        rh, absh, source = self._aggregate(
            states=[_area_state("bath", 80.0, 14.0, weight=0.0)],
            strategy="weighted",
        )
        # weight 0 is coerced to 1.0, so bath contributes normally
        assert rh == pytest.approx((50.0 + 80.0) / 2)
        assert source == "weighted avg of 2 sources"

    def test_unavailable_sources_excluded(self):
        rh, absh, source = self._aggregate(
            states=[
                _area_state("bath", 80.0, 14.0, enabled=False),
                _area_state("attic", 90.0, 16.0, valid=False),
                _area_state("kitchen", 60.0, None),  # missing abs
                _area_state("cellar", None, 9.0),  # missing rh
            ],
            strategy="max",
        )
        assert (rh, absh, source) == (50.0, 10.0, "internal")

    def test_all_sources_unavailable_keeps_baseline(self):
        rh, absh, source = self._aggregate(
            indoor_rh=0.0, indoor_abs=0.0, strategy="avg"
        )
        assert (rh, absh, source) == (0.0, 0.0, "avg of 1 sources")


class TestDetectAreaHighHumidity:
    """Tests for the static trigger_on_high_humidity area path."""

    def setup_method(self):
        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.data = MagicMock()
        self.hass.data.get.return_value = {
            "enabled_features": {"humidity_control": True}
        }
        self.hass.config = MagicMock()
        self.hass.states = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.options = {}
        self.config_entry.data = {}
        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.get_ramses_commands"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.HumidityConfig"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.HumidityServices"
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.get_fan_speed_arbiter",
                return_value=MagicMock(),
            ),
        ):
            self.manager = HumidityAutomationManager(self.hass, self.config_entry)

    def _detect(self, states: list[dict], **kwargs: object) -> list[dict]:
        args = {
            "device_id": "dev",
            "indoor_abs": 10.0,
            "outdoor_abs": 8.0,
            "offset": 0.0,
            "max_humidity": 60.0,
            "area_sensor_states": states,
        }
        args.update(kwargs)
        return self.manager._detect_area_high_humidity(**args)

    def test_triggers_when_rh_above_max(self):
        triggers = self._detect(
            [_area_state("bath", 75.0, 12.0, trigger_on_high_humidity=True)]
        )
        assert len(triggers) == 1
        assert triggers[0]["area_id"] == "bath"
        assert triggers[0]["trigger_kind"] == "high_humidity"
        assert triggers[0]["rise_percent"] is None
        assert triggers[0]["current_rh"] == 75.0

    def test_no_trigger_without_flag(self):
        triggers = self._detect([_area_state("bath", 75.0, 12.0)])
        assert triggers == []

    def test_no_trigger_below_max(self):
        triggers = self._detect(
            [_area_state("bath", 55.0, 12.0, trigger_on_high_humidity=True)]
        )
        assert triggers == []

    def test_gated_by_outdoor_abs(self):
        # outdoor wetter than the area → ventilating would make it worse
        triggers = self._detect(
            [_area_state("bath", 75.0, 12.0, trigger_on_high_humidity=True)],
            outdoor_abs=15.0,
            offset=0.5,
        )
        assert triggers == []

    def test_ignore_outdoor_compares_indoor_only(self):
        triggers = self._detect(
            [
                _area_state(
                    "bath",
                    75.0,
                    12.0,
                    trigger_on_high_humidity=True,
                    spike_ignore_outdoor=True,
                )
            ],
            outdoor_abs=15.0,
            offset=0.5,
        )
        assert len(triggers) == 1

    def test_ignore_outdoor_still_gated_by_indoor(self):
        triggers = self._detect(
            [
                _area_state(
                    "bath",
                    75.0,
                    9.0,  # drier than the indoor baseline
                    trigger_on_high_humidity=True,
                    spike_ignore_outdoor=True,
                )
            ],
            outdoor_abs=15.0,
        )
        assert triggers == []

    def test_missing_values_skipped(self):
        triggers = self._detect(
            [
                _area_state("bath", None, 12.0, trigger_on_high_humidity=True),
                _area_state("attic", 75.0, None, trigger_on_high_humidity=True),
                _area_state(
                    "cellar",
                    75.0,
                    12.0,
                    trigger_on_high_humidity=True,
                    enabled=False,
                ),
            ]
        )
        assert triggers == []

    def test_multiple_triggers_sorted_by_rh(self):
        triggers = self._detect(
            [
                _area_state("bath", 70.0, 12.0, trigger_on_high_humidity=True),
                _area_state("attic", 80.0, 13.0, trigger_on_high_humidity=True),
                _area_state("kitchen", 65.0, 11.5, trigger_on_high_humidity=True),
            ]
        )
        assert [t["area_id"] for t in triggers] == ["attic", "bath", "kitchen"]


class TestEvaluateHumidityConditionsAggregation:
    """End-to-end: aggregation and static triggers inside the decision."""

    def setup_method(self):
        self.hass = MagicMock(spec=HomeAssistant)
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

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.automation.get_ramses_commands"
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

    def _set_area_entities(
        self, area_sensors: list[dict], states: dict[str, tuple[str, str]]
    ) -> None:
        """Register area sensors in ctx and mock their entity states."""
        self.manager._latest_sensor_control_context.setdefault("test", {})[
            "area_sensors"
        ] = area_sensors

        def _get(entity_id: str):
            pair = states.get(entity_id)
            if pair is None:
                return None
            return MagicMock(state=pair[0])

        self.hass.states.get.side_effect = _get

    async def test_max_strategy_area_drives_high_rh_decision(self):
        """Under `max`, a humid area sensor raises the effective indoor RH."""
        self.manager._latest_sensor_control_context["test"] = {
            "aggregation": "max",
            "area_sensors": [
                {
                    "area_id": "bath",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_hum",
                    "spike_rise_percent": 50.0,
                    "enabled": True,
                    "valid": True,
                }
            ],
        }
        # 22°C / 75% ≈ 12.2 g/m³ abs — wetter than indoor 10 and outdoor 8
        self._set_area_entities(
            self.manager._latest_sensor_control_context["test"]["area_sensors"],
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("75.0",)},
        )

        with patch.object(self.manager, "_schedule_area_spike_recheck"):
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
        assert decision["humidity_role"] == "demand"
        assert decision["values"]["indoor_rh"] == 75.0
        assert decision["values"]["indoor_source"] == "Bathroom"
        assert "High indoor RH" in decision["reasoning"][0]

    async def test_first_valid_ignores_area_for_baseline(self):
        """Default strategy must not let area sensors affect the baseline."""
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": [
                {
                    "area_id": "bath",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_hum",
                    "spike_rise_percent": 50.0,
                    "enabled": True,
                    "valid": True,
                }
            ],
        }
        self._set_area_entities(
            self.manager._latest_sensor_control_context["test"]["area_sensors"],
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("75.0",)},
        )

        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=50.0,
            indoor_abs=10.0,
            outdoor_abs=8.0,
            min_humidity=40.0,
            max_humidity=60.0,
            offset=0.0,
        )

        assert decision["action"] == "stop"
        assert decision["values"]["indoor_rh"] == 50.0
        assert decision["values"]["indoor_source"] == "internal"

    async def test_static_high_humidity_trigger_dehumidifies(self):
        """trigger_on_high_humidity area fires without any spike history."""
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": [
                {
                    "area_id": "bath",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_hum",
                    "trigger_on_high_humidity": True,
                    "check_interval_minutes": 2,
                    "enabled": True,
                    "valid": True,
                }
            ],
        }
        self._set_area_entities(
            self.manager._latest_sensor_control_context["test"]["area_sensors"],
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("75.0",)},
        )

        with patch.object(
            self.manager, "_schedule_area_spike_recheck"
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
        trigger = decision["active_trigger"]
        assert trigger["area_id"] == "bath"
        assert trigger["trigger_kind"] == "high_humidity"
        mock_schedule.assert_called_once_with("test", 2)

    async def test_static_trigger_retained_until_recovered(self):
        """Active static trigger persists while RH stays above max."""
        area_sensors = [
            {
                "area_id": "bath",
                "label": "Bathroom",
                "temperature_entity": "sensor.bath_temp",
                "humidity_entity": "sensor.bath_hum",
                "trigger_on_high_humidity": True,
                "check_interval_minutes": 1,
                "enabled": True,
                "valid": True,
            }
        ]
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": area_sensors
        }
        self._set_area_entities(
            area_sensors,
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("75.0",)},
        )

        with patch.object(self.manager, "_schedule_area_spike_recheck"):
            first = await self.manager._evaluate_humidity_conditions(
                device_id="test",
                indoor_rh=50.0,
                indoor_abs=10.0,
                outdoor_abs=8.0,
                min_humidity=40.0,
                max_humidity=60.0,
                offset=0.0,
            )
        assert first["action"] == "dehumidify"

        # A second run with unchanged conditions must retain the trigger
        # through the active-spike path even though nothing "new" fired.
        with patch.object(self.manager, "_schedule_area_spike_recheck"):
            second = await self.manager._evaluate_humidity_conditions(
                device_id="test",
                indoor_rh=50.0,
                indoor_abs=10.0,
                outdoor_abs=8.0,
                min_humidity=40.0,
                max_humidity=60.0,
                offset=0.0,
            )
        assert second["action"] == "dehumidify"

        # RH recovers below max → demand clears
        self._set_area_entities(
            area_sensors,
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("55.0",)},
        )
        third = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=50.0,
            indoor_abs=10.0,
            outdoor_abs=8.0,
            min_humidity=40.0,
            max_humidity=60.0,
            offset=0.0,
        )
        assert third["action"] == "stop"

    async def test_static_trigger_gated_by_wet_outdoor(self):
        """Static trigger does not fire when outside is wetter."""
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": [
                {
                    "area_id": "bath",
                    "label": "Bathroom",
                    "temperature_entity": "sensor.bath_temp",
                    "humidity_entity": "sensor.bath_hum",
                    "trigger_on_high_humidity": True,
                    "enabled": True,
                    "valid": True,
                }
            ],
        }
        # 22°C / 75% ≈ 12.2 g/m³ — below outdoor 15.0
        self._set_area_entities(
            self.manager._latest_sensor_control_context["test"]["area_sensors"],
            {"sensor.bath_temp": ("22.0",), "sensor.bath_hum": ("75.0",)},
        )

        decision = await self.manager._evaluate_humidity_conditions(
            device_id="test",
            indoor_rh=50.0,
            indoor_abs=10.0,
            outdoor_abs=15.0,
            min_humidity=40.0,
            max_humidity=60.0,
            offset=0.0,
        )

        assert decision["action"] == "stop"

    async def test_multiple_areas_each_trigger(self):
        """Two flagged areas both contribute active triggers."""
        area_sensors = [
            {
                "area_id": "bath",
                "label": "Bathroom",
                "temperature_entity": "sensor.bath_temp",
                "humidity_entity": "sensor.bath_hum",
                "trigger_on_high_humidity": True,
                "check_interval_minutes": 1,
                "enabled": True,
                "valid": True,
            },
            {
                "area_id": "kitchen",
                "label": "Kitchen",
                "temperature_entity": "sensor.kit_temp",
                "humidity_entity": "sensor.kit_hum",
                "trigger_on_high_humidity": True,
                "check_interval_minutes": 1,
                "enabled": True,
                "valid": True,
            },
        ]
        self.manager._latest_sensor_control_context["test"] = {
            "area_sensors": area_sensors
        }
        self._set_area_entities(
            area_sensors,
            {
                "sensor.bath_temp": ("22.0",),
                "sensor.bath_hum": ("75.0",),
                "sensor.kit_temp": ("22.0",),
                "sensor.kit_hum": ("70.0",),
            },
        )

        with patch.object(self.manager, "_schedule_area_spike_recheck"):
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
        assert len(decision["active_triggers"]) == 2
        assert {t["area_id"] for t in decision["active_triggers"]} == {
            "bath",
            "kitchen",
        }
