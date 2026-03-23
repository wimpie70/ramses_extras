"""Tests for CO2AutomationManager unified trigger logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.co2_control.automation import (
    CO2AutomationManager,
)


class _MockState:
    def __init__(self, value: str) -> None:
        self.state = value


class TestCO2AutomationManager:
    """Test cases for CO2AutomationManager unified source logic."""

    def setup_method(self) -> None:
        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.config_entries = MagicMock()
        self.hass.config_entries.async_entries = MagicMock(return_value=[])
        self.hass.data = {
            "ramses_extras": {
                "enabled_features": {
                    "co2_control": True,
                    "sensor_control": True,
                },
                "entities": {},
                "devices": [
                    {
                        "device_id": "32:123456",
                        "type": "FAN",
                    }
                ],
                "config_entry": MagicMock(
                    data={"enabled_features": {"sensor_control": True}},
                    options={"enabled_features": {"sensor_control": True}},
                ),
            }
        }
        self.hass.states = MagicMock()
        self.fan_speed_arbiter = MagicMock()
        self.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
        self.fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)
        self.fan_speed_arbiter.is_manual_override_active.return_value = False

        self.config_entry = MagicMock()
        self.config_entry.options = {
            "enabled_features": {"co2_control": True, "sensor_control": True},
            "co2_control": {"automation_enabled": True},
        }
        self.config_entry.data = {
            "enabled_features": {"co2_control": True, "sensor_control": True}
        }

        with (
            patch(
                "custom_components.ramses_extras.features.co2_control.automation.RamsesCommands"
            ),
            patch(
                "custom_components.ramses_extras.features.co2_control.automation.get_fan_speed_arbiter",
                return_value=self.fan_speed_arbiter,
            ),
        ):
            self.manager = CO2AutomationManager(self.hass, self.config_entry)

        self.manager._automation_active = True
        self.manager.config.update_config({"automation_enabled": True})

    def test_evaluate_source_trigger_hysteresis(self) -> None:
        """Trigger uses activation/deactivation hysteresis correctly."""
        source_states: dict[str, bool] = {}

        self.hass.states.get.return_value = _MockState("1150")
        result = self.manager._evaluate_source_trigger(
            source_states,
            "bathroom",
            "Bathroom",
            "sensor.bath_co2",
            threshold=1000,
        )
        assert result is not None
        assert source_states["bathroom"] is True

        self.hass.states.get.return_value = _MockState("950")
        result = self.manager._evaluate_source_trigger(
            source_states,
            "bathroom",
            "Bathroom",
            "sensor.bath_co2",
            threshold=1000,
        )
        assert result is not None
        assert source_states["bathroom"] is True

        self.hass.states.get.return_value = _MockState("880")
        result = self.manager._evaluate_source_trigger(
            source_states,
            "bathroom",
            "Bathroom",
            "sensor.bath_co2",
            threshold=1000,
        )
        assert result is None
        assert source_states["bathroom"] is False

    def test_evaluate_trigger_sources_area_and_internal(self) -> None:
        """Area source and internal source are both evaluated."""
        self.hass.states.get.side_effect = lambda entity_id: {
            "number.co2_threshold_32_123456": _MockState("1000"),
            "sensor.bathroom_co2": _MockState("1200"),
            "sensor.32_123456_co2_level": _MockState("1100"),
        }.get(entity_id)

        sensor_ctx = {
            "mappings": {"co2": "sensor.32_123456_co2_level"},
            "area_sensors": [
                {
                    "source_id": "bathroom",
                    "label": "Bathroom",
                    "area_co2_enabled": True,
                    "co2_entity": "sensor.bathroom_co2",
                    "co2_threshold": 900,
                }
            ],
        }

        triggered = self.manager._evaluate_trigger_sources("32:123456", sensor_ctx)

        trigger_ids = {item["source_id"] for item in triggered}
        assert "bathroom" in trigger_ids
        assert "internal_co2" in trigger_ids

    def test_resolve_area_threshold_prefers_threshold_entity(self) -> None:
        """Area threshold entity should override static area threshold."""
        self.hass.states.get.side_effect = lambda entity_id: {
            "input_number.bathroom_co2_threshold": _MockState("850")
        }.get(entity_id)

        threshold = self.manager._resolve_area_threshold(
            {
                "co2_threshold_entity": "input_number.bathroom_co2_threshold",
                "co2_threshold": 800,
            },
            threshold_default=1000,
        )

        assert threshold == 850

    def test_resolve_area_threshold_falls_back_to_static_value(self) -> None:
        """Static area threshold should be used when threshold entity is unavailable."""
        self.hass.states.get.return_value = None

        threshold = self.manager._resolve_area_threshold(
            {
                "co2_threshold_entity": "input_number.bathroom_co2_threshold",
                "co2_threshold": 800,
            },
            threshold_default=1000,
        )

        assert threshold == 800

    def test_get_raw_area_sensors_from_active_entry_when_hass_data_is_stale(
        self,
    ) -> None:
        """Raw area sensor fallback should use active config entries for the device."""
        stale_entry = MagicMock()
        stale_entry.options = {"sensor_control": {"area_sensors": {}}}
        stale_entry.data = {}

        active_entry = MagicMock()
        active_entry.options = {
            "sensor_control": {
                "area_sensors": {
                    "32_123456": [
                        {
                            "source_id": "bathroom",
                            "label": "Bathroom",
                            "area_co2_enabled": True,
                            "co2_entity": "input_number.co2_helper",
                            "co2_threshold": 800,
                        }
                    ]
                }
            }
        }
        active_entry.data = {}

        self.hass.data["ramses_extras"]["config_entry"] = stale_entry
        self.hass.config_entries.async_entries.return_value = [active_entry]

        area_sensors = self.manager._get_raw_area_sensors_from_options("32_123456")

        assert len(area_sensors) == 1
        assert area_sensors[0]["source_id"] == "bathroom"
        assert area_sensors[0]["co2_entity"] == "input_number.co2_helper"

    def test_is_automation_enabled_for_device_accepts_switch_on(self) -> None:
        """Switch ON should enable evaluation even if config flag is false."""
        self.manager.config.update_config({"automation_enabled": False})
        self.hass.states.get.side_effect = lambda entity_id: {
            "switch.co2_control_32_123456": _MockState("on")
        }.get(entity_id)

        assert self.manager._is_automation_enabled_for_device("32:123456") is True

    @pytest.mark.asyncio
    async def test_get_device_entity_states_ignores_unknown_status_sensor(self) -> None:
        """Diagnostic status sensor unknown should not block automation loop."""
        self.hass.states.get.side_effect = lambda entity_id: {
            "switch.co2_control_32_123456": _MockState("on"),
            "number.co2_threshold_32_123456": _MockState("800"),
            "binary_sensor.co2_active_32_123456": _MockState("off"),
            "sensor.co2_zone_status_32_123456": _MockState("unknown"),
        }.get(entity_id)

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core.get_feature_entity_mappings",  # noqa: E501
            new=AsyncMock(
                return_value={
                    "co2_control": "switch.co2_control_32_123456",
                    "co2_threshold": "number.co2_threshold_32_123456",
                    "co2_active": "binary_sensor.co2_active_32_123456",
                    "co2_zone_status": "sensor.co2_zone_status_32_123456",
                }
            ),
        ):
            states = await self.manager._get_device_entity_states("32:123456")

        assert states["co2_control"] is True
        assert states["co2_threshold"] == 800.0
        assert "co2_zone_status" not in states

    @pytest.mark.asyncio
    async def test_on_homeassistant_started_runs_initial_evaluation(self) -> None:
        """Startup hook should evaluate current CO2 states once."""
        self.manager._evaluate_co2_control = AsyncMock()

        with patch(
            "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation._on_homeassistant_started",  # noqa: E501
            new=AsyncMock(),
        ):
            await self.manager._on_homeassistant_started(None)

        self.manager._evaluate_co2_control.assert_called()

    @pytest.mark.asyncio
    async def test_adjust_fan_speed_uses_shared_arbiter(self) -> None:
        """CO2 speed changes should be submitted through the shared arbiter."""
        zone_manager = MagicMock()
        zone_manager.calculate_combined_fan_speed = AsyncMock(return_value=4)

        await self.manager._adjust_fan_speed("32:123456", zone_manager)

        self.fan_speed_arbiter.async_set_demand.assert_awaited_once_with(
            "32:123456",
            feature_id="co2_control",
            source_id="co2_control",
            requested_speed="fan_high",
            priority=30,
            reason="co2_trigger",
            metadata={"target_speed": 4},
        )

    @pytest.mark.asyncio
    async def test_update_automation_status_updates_entities(self) -> None:
        """Binary and status entities receive trigger metadata."""
        active_entity = MagicMock()
        status_entity = MagicMock()
        self.hass.data["ramses_extras"]["entities"] = {
            "binary_sensor.co2_active_32_123456": active_entity,
            "sensor.co2_zone_status_32_123456": status_entity,
        }

        await self.manager._update_automation_status(
            "32:123456",
            triggered_zones=["zone_1"],
            triggered_sources=[
                {
                    "source_id": "bathroom",
                    "label": "Bathroom",
                    "entity_id": "sensor.bathroom_co2",
                    "value": 1234.0,
                    "threshold": 900,
                }
            ],
            sensor_ctx={"mappings": {"co2": "sensor.32_123456_co2_level"}},
        )

        active_entity.set_state.assert_called_once()
        status_entity.set_zone_status.assert_called_once()

        attrs = active_entity.set_state.call_args[0][1]
        assert attrs["active_trigger_source_id"] == "bathroom"
        assert attrs["internal_co2_entity"] == "sensor.32_123456_co2_level"

    @pytest.mark.asyncio
    async def test_process_automation_logic_calls_evaluate(self) -> None:
        """Base hook delegates to unified evaluate method."""
        self.manager._evaluate_co2_control = AsyncMock()

        await self.manager._process_automation_logic("32:123456", {})

        self.manager._evaluate_co2_control.assert_called_once_with("32:123456")

    @pytest.mark.asyncio
    async def test_process_automation_logic_skips_when_manual_override_active(
        self,
    ) -> None:
        """Sticky manual override should short-circuit CO2 automation."""
        self.manager._evaluate_co2_control = AsyncMock()
        self.fan_speed_arbiter.is_manual_override_active.return_value = True

        await self.manager._process_automation_logic("32:123456", {})

        self.manager._evaluate_co2_control.assert_not_called()

    @pytest.mark.asyncio
    async def test_automation_skips_when_device_offline(self) -> None:
        """Test that automation skips processing when device is offline."""
        device_id = "32:123456"

        # Mock transport monitor to report device offline
        with patch.object(
            self.manager, "is_device_transport_available", return_value=False
        ):
            # Mock evaluate method to track if it was called
            self.manager._evaluate_co2_control = AsyncMock()

            # Process automation logic
            await self.manager._process_automation_logic(device_id, {})

            # Verify evaluate was NOT called (automation was skipped)
            self.manager._evaluate_co2_control.assert_not_called()

    @pytest.mark.asyncio
    async def test_automation_resumes_when_device_online(self) -> None:
        """Test that automation resumes when device comes back online."""
        device_id = "32:123456"

        # Mock transport monitor to report device online
        with patch.object(
            self.manager, "is_device_transport_available", return_value=True
        ):
            # Mock evaluate method to track if it was called
            self.manager._evaluate_co2_control = AsyncMock()

            # Process automation logic
            await self.manager._process_automation_logic(device_id, {})

            # Verify evaluate WAS called (automation ran)
            self.manager._evaluate_co2_control.assert_called_once_with(device_id)
