"""Tests for default feature config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.default.config_flow import (
    async_step_default_config,
)


@pytest.fixture
def flow():
    """Mock the central options flow."""
    flow = MagicMock()
    flow._config_entry = MagicMock()
    flow._config_entry.data = {"device_feature_matrix": {}}
    flow._get_config_flow_helper = MagicMock()
    flow._get_all_devices = MagicMock(return_value=["32:123456", "37:654321"])
    flow._extract_device_id = MagicMock(side_effect=lambda x: x)
    flow._get_device_label = MagicMock(side_effect=lambda x: f"Device {x}")
    flow.async_show_form = MagicMock()
    flow._show_matrix_based_confirmation = AsyncMock()
    return flow


@pytest.fixture
def helper():
    """Mock the config flow helper."""
    helper = MagicMock()
    helper.get_devices_for_feature_selection.return_value = ["32:123456"]
    helper.get_enabled_devices_for_feature.return_value = []
    helper.get_feature_device_matrix_state.return_value = {
        "32:123456": {"default": True}
    }
    return helper


async def test_async_step_default_config_pre(flow, helper):
    """Test the pre-processing (show form) step of default config flow."""
    flow._get_config_flow_helper.return_value = helper

    await async_step_default_config(flow, None)

    flow.async_show_form.assert_called_once()
    args = flow.async_show_form.call_args[1]
    assert args["step_id"] == "feature_config"
    assert isinstance(args["data_schema"], vol.Schema)
    assert "info" in args["description_placeholders"]


async def test_async_step_default_config_post(flow, helper):
    """Test the post-processing (form submission) step of default config flow."""
    flow._get_config_flow_helper.return_value = helper
    user_input = {"enabled_devices": ["32:123456"]}

    await async_step_default_config(flow, user_input)

    helper.set_enabled_devices_for_feature.assert_called_once_with(
        "default", ["32:123456"]
    )
    assert flow._temp_matrix_state == {"32:123456": {"default": True}}
    assert flow._selected_feature == "default"
    flow._show_matrix_based_confirmation.assert_called_once()


async def test_async_step_default_config_restore_state(flow, helper):
    """Test that matrix state is restored if present."""
    flow._config_entry.data["device_feature_matrix"] = {"32:123456": {"default": True}}
    flow._get_config_flow_helper.return_value = helper

    await async_step_default_config(flow, None)

    helper.restore_matrix_state.assert_called_once_with(
        {"32:123456": {"default": True}}
    )
    assert flow._old_matrix_state == {"32:123456": {"default": True}}
