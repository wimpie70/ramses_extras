"""Tests for CO2 Control switch platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.platforms.switch import (
    CO2ControlSwitch,
    create_co2_switch,
    create_co2_switch_entities,
    switch_async_setup_entry,
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


def test_create_co2_switch(hass, config):
    """Test creating a CO2 control switch entity (covers lines 37-38, 71)."""
    device_id = "32:123456"
    switch_entity = create_co2_switch(hass, device_id, config)

    assert isinstance(switch_entity, CO2ControlSwitch)
    assert switch_entity.device_id == device_id
    assert switch_entity.hass == hass
    assert switch_entity._attr_is_on is False


def test_co2_control_switch_is_on(hass, config):
    """Test CO2ControlSwitch is_on property (covers line 43)."""
    device_id = "32:123456"
    switch_entity = CO2ControlSwitch(hass, device_id, config)

    assert switch_entity.is_on is False

    switch_entity._attr_is_on = True
    assert switch_entity.is_on is True


@pytest.mark.asyncio
async def test_co2_control_switch_async_added_to_hass(hass, config):
    """Test CO2ControlSwitch async_added_to_hass restores state (covers lines 47-50)."""
    device_id = "32:123456"
    switch_entity = CO2ControlSwitch(hass, device_id, config)

    # Mock async_get_last_state to return a state
    last_state = MagicMock()
    last_state.state = "on"
    switch_entity.async_get_last_state = AsyncMock(return_value=last_state)

    await switch_entity.async_added_to_hass()

    # Should restore the state
    assert switch_entity._attr_is_on is True


@pytest.mark.asyncio
async def test_co2_control_switch_async_turn_on(hass, config):
    """Test CO2ControlSwitch async_turn_on (covers lines 54-56)."""
    device_id = "32:123456"
    switch_entity = CO2ControlSwitch(hass, device_id, config)

    switch_entity.async_write_ha_state = MagicMock()

    await switch_entity.async_turn_on()

    assert switch_entity._attr_is_on is True
    switch_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_co2_control_switch_async_turn_off(hass, config):
    """Test CO2ControlSwitch async_turn_off (covers lines 60-62)."""
    device_id = "32:123456"
    switch_entity = CO2ControlSwitch(hass, device_id, config)
    switch_entity._attr_is_on = True

    switch_entity.async_write_ha_state = MagicMock()

    await switch_entity.async_turn_off()

    assert switch_entity._attr_is_on is False
    switch_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_create_co2_switch_entities(hass, config):
    """Test create_co2_switch_entities (covers lines 81-87)."""
    device_id = "32:123456"

    with patch(
        "custom_components.ramses_extras.features.co2_control.const.CO2_SWITCH_CONFIGS",
        {"co2_control": config},
    ):
        entities = await create_co2_switch_entities(hass, device_id, {}, None)

        assert len(entities) == 1
        assert isinstance(entities[0], CO2ControlSwitch)


@pytest.mark.asyncio
async def test_create_co2_switch_entities_no_config(hass, config):
    """Test create_co2_switch_entities with no config (covers lines 81-87)."""
    device_id = "32:123456"

    with patch(
        "custom_components.ramses_extras.features.co2_control.const.CO2_SWITCH_CONFIGS",
        {"co2_control": None},
    ):
        entities = await create_co2_switch_entities(hass, device_id, {}, None)

        assert len(entities) == 0


@pytest.mark.asyncio
async def test_switch_async_setup_entry(hass, config):
    """Test switch_async_setup_entry (covers lines 96-98)."""
    config_entry = MagicMock()
    async_add_entities = MagicMock()

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.const.CO2_SWITCH_CONFIGS",
            {"co2_control": config},
        ),
        patch(
            "custom_components.ramses_extras.features.co2_control.platforms.switch.PlatformSetup.async_create_and_add_platform_entities",
            AsyncMock(),
        ) as mock_setup,
    ):
        await switch_async_setup_entry(hass, config_entry, async_add_entities)

        mock_setup.assert_called_once()
