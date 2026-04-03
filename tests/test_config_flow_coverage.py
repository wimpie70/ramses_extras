"""Tests for config_flow to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
    _copy_card_files_config_flow,
    _get_feature_details_from_module,
    _install_card_config_flow,
    _manage_cards_config_flow,
    _remove_card_config_flow,
)
from custom_components.ramses_extras.const import AVAILABLE_FEATURES, DOMAIN


class TestGetFeatureDetailsFromModule:
    """Test _get_feature_details_from_module helper."""

    def test_get_details_existing_feature(self):
        """Test getting details for existing feature."""
        result = _get_feature_details_from_module("default")
        assert "supported_device_types" in result

    def test_get_details_nonexistent_feature(self):
        """Test getting details for non-existent feature."""
        result = _get_feature_details_from_module("nonexistent")
        assert result == {}


class TestCopyCardFilesConfigFlow:
    """Test _copy_card_files_config_flow."""

    def test_copy_files(self, tmp_path):
        """Test copying card files."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        # Create test files
        (source / "test.js").write_text("test content")
        subdir = source / "subdir"
        subdir.mkdir()
        (subdir / "test2.js").write_text("test2 content")

        _copy_card_files_config_flow(source, dest)

        assert (dest / "test.js").exists()
        assert (dest / "subdir" / "test2.js").exists()


class TestRamsesExtrasConfigFlow:
    """Test RamsesExtrasConfigFlow."""

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
    async def test_async_step_user_no_existing_entry(self, config_flow, hass):
        """Test user step when no existing entry."""
        hass.config_entries.async_entries.return_value = []

        result = await config_flow.async_step_user()
        assert result["type"] == "create_entry"
        assert result["title"] == "Ramses Extras"

    @pytest.mark.asyncio
    async def test_async_step_user_existing_entry(self, config_flow, hass):
        """Test user step when entry exists - should abort."""
        existing_entry = MagicMock()
        hass.config_entries.async_entries.return_value = [existing_entry]

        result = await config_flow.async_step_user()
        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"


class TestRamsesExtrasOptionsFlowHandler:
    """Test RamsesExtrasOptionsFlowHandler."""

    @pytest.fixture
    def entry(self):
        """Mock config entry."""
        entry = MagicMock()
        entry.options = {}
        entry.data = {"enabled_features": {"default": True}}
        entry.entry_id = "test_entry_id"
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
    async def test_async_step_init(self, options_flow):
        """Test init step redirects to main_menu."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_init()
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_async_step_advanced_settings_back(self, options_flow):
        """Test advanced_settings step with back action."""
        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={"action": "back"}
            )
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_async_step_advanced_settings_save(self, options_flow):
        """Test advanced_settings step with save action."""
        options_flow.hass.config_entries.async_update_entry = MagicMock()

        with patch.object(
            options_flow, "async_step_main_menu", return_value={"type": "menu"}
        ):
            result = await options_flow.async_step_advanced_settings(
                user_input={
                    "action": "save",
                    "frontend_log_level": "debug",
                    "log_level": "info",
                }
            )
            assert result["type"] == "menu"


class TestManageCardsConfigFlow:
    """Test _manage_cards_config_flow."""

    @pytest.mark.asyncio
    async def test_manage_cards_feature_enabled(self):
        """Test managing cards when feature enabled."""
        hass = MagicMock()
        hass.config.path.return_value = "/mock/path"

        enabled_features = {"test_feature": True}
        await _manage_cards_config_flow(hass, enabled_features)


class TestInstallCardConfigFlow:
    """Test _install_card_config_flow."""

    @pytest.mark.asyncio
    async def test_install_card_success(self):
        """Test successful card installation."""
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock()

        source_path = MagicMock()
        source_path.exists.return_value = True
        dest_path = MagicMock()

        await _install_card_config_flow(hass, source_path, dest_path)
        hass.async_add_executor_job.assert_called_once()
