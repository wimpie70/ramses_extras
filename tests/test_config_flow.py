# tests/test_config_flow.py
"""Test config flow functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from custom_components.ramses_extras import _cleanup_orphaned_devices
from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
)
from custom_components.ramses_extras.const import (
    AVAILABLE_FEATURES,
    CONF_ENABLED_FEATURES,
)


class TestRamsesExtrasConfigFlow:
    """Test RamsesExtrasConfigFlow class."""

    def test_async_get_options_flow(self):
        """Test getting options flow handler."""
        mock_config_entry = MagicMock()

        options_flow = RamsesExtrasConfigFlow.async_get_options_flow(mock_config_entry)

        assert isinstance(options_flow, RamsesExtrasOptionsFlowHandler)
        assert options_flow._config_entry == mock_config_entry


class TestRamsesExtrasOptionsFlowHandler:
    """Test RamsesExtrasOptionsFlowHandler class."""

    def test_init(self):
        """Test initialization of options flow handler."""
        mock_config_entry = MagicMock()

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        assert options_flow._config_entry == mock_config_entry
        assert options_flow._pending_data is None
        assert options_flow._entity_manager is None
        assert options_flow._config_flow_helper is None
        assert options_flow._feature_changes_detected is False

    @pytest.mark.asyncio
    async def test_async_step_init_redirects_to_main_menu(self, hass):
        """Test that async_step_init redirects to main menu."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with patch.object(options_flow, "async_step_main_menu") as mock_main_menu:
            mock_main_menu.return_value = {"type": "menu"}
            result = await options_flow.async_step_init()

            mock_main_menu.assert_called_once()
            assert result == {"type": "menu"}

    @pytest.mark.asyncio
    async def test_async_step_main_menu(self, hass):
        """Test main menu step."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_ENABLED_FEATURES: {"default": True, "sensor_control": True}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "menu_options" in result
        assert "description_placeholders" in result
        # Should include features, configure_devices, view_configuration,
        # advanced_settings
        assert "features" in result["menu_options"]
        assert "configure_devices" in result["menu_options"]
        assert "view_configuration" in result["menu_options"]
        assert "advanced_settings" in result["menu_options"]

    @pytest.mark.asyncio
    async def test_async_step_features(self, hass):
        """Test features step."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {CONF_ENABLED_FEATURES: {"default": True}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            mock_helper_instance = MagicMock()
            mock_helper.return_value = mock_helper_instance
            mock_helper_instance.get_feature_selection_schema.return_value = MagicMock()

            result = await options_flow.async_step_features()

            assert result["type"] == "form"
            assert result["step_id"] == "features"
            mock_helper.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_step_features_with_user_input(self, hass):
        """Test features step with user input."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_ENABLED_FEATURES: {"default": True, "sensor_control": False}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        user_input = {"features": ["sensor_control"]}

        with patch.object(options_flow, "async_step_confirm") as mock_confirm:
            mock_confirm.return_value = {"type": "form"}

            await options_flow.async_step_features(user_input)

            assert options_flow._pending_data is not None
            assert options_flow._feature_changes_detected is True
            mock_confirm.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_step_confirm_without_user_input(self, hass):
        """Test confirm step without user input."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {CONF_ENABLED_FEATURES: {"default": True}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            mock_helper_instance = MagicMock()
            mock_helper.return_value = mock_helper_instance
            mock_helper_instance.get_feature_device_summary.return_value = "Summary"

            result = await options_flow.async_step_confirm()

            assert result["type"] == "form"
            assert result["step_id"] == "confirm"

    @pytest.mark.asyncio
    async def test_async_step_confirm_with_user_input(self, hass):
        """Test confirm step with user input (confirmation)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {CONF_ENABLED_FEATURES: {"default": True}}
        mock_config_entry.options = {}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        options_flow._pending_data = {
            "enabled_features_new": {"default": True, "sensor_control": True}
        }

        with (
            patch.object(hass.config_entries, "async_update_entry") as mock_update,
            patch.object(options_flow, "async_step_main_menu") as mock_main_menu,
        ):
            mock_main_menu.return_value = {"type": "menu"}
            user_input = {}  # User confirmed

            result = await options_flow.async_step_confirm(user_input)

            mock_update.assert_called_once()
            mock_main_menu.assert_called_once()
            assert result == {"type": "menu"}

    @pytest.mark.asyncio
    async def test_async_step_view_configuration(self, hass):
        """Test view configuration step."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_ENABLED_FEATURES: {"default": True, "sensor_control": True}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_view_configuration()

        assert result["type"] == "form"
        assert result["step_id"] == "view_configuration"
        assert "description_placeholders" in result
        assert "Current Configuration" in result["description_placeholders"]["info"]

    @pytest.mark.asyncio
    async def test_async_step_advanced_settings(self, hass):
        """Test advanced settings step."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_advanced_settings()

        assert result["type"] == "form"
        assert result["step_id"] == "advanced_settings"
        assert "data_schema" in result

    @pytest.mark.asyncio
    async def test_async_step_sensor_control_overview_no_mappings(self, hass):
        """Test sensor control overview with no mappings."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {}
        mock_config_entry.options = {}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_sensor_control_overview()

        assert result["type"] == "form"
        assert result["step_id"] == "sensor_control_overview"
        expected_text = "No sensor control mappings"
        assert expected_text in result["description_placeholders"]["info"]

    @pytest.mark.asyncio
    async def test_async_step_feature_config_generic(self, hass):
        """Test generic feature config step."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        options_flow._selected_feature = "test_feature"

        with patch.object(options_flow, "generic_step_feature_config") as mock_generic:
            mock_generic.return_value = {"type": "form"}

            await options_flow.async_step_feature_config()

            mock_generic.assert_called_once()

    def test_get_all_devices(self, hass):
        """Test getting all devices."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Test with no devices
        devices = options_flow._get_all_devices()
        assert devices == []

        # Test with devices
        hass.data = {"ramses_extras": {"devices": ["device1", "device2"]}}
        devices = options_flow._get_all_devices()
        assert devices == ["device1", "device2"]

    def test_get_device_label(self):
        """Test getting device label."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Test string
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=None,
        ):
            assert options_flow._get_device_label("device1") == "device1"

        # Test device with name
        mock_device = MagicMock()
        mock_device.name = "Device Name"
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=None,
        ):
            assert options_flow._get_device_label(mock_device) == "Device Name"

    def test_refresh_config_entry(self):
        """Test refreshing config entry."""
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_entry"
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        mock_hass = MagicMock()
        mock_config_entries = MagicMock()
        mock_hass.config_entries = mock_config_entries

        mock_latest = MagicMock()
        mock_config_entries.async_get_entry.return_value = mock_latest

        options_flow.hass = mock_hass

        options_flow._refresh_config_entry(mock_hass)

        assert options_flow._config_entry == mock_latest

    @pytest.mark.asyncio
    async def test_feature_changes_trigger_cleanup(self, hass):
        """Test that feature enable/disable changes trigger cleanup."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {"humidity_control": True}}
        mock_config_entry.entry_id = "test_entry_id"

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Stage feature changes first
        options_flow._pending_data = {
            "enabled_features_old": {"humidity_control": True},
            "enabled_features_new": {},  # Disable all features
        }
        options_flow._feature_changes_detected = True

        # Mock the cleanup function
        with (
            patch(
                "custom_components.ramses_extras._cleanup_orphaned_devices"
            ) as mock_cleanup,
            patch(
                "custom_components.ramses_extras.config_flow._manage_cards_config_flow"
            ),
            patch.object(hass.config_entries, "async_update_entry"),
        ):
            # Confirm the feature changes
            user_input = {"confirm": True}

            await options_flow.async_step_confirm(user_input)

            # Should return to main menu after applying changes
            # Verify cleanup was called
            mock_cleanup.assert_called_once_with(hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_matrix_confirmation_triggers_cleanup(self, hass):
        """Test that matrix confirmation triggers cleanup."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {"humidity_control": True},
            "device_feature_matrix": {"32:153289": {"humidity_control": True}},
        }
        mock_config_entry.entry_id = "test_entry_id"

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Mock the cleanup function and other dependencies
        with (
            patch(
                "custom_components.ramses_extras._cleanup_orphaned_devices"
            ) as mock_cleanup,
            patch.object(options_flow, "_entity_manager") as mock_entity_manager,
            patch.object(hass, "async_create_task"),
            patch.object(hass.config_entries, "async_update_entry"),
            patch.object(hass.config_entries, "async_reload"),
        ):
            mock_entity_manager.remove_entity = AsyncMock()

            # Simulate matrix confirmation with entities to remove
            options_flow._pending_data = {
                "entities_to_remove": ["switch.test_entity"],
                "old_matrix_state": {"32:153289": {"humidity_control": True}},
                "temp_matrix_state": {},  # Device removed
            }
            # Set the temp matrix state that the method expects
            options_flow._temp_matrix_state = {}

            user_input = {"confirm": True}

            await options_flow.async_step_matrix_confirm(user_input)

            # Verify cleanup was called
            mock_cleanup.assert_called_once_with(hass, mock_config_entry)
