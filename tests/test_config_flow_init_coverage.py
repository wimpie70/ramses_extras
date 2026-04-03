"""Tests for config_flow init step and edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
)
from custom_components.ramses_extras.const import DOMAIN


class TestConfigFlowUserStepVariations:
    """Test user step with various inputs."""

    @pytest.fixture
    def hass(self):
        """Mock hass."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])
        return hass

    @pytest.fixture
    def config_flow(self, hass):
        """Create config flow instance."""
        flow = RamsesExtrasConfigFlow()
        flow.hass = hass
        return flow

    @pytest.mark.asyncio
    async def test_user_step_creates_entry_with_defaults(self, config_flow, hass):
        """Test user step creates entry with default values."""
        hass.config_entries.async_entries.return_value = []

        result = await config_flow.async_step_user(user_input={})
        assert result["type"] == "create_entry"
        assert result["title"] == "Ramses Extras"
        assert "enabled_features" in result["data"]

    @pytest.mark.asyncio
    async def test_user_step_with_none_input(self, config_flow, hass):
        """Test user step with None input."""
        hass.config_entries.async_entries.return_value = []

        result = await config_flow.async_step_user(user_input=None)
        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_user_step_existing_entries_abort(self, config_flow, hass):
        """Test user step aborts when entries exist."""
        hass.config_entries.async_entries.return_value = [MagicMock()]

        result = await config_flow.async_step_user()
        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"


class TestOptionsFlowInitVariations:
    """Test options flow init with variations."""

    @pytest.fixture
    def entry(self):
        """Mock config entry."""
        entry = MagicMock()
        entry.options = {}
        entry.data = {"enabled_features": {"default": True}}
        entry.entry_id = "test_entry"
        return entry

    @pytest.fixture
    def options_flow(self, entry):
        """Create options flow instance."""
        flow = RamsesExtrasOptionsFlowHandler(entry)
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.bus = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_init_calls_main_menu(self, options_flow):
        """Test init step calls main_menu."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ) as mock_menu:
            result = await options_flow.async_step_init()
            mock_menu.assert_called_once()
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_main_menu_shows_form(self, options_flow):
        """Test main_menu step shows menu form."""
        result = await options_flow.async_step_main_menu()
        assert result["type"] == "menu"
        assert (
            "main_menu" in str(result.get("step_id", "")).lower()
            or result["type"] == "menu"
        )


class TestOptionsFlowAdvancedSettings:
    """Test advanced settings step."""

    @pytest.fixture
    def entry(self):
        """Mock config entry."""
        entry = MagicMock()
        entry.options = {"log_level": "info", "frontend_log_level": "info"}
        entry.data = {"enabled_features": {"default": True}}
        entry.entry_id = "test_entry"
        return entry

    @pytest.fixture
    def options_flow(self, entry):
        """Create options flow instance."""
        flow = RamsesExtrasOptionsFlowHandler(entry)
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.bus = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_advanced_settings_shows_form(self, options_flow):
        """Test advanced_settings shows form with no input."""
        result = await options_flow.async_step_advanced_settings(user_input=None)
        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_advanced_settings_back_action(self, options_flow):
        """Test advanced_settings with back action."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={"action": "back"}
            )
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_advanced_settings_save_updates_options(self, options_flow):
        """Test advanced_settings save updates entry options."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={
                    "action": "save",
                    "log_level": "debug",
                    "frontend_log_level": "debug",
                }
            )
            assert result["type"] == "menu"
            options_flow.hass.config_entries.async_update_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_advanced_settings_cancel_action(self, options_flow):
        """Test advanced_settings with cancel action."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={"action": "cancel"}
            )
            assert result["type"] == "menu"


class TestOptionsFlowRefresh:
    """Test _refresh_config_entry method."""

    @pytest.fixture
    def entry(self):
        """Mock config entry."""
        entry = MagicMock()
        entry.options = {}
        entry.data = {"enabled_features": {"default": True}}
        entry.entry_id = "test_entry"
        return entry

    @pytest.fixture
    def options_flow(self, entry):
        """Create options flow instance."""
        flow = RamsesExtrasOptionsFlowHandler(entry)
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        return flow

    def test_refresh_with_none_entry_id(self, options_flow):
        """Test refresh when entry_id is None."""
        options_flow._config_entry.entry_id = None
        # Should not crash
        options_flow._refresh_config_entry(options_flow.hass)

    def test_refresh_updates_config_entry(self, options_flow):
        """Test refresh updates the config entry reference."""
        latest_entry = MagicMock()
        options_flow.hass.config_entries.async_get_entry.return_value = latest_entry

        options_flow._refresh_config_entry(options_flow.hass)
        # Should update _config_entry to latest
        assert options_flow._config_entry == latest_entry
