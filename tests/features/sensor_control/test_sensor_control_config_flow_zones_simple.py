"""Simple tests for sensor_control zones functionality."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.sensor_control.config_flow import (
    async_step_sensor_control_config,
)


@pytest.fixture
def flow():
    """Mock the central options flow."""
    flow = MagicMock()
    flow.hass = MagicMock()
    flow._config_entry = MagicMock()
    flow._config_entry.options = {"sensor_control": {}}
    flow._config_entry.data = {}
    flow._get_config_flow_helper = MagicMock()
    flow._get_all_devices = MagicMock(return_value=["32:123456"])
    flow._extract_device_id = MagicMock(side_effect=lambda x: x)
    flow._get_device_label = MagicMock(side_effect=lambda x: f"Device {x}")
    flow.async_show_form = MagicMock()
    flow.async_step_main_menu = AsyncMock()
    # Set up hass.data with proper structure
    flow.hass.data = {"ramses_extras": {"config_entry": flow._config_entry}}
    return flow


@pytest.fixture
def helper():
    """Mock the config flow helper."""
    helper = MagicMock()
    helper.get_devices_for_feature_selection.return_value = ["32:123456"]
    return helper


async def test_zones_menu_shows_zones(flow, helper):
    """Test that zones menu displays configured zones."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_menu"

    # Mock existing zones
    flow.hass.data["ramses_extras"]["config_entry"].options = {
        "ramses_extras": {
            "features": {
                "zones": {
                    "FANs": {
                        "32:123456": [
                            {
                                "zone_id": "bathroom",
                                "type": "paired_valves",
                                "enabled": True,
                                "inlet_valve_entity": "switch.bath_inlet",
                                "outlet_valve_entity": "switch.bath_outlet",
                            }
                        ]
                    }
                }
            }
        }
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, None)
        flow.async_show_form.assert_called_once()

        # Check that zone appears in menu
        call_args = flow.async_show_form.call_args
        info_text = call_args.kwargs["description_placeholders"]["info"]
        assert "Existing zones:" in info_text
        assert "zone bathroom" in info_text
        assert "type: paired_valves" in info_text
        assert "inlet: switch.bath_inlet" in info_text


async def test_zones_add_transitions_to_edit(flow, helper):
    """Test that add action transitions to edit stage."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_menu"

    flow.hass.data["ramses_extras"]["config_entry"].options = {}

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"action": "add"})
        assert flow._sensor_control_group_stage == "zones_edit"
        assert flow._sensor_control_editing_zone_id is None


async def test_zones_delete_calls_update(flow, helper):
    """Test that delete action calls config update."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_menu"

    flow.hass.data["ramses_extras"]["config_entry"].options = {
        "ramses_extras": {
            "features": {
                "zones": {
                    "FANs": {
                        "32:123456": [{"zone_id": "bathroom", "type": "paired_valves"}]
                    }
                }
            }
        }
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(
            flow, {"action": "delete", "zone_id": "bathroom"}
        )

        # Verify config update was called
        flow.hass.config_entries.async_update_entry.assert_called_once()


async def test_zones_confirm_save_calls_update(flow, helper):
    """Test that confirm save calls config update."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_confirm"

    flow._sensor_control_pending_zone = {
        "zone_id": "bathroom",
        "type": "paired_valves",
        "enabled": True,
    }

    flow.hass.data["ramses_extras"]["config_entry"].options = {
        "ramses_extras": {"features": {"zones": {"FANs": {"32:123456": []}}}}
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"confirm": "save"})

        # Verify config update was called
        flow.hass.config_entries.async_update_entry.assert_called_once()

        # Verify state was reset
        assert flow._sensor_control_pending_zone is None
        assert flow._sensor_control_group_stage == "zones_menu"


async def test_zones_confirm_edit_returns_to_edit(flow, helper):
    """Test that confirm edit returns to edit stage."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_confirm"

    flow._sensor_control_pending_zone = {"zone_id": "bathroom"}

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"confirm": "edit"})
        assert flow._sensor_control_group_stage == "zones_edit"


async def test_zones_confirm_cancel_resets_state(flow, helper):
    """Test that confirm cancel resets state."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_confirm"

    flow._sensor_control_pending_zone = {"zone_id": "bathroom"}

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"confirm": "cancel"})
        assert flow._sensor_control_pending_zone is None
        assert flow._sensor_control_group_stage == "zones_menu"


async def test_zones_menu_back_returns_to_select_group(flow, helper):
    """Test that back action returns to group selection."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_menu"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"action": "back"})
        assert flow._sensor_control_group_stage == "select_group"


async def test_zones_edit_submit_transitions_to_confirm(flow, helper):
    """Test that submitting zone edit transitions to confirm."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "zones_edit"
    flow._sensor_control_editing_zone_id = "bathroom"

    flow.hass.data["ramses_extras"]["config_entry"].options = {
        "ramses_extras": {"features": {"zones": {"FANs": {"32:123456": []}}}}
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        user_input = {
            "zone_id": "bathroom",
            "type": "paired_valves",
            "enabled": True,
            "inlet_valve_entity": "switch.bath_inlet",
            "outlet_valve_entity": "switch.bath_outlet",
        }
        await async_step_sensor_control_config(flow, user_input)

        # Should move to confirm step
        assert flow._sensor_control_group_stage == "zones_confirm"
        assert flow._sensor_control_pending_zone is not None
        assert flow._sensor_control_pending_zone["zone_id"] == "bathroom"
