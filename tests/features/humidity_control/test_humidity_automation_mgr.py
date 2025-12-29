"""Tests for Humidity Control Automation Manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.humidity_control.automation import (
    HumidityAutomationManager,
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
        self.hass.states = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.options = {}
        self.config_entry.data = {}

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

    async def test_process_automation_logic_switch_off(self):
        """Test processing automation logic when switch is off."""
        device_id = "32_123456"
        entity_states = {"dehumidify": False}

        with patch.object(self.manager, "_set_indicator_off") as mock_off:
            await self.manager._process_automation_logic(device_id, entity_states)
            mock_off.assert_called_once_with(device_id)

    @patch(
        "custom_components.ramses_extras.features.humidity_control.automation.entity_registry"
    )
    async def test_validate_device_entities(self, mock_registry):
        """Test validating device entities."""
        device_id = "32_123456"
        mock_reg = MagicMock()
        mock_registry.async_get.return_value = mock_reg

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

    def test_singularize_entity_type(self):
        """Test singularizing entity types."""
        assert self.manager._singularize_entity_type("sensor") == "sensor"
        assert self.manager._singularize_entity_type("switch") == "switch"
        assert self.manager._singularize_entity_type("devices") == "device"
        assert self.manager._singularize_entity_type("unknown") == "unknown"

    def test_generate_entity_patterns(self):
        """Test generating entity patterns."""
        patterns = self.manager._generate_entity_patterns()
        assert "sensor.indoor_absolute_humidity_*" in patterns
        assert "switch.dehumidify_*" in patterns
        assert "sensor.*_indoor_humidity" in patterns

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

        with patch.object(
            self.manager, "_get_sensor_control_context", new_callable=AsyncMock
        ) as mock_ctx:
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
        mock_entity.set_state.assert_called_once_with(False)

    async def test_activate_dehumidification(self):
        """Test activating dehumidification."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}

        # Mock success
        mock_result = MagicMock()
        mock_result.success = True
        self.manager.ramses_commands.send_command = AsyncMock(return_value=mock_result)
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

        # Command failure
        self.manager.ramses_commands.send_command = AsyncMock(
            return_value=MagicMock(success=False)
        )
        self.manager.services.async_deactivate_dehumidification = AsyncMock()

        await self.manager._activate_dehumidification(device_id, decision)
        assert self.manager._dehumidify_active is False
        self.manager.services.async_deactivate_dehumidification.assert_called_once_with(
            device_id
        )

        # Exception path
        self.manager.ramses_commands.send_command.side_effect = Exception("Test error")
        await self.manager._activate_dehumidification(device_id, decision)
        # Should log and continue

    async def test_set_fan_low_and_binary_off(self):
        """Test _set_fan_low_and_binary_off."""
        device_id = "32_123456"
        decision = {"reasoning": ["Test"]}

        # Success
        self.manager.ramses_commands.send_command = AsyncMock(
            return_value=MagicMock(success=True)
        )
        await self.manager._set_fan_low_and_binary_off(device_id, decision)
        assert self.manager._dehumidify_active is False

        # Failure
        self.manager.ramses_commands.send_command = AsyncMock(
            return_value=MagicMock(success=False)
        )
        await self.manager._set_fan_low_and_binary_off(device_id, decision)
        # Should log and continue

        # Exception
        self.manager.ramses_commands.send_command.side_effect = Exception("Test error")
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
        self.manager.ramses_commands.send_command = AsyncMock(
            return_value=MagicMock(success=True)
        )

        await self.manager._stop_dehumidification_without_switch_change(device_id)
        assert self.manager._dehumidify_active is False
        self.manager.services.async_deactivate_dehumidification.assert_called_once_with(
            device_id
        )

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
