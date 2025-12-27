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
            # Mock the calculate_entity_changes to return entities to remove
            mock_entity_manager.calculate_entity_changes = AsyncMock(
                return_value=(["entity_to_create"], ["switch.test_entity"])
            )

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

    @pytest.mark.asyncio
    async def test_matrix_confirm_persists_to_options(self, hass):
        """Test that matrix confirmation persists
        device_feature_matrix to config_entry.options."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {"humidity_control": True},
            "device_feature_matrix": {"32:153289": {"humidity_control": True}},
        }
        mock_config_entry.options = {"existing_option": "value"}
        mock_config_entry.entry_id = "test_entry_id"

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set up temp matrix state as if user configured devices
        temp_matrix = {
            "32:153289": {"humidity_control": True},
            "32:153290": {"humidity_control": True},  # New device added
        }
        options_flow._temp_matrix_state = temp_matrix

        # Mock async_create_entry and config_entries methods
        with (
            patch.object(options_flow, "async_create_entry") as mock_create_entry,
            patch.object(
                hass.config_entries, "async_update_entry"
            ) as mock_update_entry,
            patch.object(hass.config_entries, "async_reload") as mock_reload,
        ):
            mock_create_entry.return_value = {"type": "create_entry"}
            mock_update_entry.return_value = None
            mock_reload.return_value = None

            user_input = {"confirm": True}

            _ = await options_flow.async_step_matrix_confirm(user_input)

            # Verify async_create_entry was called with correct options
            mock_create_entry.assert_called_once()
            call_args = mock_create_entry.call_args
            returned_options = call_args[1]["data"]  # keyword argument 'data'

            # Verify existing options are preserved
            assert returned_options["existing_option"] == "value"

            # Verify matrix is persisted to options
            expected_matrix = {
                "32:153289": {"humidity_control": True},
                "32:153290": {"humidity_control": True},
            }
            assert returned_options["device_feature_matrix"] == expected_matrix

    @pytest.mark.asyncio
    async def test_matrix_confirm_no_temp_matrix_state(self, hass):
        """Test matrix confirmation when no temp_matrix_state is set."""
        mock_config_entry = MagicMock()
        mock_config_entry.options = {"existing_option": "value"}

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # No temp_matrix_state set
        options_flow._temp_matrix_state = None  # type: ignore[assignment]

        with patch.object(options_flow, "async_create_entry") as mock_create_entry:
            mock_create_entry.return_value = {"type": "create_entry"}

            user_input = {"confirm": True}

            _ = await options_flow.async_step_matrix_confirm(user_input)

            # Verify async_create_entry was called with existing options only
            mock_create_entry.assert_called_once()
            call_args = mock_create_entry.call_args
            returned_options = call_args[1]["data"]

            # Verify existing options are preserved
            assert returned_options["existing_option"] == "value"

            # Verify no matrix is added
            assert "device_feature_matrix" not in returned_options

    @pytest.mark.asyncio
    async def test_matrix_confirm_with_invalid_temp_matrix(self, hass):
        """Test matrix confirmation with invalid temp_matrix_state (not a Mapping)."""
        mock_config_entry = MagicMock()
        mock_config_entry.options = {"existing_option": "value"}

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set invalid temp_matrix_state - this should cause the matrix confirmation
        # logic to fail and the method should fall back to returning the confirm form
        options_flow._temp_matrix_state = "invalid_string"  # type: ignore[assignment]

        with patch.object(
            options_flow, "_show_matrix_based_confirmation"
        ) as mock_show_confirm:
            mock_show_confirm.return_value = {
                "type": "form",
                "errors": {"base": "invalid_matrix"},
            }

            user_input = {"confirm": True}

            result = await options_flow.async_step_matrix_confirm(user_input)

            # Should return the confirmation form due to error handling
            mock_show_confirm.assert_called_once()
            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_matrix"

    @pytest.mark.asyncio
    async def test_generic_step_feature_config_sets_temp_matrix(self, hass):
        """Test generic_step_feature_config sets temp_matrix_state correctly."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set the selected feature (this is normally done by async_step_feature_config)
        options_flow._selected_feature = "test_feature"

        # Mock the config flow helper
        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            helper_instance = MagicMock()
            mock_helper.return_value = helper_instance

            # Mock device selection and helper methods
            user_input = {"enabled_devices": ["device1", "device2"]}
            helper_instance.get_feature_device_matrix_state.return_value = {
                "device1": {"test_feature": True},
                "device2": {"test_feature": True},
            }

            # Mock _show_matrix_based_confirmation to return a form result
            with patch.object(
                options_flow, "_show_matrix_based_confirmation"
            ) as mock_show_confirm:
                mock_show_confirm.return_value = {
                    "type": "form",
                    "step_id": "matrix_confirm",
                }

                result = await options_flow.generic_step_feature_config(user_input)

                # Verify the method completed and returned a confirmation form
                mock_show_confirm.assert_called_once()
                assert result["type"] == "form"
                assert result["step_id"] == "matrix_confirm"

                # Verify helper methods were called correctly
                helper_instance.set_enabled_devices_for_feature.assert_called_once_with(
                    "test_feature", ["device1", "device2"]
                )

                # Verify temp_matrix_state was set
                assert options_flow._temp_matrix_state == {
                    "device1": {"test_feature": True},
                    "device2": {"test_feature": True},
                }

                # Verify selected feature was stored (should still be set)
                assert options_flow._selected_feature == "test_feature"

    @pytest.mark.asyncio
    async def test_generic_step_feature_config_empty_matrix_state(self, hass):
        """Test generic_step_feature_config handles empty matrix state."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set the selected feature (this is normally done by async_step_feature_config)
        options_flow._selected_feature = "test_feature"

        # Mock the config flow helper
        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            helper_instance = MagicMock()
            mock_helper.return_value = helper_instance

            # Mock device selection with empty matrix state
            user_input = {"enabled_devices": []}
            helper_instance.get_feature_device_matrix_state.return_value = {}

            # Mock _show_matrix_based_confirmation to return a form result
            with patch.object(
                options_flow, "_show_matrix_based_confirmation"
            ) as mock_show_confirm:
                mock_show_confirm.return_value = {
                    "type": "form",
                    "step_id": "matrix_confirm",
                }

                result = await options_flow.generic_step_feature_config(user_input)

                # Verify the method completed and returned a confirmation form
                mock_show_confirm.assert_called_once()
                assert result["type"] == "form"

                # Verify temp_matrix_state was set to empty dict
                assert options_flow._temp_matrix_state == {}

    @pytest.mark.asyncio
    async def test_matrix_confirm_error_handling(self, hass):
        """Test matrix confirmation error handling."""
        mock_config_entry = MagicMock()
        mock_config_entry.options = {}

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set up temp matrix state
        options_flow._temp_matrix_state = {"device1": {"feature1": True}}

        # Mock async_create_entry to raise an exception
        with patch.object(options_flow, "async_create_entry") as mock_create_entry:
            mock_create_entry.side_effect = Exception("Test error")

            # Mock the confirmation display method
            with patch.object(
                options_flow, "_show_matrix_based_confirmation"
            ) as mock_show_confirm:
                mock_show_confirm.return_value = {
                    "type": "form",
                    "errors": {"base": "unknown_error"},
                }

                user_input = {"confirm": True}

                result = await options_flow.async_step_matrix_confirm(user_input)

                # Verify error handling returned the confirmation form
                mock_show_confirm.assert_called_once()
                assert result["type"] == "form"
                assert result["errors"]["base"] == "unknown_error"


class TestDeviceHelperMethods:
    """Test device-related helper methods in RamsesExtrasOptionsFlowHandler."""

    def test_get_all_devices_with_devices(self, hass):
        """Test getting all devices when devices are available."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Set up devices in hass.data
        test_devices = ["device1", "device2", "device3"]
        hass.data = {"ramses_extras": {"devices": test_devices}}

        devices = options_flow._get_all_devices()

        assert devices == test_devices

    def test_get_all_devices_no_ramses_extras_data(self, hass):
        """Test getting all devices when ramses_extras data doesn't exist."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # No ramses_extras data
        hass.data = {}

        devices = options_flow._get_all_devices()

        assert devices == []

    def test_get_all_devices_no_devices_key(self, hass):
        """Test getting all devices when devices key doesn't exist."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # ramses_extras exists but no devices key
        hass.data = {"ramses_extras": {}}

        devices = options_flow._get_all_devices()

        assert devices == []

    def test_get_all_devices_invalid_devices_type(self, hass):
        """Test getting all devices when devices is not a list."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # devices is not a list
        hass.data = {"ramses_extras": {"devices": "invalid"}}

        devices = options_flow._get_all_devices()

        assert devices == []

    def test_extract_device_id_from_string(self):
        """Test extracting device ID from string."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        device_id = options_flow._extract_device_id("test_device_id")

        assert device_id == "test_device_id"

    def test_extract_device_id_from_device_with_id_attr(self):
        """Test extracting device ID from object with id attribute."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        mock_device = MagicMock()
        mock_device.id = "device_id_from_attr"

        device_id = options_flow._extract_device_id(mock_device)

        assert device_id == "device_id_from_attr"

        """Test extracting device ID from object with device_id attribute."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with device_id attribute
        device = type("Device", (), {"device_id": "device_id_from_device_attr"})()

        device_id = options_flow._extract_device_id(device)

        assert device_id == "device_id_from_device_attr"

    def test_extract_device_id_from_device_with__id_attr(self):
        """Test extracting device ID from object with _id attribute."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with _id attribute
        device = type("Device", (), {"_id": "device_id_from_private_attr"})()

        device_id = options_flow._extract_device_id(device)

        assert device_id == "device_id_from_private_attr"

    def test_extract_device_id_from_device_with_name_attr(self):
        """Test extracting device ID from object with name attribute."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with name attribute
        device = type("Device", (), {"name": "device_name_fallback"})()

        device_id = options_flow._extract_device_id(device)

        assert device_id == "device_name_fallback"

    def test_get_device_label_from_device_with_name(self):
        """Test getting device label from device object with name."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with name attribute
        device = type("Device", (), {"name": "Device Name"})()

        # Mock DeviceFilter._get_device_slugs to return empty list
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=[],
        ):
            label = options_flow._get_device_label(device)

            assert label == "Device Name"

    def test_get_device_label_from_device_with_device_id(self):
        """Test getting device label from device object with device_id."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with device_id attribute
        device = type("Device", (), {"device_id": "device_123"})()

        # Mock DeviceFilter._get_device_slugs to return empty list
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=[],
        ):
            label = options_flow._get_device_label(device)

            assert label == "device_123"

    def test_get_device_label_from_device_with_id(self):
        """Test getting device label from device object with id."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with id attribute
        device = type("Device", (), {"id": "id_456"})()

        # Mock DeviceFilter._get_device_slugs to return empty list
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=[],
        ):
            label = options_flow._get_device_label(device)

            assert label == "id_456"

    def test_get_device_label_unknown_device(self):
        """Test getting device label from device object with no valid attributes."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Create a simple object with no attributes
        device = object()

        # Mock DeviceFilter._get_device_slugs to return empty list
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=[],
        ):
            label = options_flow._get_device_label(device)

            assert label == "Unknown Device"

    def test_get_device_label_with_slugs(self):
        """Test getting device label with device slugs included."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        mock_device = MagicMock()
        mock_device.name = "Ventilation Unit"

        # Mock the DeviceFilter._get_device_slugs to return slugs
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=["FAN", "VENT"],
        ):
            label = options_flow._get_device_label(mock_device)

            assert "Ventilation Unit" in label
            assert "FAN" in label
            assert "VENT" in label

    def test_get_device_label_with_duplicate_slugs(self):
        """Test getting device label with duplicate slugs filtered out."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        mock_device = MagicMock()
        mock_device.name = "Test Device"

        # Mock slugs with duplicates
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            return_value=["FAN", "FAN", "VENT"],
        ):
            label = options_flow._get_device_label(mock_device)

            # Should contain each unique slug only once
            assert label.count("FAN") == 1
            assert "VENT" in label

    def test_get_device_label_slug_exception_handling(self):
        """Test getting device label when slug extraction raises exception."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        mock_device = MagicMock()
        mock_device.name = "Test Device"

        # Mock DeviceFilter._get_device_slugs to raise exception
        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter."
            "DeviceFilter._get_device_slugs",
            side_effect=Exception("Test error"),
        ):
            label = options_flow._get_device_label(mock_device)

            # Should still return the base label without slugs
            assert label == "Test Device"


class TestMainMenuVariations:
    """Test main menu step with different configuration states."""

    @pytest.mark.asyncio
    async def test_main_menu_with_no_enabled_features(self, hass):
        """Test main menu when no features are enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "menu_options" in result
        # Should include all menu options
        expected_options = [
            "features",
            "configure_devices",
            "view_configuration",
            "advanced_settings",
        ]
        for option in expected_options:
            assert option in result["menu_options"]

    @pytest.mark.asyncio
    async def test_main_menu_with_some_features_enabled(self, hass):
        """Test main menu when some features are enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {"humidity_control": True, "sensor_control": False}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "menu_options" in result
        # Should include all menu options
        expected_options = [
            "features",
            "configure_devices",
            "view_configuration",
            "advanced_settings",
        ]
        for option in expected_options:
            assert option in result["menu_options"]

    @pytest.mark.asyncio
    async def test_main_menu_with_all_features_enabled(self, hass):
        """Test main menu when all features are enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "sensor_control": True,
                "hello_world": True,
                "hvac_fan_card": True,
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "menu_options" in result
        # Should include all menu options
        expected_options = [
            "features",
            "configure_devices",
            "view_configuration",
            "advanced_settings",
        ]
        for option in expected_options:
            assert option in result["menu_options"]

    @pytest.mark.asyncio
    async def test_main_menu_missing_enabled_features_key(self, hass):
        """Test main menu when enabled_features key is missing from config."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {}  # No enabled_features key
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "menu_options" in result
        # Should still include all menu options
        expected_options = [
            "features",
            "configure_devices",
            "view_configuration",
            "advanced_settings",
        ]
        for option in expected_options:
            assert option in result["menu_options"]

    @pytest.mark.asyncio
    async def test_main_menu_with_invalid_enabled_features(self, hass):
        """Test main menu when enabled_features is not a dict."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": "invalid"}  # Not a dict
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # The method crashes when enabled_features is invalid (not a dict)
        # This is expected behavior since the method assumes enabled_features is a dict
        with pytest.raises(AttributeError, match="'str' object has no attribute 'get'"):
            await options_flow.async_step_main_menu()

    @pytest.mark.asyncio
    async def test_main_menu_description_placeholders(self, hass):
        """Test that main menu includes proper description placeholders."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {"humidity_control": True}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_main_menu()

        assert result["type"] == "menu"
        assert "description_placeholders" in result
        placeholders = result["description_placeholders"]

        # Should include menu description
        assert "info" in placeholders
        description = placeholders["info"]

        # Should contain the count of enabled features
        assert (
            "1 features enabled" in description
            or "have 1 features enabled" in description
        )


class TestFeatureSelection:
    """Test feature selection step functionality."""

    @pytest.mark.asyncio
    async def test_feature_selection_show_form(self, hass):
        """Test feature selection step shows form without user input."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "sensor_control": False,
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Mock the config flow helper
        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            helper_instance = MagicMock()
            mock_helper.return_value = helper_instance

            # Mock helper methods
            mock_schema = MagicMock()
            helper_instance.get_feature_selection_schema.return_value = mock_schema
            helper_instance.build_feature_info_text.return_value = "Feature info text"

            result = await options_flow.async_step_features()

            assert result["type"] == "form"
            assert result["step_id"] == "features"
            assert result["data_schema"] == mock_schema
            assert result["description_placeholders"]["info"] == "Feature info text"

            # Verify helper was called correctly
            helper_instance.get_feature_selection_schema.assert_called_once()
            helper_instance.build_feature_info_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_feature_selection_with_user_input(self, hass):
        """Test feature selection step processes user input correctly."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": False,
                "sensor_control": True,
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        user_input = {"features": ["humidity_control", "hello_world"]}

        # Mock confirm step
        with patch.object(options_flow, "async_step_confirm") as mock_confirm:
            mock_confirm.return_value = {"type": "form"}

            result = await options_flow.async_step_features(user_input)

            # Should redirect to confirm step
            mock_confirm.assert_called_once()
            assert result == {"type": "form"}

            # Verify pending data was set correctly
            expected_old_features = {
                "default": True,
                "humidity_control": False,
                "sensor_control": True,
            }
            # All features should be included in
            #  new features, with selected ones enabled
            expected_new_features = {
                "default": True,  # Always enabled
                "humidity_control": True,  # Selected
                "hvac_fan_card": False,  # Not selected
                "hello_world": True,  # Selected
                "sensor_control": False,  # Was enabled but not selected
            }

            pending_data = options_flow._pending_data
            assert pending_data["enabled_features_old"] == expected_old_features
            assert pending_data["enabled_features_new"] == expected_new_features
            assert options_flow._feature_changes_detected is True

    @pytest.mark.asyncio
    async def test_feature_selection_no_changes(self, hass):
        """Test feature selection when user makes no changes."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": False,
                "hello_world": False,
                "sensor_control": False,
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        user_input = {"features": ["humidity_control"]}
        # Only humidity_control selected (besides default which is always enabled)

        # Mock confirm step
        with patch.object(options_flow, "async_step_confirm") as mock_confirm:
            mock_confirm.return_value = {"type": "form"}

            result = await options_flow.async_step_features(user_input)

            # Should still redirect to confirm step
            mock_confirm.assert_called_once()
            assert result == {"type": "form"}

            # Verify pending data was set
            assert options_flow._pending_data is not None
            assert options_flow._feature_changes_detected is False
            # No changes detected

    @pytest.mark.asyncio
    async def test_feature_selection_empty_selection(self, hass):
        """Test feature selection when user selects no features."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {"default": True, "humidity_control": True}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        user_input = {"features": []}  # No features selected

        # Mock confirm step
        with patch.object(options_flow, "async_step_confirm") as mock_confirm:
            mock_confirm.return_value = {"type": "form"}

            result = await options_flow.async_step_features(user_input)

            # Should redirect to confirm step
            mock_confirm.assert_called_once()
            assert result == {"type": "form"}

            # Verify pending data shows default remains enabled, others disabled
            expected_new_features = {
                "default": True,  # Always enabled
                "humidity_control": False,  # Not selected
                "hvac_fan_card": False,  # Not selected
                "hello_world": False,  # Not selected
                "sensor_control": False,  # Not selected
            }
            pending_data = options_flow._pending_data
            assert pending_data["enabled_features_new"] == expected_new_features
            assert options_flow._feature_changes_detected is True

    @pytest.mark.asyncio
    async def test_feature_selection_missing_enabled_features(self, hass):
        """Test feature selection when enabled_features key is missing."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {}  # No enabled_features key
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Mock the config flow helper
        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            helper_instance = MagicMock()
            mock_helper.return_value = helper_instance

            # Mock helper methods
            mock_schema = MagicMock()
            helper_instance.get_feature_selection_schema.return_value = mock_schema
            helper_instance.build_feature_info_text.return_value = "Feature info text"

            result = await options_flow.async_step_features()

            assert result["type"] == "form"
            assert result["step_id"] == "features"

            # Verify helper was called with empty dict as enabled_features
            helper_instance.get_feature_selection_schema.assert_called_once_with({})


class TestViewConfiguration:
    """Test view configuration step functionality."""

    @pytest.mark.asyncio
    async def test_view_configuration_basic(self, hass):
        """Test view configuration step shows current config."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "sensor_control": False,
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_view_configuration()

        assert result["type"] == "form"
        assert result["step_id"] == "view_configuration"
        assert "description_placeholders" in result

        info_text = result["description_placeholders"]["info"]
        assert "Current Configuration" in info_text
        assert "Enabled features: 2" in info_text
        assert "Humidity Control" in info_text

    @pytest.mark.asyncio
    async def test_view_configuration_no_features(self, hass):
        """Test view configuration step when no features are enabled."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": {}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_view_configuration()

        assert result["type"] == "form"
        info_text = result["description_placeholders"]["info"]
        assert "Enabled features: 0" in info_text

    @pytest.mark.asyncio
    async def test_view_configuration_invalid_features(self, hass):
        """Test view configuration step handles invalid enabled_features."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {"enabled_features": "invalid"}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # The method crashes when enabled_features is invalid (not a dict)
        # This is expected behavior since the method assumes enabled_features is a dict
        with pytest.raises(
            AttributeError, match="'str' object has no attribute 'values'"
        ):
            await options_flow.async_step_view_configuration()


class TestAdvancedSettings:
    """Test advanced settings step functionality."""

    @pytest.mark.asyncio
    async def test_advanced_settings_show_form(self, hass):
        """Test advanced settings step shows form."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_advanced_settings()

        assert result["type"] == "form"
        assert result["step_id"] == "advanced_settings"
        assert "data_schema" in result
        assert (
            result["description_placeholders"]["info"] == "Configure advanced settings"
        )

    @pytest.mark.asyncio
    async def test_advanced_settings_with_user_input(self, hass):
        """Test advanced settings step handles user input."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        user_input = {"debug_mode": True, "log_level": "debug"}

        # Currently the method doesn't process user input, just shows form
        result = await options_flow.async_step_advanced_settings(user_input)

        # Should still return the form since no processing is implemented
        assert result["type"] == "form"
        assert result["step_id"] == "advanced_settings"
