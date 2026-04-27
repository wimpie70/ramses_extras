"""Tests for CO2 Control number platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.platforms.number import (
    CO2ControlNumber,
    create_co2_number,
    create_co2_number_entities,
    number_async_setup_entry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def config():
    """Mock configuration."""
    return {
        "min_value": 400.0,
        "max_value": 2000.0,
        "step": 10.0,
        "default_value": 1000.0,
        "unit": "ppm",
    }


def test_create_co2_number(hass, config):
    """Test creating a CO2 control number entity (covers lines 32-45, 76)."""
    device_id = "32:123456"
    number_type = "threshold"
    config_entry = MagicMock()

    number_entity = create_co2_number(
        hass, device_id, number_type, config, config_entry
    )

    assert isinstance(number_entity, CO2ControlNumber)
    assert number_entity.device_id == device_id
    assert number_entity._attr_native_min_value == 400.0
    assert number_entity._attr_native_max_value == 2000.0
    assert number_entity._attr_native_step == 10.0
    assert number_entity._attr_native_value == 1000.0
    assert number_entity._attr_native_unit_of_measurement == "ppm"


def test_co2_control_number_native_value(hass, config):
    """Test CO2ControlNumber native_value property (covers line 52)."""
    device_id = "32:123456"
    number_type = "threshold"

    number_entity = CO2ControlNumber(hass, device_id, number_type, config)

    assert number_entity.native_value == 1000.0

    # Test with None value
    number_entity._attr_native_value = None
    assert number_entity.native_value == 1000.0  # Should return default 1000.0


@pytest.mark.asyncio
async def test_co2_control_number_async_set_native_value(hass, config):
    """Test CO2ControlNumber async_set_native_value (covers lines 58-60)."""
    device_id = "32:123456"
    number_type = "threshold"

    number_entity = CO2ControlNumber(hass, device_id, number_type, config)
    number_entity.async_write_ha_state = MagicMock()

    await number_entity.async_set_native_value(1500.0)

    assert number_entity._attr_native_value == 1500.0
    number_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_create_co2_number_entities(hass, config):
    """Test create_co2_number_entities (covers lines 86-91)."""
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {
        "threshold": config,
        "upper_limit": config,
    }

    entities = await create_co2_number_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 2
    assert all(isinstance(entity, CO2ControlNumber) for entity in entities)


@pytest.mark.asyncio
async def test_create_co2_number_entities_empty(hass):
    """Test create_co2_number_entities with empty configs (covers lines 86-91)."""
    device_id = "32:123456"
    config_entry = MagicMock()

    entity_configs = {}

    entities = await create_co2_number_entities(
        hass, device_id, entity_configs, config_entry
    )

    assert len(entities) == 0


@pytest.mark.asyncio
async def test_number_async_setup_entry(hass, config):
    """Test number_async_setup_entry (covers lines 100-102)."""
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.const.CO2_NUMBER_CONFIGS",
            {"threshold": config},
        ),
        patch(
            "custom_components.ramses_extras.features.co2_control.platforms.number.PlatformSetup.async_create_and_add_platform_entities",
            AsyncMock(),
        ) as mock_setup,
    ):
        await number_async_setup_entry(hass, config_entry, async_add_entities)

        mock_setup.assert_called_once()
