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

        self.config_entry = MagicMock()
        self.config_entry.options = {
            "enabled_features": {"co2_control": True, "sensor_control": True},
            "co2_control": {"automation_enabled": True},
        }
        self.config_entry.data = {
            "enabled_features": {"co2_control": True, "sensor_control": True}
        }

        with patch(
            "custom_components.ramses_extras.features.co2_control.automation.RamsesCommands"
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
