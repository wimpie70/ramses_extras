"""Tests for Hello World automation manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
                entity_states = {"hello_world_switch": True}

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
                entity_states = {"hello_world_switch": False}

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
