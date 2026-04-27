"""Tests for CO2 control binary sensor platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.platforms.binary_sensor import (  # noqa: E501
    CO2ControlBinarySensor,
    binary_sensor_async_setup_entry,
    create_co2_binary_sensor_entities,
    create_co2_control_binary_sensor,
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


def test_create_co2_control_binary_sensor(hass, config):
    """Test creating a CO2 control binary sensor entity (covers line 66)."""
    device_id = "32:123456"
    sensor_type = "co2_active"

    sensor_entity = create_co2_control_binary_sensor(
        hass, device_id, sensor_type, config
    )

    assert isinstance(sensor_entity, CO2ControlBinarySensor)
    assert sensor_entity.device_id == device_id
    assert sensor_entity._attr_is_on is False


def test_co2_control_binary_sensor_is_on(hass, config):
    """Test CO2ControlBinarySensor is_on property."""
    device_id = "32:123456"
    sensor_type = "co2_active"

    sensor_entity = CO2ControlBinarySensor(hass, device_id, sensor_type, config)

    assert sensor_entity.is_on is False

    sensor_entity._attr_is_on = True
    assert sensor_entity.is_on is True


def test_co2_control_binary_sensor_extra_state_attributes(hass, config):
    """Test CO2ControlBinarySensor extra_state_attributes property."""
    device_id = "32:123456"
    sensor_type = "co2_active"

    sensor_entity = CO2ControlBinarySensor(hass, device_id, sensor_type, config)

    assert sensor_entity.extra_state_attributes == {}

    sensor_entity._automation_attrs = {"threshold": 1000}
    assert sensor_entity.extra_state_attributes == {"threshold": 1000}


def test_co2_control_binary_sensor_set_state_no_change(hass, config):
    """Test set_state when state hasn't changed (covers line 52)."""
    device_id = "32:123456"
    sensor_type = "co2_active"

    sensor_entity = CO2ControlBinarySensor(hass, device_id, sensor_type, config)
    sensor_entity.async_write_ha_state = MagicMock()

    # Set state with same values - should not call async_write_ha_state
    sensor_entity.set_state(False, {})

    sensor_entity.async_write_ha_state.assert_not_called()


def test_co2_control_binary_sensor_set_state_with_change(hass, config):
    """Test set_state when state changes."""
    device_id = "32:123456"
    sensor_type = "co2_active"

    sensor_entity = CO2ControlBinarySensor(hass, device_id, sensor_type, config)
    sensor_entity.async_write_ha_state = MagicMock()

    # Set state with different values - should call async_write_ha_state
    sensor_entity.set_state(True, {"threshold": 1000})

    assert sensor_entity._attr_is_on is True
    assert sensor_entity._automation_attrs == {"threshold": 1000}
    sensor_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_create_co2_binary_sensor_entities(hass, config):
    """Test create_co2_binary_sensor_entities (covers lines 76-81)."""
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {
        "co2_active": config,
        "co2_automation_active": config,
    }

    entities = await create_co2_binary_sensor_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 2
    assert all(isinstance(entity, CO2ControlBinarySensor) for entity in entities)


@pytest.mark.asyncio
async def test_create_co2_binary_sensor_entities_empty(hass):
    """Test create_co2_binary_sensor_entities with empty configs (covers lines 76-81)."""  # noqa: E501
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {}

    entities = await create_co2_binary_sensor_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 0


@pytest.mark.asyncio
async def test_binary_sensor_async_setup_entry(hass, config):
    """Test binary_sensor_async_setup_entry (covers lines 90-92)."""
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.const.CO2_BINARY_SENSOR_CONFIGS",
            {"co2_active": config},
        ),
        patch(
            "custom_components.ramses_extras.features.co2_control.platforms.binary_sensor.PlatformSetup.async_create_and_add_platform_entities",
            AsyncMock(),
        ) as mock_setup,
    ):
        await binary_sensor_async_setup_entry(hass, config_entry, async_add_entities)

        mock_setup.assert_called_once()
