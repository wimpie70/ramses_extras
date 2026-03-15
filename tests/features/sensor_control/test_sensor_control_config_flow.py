"""Tests for sensor_control feature config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.sensor_control.config_flow import (
    _device_key,
    _get_device_type,
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
    return flow


@pytest.fixture
def helper():
    """Mock the config flow helper."""
    helper = MagicMock()
    helper.get_devices_for_feature_selection.return_value = ["32:123456"]
    return helper


def test_device_key():
    """Test _device_key helper."""
    assert _device_key("32:123456") == "32_123456"


def test_get_device_type(flow):
    """Test _get_device_type helper."""
    mock_device = MagicMock()
    mock_device.id = "32:123456"
    flow.hass.data = {"ramses_extras": {"devices": [mock_device]}}

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.DeviceFilter"
    ) as mock_filter:
        mock_filter._get_device_slugs.return_value = ["FAN"]
        assert _get_device_type(flow, "32:123456") == "FAN"

    # Test fallback to upper case slug
    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.DeviceFilter"
    ) as mock_filter:
        mock_filter._get_device_slugs.return_value = ["unknown_type"]
        assert _get_device_type(flow, "32:123456") == "UNKNOWN_TYPE"

    # Test no slugs
    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.DeviceFilter"
    ) as mock_filter:
        mock_filter._get_device_slugs.return_value = []
        assert _get_device_type(flow, "32:123456") is None

    # Test device not found
    assert _get_device_type(flow, "nonexistent") is None


async def test_async_step_sensor_control_config_select_device(flow, helper):
    """Test the device selection stage."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"

    # Pre-processing (show form)
    await async_step_sensor_control_config(flow, None)
    flow.async_show_form.assert_called_once()
    assert flow.async_show_form.call_args[1]["step_id"] == "feature_config"

    # Post-processing (submit device)
    user_input = {"device_id": "32:123456"}
    await async_step_sensor_control_config(flow, user_input)
    assert flow._sensor_control_selected_device == "32:123456"
    assert flow._sensor_control_stage == "configure_device"


async def test_async_step_sensor_control_config_select_device_with_overview(
    flow, helper
):
    """Test the device selection stage with existing configuration overview."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"

    # Mock existing config to trigger overview generation
    flow._config_entry.options = {
        "sensor_control": {
            "sources": {
                "32_123456": {
                    "indoor_temperature": {
                        "kind": "external",
                        "entity_id": "sensor.test",
                    }
                }
            },
            "abs_humidity_inputs": {
                "32_123456": {
                    "indoor_abs_humidity": {
                        "temperature": {"kind": "external", "entity_id": "sensor.temp"},
                        "humidity": {"kind": "external", "entity_id": "sensor.hum"},
                    }
                }
            },
        }
    }

    await async_step_sensor_control_config(flow, None)
    flow.async_show_form.assert_called_once()
    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "Existing Sensor Control Mappings" in info_text
    assert "Device 32:123456" in info_text
    assert "indoor_temperature: external  sensor.test" in info_text
    assert "indoor_abs_humidity" in info_text


async def test_async_step_sensor_control_config_select_device_with_area_sensor_overview(
    flow, helper
):
    """Test global overview includes configured area sensors."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "source_id": "bathroom",
                        "label": "Bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "check_interval_minutes": 1,
                        "enabled": True,
                    }
                ]
            }
        }
    }

    await async_step_sensor_control_config(flow, None)
    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "area sensor Bathroom" in info_text
    assert "spike: 12.0%/3m" in info_text
    assert "check: 1m" in info_text


async def test_async_step_sensor_control_config_select_device_refresh(flow, helper):
    """Test that config entry is refreshed if possible."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"

    flow._refresh_config_entry = MagicMock()

    await async_step_sensor_control_config(flow, None)
    flow._refresh_config_entry.assert_called_once()


async def test_async_step_sensor_control_config_select_group_select(flow, helper):
    """Test selecting a group from the group selection menu."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        # Pre-processing
        await async_step_sensor_control_config(flow, None)
        flow.async_show_form.assert_called_once()

        # Post-processing - Select group
        user_input = {"group_action": "indoor_basic"}
        await async_step_sensor_control_config(flow, user_input)
        assert flow._sensor_control_group_stage == "indoor_basic"


async def test_async_step_sensor_control_config_select_group_done(flow, helper):
    """Test the 'done' action in the group selection menu."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        # Post-processing - Done
        user_input = {"group_action": "done"}
        await async_step_sensor_control_config(flow, user_input)
        assert flow._sensor_control_stage == "select_device"
        flow.async_step_main_menu.assert_called_once()


async def test_async_step_sensor_control_config_select_group_area_sensors(flow, helper):
    """Test selecting the area_sensors submenu from the group menu."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"group_action": "area_sensors"})
        assert flow._sensor_control_group_stage == "area_sensors_menu"


async def test_async_step_sensor_control_config_configure_group(flow, helper):
    """Test configuring a specific group."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "indoor_basic"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        # Pre-processing
        await async_step_sensor_control_config(flow, None)
        flow.async_show_form.assert_called_once()

        # Post-processing - Submit configuration
        user_input = {
            "indoor_temperature_kind": "internal",
            "indoor_humidity_kind": "internal",
        }
        await async_step_sensor_control_config(flow, user_input)

        # Verify state reset to select_group
        assert flow._sensor_control_group_stage == "select_group"
        # Verify config entry update called
        flow.hass.config_entries.async_update_entry.assert_called_once()


async def test_async_step_sensor_control_config_area_sensors_add_and_edit(flow, helper):
    """Test adding and editing an area sensor."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, {"area_sensor_action": "add"})
        assert flow._sensor_control_group_stage == "area_sensors_edit"

        user_input = {
            "area_sensor_label": "Bathroom",
            "area_sensor_enabled": True,
            "zone_id": "zone_1",
            "temperature_entity": "sensor.bath_temp",
            "humidity_entity": "sensor.bath_humidity",
            "spike_rise_percent": 15.0,
            "spike_window_minutes": 3,
            "check_interval_minutes": 1,
        }
        await async_step_sensor_control_config(flow, user_input)

        options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        area_sensors = options["sensor_control"]["area_sensors"]["32_123456"]
        assert len(area_sensors) == 1
        assert area_sensors[0]["source_id"] == "bathroom"
        assert area_sensors[0]["zone_id"] == "zone_1"
        assert flow._sensor_control_group_stage == "area_sensors_menu"

        flow._config_entry.options = options
        flow.hass.config_entries.async_update_entry.reset_mock()
        flow._sensor_control_area_sensor_id = "bathroom"
        flow._sensor_control_group_stage = "area_sensors_edit"

        edit_input = {
            "area_sensor_label": "Bathroom Shower",
            "area_sensor_enabled": False,
            "zone_id": "zone_2",
            "temperature_entity": "sensor.shower_temp",
            "humidity_entity": "sensor.shower_humidity",
            "spike_rise_percent": 18.0,
            "spike_window_minutes": 2,
            "check_interval_minutes": 2,
        }
        await async_step_sensor_control_config(flow, edit_input)

        edited_options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        edited_area_sensor = edited_options["sensor_control"]["area_sensors"][
            "32_123456"
        ][0]
        assert edited_area_sensor["source_id"] == "bathroom"
        assert edited_area_sensor["label"] == "Bathroom Shower"
        assert edited_area_sensor["enabled"] is False
        assert edited_area_sensor["zone_id"] == "zone_2"
        assert edited_area_sensor["check_interval_minutes"] == 2


async def test_async_step_sensor_control_config_area_sensors_delete(flow, helper):
    """Test deleting an area sensor."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "source_id": "bathroom",
                        "label": "Bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "check_interval_minutes": 1,
                        "enabled": True,
                    }
                ]
            }
        }
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(
            flow,
            {"area_sensor_action": "delete:bathroom"},
        )

        options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        assert options["sensor_control"]["area_sensors"]["32_123456"] == []
