"""Tests for Hello World automation manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.hello_world.automation import (
    HelloWorldAutomationManager,
    create_hello_world_automation,
)


class TestHelloWorldAutomationManager:
    """Test cases for HelloWorldAutomationManager."""

    @pytest.fixture
    def hass(self):
        """Mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def config_entry(self):
        """Mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.data = {"enabled_features": {"hello_world": True}}
        entry.options = {}
        return entry

    def test_create_hello_world_automation(self, hass, config_entry):
        """Test creating Hello World automation instance."""
        result = create_hello_world_automation(hass, config_entry)

        assert isinstance(result, HelloWorldAutomationManager)
        assert result.hass == hass
        assert result.config_entry == config_entry
        assert result.feature_id == "hello_world"

    @pytest.mark.asyncio
    async def test_start_automation_enabled(self, hass, config_entry):
        """Test starting automation when feature is enabled."""
        # Mock hass.data
        hass.data = {"ramses_extras": {"enabled_features": {"hello_world": True}}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        # Mock super().start()
        with patch.object(
            automation.__class__.__bases__[0],
            "start",
            new_callable=AsyncMock,
        ) as mock_super_start:
            await automation.start()

            assert automation._automation_active is True
            mock_super_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_automation_disabled(self, hass, config_entry):
        """Test starting automation when feature is disabled."""
        # Mock hass.data
        hass.data = {"ramses_extras": {"enabled_features": {"hello_world": False}}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        # Mock super().start() - should not be called
        with patch.object(
            automation.__class__.__bases__[0],
            "start",
            new_callable=AsyncMock,
        ) as mock_super_start:
            await automation.start()

            assert automation._automation_active is False
            mock_super_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_automation(self, hass, config_entry):
        """Test stopping automation."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        # Mock super().stop()
        with patch.object(
            automation.__class__.__bases__[0],
            "stop",
            new_callable=AsyncMock,
        ) as mock_super_stop:
            await automation.stop()

            assert automation._automation_active is False
            mock_super_stop.assert_called_once()

    def test_generate_entity_patterns(self, hass, config_entry):
        """Test generating entity patterns."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        patterns = automation._generate_entity_patterns()

        assert isinstance(patterns, list)
        assert "switch.hello_world_switch_*" in patterns

    def test_is_feature_enabled_true(self, hass, config_entry):
        """Test feature enabled check returns True."""
        hass.data = {"ramses_extras": {"enabled_features": {"hello_world": True}}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        assert automation._is_feature_enabled() is True

    def test_is_feature_enabled_false(self, hass, config_entry):
        """Test feature enabled check returns False."""
        hass.data = {"ramses_extras": {"enabled_features": {"hello_world": False}}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        assert automation._is_feature_enabled() is False

    @pytest.mark.asyncio
    async def test_process_automation_logic_switch_on(self, hass, config_entry):
        """Test automation logic when switch is on."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        # Mock _is_feature_enabled
        with patch.object(automation, "_is_feature_enabled", return_value=True):
            # Mock _trigger_binary_sensor_update
            with patch.object(
                automation,
                "_trigger_binary_sensor_update",
                new_callable=AsyncMock,
            ) as mock_trigger:
                entity_states = {"switch_state": True}

                await automation._process_automation_logic("test_device", entity_states)

                mock_trigger.assert_called_once_with("test_device", True)

    @pytest.mark.asyncio
    async def test_process_automation_logic_switch_off(self, hass, config_entry):
        """Test automation logic when switch is off."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        # Mock _is_feature_enabled
        with patch.object(automation, "_is_feature_enabled", return_value=True):
            # Mock _trigger_binary_sensor_update
            with patch.object(
                automation,
                "_trigger_binary_sensor_update",
                new_callable=AsyncMock,
            ) as mock_trigger:
                entity_states = {"switch_state": False}

                await automation._process_automation_logic("test_device", entity_states)

                mock_trigger.assert_called_once_with("test_device", False)

    @pytest.mark.asyncio
    async def test_ignore_non_hello_world_switch(self, hass, config_entry):
        """Test that non-Hello World switch changes are ignored."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        # Mock _is_feature_enabled
        with patch.object(automation, "_is_feature_enabled", return_value=True):
            # Mock super()._async_handle_state_change - should not be called
            with patch.object(
                automation.__class__.__bases__[0],
                "_async_handle_state_change",
                new_callable=AsyncMock,
            ) as mock_super_handle:
                await automation._async_handle_state_change(
                    "switch.other_switch_123", None, None
                )

                mock_super_handle.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_hello_world_switch(self, hass, config_entry):
        """Test that Hello World switch changes are processed."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        # Mock _is_feature_enabled
        with patch.object(automation, "_is_feature_enabled", return_value=True):
            # Mock super()._async_handle_state_change
            with patch.object(
                automation.__class__.__bases__[0],
                "_async_handle_state_change",
                new_callable=AsyncMock,
            ) as mock_super_handle:
                await automation._async_handle_state_change(
                    "switch.hello_world_switch_123", None, None
                )

                mock_super_handle.assert_called_once()

    def test_is_automation_active(self, hass, config_entry):
        """Test is_automation_active method."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        # Initially False
        assert automation.is_automation_active() is False

        # After setting active
        automation._automation_active = True
        assert automation.is_automation_active() is True

    def test_is_feature_enabled_fallback_to_config_entry(self, hass, config_entry):
        """Test fallback to config_entry when hass.data has no dict."""
        # hass.data.get(DOMAIN, {}) returns {} when DOMAIN not present
        hass.data = {DOMAIN: {}}

        config_entry.options = {"enabled_features": {"hello_world": True}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        assert automation._is_feature_enabled() is True

    def test_is_feature_enabled_fallback_to_config_entry_data(self, hass, config_entry):
        """Test feature enabled check falls back to config_entry.data."""
        hass.data = {DOMAIN: {}}

        config_entry.options = {}
        config_entry.data = {"enabled_features": {"hello_world": True}}

        automation = HelloWorldAutomationManager(hass, config_entry)

        assert automation._is_feature_enabled() is True

    def test_is_feature_enabled_exception_returns_false(self, hass, config_entry):
        """Test feature enabled check returns False on exception."""
        hass.data = MagicMock()
        hass.data.get.side_effect = Exception("test error")

        automation = HelloWorldAutomationManager(hass, config_entry)

        assert automation._is_feature_enabled() is False

    @pytest.mark.asyncio
    async def test_process_automation_logic_not_active(self, hass, config_entry):
        """Test automation logic does nothing when not active."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = False

        with patch.object(
            automation, "_trigger_binary_sensor_update", new_callable=AsyncMock
        ) as mock_trigger:
            await automation._process_automation_logic(
                "test_device", {"switch_state": True}
            )

            mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_automation_logic_feature_disabled(self, hass, config_entry):
        """Test automation logic does nothing when feature is disabled."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        with (
            patch.object(automation, "_is_feature_enabled", return_value=False),
            patch.object(
                automation, "_trigger_binary_sensor_update", new_callable=AsyncMock
            ) as mock_trigger,
        ):
            await automation._process_automation_logic(
                "test_device", {"switch_state": True}
            )

            mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_automation_logic_exception(self, hass, config_entry, caplog):
        """Test automation logic handles exceptions gracefully."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        with patch.object(automation, "_is_feature_enabled", return_value=True):
            # Pass entity_states that will cause an exception
            with patch.object(
                automation, "_trigger_binary_sensor_update", new_callable=AsyncMock
            ) as mock_trigger:
                mock_trigger.side_effect = Exception("trigger failed")

                await automation._process_automation_logic(
                    "test_device", {"switch_state": True}
                )

                assert "Automation logic error for device test_device" in caplog.text

    @pytest.mark.asyncio
    async def test_async_handle_state_change_feature_disabled(
        self, hass, config_entry, caplog
    ):
        """Test state change handler ignores when feature is disabled."""
        import logging

        caplog.set_level(logging.DEBUG)

        automation = HelloWorldAutomationManager(hass, config_entry)

        with patch.object(automation, "_is_feature_enabled", return_value=False):
            with patch.object(
                automation.__class__.__bases__[0],
                "_async_handle_state_change",
                new_callable=AsyncMock,
            ) as mock_super_handle:
                await automation._async_handle_state_change(
                    "switch.hello_world_switch_123", None, None
                )

                mock_super_handle.assert_not_called()
                assert "Feature hello_world disabled" in caplog.text

    @pytest.mark.asyncio
    async def test_trigger_binary_sensor_update_success(self, hass, config_entry):
        """Test triggering binary sensor update successfully."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        with (
            patch(
                "custom_components.ramses_extras.features.hello_world.automation.EntityHelpers"
            ) as mock_helpers,
            patch.object(
                automation, "set_binary_sensor_state", new_callable=AsyncMock
            ) as mock_set_state,
        ):
            mock_helpers.generate_entity_name_from_template.return_value = (
                "binary_sensor.hello_world_status_test"
            )
            mock_set_state.return_value = True

            await automation._trigger_binary_sensor_update("test_device", True)

            mock_set_state.assert_called_once_with(
                "binary_sensor.hello_world_status_test", True
            )

    @pytest.mark.asyncio
    async def test_trigger_binary_sensor_update_failure(
        self, hass, config_entry, caplog
    ):
        """Test triggering binary sensor update when set_binary_sensor_state fails."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        with (
            patch(
                "custom_components.ramses_extras.features.hello_world.automation.EntityHelpers"
            ) as mock_helpers,
            patch.object(
                automation, "set_binary_sensor_state", new_callable=AsyncMock
            ) as mock_set_state,
        ):
            mock_helpers.generate_entity_name_from_template.return_value = (
                "binary_sensor.hello_world_status_test"
            )
            mock_set_state.return_value = False

            await automation._trigger_binary_sensor_update("test_device", True)

            assert "Failed to update binary sensor" in caplog.text

    @pytest.mark.asyncio
    async def test_trigger_binary_sensor_update_exception(
        self, hass, config_entry, caplog
    ):
        """Test triggering binary sensor update handles exceptions."""
        automation = HelloWorldAutomationManager(hass, config_entry)

        with patch(
            "custom_components.ramses_extras.features.hello_world.automation.EntityHelpers"
        ) as mock_helpers:
            mock_helpers.generate_entity_name_from_template.side_effect = Exception(
                "entity error"
            )

            await automation._trigger_binary_sensor_update("test_device", True)

            assert "Failed to trigger binary sensor update" in caplog.text

    @pytest.mark.asyncio
    async def test_async_trigger_binary_sensor_not_active(
        self, hass, config_entry, caplog
    ):
        """Test manual trigger when automation is not active."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = False

        result = await automation.async_trigger_binary_sensor("test_device", True)

        assert result is False
        assert "Automation not active" in caplog.text

    @pytest.mark.asyncio
    async def test_async_trigger_binary_sensor_success(self, hass, config_entry):
        """Test manual trigger when automation is active."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        with patch.object(
            automation, "_trigger_binary_sensor_update", new_callable=AsyncMock
        ) as mock_trigger:
            result = await automation.async_trigger_binary_sensor("test_device", True)

            assert result is True
            mock_trigger.assert_called_once_with("test_device", True)

    @pytest.mark.asyncio
    async def test_async_trigger_binary_sensor_exception(
        self, hass, config_entry, caplog
    ):
        """Test manual trigger handles exceptions."""
        automation = HelloWorldAutomationManager(hass, config_entry)
        automation._automation_active = True

        with patch.object(
            automation, "_trigger_binary_sensor_update", new_callable=AsyncMock
        ) as mock_trigger:
            mock_trigger.side_effect = Exception("trigger failed")

            result = await automation.async_trigger_binary_sensor("test_device", True)

            assert result is False
            assert "Failed to manually trigger binary sensor" in caplog.text
