"""Tests for temp_control platform entities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.temp_control.const import (
    TEMP_CONTROL_BOOLEAN_CONFIGS,
    TEMP_CONTROL_SELECT_CONFIGS,
    TEMP_CONTROL_SENSOR_CONFIGS,
    TEMP_CONTROL_SWITCH_CONFIGS,
)
from custom_components.ramses_extras.features.temp_control.platforms import (
    binary_sensor as tc_bs,
)
from custom_components.ramses_extras.features.temp_control.platforms import (
    select as tc_sel,
)
from custom_components.ramses_extras.features.temp_control.platforms import (
    sensor as tc_sn,
)
from custom_components.ramses_extras.features.temp_control.platforms import (
    switch as tc_sw,
)


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {"ramses_extras": {}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    hass.config_entries.async_update_entry = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    ce = MagicMock()
    ce.entry_id = "test_entry"
    ce.options = {}
    ce.data = {}
    return ce


class TestTempControlSwitch:
    """Test the switch platform."""

    def test_create(self, mock_hass):
        switches = asyncio.get_event_loop().run_until_complete(
            tc_sw.create_temp_control_switch(mock_hass, "32:153289")
        )
        assert len(switches) == 1
        assert isinstance(switches[0], tc_sw.TempControlSwitch)

    def test_default_off(self, mock_hass):
        config = list(TEMP_CONTROL_SWITCH_CONFIGS.values())[0]
        sw = tc_sw.TempControlSwitch(mock_hass, "32:153289", "temp_control", config)
        assert sw._is_on is False

    @pytest.mark.asyncio
    async def test_restores_last_state_on(self, mock_hass):
        config = list(TEMP_CONTROL_SWITCH_CONFIGS.values())[0]
        sw = tc_sw.TempControlSwitch(mock_hass, "32:153289", "temp_control", config)
        sw.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))
        sw.async_write_ha_state = MagicMock()

        await sw.async_added_to_hass()

        assert sw._is_on is True
        sw.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_last_state(self, mock_hass):
        config = list(TEMP_CONTROL_SWITCH_CONFIGS.values())[0]
        sw = tc_sw.TempControlSwitch(mock_hass, "32:153289", "temp_control", config)
        sw.async_get_last_state = AsyncMock(return_value=None)
        sw.async_write_ha_state = MagicMock()

        await sw.async_added_to_hass()

        sw.async_write_ha_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_on_off(self, mock_hass):
        config = list(TEMP_CONTROL_SWITCH_CONFIGS.values())[0]
        sw = tc_sw.TempControlSwitch(mock_hass, "32:153289", "temp_control", config)
        sw.async_write_ha_state = MagicMock()

        await sw.async_turn_on()
        assert sw._is_on is True

        await sw.async_turn_off()
        assert sw._is_on is False


class TestTempControlBinarySensor:
    """Test the binary_sensor platform."""

    def test_create(self, mock_hass):
        sensors = asyncio.get_event_loop().run_until_complete(
            tc_bs.create_temp_control_active_binary_sensor(mock_hass, "32:153289")
        )
        assert len(sensors) == 1
        assert isinstance(sensors[0], tc_bs.TempControlActiveBinarySensor)

    def test_set_state_with_attrs(self, mock_hass):
        config = list(TEMP_CONTROL_BOOLEAN_CONFIGS.values())[0]
        sensor = tc_bs.TempControlActiveBinarySensor(
            mock_hass, "32:153289", "temp_control_active", config
        )
        sensor.async_write_ha_state = MagicMock()

        sensor.set_state(True, {"mode": "cooling"})

        assert sensor._is_on is True
        assert sensor._automation_attrs == {"mode": "cooling"}

    def test_set_state_no_attrs(self, mock_hass):
        config = list(TEMP_CONTROL_BOOLEAN_CONFIGS.values())[0]
        sensor = tc_bs.TempControlActiveBinarySensor(
            mock_hass, "32:153289", "temp_control_active", config
        )
        sensor.async_write_ha_state = MagicMock()

        sensor.set_state(False)

        assert sensor._is_on is False
        assert sensor._automation_attrs == {}

    def test_extra_state_attributes(self, mock_hass):
        config = list(TEMP_CONTROL_BOOLEAN_CONFIGS.values())[0]
        sensor = tc_bs.TempControlActiveBinarySensor(
            mock_hass, "32:153289", "temp_control_active", config
        )
        sensor._automation_attrs = {"mode": "cooling", "temp": 24.0}

        attrs = sensor.extra_state_attributes
        assert attrs["mode"] == "cooling"
        assert attrs["temp"] == 24.0


class TestTempControlSensor:
    """Test the sensor platform."""

    def test_create(self, mock_hass):
        sensors = asyncio.get_event_loop().run_until_complete(
            tc_sn.create_temp_control_status_sensor(mock_hass, "32:153289")
        )
        assert len(sensors) == 1
        assert isinstance(sensors[0], tc_sn.TempControlStatusSensor)

    def test_default_value_disabled(self, mock_hass):
        config = list(TEMP_CONTROL_SENSOR_CONFIGS.values())[0]
        sensor = tc_sn.TempControlStatusSensor(
            mock_hass, "32:153289", "temp_control_status", config
        )
        assert sensor._attr_native_value == "disabled"

    def test_set_status_with_attrs(self, mock_hass):
        config = list(TEMP_CONTROL_SENSOR_CONFIGS.values())[0]
        sensor = tc_sn.TempControlStatusSensor(
            mock_hass, "32:153289", "temp_control_status", config
        )
        sensor.async_write_ha_state = MagicMock()

        sensor.set_status("cooling", {"mode": "cooling", "temp": 24.0})

        assert sensor._attr_native_value == "cooling"
        assert sensor._status_attrs == {
            "mode": "cooling",
            "temp": 24.0,
        }

    def test_set_status_no_attrs(self, mock_hass):
        config = list(TEMP_CONTROL_SENSOR_CONFIGS.values())[0]
        sensor = tc_sn.TempControlStatusSensor(
            mock_hass, "32:153289", "temp_control_status", config
        )
        sensor.async_write_ha_state = MagicMock()

        sensor.set_status("idle")

        assert sensor._attr_native_value == "idle"
        assert sensor._status_attrs == {}

    def test_extra_state_attributes(self, mock_hass):
        config = list(TEMP_CONTROL_SENSOR_CONFIGS.values())[0]
        sensor = tc_sn.TempControlStatusSensor(
            mock_hass, "32:153289", "temp_control_status", config
        )
        sensor._status_attrs = {"mode": "heating_retention"}

        attrs = sensor.extra_state_attributes
        assert "mode" in attrs


class TestTempControlSelect:
    """Test the select platform."""

    def test_create(self, mock_hass, mock_config_entry):
        selects = asyncio.get_event_loop().run_until_complete(
            tc_sel.create_temp_control_desired_speed_select(
                mock_hass, "32:153289", mock_config_entry
            )
        )
        assert len(selects) == 1
        assert isinstance(selects[0], tc_sel.TempControlDesiredSpeedSelect)

    def test_options(self, mock_hass, mock_config_entry):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        assert "low" in sel._attr_options
        assert "medium" in sel._attr_options
        assert "high" in sel._attr_options

    @pytest.mark.asyncio
    async def test_restores_last_state(self, mock_hass, mock_config_entry):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        sel.async_get_last_state = AsyncMock(return_value=MagicMock(state="medium"))
        sel.async_write_ha_state = MagicMock()

        await sel.async_added_to_hass()

        assert sel._attr_current_option == "medium"

    @pytest.mark.asyncio
    async def test_no_last_state_falls_back(self, mock_hass, mock_config_entry):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        sel.async_get_last_state = AsyncMock(return_value=None)
        sel.async_write_ha_state = MagicMock()

        await sel.async_added_to_hass()

        assert sel._attr_current_option in ("high", "low", "medium", None)

    @pytest.mark.asyncio
    async def test_async_select_option(self, mock_hass, mock_config_entry):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        sel.async_write_ha_state = MagicMock()

        async def fake_select(option):
            sel._attr_current_option = option

        with patch.object(
            type(sel).__mro__[1],
            "async_select_option",
            side_effect=fake_select,
        ):
            await sel.async_select_option("low")

        assert sel._attr_current_option == "low"

    def test_load_value_no_config_entry(self, mock_hass):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            None,
        )
        result = sel._load_value_from_config()
        assert result in ("high", "low", "medium")

    def test_load_value_legacy_store(self, mock_hass, mock_config_entry):
        mock_config_entry.options = {
            "temp_control": {"32_153289": {"desired_speed": "low"}},
        }
        mock_hass.config_entries.async_get_entry = MagicMock(
            return_value=mock_config_entry
        )

        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        assert sel._load_value_from_config() == "low"

    def test_load_value_canonical_store(self, mock_hass, mock_config_entry):
        mock_config_entry.options = {
            "ramses_extras": {
                "features": {
                    "temp_control": {
                        "32_153289": {"desired_speed": "medium"},
                    }
                }
            }
        }
        mock_hass.config_entries.async_get_entry = MagicMock(
            return_value=mock_config_entry
        )

        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )
        assert sel._load_value_from_config() == "medium"

    @pytest.mark.asyncio
    async def test_save_value_to_config(self, mock_hass, mock_config_entry):
        mock_config_entry.options = {}
        mock_hass.config_entries.async_get_entry = MagicMock(
            return_value=mock_config_entry
        )

        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            mock_config_entry,
        )

        await sel._save_value_to_config("low")

        mock_hass.config_entries.async_update_entry.assert_called_once()
        opts = mock_hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert opts["temp_control"]["32_153289"]["desired_speed"] == "low"
        assert (
            opts["ramses_extras"]["features"]["temp_control"]["32_153289"][
                "desired_speed"
            ]
            == "low"
        )

    @pytest.mark.asyncio
    async def test_save_value_no_config_entry(self, mock_hass):
        config = list(TEMP_CONTROL_SELECT_CONFIGS.values())[0]
        sel = tc_sel.TempControlDesiredSpeedSelect(
            mock_hass,
            "32:153289",
            "temp_control_desired_speed",
            config,
            None,
        )
        await sel._save_value_to_config("low")


class TestTempControlInit:
    """Test the feature factory."""

    def test_create_temp_control_feature(self, mock_hass, mock_config_entry):
        from custom_components.ramses_extras.features.temp_control import (
            create_temp_control_feature,
        )

        result = create_temp_control_feature(mock_hass, mock_config_entry)

        assert "automation" in result
        assert "config" in result
        assert "platforms" in result
        assert "entities" in result
        assert "switch" in result["platforms"]
        assert "select" in result["platforms"]
        assert "binary_sensor" in result["platforms"]
        assert "sensor" in result["platforms"]


class TestIsSupportedDevice:
    """Test is_supported_temp_control_device for each platform."""

    def test_switch_supported_yes(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch.find_ramses_device",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch.get_device_type",
                return_value="HvacVentilator",
            ),
        ):
            assert (
                tc_sw.is_supported_temp_control_device(mock_hass, "32:153289") is True
            )

    def test_switch_supported_no(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch.find_ramses_device",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch.get_device_type",
                return_value="Other",
            ),
        ):
            assert (
                tc_sw.is_supported_temp_control_device(mock_hass, "32:153289") is False
            )

    def test_binary_sensor_supported_yes(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor.find_ramses_device",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor.get_device_type",
                return_value="HvacVentilator",
            ),
        ):
            assert (
                tc_bs.is_supported_temp_control_device(mock_hass, "32:153289") is True
            )

    def test_binary_sensor_supported_no(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor.find_ramses_device",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor.get_device_type",
                return_value=None,
            ),
        ):
            assert (
                tc_bs.is_supported_temp_control_device(mock_hass, "32:153289") is False
            )

    def test_sensor_supported_yes(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.sensor.find_ramses_device",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.sensor.get_device_type",
                return_value="HvacVentilator",
            ),
        ):
            assert (
                tc_sn.is_supported_temp_control_device(mock_hass, "32:153289") is True
            )

    def test_select_supported_no(self, mock_hass):
        with (
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.select.find_ramses_device",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.select.get_device_type",
                return_value=None,
            ),
        ):
            assert (
                tc_sel.is_supported_temp_control_device(mock_hass, "32:153289") is False
            )


class TestAsyncSetupEntry:
    """Test async_setup_entry for each platform."""

    @pytest.mark.asyncio
    async def test_switch_no_filtered_devices(self, mock_hass):
        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "platform.PlatformSetup."
            "get_filtered_devices_for_feature",
            return_value=[],
        ):
            await tc_sw.async_setup_entry(mock_hass, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_switch_with_devices(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch."
                "is_supported_temp_control_device",
                return_value=True,
            ),
        ):
            await tc_sw.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_unsupported_device_skipped(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.switch."
                "is_supported_temp_control_device",
                return_value=False,
            ),
        ):
            await tc_sw.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_binary_sensor_no_filtered_devices(self, mock_hass):
        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "platform.PlatformSetup."
            "get_filtered_devices_for_feature",
            return_value=[],
        ):
            await tc_bs.async_setup_entry(mock_hass, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_binary_sensor_with_devices(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor."
                "is_supported_temp_control_device",
                return_value=True,
            ),
            patch(
                "custom_components.ramses_extras.framework."
                "helpers.platform.PlatformSetup."
                "_store_entities_for_automation",
            ),
        ):
            await tc_bs.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_binary_sensor_unsupported_skipped(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.binary_sensor."
                "is_supported_temp_control_device",
                return_value=False,
            ),
        ):
            await tc_bs.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sensor_no_filtered_devices(self, mock_hass):
        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "platform.PlatformSetup."
            "get_filtered_devices_for_feature",
            return_value=[],
        ):
            await tc_sn.async_setup_entry(mock_hass, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_sensor_with_devices(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.sensor."
                "is_supported_temp_control_device",
                return_value=True,
            ),
            patch(
                "custom_components.ramses_extras.framework."
                "helpers.platform.PlatformSetup."
                "_store_entities_for_automation",
            ),
        ):
            await tc_sn.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_sensor_unsupported_skipped(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.sensor."
                "is_supported_temp_control_device",
                return_value=False,
            ),
        ):
            await tc_sn.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_no_filtered_devices(self, mock_hass):
        with patch(
            "custom_components.ramses_extras.framework.helpers."
            "platform.PlatformSetup."
            "get_filtered_devices_for_feature",
            return_value=[],
        ):
            await tc_sel.async_setup_entry(mock_hass, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_select_unsupported_skipped(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.select."
                "is_supported_temp_control_device",
                return_value=False,
            ),
        ):
            await tc_sel.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_with_devices(self, mock_hass):
        mock_add = MagicMock()
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers."
                "platform.PlatformSetup."
                "get_filtered_devices_for_feature",
                return_value=["32:153289"],
            ),
            patch(
                "custom_components.ramses_extras.features."
                "temp_control.platforms.select."
                "is_supported_temp_control_device",
                return_value=True,
            ),
        ):
            await tc_sel.async_setup_entry(mock_hass, MagicMock(), mock_add)
            mock_add.assert_called_once()
