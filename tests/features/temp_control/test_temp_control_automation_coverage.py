"""Tests for temp_control automation — lifecycle and helper methods.

Targets 100% coverage of automation.py by testing:
- start/stop lifecycle
- _is_feature_enabled fallback paths
- _on_homeassistant_started
- _reconcile_startup_states
- _iter_candidate_device_ids
- _get_device_entity_states
- _async_handle_state_change (bypass safety net)
- _get_desired_speed_option
- _set_active_indicator / _set_status_sensor
- _is_sensor_control_enabled / _get_device_type_for_sensor_control
- _get_sensor_control_context
- _evaluate_areas edge cases
- _clear_speed_demand exception path
- zone demand registry missing
"""

import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.temp_control.config import (
    TempControlSettings,
)
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)


def make_settings(**overrides) -> TempControlSettings:
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
        "comfort_temp_entity": "",
    }
    defaults.update(overrides)
    return TempControlSettings(**defaults)


def make_entity_states(**kwargs):
    defaults = {
        "temp_control": True,
        "indoor_temp": 22.0,
        "outdoor_temp": 18.0,
        "supply_temp": 18.0,
        "comfort_temp": 21.0,
        "indoor_rh": 50.0,
        "min_rh": 40.0,
        "max_rh": 60.0,
        "dehumidifying_active": False,
        "co2_active": False,
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def automation_manager():
    hass = MagicMock()
    hass.data = {"ramses_extras": {"enabled_features": {"temp_control": True}}}
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.states.get = MagicMock(return_value=None)
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.loop = MagicMock()

    config_entry = MagicMock()
    config_entry.options = {}
    config_entry.data = {}

    with (
        patch(
            "custom_components.ramses_extras.features."
            "temp_control.automation.get_fan_speed_arbiter"
        ),
        patch(
            "custom_components.ramses_extras.features."
            "temp_control.automation.RamsesCommands"
        ),
        patch(
            "custom_components.ramses_extras.features."
            "temp_control.automation.get_zone_demand_registry"
        ),
        patch(
            "custom_components.ramses_extras.features."
            "temp_control.automation.TempControlConfig"
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


# ---- is_automation_active ----


class TestIsAutomationActive:
    def test_returns_true_when_active(self, automation_manager):
        automation_manager._automation_active = True
        assert automation_manager.is_automation_active() is True

    def test_returns_false_when_inactive(self, automation_manager):
        automation_manager._automation_active = False
        assert automation_manager.is_automation_active() is False


# ---- _is_feature_enabled ----


class TestIsFeatureEnabled:
    def test_enabled_via_domain_data(self, automation_manager):
        assert automation_manager._is_feature_enabled() is True

    def test_disabled_via_domain_data(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {"enabled_features": {"temp_control": False}}
        }
        assert automation_manager._is_feature_enabled() is False

    def test_fallback_to_config_entry_options(self, automation_manager):
        """When domain data has no dict, fall back to config_entry."""
        automation_manager.hass.data = {"ramses_extras": {}}
        automation_manager.config_entry.options = {
            "enabled_features": {"temp_control": True}
        }
        assert automation_manager._is_feature_enabled() is True

    def test_fallback_to_config_entry_data(self, automation_manager):
        """When options has nothing, fall back to data."""
        automation_manager.hass.data = {"ramses_extras": {}}
        automation_manager.config_entry.options = {}
        automation_manager.config_entry.data = {
            "enabled_features": {"temp_control": True}
        }
        assert automation_manager._is_feature_enabled() is True

    def test_exception_returns_false(self, automation_manager):
        """If hass.data raises, return False."""
        automation_manager.hass.data = MagicMock()
        automation_manager.hass.data.get = MagicMock(side_effect=RuntimeError("boom"))
        assert automation_manager._is_feature_enabled() is False


# ---- _generate_entity_patterns ----


class TestGenerateEntityPatterns:
    def test_returns_list_with_expected_patterns(self, automation_manager):
        patterns = automation_manager._generate_entity_patterns()
        assert isinstance(patterns, list)
        assert "switch.temp_control_*" in patterns
        assert "binary_sensor.*_bypass_position" in patterns


# ---- start / stop ----


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_when_feature_enabled(self, automation_manager):
        automation_manager._automation_active = False
        with patch.object(
            ExtrasBaseAutomation,
            "start",
            new_callable=AsyncMock,
        ) as mock_super_start:
            await automation_manager.start()
            assert automation_manager._automation_active is True
            mock_super_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_when_feature_disabled(self, automation_manager):
        automation_manager._automation_active = False
        automation_manager.hass.data = {
            "ramses_extras": {"enabled_features": {"temp_control": False}}
        }
        with patch.object(
            ExtrasBaseAutomation,
            "start",
            new_callable=AsyncMock,
        ) as mock_super_start:
            await automation_manager.start()
            assert automation_manager._automation_active is False
            mock_super_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_clears_speed_and_zone_demands(self, automation_manager):
        automation_manager._mode["32:153289"] = "cooling"
        automation_manager._temp_demand_zones["32:153289"] = {"z1"}
        automation_manager._clear_speed_demand = AsyncMock()
        automation_manager._clear_all_zone_demands = AsyncMock()

        with patch.object(
            ExtrasBaseAutomation,
            "stop",
            new_callable=AsyncMock,
        ):
            await automation_manager.stop()

            assert automation_manager._automation_active is False
            automation_manager._clear_speed_demand.assert_called_once_with("32:153289")
            automation_manager._clear_all_zone_demands.assert_called_once_with(
                "32:153289"
            )


# ---- _on_homeassistant_started ----


class TestOnHomeassistantStarted:
    @pytest.mark.asyncio
    async def test_skipped_when_not_active(self, automation_manager):
        automation_manager._automation_active = False
        with patch.object(
            ExtrasBaseAutomation,
            "_on_homeassistant_started",
            new_callable=AsyncMock,
        ):
            await automation_manager._on_homeassistant_started(None)
            # Should not iterate candidate devices
            automation_manager.hass.states.async_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_when_feature_disabled(self, automation_manager):
        automation_manager._automation_active = True
        automation_manager.hass.data = {
            "ramses_extras": {"enabled_features": {"temp_control": False}}
        }
        with patch.object(
            ExtrasBaseAutomation,
            "_on_homeassistant_started",
            new_callable=AsyncMock,
        ):
            await automation_manager._on_homeassistant_started(None)

    @pytest.mark.asyncio
    async def test_evaluates_devices_on_startup(self, automation_manager):
        automation_manager._iter_candidate_device_ids = MagicMock(
            return_value=["32:153289"]
        )
        automation_manager._get_device_entity_states = AsyncMock(
            return_value=make_entity_states()
        )
        automation_manager._process_automation_logic = AsyncMock()

        with patch.object(
            ExtrasBaseAutomation,
            "_on_homeassistant_started",
            new_callable=AsyncMock,
        ):
            await automation_manager._on_homeassistant_started(None)

            automation_manager._process_automation_logic.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_device_on_value_error(self, automation_manager):
        automation_manager._iter_candidate_device_ids = MagicMock(
            return_value=["32:153289", "32:153290"]
        )
        automation_manager._get_device_entity_states = AsyncMock(
            side_effect=[ValueError("bad state"), make_entity_states()]
        )
        automation_manager._process_automation_logic = AsyncMock()

        with patch.object(
            ExtrasBaseAutomation,
            "_on_homeassistant_started",
            new_callable=AsyncMock,
        ):
            await automation_manager._on_homeassistant_started(None)

            # Only the second device should be processed
            automation_manager._process_automation_logic.assert_called_once()


# ---- _reconcile_startup_states ----


class TestReconcileStartupStates:
    @pytest.mark.asyncio
    async def test_skipped_when_not_active(self, automation_manager):
        automation_manager._automation_active = False
        await automation_manager._reconcile_startup_states()
        # No crash, no iteration

    @pytest.mark.asyncio
    async def test_skipped_when_feature_disabled(self, automation_manager):
        automation_manager._automation_active = True
        automation_manager.hass.data = {
            "ramses_extras": {"enabled_features": {"temp_control": False}}
        }
        await automation_manager._reconcile_startup_states()

    @pytest.mark.asyncio
    async def test_with_specific_device_id(self, automation_manager):
        automation_manager._get_device_entity_states = AsyncMock(
            return_value=make_entity_states()
        )
        automation_manager._process_automation_logic = AsyncMock()

        await automation_manager._reconcile_startup_states("32:153289")

        automation_manager._process_automation_logic.assert_called_once_with(
            "32:153289", make_entity_states()
        )

    @pytest.mark.asyncio
    async def test_with_all_devices(self, automation_manager):
        automation_manager._iter_candidate_device_ids = MagicMock(
            return_value=["32:153289", "32:153290"]
        )
        automation_manager._get_device_entity_states = AsyncMock(
            return_value=make_entity_states()
        )
        automation_manager._process_automation_logic = AsyncMock()

        await automation_manager._reconcile_startup_states()

        assert automation_manager._process_automation_logic.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_device_on_value_error(self, automation_manager):
        automation_manager._get_device_entity_states = AsyncMock(
            side_effect=ValueError("bad")
        )
        automation_manager._process_automation_logic = AsyncMock()

        await automation_manager._reconcile_startup_states("32:153289")

        automation_manager._process_automation_logic.assert_not_called()


# ---- _async_handle_state_change (bypass safety net) ----


class TestAsyncHandleStateChange:
    @pytest.mark.asyncio
    async def test_non_bypass_entity_passes_through(self, automation_manager):
        """Non-bypass entities should be passed to super."""
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "sensor.32_153289_indoor_temp",
                MagicMock(),
                MagicMock(),
            )
            mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_change_with_switch_off_passes_through(
        self, automation_manager
    ):
        """Bypass change when temp_control is off → pass to super."""
        automation_manager.hass.states.get = MagicMock(
            return_value=MagicMock(state="off")
        )
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                MagicMock(state="open"),
                MagicMock(state="closed"),
            )
            mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_change_within_command_window_passes_through(
        self, automation_manager
    ):
        """Bypass change within 10s of our own command → pass to super."""
        now = _time.time()
        automation_manager._last_bypass_command_time["32:153289"] = now
        automation_manager.hass.states.get = MagicMock(
            return_value=MagicMock(state="on")
        )
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                MagicMock(state="open"),
                MagicMock(state="closed"),
            )
            mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_external_bypass_change_turns_off_switch(self, automation_manager):
        """External bypass change while forcing bypass (cooling) → turn off switch."""
        automation_manager._mode["32:153289"] = "cooling"
        automation_manager._last_bypass_command_time["32:153289"] = 0.0
        automation_manager.hass.states.get = MagicMock(
            return_value=MagicMock(state="on")
        )
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                MagicMock(state="open"),
                MagicMock(state="closed"),
            )
            automation_manager.hass.services.async_call.assert_called_once_with(
                "switch",
                "turn_off",
                {"entity_id": "switch.temp_control_32_153289"},
            )
            mock_super.assert_not_called()

    @pytest.mark.asyncio
    async def test_external_bypass_change_in_idle_does_not_turn_off(
        self, automation_manager
    ):
        """Bypass change in idle mode (bypass auto) → NOT a manual override.

        In idle mode temp_control sent fan_bypass_auto, so the device is
        free to move the damper on its own.  These changes must not
        disable temp_control.
        """
        automation_manager._mode["32:153289"] = "idle"
        automation_manager._last_bypass_command_time["32:153289"] = 0.0
        automation_manager.hass.states.get = MagicMock(
            return_value=MagicMock(state="on")
        )
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                MagicMock(state="open"),
                MagicMock(state="closed"),
            )
            automation_manager.hass.services.async_call.assert_not_called()
            mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_change_no_old_state_passes_through(self, automation_manager):
        """Bypass change with old_state=None → pass to super."""
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                None,
                MagicMock(state="closed"),
            )
            mock_super.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_change_no_new_state_passes_through(self, automation_manager):
        with patch.object(
            ExtrasBaseAutomation,
            "_async_handle_state_change",
            new_callable=AsyncMock,
        ) as mock_super:
            await automation_manager._async_handle_state_change(
                "binary_sensor.32_153289_bypass_position",
                MagicMock(state="open"),
                None,
            )
            mock_super.assert_called_once()


# ---- _iter_candidate_device_ids ----


class TestIterCandidateDeviceIds:
    def test_from_switch_states(self, automation_manager):
        switch_state = MagicMock()
        switch_state.entity_id = "switch.temp_control_32_153289"
        automation_manager.hass.states.async_all = MagicMock(
            return_value=[switch_state]
        )
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [],
            }
        }
        result = automation_manager._iter_candidate_device_ids()
        assert "32:153289" in result

    def test_from_devices_list_dict(self, automation_manager):
        automation_manager.hass.states.async_all = MagicMock(return_value=[])
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [{"device_id": "32:153289", "type": "FAN"}],
            }
        }
        result = automation_manager._iter_candidate_device_ids()
        assert "32:153289" in result

    def test_from_devices_list_objects(self, automation_manager):
        device = MagicMock()
        device.device_id = "32:153290"
        automation_manager.hass.states.async_all = MagicMock(return_value=[])
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [device],
            }
        }
        result = automation_manager._iter_candidate_device_ids()
        assert "32:153290" in result

    def test_from_devices_list_object_with_id_attr(self, automation_manager):
        device = MagicMock()
        del device.device_id
        device.id = "32:153291"
        automation_manager.hass.states.async_all = MagicMock(return_value=[])
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [device],
            }
        }
        result = automation_manager._iter_candidate_device_ids()
        assert "32:153291" in result


# ---- _get_device_entity_states ----


class TestGetDeviceEntityStates:
    @pytest.mark.asyncio
    async def test_resolves_all_states(self, automation_manager):
        """Test that _get_device_entity_states resolves entity states."""
        from custom_components.ramses_extras.const import DOMAIN

        def mock_get(entity_id):
            states = {
                "switch.temp_control_32_153289": "on",
                "sensor.32_153289_indoor_temp": "22.0",
                "sensor.32_153289_outdoor_temp": "18.0",
                "sensor.32_153289_supply_temp": "18.0",
                "number.32_153289_param_75": "21.0",
                "sensor.32_153289_indoor_humidity": "50.0",
                "number.relative_humidity_minimum_32_153289": "40.0",
                "number.relative_humidity_maximum_32_153289": "60.0",
                "binary_sensor.dehumidifying_active_32_153289": "off",
                "binary_sensor.co2_active_32_153289": "off",
            }
            s = MagicMock()
            s.state = states.get(entity_id, "0")
            return s

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
                "co2_active": "binary_sensor.co2_active_32_153289",
            }
            result = await automation_manager._get_device_entity_states("32:153289")

            assert result["temp_control"] is True
            assert result["indoor_temp"] == 22.0
            assert result["outdoor_temp"] == 18.0
            assert result["comfort_temp"] == 21.0

    @pytest.mark.asyncio
    async def test_sensor_control_overlay_applied(self, automation_manager):
        """sensor_control mappings override default entity IDs."""

        def mock_get(entity_id):
            s = MagicMock()
            s.state = "22.0"
            return s

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {
                    "indoor_temperature": "sensor.external_indoor",
                    "outdoor_temperature": "sensor.external_outdoor",
                    "indoor_humidity": "sensor.external_humidity",
                },
                "sources": {},
                "area_sensors": [],
            }
        )

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
            }

            # Make switch state "on"
            def mock_get_switch(entity_id):
                s = MagicMock()
                if "switch" in entity_id:
                    s.state = "on"
                else:
                    s.state = "22.0"
                return s

            automation_manager.hass.states.get = mock_get_switch

            result = await automation_manager._get_device_entity_states("32:153289")

            # The overlay should have been applied
            assert result["temp_control"] is True

    @pytest.mark.asyncio
    async def test_raises_on_unavailable_state(self, automation_manager):
        """ValueError raised when a required entity is unavailable."""
        s = MagicMock()
        s.state = "unavailable"
        automation_manager.hass.states.get = MagicMock(return_value=s)
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
            }
            with pytest.raises(ValueError):
                await automation_manager._get_device_entity_states("32:153289")

    @pytest.mark.asyncio
    async def test_co2_active_missing_defaults_false(self, automation_manager):
        """When co2_active entity is missing, defaults to False."""

        def mock_get(entity_id):
            states = {
                "switch.temp_control_32_153289": "on",
                "sensor.32_153289_indoor_temp": "22.0",
                "sensor.32_153289_outdoor_temp": "18.0",
                "sensor.32_153289_supply_temp": "18.0",
                "number.32_153289_param_75": "21.0",
                "sensor.32_153289_indoor_humidity": "50.0",
                "number.relative_humidity_minimum_32_153289": "40.0",
                "number.relative_humidity_maximum_32_153289": "60.0",
                "binary_sensor.dehumidifying_active_32_153289": "off",
            }
            s = MagicMock()
            s.state = states.get(entity_id)
            return s

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
                # co2_active intentionally missing
            }
            result = await automation_manager._get_device_entity_states("32:153289")
            assert result["co2_active"] is False

    @pytest.mark.asyncio
    async def test_comfort_temp_entity_overlay(self, automation_manager):
        """Configured comfort_temp_entity overrides default param_75 mapping."""

        def mock_get(entity_id):
            states = {
                "switch.temp_control_32_153289": "on",
                "sensor.32_153289_indoor_temp": "22.0",
                "sensor.32_153289_outdoor_temp": "18.0",
                "sensor.32_153289_supply_temp": "18.0",
                # param_75 is unavailable (the problem we're solving)
                "number.32_153289_param_75": "unavailable",
                # external entity provides the comfort temp
                "input_number.my_comfort": "19.5",
                "sensor.32_153289_indoor_humidity": "50.0",
                "number.relative_humidity_minimum_32_153289": "40.0",
                "number.relative_humidity_maximum_32_153289": "60.0",
                "binary_sensor.dehumidifying_active_32_153289": "off",
                "binary_sensor.co2_active_32_153289": "off",
            }
            s = MagicMock()
            s.state = states.get(entity_id, "0")
            return s

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)

        # Configure comfort_temp_entity in settings
        automation_manager.config.get_settings = MagicMock(
            return_value=make_settings(comfort_temp_entity="input_number.my_comfort")
        )

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
                "co2_active": "binary_sensor.co2_active_32_153289",
            }
            result = await automation_manager._get_device_entity_states("32:153289")

            # Should use the external entity, not the unavailable param_75
            assert result["comfort_temp"] == 19.5

    @pytest.mark.asyncio
    async def test_comfort_temp_unavailable_raises_specific(self, automation_manager):
        """ComfortTempUnavailableError raised when comfort temp is unavailable
        and no fallback entity is configured."""
        from custom_components.ramses_extras.features.temp_control.automation import (
            ComfortTempUnavailableError,
        )

        def mock_get(entity_id):
            states = {
                "switch.temp_control_32_153289": "on",
                "sensor.32_153289_indoor_temp": "22.0",
                "sensor.32_153289_outdoor_temp": "18.0",
                "sensor.32_153289_supply_temp": "18.0",
                "number.32_153289_param_75": "unavailable",
                "sensor.32_153289_indoor_humidity": "50.0",
                "number.relative_humidity_minimum_32_153289": "40.0",
                "number.relative_humidity_maximum_32_153289": "60.0",
                "binary_sensor.dehumidifying_active_32_153289": "off",
                "binary_sensor.co2_active_32_153289": "off",
            }
            s = MagicMock()
            s.state = states.get(entity_id, "0")
            return s

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(return_value=None)
        # No comfort_temp_entity configured (default empty string)
        automation_manager.config.get_settings = MagicMock(
            return_value=make_settings(comfort_temp_entity="")
        )

        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "entity.core.get_feature_entity_mappings",
            new_callable=AsyncMock,
        ) as mock_mappings:
            mock_mappings.return_value = {
                "temp_control": "switch.temp_control_32_153289",
                "indoor_temp": "sensor.32_153289_indoor_temp",
                "outdoor_temp": "sensor.32_153289_outdoor_temp",
                "supply_temp": "sensor.32_153289_supply_temp",
                "comfort_temp": "number.32_153289_param_75",
                "indoor_rh": "sensor.32_153289_indoor_humidity",
                "min_rh": "number.relative_humidity_minimum_32_153289",
                "max_rh": "number.relative_humidity_maximum_32_153289",
                "dehumidifying_active": (
                    "binary_sensor.dehumidifying_active_32_153289"
                ),
                "co2_active": "binary_sensor.co2_active_32_153289",
            }
            with pytest.raises(ComfortTempUnavailableError):
                await automation_manager._get_device_entity_states("32:153289")

    @pytest.mark.asyncio
    async def test_set_waiting_for_comfort_temp_sets_status(self, automation_manager):
        """_set_waiting_for_comfort_temp sets status and active indicator."""
        automation_manager._set_active_indicator = MagicMock()
        automation_manager._set_status_sensor = MagicMock()

        automation_manager._set_waiting_for_comfort_temp("32:153289")

        automation_manager._set_active_indicator.assert_called_once()
        call_args = automation_manager._set_active_indicator.call_args
        assert call_args[0][0] == "32:153289"
        assert call_args[0][1] is False  # active=False

        automation_manager._set_status_sensor.assert_called_once()
        status_args = automation_manager._set_status_sensor.call_args
        assert status_args[0][0] == "32:153289"
        assert status_args[0][1] == "waiting_for_comfort_temp"


# ---- _process_automation_logic early return ----


class TestProcessAutomationLogicEarlyReturn:
    @pytest.mark.asyncio
    async def test_skipped_when_not_active(self, automation_manager):
        automation_manager._automation_active = False
        await automation_manager._process_automation_logic(
            "32:153289", make_entity_states()
        )
        assert "32:153289" not in automation_manager._mode


# ---- aggregate heating_retention branch ----


class TestAggregateHeatingRetention:
    @pytest.mark.asyncio
    async def test_aggregate_heating_retention_only(self, automation_manager):
        """When one area needs heating_retention and none need cooling."""
        area_results = [
            {
                "area_id": "bedroom",
                "zone_id": "z2",
                "area_temp": 18.0,
                "area_comfort": 21.0,
                "decision": "heating_retention",
                "reason": "too cold",
            }
        ]
        automation_manager._evaluate_areas = AsyncMock(return_value=area_results)
        automation_manager._publish_zone_demands = AsyncMock()
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": []}
        )

        states = make_entity_states()
        await automation_manager._process_automation_logic("32:153289", states)

        assert automation_manager._mode["32:153289"] == "heating_retention"


# ---- _clear_speed_demand exception ----


class TestClearSpeedDemandException:
    @pytest.mark.asyncio
    async def test_exception_swallowed(self, automation_manager):
        """_clear_speed_demand should not raise on arbiter error."""
        automation_manager.fan_speed_arbiter.async_clear_demand = AsyncMock(
            side_effect=RuntimeError("arbiter error")
        )
        # Should not raise
        await automation_manager._clear_speed_demand("32:153289")


# ---- _get_desired_speed_option ----


class TestGetDesiredSpeedOption:
    def test_from_select_entity(self, automation_manager):
        """When select entity has a valid state, use it."""
        automation_manager._get_desired_speed_option = None  # remove mock

        s = MagicMock()
        s.state = "medium"
        automation_manager.hass.states.get = MagicMock(return_value=s)
        automation_manager.config.get_settings = MagicMock(return_value=make_settings())

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        # Call the real method
        result = TempControlAutomationManager._get_desired_speed_option(
            automation_manager, "32:153289"
        )
        assert result == "medium"

    def test_falls_back_to_config_default(self, automation_manager):
        """When select entity has no state, use config default."""
        automation_manager._get_desired_speed_option = None

        automation_manager.hass.states.get = MagicMock(return_value=None)
        automation_manager.config.get_settings = MagicMock(
            return_value=make_settings(default_desired_speed="low")
        )

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        result = TempControlAutomationManager._get_desired_speed_option(
            automation_manager, "32:153289"
        )
        assert result == "low"

    def test_invalid_default_falls_back_to_high(self, automation_manager):
        automation_manager._get_desired_speed_option = None

        automation_manager.hass.states.get = MagicMock(return_value=None)
        automation_manager.config.get_settings = MagicMock(
            return_value=make_settings(default_desired_speed="invalid")
        )

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        result = TempControlAutomationManager._get_desired_speed_option(
            automation_manager, "32:153289"
        )
        assert result == "high"


# ---- _set_active_indicator / _set_status_sensor ----


class TestSetActiveIndicator:
    def test_with_entity(self, automation_manager):
        entity = MagicMock()
        entity.set_state = MagicMock()
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {
                    "binary_sensor.temp_control_active_32_153289": entity,
                },
            }
        }
        automation_manager._set_active_indicator = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        TempControlAutomationManager._set_active_indicator(
            automation_manager, "32:153289", True, {"mode": "cooling"}
        )
        entity.set_state.assert_called_once_with(True, {"mode": "cooling"})

    def test_entity_set_state_exception_falls_back(self, automation_manager):
        entity = MagicMock()
        call_count = [0]

        def set_state_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")
            # Second call (fallback) succeeds

        entity.set_state = MagicMock(side_effect=set_state_side_effect)
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {
                    "binary_sensor.temp_control_active_32_153289": entity,
                },
            }
        }
        automation_manager._set_active_indicator = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        # Should not raise; fallback call succeeds
        TempControlAutomationManager._set_active_indicator(
            automation_manager, "32:153289", True, {}
        )
        assert entity.set_state.call_count == 2

    def test_no_entity_does_nothing(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {},
            }
        }
        automation_manager._set_active_indicator = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        # Should not raise
        TempControlAutomationManager._set_active_indicator(
            automation_manager, "32:153289", True, {}
        )


class TestSetStatusSensor:
    def test_with_entity(self, automation_manager):
        entity = MagicMock()
        entity.set_status = MagicMock()
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {
                    "sensor.temp_control_status_32_153289": entity,
                },
            }
        }
        automation_manager._set_status_sensor = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        TempControlAutomationManager._set_status_sensor(
            automation_manager, "32:153289", "cooling", {"mode": "cooling"}
        )
        entity.set_status.assert_called_once_with("cooling", {"mode": "cooling"})

    def test_set_status_exception_falls_back(self, automation_manager):
        entity = MagicMock()
        entity.set_status = MagicMock(side_effect=RuntimeError("boom"))
        entity.set_native_value = MagicMock()
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {
                    "sensor.temp_control_status_32_153289": entity,
                },
            }
        }
        automation_manager._set_status_sensor = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        TempControlAutomationManager._set_status_sensor(
            automation_manager, "32:153289", "idle", {}
        )
        entity.set_native_value.assert_called_once_with("idle")

    def test_no_entity_does_nothing(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "entities": {},
            }
        }
        automation_manager._set_status_sensor = None

        from custom_components.ramses_extras.features.temp_control.automation import (
            TempControlAutomationManager,
        )

        TempControlAutomationManager._set_status_sensor(
            automation_manager, "32:153289", "idle", {}
        )


# ---- _is_sensor_control_enabled ----


class TestIsSensorControlEnabled:
    def test_enabled_dict(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "config_entry": MagicMock(
                    data={"enabled_features": {"sensor_control": True}},
                    options={},
                ),
            }
        }
        assert automation_manager._is_sensor_control_enabled() is True

    def test_enabled_via_options(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "config_entry": MagicMock(
                    data={},
                    options={"enabled_features": {"sensor_control": True}},
                ),
            }
        }
        assert automation_manager._is_sensor_control_enabled() is True

    def test_enabled_list(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "config_entry": MagicMock(
                    data={"enabled_features": ["sensor_control"]},
                    options={},
                ),
            }
        }
        assert automation_manager._is_sensor_control_enabled() is True

    def test_disabled(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "config_entry": MagicMock(
                    data={"enabled_features": {}},
                    options={},
                ),
            }
        }
        assert automation_manager._is_sensor_control_enabled() is False

    def test_no_config_entry(self, automation_manager):
        automation_manager.hass.data = {"ramses_extras": {}}
        assert automation_manager._is_sensor_control_enabled() is False

    def test_exception_returns_false(self, automation_manager):
        automation_manager.hass.data = MagicMock()
        automation_manager.hass.data.get = MagicMock(side_effect=RuntimeError("boom"))
        assert automation_manager._is_sensor_control_enabled() is False

    def test_enabled_features_neither_dict_nor_list(self, automation_manager):
        """When enabled_features is a string or other type, return False."""
        automation_manager.hass.data = {
            "ramses_extras": {
                "config_entry": MagicMock(
                    data={"enabled_features": "not_a_dict_or_list"},
                    options={},
                ),
            }
        }
        assert automation_manager._is_sensor_control_enabled() is False


# ---- _get_device_type_for_sensor_control ----


class TestGetDeviceTypeForSensorControl:
    def test_dict_device_with_type(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [{"device_id": "32:153289", "type": "FAN"}],
            }
        }
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result == "FAN"

    def test_dict_device_no_type(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [{"device_id": "32:153289"}],
            }
        }
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result is None

    def test_object_device_with_type(self, automation_manager):
        device = MagicMock()
        device._SLUG = "FAN"
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [device],
            }
        }
        # When device is a MagicMock, raw_id = device (not a string)
        # so it goes through the attr resolution path
        device.id = "32:153289"
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result == "FAN"

    def test_object_device_string_id(self, automation_manager):
        device = MagicMock()
        device._SLUG = "FAN"
        # Make device_id a plain string
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [device],
            }
        }
        # Patch isinstance check: device is dict → False
        # raw_id = device (object), not a string → attr resolution
        device.id = "32:153289"
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result == "FAN"

    def test_no_matching_device(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [],
            }
        }
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result is None

    def test_device_with_none_id_skipped(self, automation_manager):
        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [{"device_id": None, "type": "FAN"}],
            }
        }
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result is None

    def test_object_device_falls_back_to_str(self, automation_manager):
        """When raw_id is an object with no id attrs, str() is used."""
        raw_obj = MagicMock()
        del raw_obj.id
        del raw_obj.device_id
        del raw_obj._id
        del raw_obj.name
        raw_obj.__str__ = MagicMock(return_value="32:153289")
        raw_obj._SLUG = "FAN"

        automation_manager.hass.data = {
            "ramses_extras": {
                "enabled_features": {"temp_control": True},
                "devices": [raw_obj],
            }
        }
        result = automation_manager._get_device_type_for_sensor_control("32:153289")
        assert result == "FAN"


# ---- _get_sensor_control_context ----


class TestGetSensorControlContext:
    @pytest.mark.asyncio
    async def test_returns_none_when_sensor_control_disabled(self, automation_manager):
        automation_manager._is_sensor_control_enabled = MagicMock(return_value=False)
        result = await automation_manager._get_sensor_control_context("32:153289")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_context_when_enabled(self, automation_manager):
        automation_manager._is_sensor_control_enabled = MagicMock(return_value=True)
        automation_manager._get_device_type_for_sensor_control = MagicMock(
            return_value="FAN"
        )

        mock_resolver = MagicMock()
        mock_resolver.resolve_entity_mappings = AsyncMock(
            return_value={
                "mappings": {"indoor_temperature": "sensor.ext"},
                "sources": {},
                "area_sensors": [],
            }
        )

        with patch(
            "custom_components.ramses_extras.features."
            "sensor_control.resolver.SensorControlResolver",
            return_value=mock_resolver,
        ):
            result = await automation_manager._get_sensor_control_context("32:153289")

            assert result is not None
            assert result["mappings"]["indoor_temperature"] == "sensor.ext"
            assert result["area_sensors"] == []

    @pytest.mark.asyncio
    async def test_defaults_to_fan_when_no_type(self, automation_manager):
        automation_manager._is_sensor_control_enabled = MagicMock(return_value=True)
        automation_manager._get_device_type_for_sensor_control = MagicMock(
            return_value=None
        )

        mock_resolver = MagicMock()
        mock_resolver.resolve_entity_mappings = AsyncMock(
            return_value={"mappings": {}, "sources": {}, "area_sensors": []}
        )

        with patch(
            "custom_components.ramses_extras.features."
            "sensor_control.resolver.SensorControlResolver",
            return_value=mock_resolver,
        ):
            await automation_manager._get_sensor_control_context("32:153289")
            # Should have been called with "FAN" as device_type
            call_args = mock_resolver.resolve_entity_mappings.call_args
            assert call_args.args[1] == "FAN"

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, automation_manager):
        automation_manager._is_sensor_control_enabled = MagicMock(return_value=True)
        automation_manager._get_device_type_for_sensor_control = MagicMock(
            side_effect=RuntimeError("boom")
        )

        result = await automation_manager._get_sensor_control_context("32:153289")
        assert result is None


# ---- _evaluate_areas edge cases ----


class TestEvaluateAreasEdgeCases:
    @pytest.mark.asyncio
    async def test_area_sensors_not_list(self, automation_manager):
        """When area_sensors is not a list, return []."""
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": "not_a_list"}
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_area_not_dict_skipped(self, automation_manager):
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={"mappings": {}, "area_sensors": ["not_a_dict"]}
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_area_no_temp_entity_skipped(self, automation_manager):
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [{"area_id": "x", "enabled": True}],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_area_temp_unavailable_skipped(self, automation_manager):
        s = MagicMock()
        s.state = "unavailable"
        automation_manager.hass.states.get = MagicMock(return_value=s)
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x",
                    }
                ],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_area_temp_non_float_skipped(self, automation_manager):
        def mock_get(eid):
            if eid == "sensor.x":
                s = MagicMock()
                s.state = "not_a_number"
                return s
            if eid == "number.32_153289_param_75":
                s = MagicMock()
                s.state = "21.0"
                return s
            return None

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x",
                    }
                ],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_comfort_entity_non_float_falls_back(self, automation_manager):
        """When comfort_temperature_entity has non-float state,
        fall back to global comfort."""

        def mock_get(eid):
            if eid == "sensor.x_temp":
                s = MagicMock()
                s.state = "24.0"
                return s
            if eid == "input_number.x_comfort":
                s = MagicMock()
                s.state = "not_a_number"
                return s
            if eid == "number.32_153289_param_75":
                s = MagicMock()
                s.state = "21.0"
                return s
            return None

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x_temp",
                        "comfort_temperature_entity": "input_number.x_comfort",
                    }
                ],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert len(result) == 1
        assert result[0]["area_comfort"] == 21.0

    @pytest.mark.asyncio
    async def test_no_comfort_available_skips_area(self, automation_manager):
        """When neither area comfort nor global comfort is available."""
        automation_manager.hass.states.get = MagicMock(return_value=None)
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x",
                    }
                ],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_global_comfort_non_float_returns_none(self, automation_manager):
        """When global comfort entity has a non-float state,
        it should be treated as None (not crash)."""

        def mock_get(eid):
            if eid == "sensor.x_temp":
                s = MagicMock()
                s.state = "24.0"
                return s
            if eid == "number.32_153289_param_75":
                s = MagicMock()
                s.state = "bad_value"
                return s
            return None

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x_temp",
                    }
                ],
            }
        )
        # Should not crash; area skipped because comfort is None
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_global_comfort_type_error_returns_none(self, automation_manager):
        """When global comfort entity state causes TypeError,
        it should be treated as None."""

        def mock_get(eid):
            if eid == "sensor.x_temp":
                s = MagicMock()
                s.state = "24.0"
                return s
            if eid == "number.32_153289_param_75":
                s = MagicMock()
                # float(None) raises TypeError
                s.state = None
                return s
            return None

        automation_manager.hass.states.get = mock_get
        automation_manager._get_sensor_control_context = AsyncMock(
            return_value={
                "mappings": {},
                "area_sensors": [
                    {
                        "area_id": "x",
                        "enabled": True,
                        "temperature_entity": "sensor.x_temp",
                    }
                ],
            }
        )
        result = await automation_manager._evaluate_areas(
            "32:153289", make_settings(), 18.0
        )
        assert result == []


# ---- zone demand registry missing ----


class TestZoneDemandRegistryMissing:
    @pytest.mark.asyncio
    async def test_publish_no_registry(self, automation_manager):
        """_publish_zone_demands does nothing when registry is None."""
        automation_manager._zone_demand_registry = None
        await automation_manager._publish_zone_demands(
            "32:153289",
            [{"zone_id": "z1", "decision": "cooling"}],
            "cooling",
        )
        # No crash

    @pytest.mark.asyncio
    async def test_clear_all_no_registry(self, automation_manager):
        """_clear_all_zone_demands does nothing when registry is None."""
        automation_manager._zone_demand_registry = None
        automation_manager._temp_demand_zones["32:153289"] = {"z1"}
        await automation_manager._clear_all_zone_demands("32:153289")
        # No crash; zones dict not popped because registry is None
        assert "32:153289" in automation_manager._temp_demand_zones
