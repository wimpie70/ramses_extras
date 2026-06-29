"""Tests for temp_control config flow."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.temp_control.config_flow import (
    _get_section_defaults,
    _persist_temp_control_settings,
    async_step_temp_control_config,
)


@pytest.fixture
def mock_flow():
    """Create a mock flow object with the needed attributes."""
    flow = MagicMock()
    flow.hass = MagicMock()
    flow._config_entry = MagicMock()
    flow._config_entry.options = {}
    flow._config_entry.data = {}
    flow._refresh_config_entry = MagicMock()
    flow._get_config_flow_helper = MagicMock()
    flow._get_persisted_matrix_state = MagicMock(return_value=None)
    flow._old_matrix_state = None
    flow._get_all_devices = MagicMock(return_value=[])
    flow._get_device_label = MagicMock(return_value="Test Device")
    flow._extract_device_id = MagicMock(return_value="32_153289")
    flow._show_matrix_based_confirmation = AsyncMock(return_value=MagicMock())
    flow.async_show_form = MagicMock()
    flow._selected_feature = None
    flow._temp_matrix_state = None

    helper = MagicMock()
    helper.restore_matrix_state = MagicMock()
    helper.get_devices_for_feature_selection = MagicMock(return_value=[])
    helper.get_enabled_devices_for_feature = MagicMock(return_value=[])
    helper.set_enabled_devices_for_feature = MagicMock()
    helper.get_feature_device_matrix_state = MagicMock(return_value={})
    flow._get_config_flow_helper.return_value = helper

    return flow


class TestGetSectionDefaults:
    """Test _get_section_defaults."""

    def test_defaults_from_empty_config(self, mock_flow):
        mock_flow._config_entry.options = {}
        mock_flow._config_entry.data = {}

        defaults = _get_section_defaults(mock_flow)

        assert defaults["comfort_delta_activate"] == 1.0
        assert defaults["comfort_delta_deactivate"] == 0.5
        assert defaults["cooling_delta_activate"] == 1.0
        assert defaults["cooling_delta_deactivate"] == 0.5
        assert defaults["min_outdoor_temp"] == 10.0
        assert defaults["min_bypass_mode_interval_seconds"] == 180
        assert defaults["default_desired_speed"] == "high"
        assert defaults["dewpoint_guard_enabled"] is False
        assert defaults["dewpoint_margin_c"] == 1.0

    def test_defaults_from_legacy_store(self, mock_flow):
        mock_flow._config_entry.options = {
            "temp_control": {
                "comfort_delta_activate": 2.0,
                "default_desired_speed": "low",
                "dewpoint_guard_enabled": True,
            }
        }

        defaults = _get_section_defaults(mock_flow)

        assert defaults["comfort_delta_activate"] == 2.0
        assert defaults["default_desired_speed"] == "low"
        assert defaults["dewpoint_guard_enabled"] is True

    def test_defaults_from_canonical_store(self, mock_flow):
        mock_flow._config_entry.options = {
            "ramses_extras": {
                "features": {
                    "temp_control": {
                        "min_outdoor_temp": 5.0,
                        "min_bypass_mode_interval_seconds": 300,
                        "dewpoint_margin_c": 2.5,
                    }
                }
            }
        }

        defaults = _get_section_defaults(mock_flow)

        assert defaults["min_outdoor_temp"] == 5.0
        assert defaults["min_bypass_mode_interval_seconds"] == 300
        assert defaults["dewpoint_margin_c"] == 2.5


class TestPersistTempControlSettings:
    """Test _persist_temp_control_settings."""

    def test_persist_writes_legacy_and_canonical(self, mock_flow):
        mock_flow._config_entry.options = {}

        settings = {
            "comfort_delta_activate": 2.0,
            "default_desired_speed": "medium",
        }
        _persist_temp_control_settings(mock_flow, settings)

        call_args = mock_flow.hass.config_entries.async_update_entry.call_args
        opts = call_args.kwargs["options"]

        assert opts["temp_control"]["comfort_delta_activate"] == 2.0
        assert opts["temp_control"]["default_desired_speed"] == "medium"
        assert (
            opts["ramses_extras"]["features"]["temp_control"]["comfort_delta_activate"]
            == 2.0
        )

    def test_persist_merges_with_existing(self, mock_flow):
        mock_flow._config_entry.options = {
            "temp_control": {"comfort_delta_activate": 1.0},
            "ramses_extras": {"features": {"temp_control": {"min_outdoor_temp": 8.0}}},
        }

        settings = {"comfort_delta_activate": 2.0}
        _persist_temp_control_settings(mock_flow, settings)

        opts = mock_flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        # New value overwrites
        assert opts["temp_control"]["comfort_delta_activate"] == 2.0
        # Existing canonical value preserved
        assert (
            opts["ramses_extras"]["features"]["temp_control"]["min_outdoor_temp"] == 8.0
        )

    def test_persist_calls_refresh(self, mock_flow):
        mock_flow._refresh_config_entry = MagicMock()
        _persist_temp_control_settings(mock_flow, {})

        mock_flow._refresh_config_entry.assert_called_once()


class TestAsyncStepTempControlConfig:
    """Test the main config flow step."""

    @pytest.mark.asyncio
    async def test_show_form_when_no_user_input(self, mock_flow):
        await async_step_temp_control_config(mock_flow, None)

        mock_flow.async_show_form.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_form_has_schema(self, mock_flow):
        await async_step_temp_control_config(mock_flow, None)

        call_args = mock_flow.async_show_form.call_args
        assert call_args.kwargs["step_id"] == "feature_config"
        assert "data_schema" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_show_form_description_text(self, mock_flow):
        await async_step_temp_control_config(mock_flow, None)

        call_args = mock_flow.async_show_form.call_args
        placeholders = call_args.kwargs["description_placeholders"]
        assert "info" in placeholders
        assert "Temperature Control" in placeholders["info"]

    @pytest.mark.asyncio
    async def test_submit_persists_settings(self, mock_flow):
        user_input = {
            "enabled_devices": ["32_153289"],
            "comfort_delta_activate": 2.0,
            "comfort_delta_deactivate": 1.0,
            "cooling_delta_activate": 1.5,
            "cooling_delta_deactivate": 0.8,
            "min_outdoor_temp": 12.0,
            "min_bypass_mode_interval_seconds": 240,
            "default_desired_speed": "low",
        }

        await async_step_temp_control_config(mock_flow, user_input)

        helper = mock_flow._get_config_flow_helper.return_value
        helper.set_enabled_devices_for_feature.assert_called_once_with(
            "temp_control", ["32_153289"]
        )

        opts = mock_flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        assert opts["temp_control"]["comfort_delta_activate"] == 2.0
        assert opts["temp_control"]["default_desired_speed"] == "low"
        assert opts["temp_control"]["min_outdoor_temp"] == 12.0
        assert (
            opts["ramses_extras"]["features"]["temp_control"]["comfort_delta_activate"]
            == 2.0
        )

    @pytest.mark.asyncio
    async def test_submit_shows_confirmation(self, mock_flow):
        user_input = {
            "enabled_devices": [],
            "comfort_delta_activate": 1.0,
            "comfort_delta_deactivate": 0.5,
            "cooling_delta_activate": 1.0,
            "cooling_delta_deactivate": 0.5,
            "min_outdoor_temp": 10.0,
            "min_bypass_mode_interval_seconds": 180,
            "default_desired_speed": "high",
        }

        await async_step_temp_control_config(mock_flow, user_input)

        mock_flow._show_matrix_based_confirmation.assert_called_once()
        assert mock_flow._selected_feature == "temp_control"

    @pytest.mark.asyncio
    async def test_submit_restores_matrix_state(self, mock_flow):
        matrix_state = {"temp_control": {"32_153289": True}}
        mock_flow._get_persisted_matrix_state.return_value = matrix_state

        user_input = {
            "enabled_devices": ["32_153289"],
            "comfort_delta_activate": 1.0,
            "comfort_delta_deactivate": 0.5,
            "cooling_delta_activate": 1.0,
            "cooling_delta_deactivate": 0.5,
            "min_outdoor_temp": 10.0,
            "min_bypass_mode_interval_seconds": 180,
            "default_desired_speed": "high",
        }

        await async_step_temp_control_config(mock_flow, user_input)

        helper = mock_flow._get_config_flow_helper.return_value
        helper.restore_matrix_state.assert_called_once_with(matrix_state)

    @pytest.mark.asyncio
    async def test_device_options_built_from_filtered_devices(self, mock_flow):
        mock_flow._get_all_devices.return_value = [
            {"device_id": "32:153289", "name": "Living Room FAN"},
        ]
        mock_flow._extract_device_id = MagicMock(return_value="32_153289")
        helper = mock_flow._get_config_flow_helper.return_value
        helper.get_devices_for_feature_selection = MagicMock(
            return_value=[{"device_id": "32:153289"}]
        )

        await async_step_temp_control_config(mock_flow, None)

        mock_flow.async_show_form.assert_called_once()
