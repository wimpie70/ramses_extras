"""Tests for config_flow error paths and edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
    _get_feature_details_from_module,
    _manage_cards_config_flow,
)


class TestRamsesExtrasConfigFlowUserStep:
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
    async def test_user_step_empty_input(self, config_flow, hass):
        """Test user step with empty input."""
        hass.config_entries.async_entries.return_value = []

        result = await config_flow.async_step_user(user_input={})
        # Should create entry with default values
        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_user_step_none_input(self, config_flow, hass):
        """Test user step with None input."""
        hass.config_entries.async_entries.return_value = []

        result = await config_flow.async_step_user(user_input=None)
        assert result["type"] == "create_entry"


class TestRamsesExtrasOptionsFlowAdvanced:
    """Test options flow advanced settings."""

    @pytest.fixture
    def entry(self):
        """Mock config entry."""
        entry = MagicMock()
        entry.options = {"log_level": "info"}
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
    async def test_advanced_settings_cancel(self, options_flow):
        """Test advanced settings with cancel action."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={"action": "cancel"}
            )
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_advanced_settings_invalid_action(self, options_flow):
        """Test advanced settings with invalid action."""
        options_flow.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={"action": "invalid"}
            )
            # Should still return to main menu
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_advanced_settings_no_user_input(self, options_flow):
        """Test advanced settings with no user_input."""
        result = await options_flow.async_step_advanced_settings(user_input=None)
        # Should show form
        assert result["type"] == "form"


class TestGetFeatureDetailsFromModule:
    """Test _get_feature_details_from_module."""

    def test_feature_with_no_details(self):
        """Test feature with minimal details."""
        result = _get_feature_details_from_module("default")
        # Should return at least supported_device_types
        assert "supported_device_types" in result

    def test_nonexistent_feature_returns_empty(self):
        """Test non-existent feature returns empty dict."""
        result = _get_feature_details_from_module("nonexistent_feature_12345")
        assert result == {}


class TestManageCardsConfigFlow:
    """Test _manage_cards_config_flow."""

    @pytest.mark.asyncio
    async def test_manage_cards_no_features(self):
        """Test managing cards with no features enabled."""
        hass = MagicMock()
        hass.config.path.return_value = "/mock/path"

        enabled_features = {}
        await _manage_cards_config_flow(hass, enabled_features)
        # Should not crash

    @pytest.mark.asyncio
    async def test_manage_cards_all_disabled(self):
        """Test managing cards with all features disabled."""
        hass = MagicMock()
        hass.config.path.return_value = "/mock/path"

        enabled_features = {"default": False, "fan_control": False}
        await _manage_cards_config_flow(hass, enabled_features)
        # Should handle gracefully

    @pytest.mark.asyncio
    async def test_manage_cards_mixed(self):
        """Test managing cards with mixed enabled/disabled."""
        hass = MagicMock()
        hass.config.path.return_value = "/mock/path"

        enabled_features = {"default": True, "fan_control": False}
        await _manage_cards_config_flow(hass, enabled_features)
        # Should handle mixed states


class TestOptionsFlowHandlerRefresh:
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

    def test_refresh_no_entry_id(self, options_flow):
        """Test refresh when entry has no ID."""
        options_flow._config_entry.entry_id = None
        # Should not crash
        options_flow._refresh_config_entry(options_flow.hass)
