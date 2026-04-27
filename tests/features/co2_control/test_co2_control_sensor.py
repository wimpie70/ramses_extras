"""Tests for CO2 Control sensor platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.platforms.sensor import (
    CO2ControlSensor,
    create_co2_sensor,
    create_co2_sensor_entities,
    sensor_async_setup_entry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def config():
    """Mock configuration."""
    return {
        "enabled": True,
    }


def test_create_co2_sensor(hass, config):
    """Test creating a CO2 control sensor entity (covers line 67)."""
    device_id = "32:123456"
    sensor_type = "zone_status"

    sensor_entity = create_co2_sensor(hass, device_id, sensor_type, config)

    assert isinstance(sensor_entity, CO2ControlSensor)
    assert sensor_entity.device_id == device_id
    assert sensor_entity._zone_status is None


def test_co2_control_sensor_native_value(hass, config):
    """Test CO2ControlSensor native_value property."""
    device_id = "32:123456"
    sensor_type = "zone_status"

    sensor_entity = CO2ControlSensor(hass, device_id, sensor_type, config)

    assert sensor_entity.native_value == "unknown"

    sensor_entity._zone_status = "active"
    assert sensor_entity.native_value == "active"


def test_co2_control_sensor_extra_state_attributes(hass, config):
    """Test CO2ControlSensor extra_state_attributes property."""
    device_id = "32:123456"
    sensor_type = "zone_status"

    sensor_entity = CO2ControlSensor(hass, device_id, sensor_type, config)

    assert sensor_entity.extra_state_attributes == {}

    sensor_entity._automation_attrs = {"zone_id": "zone_1"}
    assert sensor_entity.extra_state_attributes == {"zone_id": "zone_1"}


def test_co2_control_sensor_set_zone_status_no_change(hass, config):
    """Test set_zone_status when status hasn't changed (covers line 53)."""
    device_id = "32:123456"
    sensor_type = "zone_status"

    sensor_entity = CO2ControlSensor(hass, device_id, sensor_type, config)
    sensor_entity.async_write_ha_state = MagicMock()

    # Set initial state
    sensor_entity.set_zone_status("active", {"zone_id": "zone_1"})
    sensor_entity.async_write_ha_state.reset_mock()

    # Set status with same values - should not call async_write_ha_state
    sensor_entity.set_zone_status("active", {"zone_id": "zone_1"})

    sensor_entity.async_write_ha_state.assert_not_called()


def test_co2_control_sensor_set_zone_status_with_change(hass, config):
    """Test set_zone_status when status changes."""
    device_id = "32:123456"
    sensor_type = "zone_status"

    sensor_entity = CO2ControlSensor(hass, device_id, sensor_type, config)
    sensor_entity.async_write_ha_state = MagicMock()

    # Set status with different values - should call async_write_ha_state
    sensor_entity.set_zone_status("active", {"zone_id": "zone_1"})

    assert sensor_entity._zone_status == "active"
    assert sensor_entity._automation_attrs == {"zone_id": "zone_1"}
    sensor_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_create_co2_sensor_entities(hass, config):
    """Test create_co2_sensor_entities (covers lines 77-80)."""
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {
        "zone_status": config,
        "worst_zone": config,
    }

    entities = await create_co2_sensor_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 2
    assert all(isinstance(entity, CO2ControlSensor) for entity in entities)


@pytest.mark.asyncio
async def test_create_co2_sensor_entities_empty(hass):
    """Test create_co2_sensor_entities with empty configs (covers lines 77-80)."""
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {}

    entities = await create_co2_sensor_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 0


@pytest.mark.asyncio
async def test_sensor_async_setup_entry(hass, config):
    """Test sensor_async_setup_entry (covers lines 89-91)."""
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.const.CO2_SENSOR_CONFIGS",
            {"zone_status": config},
        ),
        patch(
            "custom_components.ramses_extras.features.co2_control.platforms.sensor.PlatformSetup.async_create_and_add_platform_entities",
            AsyncMock(),
        ) as mock_setup,
    ):
        await sensor_async_setup_entry(hass, config_entry, async_add_entities)

        mock_setup.assert_called_once()
