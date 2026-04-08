"""Tests for sensor_control feature config flow."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.sensor_control.config_flow import (
    _async_handle_rems_edit,
    _async_handle_rems_menu,
    _device_key,
    _get_area_id_options,
    _get_area_id_options_from_legacy,
    _get_device_type,
    _get_rem_device_options,
    async_step_sensor_control_config,
)
from custom_components.ramses_extras.framework.helpers.config.validation import (
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
)


@pytest.fixture
def flow():
    """Mock the central options flow."""
    flow = MagicMock()
    flow._config_entry = MagicMock()
    flow._config_entry.options = {"sensor_control": {}}
    flow._config_entry.data = {}
    flow.hass = MagicMock()
    flow.hass.data = {DOMAIN: {"config_entry": flow._config_entry}}
    flow._get_config_flow_helper = MagicMock()
    flow._get_all_devices = MagicMock(return_value=["32:123456"])
    flow._extract_device_id = MagicMock(side_effect=lambda x: x)
    flow._get_device_label = MagicMock(side_effect=lambda x: f"Device {x}")
    flow.async_show_form = MagicMock()
    flow.async_step_main_menu = AsyncMock()
    flow._refresh_config_entry = MagicMock()
    return flow


@pytest.fixture
def helper():
    """Mock the config flow helper."""
    helper = MagicMock()
    helper.get_devices_for_feature_selection.return_value = ["32:123456"]
    return helper


def _get_persisted_sensor_control_sections(
    options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    legacy = options["sensor_control"]
    canonical = options["ramses_extras"]["features"]["sensor_control"]
    return legacy, canonical


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
                },
            },
            "abs_humidity_inputs": {
                "32_123456": {
                    "indoor_abs_humidity": {
                        "temperature": {"kind": "external", "entity_id": "sensor.abs"},
                        "humidity": {"kind": "internal"},
                    }
                }
            },
        }
    }

    await async_step_sensor_control_config(flow, None)
    flow.async_show_form.assert_called_once()
    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "Existing FAN Configuration Mappings" in info_text
    assert "Device 32:123456" in info_text
    assert "sensor.test" in info_text
    assert "temp: external  sensor.abs" in info_text


async def test_select_device_abs_overview_variants(
    flow,
    helper,
):
    """Test global overview formatting for varied absolute humidity mappings."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"
    flow._config_entry.options = {
        "sensor_control": {
            "abs_humidity_inputs": {
                "32_123456": {
                    "indoor_abs_humidity": {
                        "temperature": {
                            "kind": "external_abs",
                            "entity_id": "sensor.abs",
                        },
                        "humidity": {"kind": "internal"},
                    },
                    "outdoor_abs_humidity": {
                        "temperature": {
                            "kind": "external_temp",
                            "entity_id": "sensor.outdoor_temp",
                        },
                        "humidity": {"kind": "none"},
                    },
                }
            }
        }
    }

    await async_step_sensor_control_config(flow, None)
    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "external abs  sensor.abs" in info_text
    assert "humidity: none" in info_text


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
                        "area_id": "bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "enabled": True,
                    }
                ]
            }
        }
    }

    await async_step_sensor_control_config(flow, None)
    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "area sensor bathroom" in info_text
    assert "spike: 12.0%/3m" in info_text
    assert "max RH trigger" in info_text


async def test_async_step_sensor_control_config_select_device_with_canonical_root_overview(  # noqa: E501
    flow, helper
):
    """The overview should also read canonical-root sensor_control config."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "select_device"
    flow._config_entry.options = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                "sensor_control": {
                    "devices": {
                        "32:123456": {
                            "sources": {
                                "indoor_temperature": {
                                    "kind": "external",
                                    "entity_id": "sensor.test",
                                }
                            },
                            "abs_humidity_inputs": {
                                "indoor_abs_humidity": {
                                    "temperature": {
                                        "kind": "external_abs",
                                        "entity_id": "sensor.abs",
                                    },
                                    "humidity": {"kind": "none"},
                                }
                            },
                            "area_sensors": [
                                {
                                    "area_id": "bathroom",
                                    "temperature_entity": "sensor.bath_temp",
                                    "humidity_entity": "sensor.bath_humidity",
                                    "trigger_on_high_humidity": True,
                                }
                            ],
                        }
                    }
                }
            },
        }
    }

    await async_step_sensor_control_config(flow, None)

    info_text = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
    assert "Existing FAN Configuration Mappings" in info_text
    assert "Device 32:123456" in info_text
    assert "sensor.test" in info_text
    assert "external abs  sensor.abs" in info_text
    assert "area sensor bathroom" in info_text


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

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        # Pre-processing
        await async_step_sensor_control_config(flow, None)
        flow.async_show_form.assert_called_once()

        # Post-processing - Select group
        user_input = {"action": "area_sensors"}
        await async_step_sensor_control_config(flow, user_input)
        assert flow._sensor_control_group_stage == "area_sensors_menu"


async def test_async_step_sensor_control_config_select_group_shows_area_sensors(
    flow, helper
):
    """The FAN group menu should expose the area sensors entry."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, None)

    config = flow.async_show_form.call_args.kwargs["data_schema"].schema["action"]
    options = config.config["options"]
    assert any(option["value"] == "area_sensors" for option in options)


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
        user_input = {"action": "done"}
        await async_step_sensor_control_config(flow, user_input)
        assert flow._sensor_control_stage == "select_device"
        flow.async_step_main_menu.assert_called_once()


async def test_async_step_sensor_control_config_select_group_area_sensors(flow, helper):
    """Test selecting the area_sensors submenu from the group menu."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(flow, {"action": "area_sensors"})
        assert flow._sensor_control_group_stage == "area_sensors_menu"


async def test_async_step_sensor_control_config_configure_group(flow, helper):
    """Test configuring a specific group."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors"

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        # Pre-processing
        await async_step_sensor_control_config(flow, None)
        flow.async_show_form.assert_called_once()

        # Post-processing - Submit configuration
        user_input = {
            "indoor_temperature_kind": "external",
            "indoor_temperature_entity": "sensor.indoor_temp",
            "indoor_humidity_kind": "internal",
        }
        await async_step_sensor_control_config(flow, user_input)

        # Verify state reset to select_group (no update for invalid group_stage)
        assert flow._sensor_control_group_stage == "select_group"
        # async_update_entry should NOT be called for unknown group_stage


async def test_async_step_sensor_control_config_area_sensors_edit_selection(
    flow, helper
):
    """Edit selection should store the selected source id."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(
            flow, {"action": "edit", "area_id": "bathroom"}
        )

    assert flow._sensor_control_group_stage == "area_sensors_edit"
    assert flow._sensor_control_area_sensor_id == "bathroom"


async def test_async_step_sensor_control_config_area_sensors_add_and_edit(flow, helper):
    """Test adding and editing an area sensor."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(flow, {"action": "add"})
        assert flow._sensor_control_group_stage == "area_sensors_edit"

        user_input = {
            "area_id": "Bathroom",
            "area_sensor_enabled": True,
            "temperature_entity": "input_number.temp_helper",
            "humidity_entity": "input_number.humid_helper",
            "trigger_on_high_humidity": True,
            "spike_rise_percent": 5.0,
            "spike_window_minutes": 3,
            "area_co2_enabled": True,
            "co2_entity": "input_number.co2_helper",
            "co2_threshold_entity": "input_number.bathroom_co2_threshold",
            "co2_threshold": 800,
        }
        await async_step_sensor_control_config(flow, user_input)

        options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        legacy, canonical = _get_persisted_sensor_control_sections(options)
        area_sensor = legacy["area_sensors"]["32_123456"][0]
        assert area_sensor["area_id"] == "Bathroom"
        assert area_sensor["co2_entity"] == "input_number.co2_helper"
        assert (
            area_sensor["co2_threshold_entity"] == "input_number.bathroom_co2_threshold"
        )
        assert area_sensor["co2_threshold"] == 800
        assert canonical["devices"]["32:123456"]["area_sensors"][0] == area_sensor
        assert flow._sensor_control_group_stage == "area_sensors_menu"

        flow._config_entry.options = options
        flow.hass.config_entries.async_update_entry.reset_mock()
        flow._sensor_control_area_sensor_id = "Bathroom"
        flow._sensor_control_group_stage = "area_sensors_edit"

        edit_input = {
            "area_id": "Bathroom Shower",
            "area_sensor_enabled": False,
            "zone_id": "zone_2",
            "temperature_entity": "sensor.shower_temp",
            "humidity_entity": "sensor.shower_humidity",
            "trigger_on_high_humidity": False,
            "spike_rise_percent": 18.0,
            "spike_window_minutes": 2,
        }
        await async_step_sensor_control_config(flow, edit_input)

        edited_options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        edited_legacy, edited_canonical = _get_persisted_sensor_control_sections(
            edited_options
        )
        edited_area_sensor = edited_legacy["area_sensors"]["32_123456"][0]
        assert edited_area_sensor["area_id"] == "Bathroom Shower"
        assert edited_area_sensor["enabled"] is False
        assert edited_area_sensor["zone_id"] == "zone_2"
        assert edited_area_sensor["trigger_on_high_humidity"] is False
        assert (
            edited_canonical["devices"]["32:123456"]["area_sensors"][0]
            == edited_area_sensor
        )


async def test_area_sensors_edit_cascades_area_id_to_remote_binding(flow, helper):
    """Renaming an area_id should update REM bindings referencing it."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_edit"
    flow._sensor_control_area_sensor_id = "Bathroom"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "area_id": "Bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 10.0,
                        "spike_window_minutes": 3,
                        "enabled": True,
                        "area_co2_enabled": True,
                        "co2_entity": "sensor.bath_co2",
                        "co2_threshold": 800,
                    }
                ]
            }
        },
        "remote_binding": {
            "FANs": {
                "32:123456": {
                    "REMs": [
                        {
                            "rem_id": "12:111111",
                            "role": "primary",
                            "enabled": True,
                            "area_id": "Bathroom",
                        }
                    ]
                }
            }
        },
    }

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "area_id": "Dining",
                "area_sensor_enabled": True,
                "zone_id": "zone_2",
                "temperature_entity": "sensor.dining_temp",
                "humidity_entity": "sensor.dining_humidity",
                "trigger_on_high_humidity": True,
                "spike_rise_percent": 10.0,
                "spike_window_minutes": 3,
                "area_co2_enabled": True,
                "co2_entity": "sensor.dining_co2",
                "co2_threshold_entity": "",
                "co2_threshold": 800,
            },
        )

    saved_options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
        "options"
    ]
    saved_remote_binding = saved_options["remote_binding"]["FANs"]["32:123456"]
    assert saved_remote_binding["REMs"][0]["area_id"] == "Dining"


async def test_area_sensors_save_co2_threshold_entity_per_area(flow, helper):
    """Area sensor should persist co2_threshold_entity and static fallback."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(flow, {"action": "add"})

        await async_step_sensor_control_config(
            flow,
            {
                "area_id": "area_sensor",
                "area_sensor_enabled": True,
                "temperature_entity": "input_number.temp_helper",
                "humidity_entity": "input_number.humid_helper",
                "trigger_on_high_humidity": True,
                "spike_rise_percent": 5.0,
                "spike_window_minutes": 3,
                "area_co2_enabled": True,
                "co2_entity": "input_number.co2_helper",
                "co2_threshold_entity": "input_number.bathroom_co2_threshold",
                "co2_threshold": 800,
            },
        )

    options = flow.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    legacy, canonical = _get_persisted_sensor_control_sections(options)
    area_sensor = legacy["area_sensors"]["32_123456"][0]
    assert area_sensor["area_id"] == "area_sensor"
    assert area_sensor["co2_entity"] == "input_number.co2_helper"
    assert area_sensor["co2_threshold_entity"] == "input_number.bathroom_co2_threshold"
    assert area_sensor["co2_threshold"] == 800
    assert canonical["devices"]["32:123456"]["area_sensors"][0] == area_sensor


async def test_area_sensors_edit_preserves_other_area_co2_settings(flow, helper):
    """Editing one area should keep other area's CO2 settings unchanged."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_edit"
    flow._sensor_control_area_sensor_id = "bathroom"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "area_id": "bathroom",
                        "temperature_entity": "input_number.temp_helper",
                        "humidity_entity": "input_number.humid_helper",
                        "area_co2_enabled": True,
                        "co2_entity": "input_number.co2_helper",
                        "co2_threshold_entity": "input_number.bathroom_co2_threshold",
                        "co2_threshold": 800,
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 5.0,
                        "spike_window_minutes": 3,
                    },
                    {
                        "area_id": "kitchen",
                        "temperature_entity": "sensor.kitchen_temp",
                        "humidity_entity": "sensor.kitchen_humidity",
                        "area_co2_enabled": True,
                        "co2_entity": "sensor.kitchen_co2",
                        "co2_threshold_entity": "input_number.kitchen_co2_threshold",
                        "co2_threshold": 950,
                        "trigger_on_high_humidity": False,
                        "spike_rise_percent": 10.0,
                        "spike_window_minutes": 5,
                    },
                ]
            }
        }
    }

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "area_id": "bathroom",
                "area_sensor_enabled": True,
                "temperature_entity": "input_number.temp_helper",
                "humidity_entity": "input_number.humid_helper",
                "trigger_on_high_humidity": True,
                "spike_rise_percent": 6.0,
                "spike_window_minutes": 3,
                "area_co2_enabled": True,
                "co2_entity": "input_number.co2_helper",
                "co2_threshold_entity": "input_number.bathroom_co2_threshold",
                "co2_threshold": 820,
            },
        )

    updated = flow.hass.config_entries.async_update_entry.call_args.kwargs["options"][
        "sensor_control"
    ]["area_sensors"]["32_123456"]
    legacy, canonical = _get_persisted_sensor_control_sections(
        flow.hass.config_entries.async_update_entry.call_args.kwargs["options"]
    )
    assert updated[0]["area_id"] == "bathroom"
    assert updated[0]["co2_threshold"] == 820
    assert updated[1]["area_id"] == "kitchen"
    assert updated[1]["co2_threshold"] == 950
    assert updated[1]["co2_entity"] == "sensor.kitchen_co2"
    assert updated[1]["co2_threshold_entity"] == "input_number.kitchen_co2_threshold"
    assert legacy["area_sensors"]["32_123456"] == updated
    assert canonical["devices"]["32:123456"]["area_sensors"] == updated


async def test_async_step_sensor_control_config_area_sensors_edit_preserves_others(
    flow, helper
):
    """Editing one area sensor should keep non-edited entries intact."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_edit"
    flow._sensor_control_area_sensor_id = "bathroom"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "area_id": "bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "enabled": True,
                    },
                    {
                        "area_id": "kitchen",
                        "temperature_entity": "sensor.kitchen_temp",
                        "humidity_entity": "sensor.kitchen_humidity",
                        "trigger_on_high_humidity": False,
                        "spike_rise_percent": 10.0,
                        "spike_window_minutes": 5,
                        "enabled": True,
                    },
                ]
            }
        }
    }

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "area_id": "Bathroom Updated",
                "area_sensor_enabled": True,
                "temperature_entity": "sensor.bath_temp_2",
                "humidity_entity": "sensor.bath_humidity_2",
                "trigger_on_high_humidity": True,
                "spike_rise_percent": 14.0,
                "spike_window_minutes": 4,
            },
        )

    updated = flow.hass.config_entries.async_update_entry.call_args.kwargs["options"][
        "sensor_control"
    ]["area_sensors"]["32_123456"]
    assert len(updated) == 2
    assert updated[0]["area_id"] == "Bathroom Updated"
    assert updated[1]["area_id"] == "kitchen"


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
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "enabled": True,
                    }
                ]
            }
        }
    }

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {"action": "delete", "area_id": "bathroom"},
        )

        options = flow.hass.config_entries.async_update_entry.call_args.kwargs[
            "options"
        ]
        legacy, canonical = _get_persisted_sensor_control_sections(options)
        assert legacy["area_sensors"]["32_123456"] == []
        assert canonical["devices"]["32:123456"]["area_sensors"] == []


async def test_async_step_sensor_control_config_area_sensors_menu_back(flow, helper):
    """Test returning from the area sensors menu to group selection."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(flow, {"action": "back"})

    assert flow._sensor_control_group_stage == "select_group"


async def test_async_step_sensor_control_config_area_sensors_menu_shows_edit_options(
    flow, helper
):
    """Configured area sensors should appear in the menu info and actions."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "area_sensors_menu"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "area_id": "",
                        "label": "Ignored",
                        "temperature_entity": "sensor.ignore_temp",
                        "humidity_entity": "sensor.ignore_humidity",
                    },
                    {
                        "area_id": "bathroom",
                        "label": "Bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
                        "enabled": True,
                    },
                ]
            }
        }
    }

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        await async_step_sensor_control_config(flow, None)

    info_text = flow.async_show_form.call_args.kwargs["description_placeholders"][
        "info"
    ]
    assert "Existing area sensors:" in info_text
    assert "area sensor bathroom" in info_text


async def test_async_step_sensor_control_config_selectors_allow_input_number(
    flow, helper
):
    """Selectors should allow sensor, number and input_number entities."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
            return_value="FAN",
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            return_value={},
        ),
    ):
        flow._sensor_control_group_stage = "area_sensors_menu"
        await async_step_sensor_control_config(flow, None)
        # area_sensors_menu doesn't have temperature_entity/humidity_entity fields

        flow.async_show_form.reset_mock()
        flow._sensor_control_group_stage = "area_sensors_edit"
        flow._sensor_control_area_sensor_id = None
        await async_step_sensor_control_config(flow, None)
        area_schema = flow.async_show_form.call_args.kwargs["data_schema"].schema
        area_temp_selector = area_schema["temperature_entity"]
        area_hum_selector = area_schema["humidity_entity"]
        assert "check_interval_minutes" not in area_schema
        assert "trigger_on_high_humidity" in area_schema
        assert area_temp_selector.config["domain"] == [
            "sensor",
            "number",
            "input_number",
        ]
        assert area_hum_selector.config["domain"] == [
            "sensor",
            "number",
            "input_number",
        ]


async def test_async_step_sensor_control_config_device_overview_formats_mappings(
    flow, helper
):
    """Device overview should summarize source and abs humidity mappings."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"
    flow._config_entry.options = {
        "sensor_control": {
            "sources": {
                "32_123456": {
                    "indoor_temperature": {
                        "kind": "external",
                        "entity_id": "sensor.indoor_temp",
                    },
                    "indoor_humidity": {"kind": "none"},
                    "outdoor_temperature": {"kind": "derived"},
                    "outdoor_humidity": {"kind": "external"},
                }
            },
            "abs_humidity_inputs": {
                "32_123456": {
                    "indoor_abs_humidity": {
                        "temperature": {
                            "kind": "external_abs",
                            "entity_id": "sensor.indoor_abs",
                        },
                        "humidity": {"kind": "internal"},
                    },
                    "outdoor_abs_humidity": {
                        "temperature": {
                            "kind": "external_temp",
                            "entity_id": "sensor.outdoor_temp",
                        },
                        "humidity": {"kind": "none"},
                    },
                }
            },
        }
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow._get_device_type",
        return_value="FAN",
    ):
        await async_step_sensor_control_config(flow, None)

    info_text = flow.async_show_form.call_args.kwargs["description_placeholders"][
        "info"
    ]
    assert "indoor_temperature: external  sensor.indoor_temp" in info_text
    assert "indoor_humidity: disabled" in info_text
    assert "outdoor_temperature: derived" in info_text
    assert "outdoor_humidity: external (no entity)" in info_text
    assert "external abs  sensor.indoor_abs" in info_text
    assert "temp: external  sensor.outdoor_temp" in info_text
    assert "humidity: none" in info_text


async def test_async_step_sensor_control_config_device_overview_includes_area_sensors(
    flow, helper
):
    """Device overview should include area sensor descriptions."""
    flow._get_config_flow_helper.return_value = helper
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_group_stage = "select_group"
    flow._config_entry.options = {
        "sensor_control": {
            "area_sensors": {
                "32_123456": [
                    {
                        "area_id": "bathroom",
                        "label": "Bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 12.0,
                        "spike_window_minutes": 3,
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
        await async_step_sensor_control_config(flow, None)

    info_text = flow.async_show_form.call_args.kwargs["description_placeholders"][
        "info"
    ]
    assert "Current mappings for this device" in info_text
    assert "area sensor bathroom" in info_text


# ---------------------------------------------------------------------------
# Additional coverage for zones_import, REM menus, and helper builders
# ---------------------------------------------------------------------------


def _prepare_zones_import(flow: MagicMock) -> None:
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_group_stage = "zones_import"
    flow._sensor_control_selected_device = "32:123456"
    flow._config_entry.options = {FEATURE_ZONES: {}}
    flow.hass.data[DOMAIN]["config_entry"] = flow._config_entry
    flow.async_show_form.reset_mock()


async def test_zones_import_back_action(flow):
    _prepare_zones_import(flow)

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
        AsyncMock(return_value={"labels": {}, "errors": {}}),
    ):
        await async_step_sensor_control_config(flow, {"action": "back"})

    assert flow._sensor_control_group_stage == "zones_menu"


async def test_zones_import_empty_yaml(flow):
    _prepare_zones_import(flow)
    translations = {
        "labels": {},
        "errors": {"yaml_content_required": "YAML content is required"},
    }

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
        AsyncMock(return_value=translations),
    ):
        await async_step_sensor_control_config(
            flow,
            {"action": "import", "yaml_content": "", "overwrite_existing": False},
        )

    errors = flow.async_show_form.call_args.kwargs["errors"]
    assert errors["yaml_content"] == "YAML content is required"


async def test_zones_import_without_zones(flow):
    _prepare_zones_import(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(
                return_value={"labels": {}, "errors": {"no_zones_in_yaml": "No zones"}}
            ),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.parse_zones_yaml",
            return_value={"zones": []},
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "action": "import",
                "yaml_content": "zones: []",
                "overwrite_existing": False,
            },
        )

    errors = flow.async_show_form.call_args.kwargs["errors"]
    assert errors["yaml_content"] == "No zones"


async def test_zones_import_parse_error(flow):
    _prepare_zones_import(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(return_value={"labels": {}, "errors": {}}),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.parse_zones_yaml",
            side_effect=ValueError("Invalid YAML"),
        ),
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "action": "import",
                "yaml_content": "invalid",
                "overwrite_existing": False,
            },
        )

    errors = flow.async_show_form.call_args.kwargs["errors"]
    assert errors["yaml_content"] == "Invalid YAML"


async def test_zones_import_success(flow):
    _prepare_zones_import(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(return_value={"labels": {}, "errors": {}}),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.parse_zones_yaml",
            return_value={"zones": [{"zone_id": "bath"}]},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.merge_zones_config",
            return_value=[{"zone_id": "bath"}],
        ) as mock_merge,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.set_fan_section",
        ) as mock_set,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._persist_zones_section",
        ) as mock_persist,
    ):
        await async_step_sensor_control_config(
            flow,
            {
                "action": "import",
                "yaml_content": "zones:\n  - zone_id: bath",
                "overwrite_existing": True,
            },
        )

    mock_merge.assert_called_once()
    mock_set.assert_called_once()
    mock_persist.assert_called_once()
    assert flow._sensor_control_group_stage == "zones_menu"


async def test_zones_import_form_display(flow):
    _prepare_zones_import(flow)

    with patch(
        "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
        AsyncMock(return_value={"labels": {}, "errors": {}}),
    ):
        await async_step_sensor_control_config(flow, None)

    flow.async_show_form.assert_called_once()


def _prepare_rems_menu_flow(flow: MagicMock) -> None:
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_group_stage = "rems_menu"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_editing_rem_id = None
    flow._config_entry.options = {FEATURE_REMOTE_BINDING: {}}
    flow.hass.data[DOMAIN] = {"config_entry": flow._config_entry, "devices": []}


async def test_rems_menu_form_display(flow):
    _prepare_rems_menu_flow(flow)

    fan_rems = [{"rem_id": "18:1", "enabled": True}]
    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=fan_rems,
        ),
    ):
        result = await _async_handle_rems_menu(flow, MagicMock(), "32:123456", None)

    assert result == flow.async_show_form.return_value


async def test_rems_menu_add_edit_back_actions(flow):
    _prepare_rems_menu_flow(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_step_sensor_control_config",
            AsyncMock(return_value={"type": "form"}),
        ) as mock_step,
    ):
        await _async_handle_rems_menu(flow, MagicMock(), "32:123456", {"action": "add"})
        await _async_handle_rems_menu(
            flow, MagicMock(), "32:123456", {"action": "back"}
        )
        await _async_handle_rems_menu(
            flow,
            MagicMock(),
            "32:123456",
            {"action": "edit:18:1"},
        )

    assert flow._sensor_control_group_stage == "rems_edit"
    assert flow._sensor_control_editing_rem_id == "18:1"
    assert mock_step.await_count == 3


async def test_rems_menu_delete_action(flow):
    _prepare_rems_menu_flow(flow)
    fan_rems = [{"rem_id": "18:1"}, {"rem_id": "18:2"}]

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={"FANs": {"32:123456": {"REMs": fan_rems}}},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=fan_rems,
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.set_fan_section",
        ) as mock_set,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._persist_remote_binding_section",
        ) as mock_persist,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_step_sensor_control_config",
            AsyncMock(return_value={"type": "form"}),
        ),
    ):
        await _async_handle_rems_menu(
            flow, MagicMock(), "32:123456", {"action": "delete:18:1"}
        )

    mock_set.assert_called_once()
    mock_persist.assert_called_once()


def _prepare_rems_edit_flow(flow: MagicMock) -> None:
    flow._sensor_control_stage = "configure_device"
    flow._sensor_control_group_stage = "rems_edit"
    flow._sensor_control_selected_device = "32:123456"
    flow._sensor_control_editing_rem_id = None
    flow._config_entry.options = {
        FEATURE_REMOTE_BINDING: {},
        FEATURE_ZONES: {},
    }
    flow.hass.data[DOMAIN]["config_entry"] = flow._config_entry


async def test_rems_edit_validation_errors(flow):
    _prepare_rems_edit_flow(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(
                return_value={"labels": {}, "errors": {"rem_id_required": "Required"}}
            ),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_rem_device_options",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_area_id_options",
            return_value=[],
        ),
    ):
        await _async_handle_rems_edit(flow, MagicMock(), "32:123456", {"rem_id": ""})

    errors = flow.async_show_form.call_args.kwargs["errors"]
    assert errors["rem_id"] == "Required"


async def test_rems_edit_duplicate(flow):
    _prepare_rems_edit_flow(flow)
    flow._sensor_control_editing_rem_id = None
    fan_rems = [{"rem_id": "18:1"}]

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=fan_rems,
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(
                return_value={"labels": {}, "errors": {"rem_id_exists": "Exists"}}
            ),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_rem_device_options",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_area_id_options",
            return_value=[],
        ),
    ):
        await _async_handle_rems_edit(
            flow,
            MagicMock(),
            "32:123456",
            {"rem_id": "18:1", "enabled": True},
        )

    errors = flow.async_show_form.call_args.kwargs["errors"]
    assert errors["rem_id"] == "Exists"


async def test_rems_edit_success(flow):
    _prepare_rems_edit_flow(flow)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(return_value={"labels": {}, "errors": {}}),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.set_fan_section",
        ) as mock_set,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._persist_remote_binding_section",
        ) as mock_persist,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_rem_device_options",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_area_id_options",
            return_value=[],
        ),
    ):
        await _async_handle_rems_edit(
            flow,
            MagicMock(),
            "32:123456",
            {
                "rem_id": "18:1",
                "enabled": True,
                "zone_id": "zone1",
                "area_id": "bath",
            },
        )

    mock_set.assert_called_once()
    mock_persist.assert_called_once()
    assert flow._sensor_control_group_stage == "rems_menu"


async def test_rems_edit_success_existing(flow):
    _prepare_rems_edit_flow(flow)
    flow._sensor_control_editing_rem_id = "18:1"
    fan_rems = [{"rem_id": "18:1", "enabled": False}]

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=fan_rems,
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(return_value={"labels": {}, "errors": {}}),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.set_fan_section",
        ) as mock_set,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._persist_remote_binding_section",
        ) as mock_persist,
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_rem_device_options",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_area_id_options",
            return_value=[],
        ),
    ):
        await _async_handle_rems_edit(
            flow,
            MagicMock(),
            "32:123456",
            {
                "rem_id": "18:1",
                "enabled": False,
                "zone_id": "zone2",
                "area_id": "kitchen",
            },
        )

    mock_set.assert_called_once()
    mock_persist.assert_called_once()
    assert flow._sensor_control_editing_rem_id is None


async def test_rems_edit_form_display(flow):
    _prepare_rems_edit_flow(flow)
    flow._sensor_control_editing_rem_id = "18:1"
    fan_rems = [{"rem_id": "18:1", "enabled": True}]

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_migrated_feature_section",
            return_value={},
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_remote_binding_rems",
            return_value=fan_rems,
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.async_get_feature_translations",
            AsyncMock(return_value={"labels": {}, "errors": {}}),
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow.get_zones_for_fan",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_rem_device_options",
            return_value=[],
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.config_flow._get_area_id_options",
            return_value=[],
        ),
    ):
        result = await _async_handle_rems_edit(flow, MagicMock(), "32:123456", None)

    assert result == flow.async_show_form.return_value


def test_get_area_id_options_combines_sources():
    options = {
        FEATURE_SENSOR_CONTROL: {"area_sensors": {"32_123456": [{"area_id": "bath"}]}},
        "ramses_extras": {
            "features": {
                "sensor_control": {
                    "devices": {"32:123456": {"area_sensors": [{"area_id": "kitchen"}]}}
                }
            }
        },
    }

    values = [opt["value"] for opt in _get_area_id_options(options, "32:123456")]
    assert "bath" in values and "kitchen" in values


def test_get_rem_device_options_includes_configured():
    hass = MagicMock()

    class Device:
        id = "18:123456"
        slugs = ["DIS"]

    hass.data = {
        DOMAIN: {
            "devices": ["18:000002", "01:999999", Device()],
            "config_entry": MagicMock(data={}, options={}),
        }
    }

    values = [opt["value"] for opt in _get_rem_device_options(hass)]
    assert "18:000002" in values
    assert "01:999999" not in values


def test_get_area_id_options_from_legacy_reads_rems():
    options = {
        "ramses_extras": {
            "features": {
                "sensor_control": {
                    "devices": {"32:123456": {"area_sensors": [{"area_id": "bath"}]}}
                }
            }
        },
        FEATURE_REMOTE_BINDING: {
            "FANs": {"32:123456": {"REMs": [{"rem_id": "18:1", "area_id": "hall"}]}}
        },
    }

    values = [
        opt["value"] for opt in _get_area_id_options_from_legacy(options, "32:123456")
    ]
    assert "bath" in values and "hall" in values
