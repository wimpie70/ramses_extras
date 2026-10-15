"""Tests for features/default/platforms/sensor.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.platforms.sensor import (
    DefaultHumiditySensor,
    FanControlModeSensor,
    _check_underlying_entities_exist,
    _get_area_sensors_config,
    create_default_sensor,
)


def test_get_area_sensors_config_no_entry():
    """Test _get_area_sensors_config when no config entry"""
    hass = MagicMock()
    hass.data = {}
    result = _get_area_sensors_config(hass, "32:153289")
    assert result == []


def test_get_area_sensors_config_no_sensor_control():
    """Test _get_area_sensors_config when no sensor_control section"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert result == []


def test_get_area_sensors_config_with_area_sensors():
    """Test _get_area_sensors_config with valid area_sensors"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {
        "sensor_control": {
            "FANs": {"32_153289": {"area_sensors": [{"area_id": "living_room"}]}}
        }
    }
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={
            "FANs": {"32_153289": {"area_sensors": [{"area_id": "living_room"}]}}
        },
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={"area_sensors": [{"area_id": "living_room"}]},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["area_id"] == "living_room"


@pytest.mark.asyncio
async def test_check_underlying_entities_exist_non_absolute_humidity():
    """Test _check_underlying_entities_exist returns True for non-abs humidity."""
    hass = MagicMock()
    # fan_control_mode is not an absolute humidity sensor
    result = await _check_underlying_entities_exist(
        hass, "32:123456", "fan_control_mode"
    )
    assert result is True


def test_get_area_sensors_config_with_config_entry_param():
    """Test _get_area_sensors_config with config_entry parameter"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {}  # No entry in hass.data

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={},
        ):
            result = _get_area_sensors_config(
                hass, "32:153289", config_entry=mock_entry
            )
            assert result == []


def test_get_area_sensors_config_invalid_area_sensors_type():
    """Test _get_area_sensors_config when area_sensors is not a list"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={"area_sensors": "not_a_list"},
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert result == []


def test_get_area_sensors_config_filters_non_dict_items():
    """Test _get_area_sensors_config filters non-dict items"""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.get_sensor_control_device_section",
            return_value={
                "area_sensors": [{"area_id": "valid"}, "invalid_string", 123, None]
            },
        ):
            result = _get_area_sensors_config(hass, "32:153289")
            assert len(result) == 1
            assert result[0]["area_id"] == "valid"


def test_fan_control_mode_sensor_extra_state_attributes():
    """Test FanControlModeSensor extra_state_attributes property (lines 273-274)"""
    hass = MagicMock()
    mock_arbiter = MagicMock()
    mock_arbiter.get_device_debug_state.return_value = {"test": "value"}
    mock_arbiter.get_control_mode.return_value = "auto"

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_fan_speed_arbiter",
        return_value=mock_arbiter,
    ):
        sensor = FanControlModeSensor(hass, "32:123456", "fan_control_mode", {})
        attrs = sensor.extra_state_attributes

        assert "test" in attrs
        assert attrs["test"] == "value"
        mock_arbiter.get_device_debug_state.assert_called_once_with("32:123456")


@pytest.mark.asyncio
async def test_default_humidity_sensor_queue_recalculate_in_progress():
    """Test _queue_recalculate when recalculation is in progress (lines 564-566)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})
    sensor._recalc_in_progress = True

    await sensor._queue_recalculate()
    # Should set _recalc_requested and return early
    assert sensor._recalc_requested is True


@pytest.mark.asyncio
async def test_default_humidity_sensor_queue_recalculate_success():
    """Test _queue_recalculate successful execution (lines 568-576)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})
    sensor._recalculate_and_update = AsyncMock()

    await sensor._queue_recalculate()
    # Should execute recalculation and reset _recalc_in_progress
    assert sensor._recalc_in_progress is False
    sensor._recalculate_and_update.assert_called_once()


@pytest.mark.asyncio
async def test_default_humidity_sensor_recalculate_and_update_exception():
    """Test _recalculate_and_update exception handling (lines 612-613)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Mock to raise an exception
    sensor._get_area_temp_and_humidity_result = MagicMock(
        side_effect=Exception("test error")
    )
    sensor._area_sensor = {"temperature_entity": "temp", "humidity_entity": "humidity"}

    # Should handle exception gracefully
    await sensor._recalculate_and_update()
    # Should not raise exception


@pytest.mark.asyncio
async def test_default_humidity_sensor_recalculate_and_update_no_change():
    """Test _recalculate_and_update when value hasn't changed (lines 601-604)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})
    sensor._attr_native_value = 10.0

    # Mock to return same value
    sensor._get_area_temp_and_humidity_result = MagicMock(return_value=10.0)
    sensor._area_sensor = {"temperature_entity": "temp", "humidity_entity": "humidity"}

    with patch.object(sensor, "async_write_ha_state") as mock_write:
        await sensor._recalculate_and_update()
        # Should not call async_write_ha_state since value hasn't changed
        mock_write.assert_not_called()


@pytest.mark.asyncio
async def test_default_humidity_sensor_recalculate_and_update_with_sensor_control():
    """Test _recalculate_and_update with sensor_control (lines 591-595)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Mock to return value from sensor_control
    sensor._async_compute_abs_from_sensor_control = AsyncMock(return_value=15.0)
    sensor._area_sensor = None

    with patch.object(sensor, "async_write_ha_state") as mock_write:
        await sensor._recalculate_and_update()
        # Should call async_write_ha_state with new value
        mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_default_humidity_sensor_recalculate_and_update_fallback():
    """Test _recalculate_and_update fallback to temp/humidity (lines 597-599)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Mock sensor_control to return None
    sensor._async_compute_abs_from_sensor_control = AsyncMock(return_value=None)
    sensor._get_temp_and_humidity = MagicMock(return_value=(20.0, 50.0))
    sensor._calculate_abs_humidity = MagicMock(return_value=8.5)
    sensor._area_sensor = None

    with patch.object(sensor, "async_write_ha_state") as mock_write:
        await sensor._recalculate_and_update()
        # Should call async_write_ha_state with calculated value
        mock_write.assert_called_once()
        sensor._get_temp_and_humidity.assert_called_once()
        sensor._calculate_abs_humidity.assert_called_once_with(20.0, 50.0)


def test_default_humidity_sensor_get_temp_and_humidity_unknown_type():
    """Test _get_temp_and_humidity with unknown sensor type (lines 630-634)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "unknown_type", {})

    result = sensor._get_temp_and_humidity()
    # Should return None, None for unknown sensor type
    assert result == (None, None)


def test_default_humidity_sensor_get_temp_and_humidity_missing_entity():
    """Test _get_temp_and_humidity with missing humidity entity (lines 702-708)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Mock states to return None for humidity entity
    hass.states.get = MagicMock(
        side_effect=lambda x: None if "humidity" in x else MagicMock(state="20")
    )

    result = sensor._get_temp_and_humidity()
    # Should return None, None for missing humidity entity
    assert result == (None, None)


def test_default_humidity_sensor_get_temp_and_humidity_parse_error():
    """Test _get_temp_and_humidity with parse error (lines 723-725)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Mock states to raise ValueError when parsing
    mock_temp_state = MagicMock(state="invalid")
    mock_humidity_state = MagicMock(state="50")
    hass.states.get = MagicMock(
        side_effect=lambda x: mock_temp_state if "temp" in x else mock_humidity_state
    )

    result = sensor._get_temp_and_humidity()
    # Should return None, None for parse error
    assert result == (None, None)


def test_default_humidity_sensor_get_area_temp_and_humidity_missing_state():
    """Test _get_area_temp_and_humidity_result with missing state (line 736)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(
        hass,
        "32:123456",
        "area_absolute_humidity",
        {"temperature_entity": "temp", "humidity_entity": "humidity"},
    )

    # Mock states to return None for humidity entity
    hass.states.get = MagicMock(
        side_effect=lambda x: None if "humidity" in x else MagicMock(state="20")
    )

    result = sensor._get_area_temp_and_humidity_result()
    # Should return None for missing state
    assert result is None


def test_default_humidity_sensor_get_area_temp_and_humidity_unavailable_state():
    """Test _get_area_temp_and_humidity_result with unavailable state (lines 738-740)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(
        hass,
        "32:123456",
        "area_absolute_humidity",
        {"temperature_entity": "temp", "humidity_entity": "humidity"},
    )

    # Mock states to return unavailable for temp entity
    hass.states.get = MagicMock(
        side_effect=lambda x: (
            MagicMock(state="unavailable") if "temp" in x else MagicMock(state="50")
        )
    )

    result = sensor._get_area_temp_and_humidity_result()
    # Should return None for unavailable state
    assert result is None


def test_default_humidity_sensor_get_area_temp_and_humidity_invalid_humidity():
    """Test _get_area_temp_and_humidity_result with invalid humidity (line 749)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(
        hass,
        "32:123456",
        "area_absolute_humidity",
        {"temperature_entity": "temp", "humidity_entity": "humidity"},
    )

    # Mock states to return invalid humidity value
    hass.states.get = MagicMock(
        side_effect=lambda x: (
            MagicMock(state="20") if "temp" in x else MagicMock(state="150")
        )
    )

    result = sensor._get_area_temp_and_humidity_result()
    # Should return None for invalid humidity
    assert result is None


def test_default_humidity_sensor_is_sensor_control_enabled():
    """Test _is_sensor_control_enabled (lines 893-906)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Test with sensor_control enabled
    hass.data.get = MagicMock(
        return_value={
            "config_entry": MagicMock(
                data={}, options={"enabled_features": {"sensor_control": True}}
            )
        }
    )
    result = sensor._is_sensor_control_enabled()
    assert result is True

    # Test with sensor_control disabled
    hass.data.get = MagicMock(
        return_value={
            "config_entry": MagicMock(
                data={}, options={"enabled_features": {"sensor_control": False}}
            )
        }
    )
    result = sensor._is_sensor_control_enabled()
    assert result is False

    # Test with no config_entry
    hass.data.get = MagicMock(return_value={})
    result = sensor._is_sensor_control_enabled()
    assert result is False


def test_default_humidity_sensor_get_device_type():
    """Test _get_device_type (lines 914-929)"""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "indoor_absolute_humidity", {})

    # Test with device found (dict)
    hass.data.get = MagicMock(
        return_value={"devices": [{"device_id": "32:123456", "type": "FAN"}]}
    )
    result = sensor._get_device_type("32:123456")
    assert result == "FAN"

    # Test with device not found
    hass.data.get = MagicMock(
        return_value={"devices": [{"device_id": "32:999999", "type": "FAN"}]}
    )
    result = sensor._get_device_type("32:123456")
    assert result is None

    # Test with no devices
    hass.data.get = MagicMock(return_value={"devices": []})
    result = sensor._get_device_type("32:123456")
    assert result is None


def test_default_humidity_sensor_get_abs_temperature_kind():
    """Test _get_abs_temperature_kind reads the stored sensor_control config."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data = {"ramses_extras": {"config_entry": mock_entry}}
    sensor = DefaultHumiditySensor(hass, "32:123456", "outdoor_absolute_humidity", {})

    sensor_control_section = {
        "devices": {
            "32:123456": {
                "abs_humidity_inputs": {
                    "outdoor_abs_humidity": {
                        "temperature": {"kind": "internal_supply"},
                        "humidity": {"kind": "internal"},
                    }
                }
            }
        }
    }

    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value=sensor_control_section,
    ):
        assert (
            sensor._get_abs_temperature_kind("outdoor_abs_humidity")
            == "internal_supply"
        )

    # No sensor_control section → default "internal"
    with patch(
        "custom_components.ramses_extras.features.default.platforms.sensor.get_migrated_feature_section",
        return_value={},
    ):
        assert sensor._get_abs_temperature_kind("outdoor_abs_humidity") == "internal"


@pytest.mark.asyncio
async def test_default_humidity_sensor_abs_internal_supply_uses_supply_temp():
    """internal_supply pairs the outdoor RH with the supply temperature."""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "outdoor_absolute_humidity", {})
    sensor._is_sensor_control_enabled = MagicMock(return_value=True)
    sensor._get_device_type = MagicMock(return_value="FAN")
    sensor._resolve_cc_sensor_entity_id = MagicMock(
        return_value="sensor.32_123456_supply_temp"
    )

    resolver_result = {
        "abs_humidity_inputs": {
            "outdoor_abs_humidity": {
                "temperature": {"kind": "internal_supply"},
                "humidity": {"kind": "internal"},
            }
        },
        "mappings": {
            "outdoor_temperature": "sensor.32_123456_outdoor_temp",
            "outdoor_humidity": "sensor.32_123456_outdoor_humidity",
        },
    }

    states = {
        "sensor.32_123456_supply_temp": MagicMock(state="14.0"),
        "sensor.32_123456_outdoor_humidity": MagicMock(state="70"),
    }
    hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))

    mock_resolver = MagicMock()
    mock_resolver.resolve_entity_mappings = AsyncMock(return_value=resolver_result)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver",
            return_value=mock_resolver,
        ),
        patch(
            "custom_components.ramses_extras.framework.helpers.common.calculate_absolute_humidity",
            return_value=9.1,
        ) as mock_calc,
    ):
        result = await sensor._async_compute_abs_from_sensor_control()

    assert result == 9.1
    sensor._resolve_cc_sensor_entity_id.assert_called_once_with("supply_temp")
    # The outdoor temperature mapping must NOT be used for the pairing
    mock_calc.assert_called_once_with(14.0, 70.0)


@pytest.mark.asyncio
async def test_default_humidity_sensor_abs_internal_uses_outdoor_temp():
    """Default internal pairing still uses the outdoor temperature."""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "outdoor_absolute_humidity", {})
    sensor._is_sensor_control_enabled = MagicMock(return_value=True)
    sensor._get_device_type = MagicMock(return_value="FAN")

    resolver_result = {
        "abs_humidity_inputs": {
            "outdoor_abs_humidity": {
                "temperature": {"kind": "internal"},
                "humidity": {"kind": "internal"},
            }
        },
        "mappings": {
            "outdoor_temperature": "sensor.32_123456_outdoor_temp",
            "outdoor_humidity": "sensor.32_123456_outdoor_humidity",
        },
    }

    states = {
        "sensor.32_123456_outdoor_temp": MagicMock(state="10.0"),
        "sensor.32_123456_outdoor_humidity": MagicMock(state="70"),
    }
    hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))

    mock_resolver = MagicMock()
    mock_resolver.resolve_entity_mappings = AsyncMock(return_value=resolver_result)

    with (
        patch(
            "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver",
            return_value=mock_resolver,
        ),
        patch(
            "custom_components.ramses_extras.framework.helpers.common.calculate_absolute_humidity",
            return_value=5.4,
        ) as mock_calc,
    ):
        result = await sensor._async_compute_abs_from_sensor_control()

    assert result == 5.4
    mock_calc.assert_called_once_with(10.0, 70.0)


@pytest.mark.asyncio
async def test_default_humidity_sensor_setup_listeners_internal_supply():
    """_setup_listeners subscribes to supply_temp for internal_supply."""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "outdoor_absolute_humidity", {})
    sensor._area_sensor = None
    sensor._get_abs_temperature_kind = MagicMock(return_value="internal_supply")

    registry = MagicMock()
    registry.async_get = MagicMock(return_value=MagicMock())

    captured: dict = {}

    def _fake_track(_hass, entities, _callback):
        captured["entities"] = entities

    with (
        patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.async_track_state_change_event",
            side_effect=_fake_track,
        ),
        patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ),
    ):
        await sensor._setup_listeners()

    assert "sensor.32_123456_supply_temp" in captured["entities"]
    assert "sensor.32_123456_outdoor_humidity" in captured["entities"]
    assert sensor._listeners_set_up is True


@pytest.mark.asyncio
async def test_default_humidity_sensor_setup_listeners_default_outdoor():
    """_setup_listeners keeps outdoor_temp for the default pairing."""
    hass = MagicMock()
    sensor = DefaultHumiditySensor(hass, "32:123456", "outdoor_absolute_humidity", {})
    sensor._area_sensor = None
    sensor._get_abs_temperature_kind = MagicMock(return_value="internal")

    registry = MagicMock()
    registry.async_get = MagicMock(return_value=MagicMock())

    captured: dict = {}

    def _fake_track(_hass, entities, _callback):
        captured["entities"] = entities

    with (
        patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.async_track_state_change_event",
            side_effect=_fake_track,
        ),
        patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ),
    ):
        await sensor._setup_listeners()

    assert "sensor.32_123456_outdoor_temp" in captured["entities"]
    assert "sensor.32_123456_outdoor_humidity" in captured["entities"]
