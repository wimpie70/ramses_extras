"""Tests for Hello World feature platforms (switch and binary_sensor)."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.hello_world.const import (
    HELLO_WORLD_BINARY_SENSOR_CONFIGS,
    HELLO_WORLD_SWITCH_CONFIGS,
)
from custom_components.ramses_extras.features.hello_world.platforms.binary_sensor import (  # noqa: E501
    HelloWorldBinarySensor,
    create_hello_world_binary_sensor,
)
from custom_components.ramses_extras.features.hello_world.platforms.switch import (
    HelloWorldSwitch,
    create_hello_world_switch,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    return hass


class TestHelloWorldSwitch:
    """Test cases for HelloWorldSwitch."""

    def test_init(self, hass):
        """Test initialization."""
        config = HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]
        switch = HelloWorldSwitch(hass, "32:123456", "hello_world_switch", config)
        assert switch.device_id == "32:123456"
        assert switch.is_on is False

    async def test_turn_on_off(self, hass):
        """Test turn_on and turn_off methods."""
        config = HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]
        switch = HelloWorldSwitch(hass, "32:123456", "hello_world_switch", config)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()
        assert switch.is_on is True
        switch.async_write_ha_state.assert_called_once()

        await switch.async_turn_off()
        assert switch.is_on is False
        assert switch.async_write_ha_state.call_count == 2

    def test_extra_state_attributes(self, hass):
        """Test extra state attributes."""
        config = HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]
        switch = HelloWorldSwitch(hass, "32:123456", "hello_world_switch", config)
        attrs = switch.extra_state_attributes
        assert attrs["hello_world_active"] is False
        assert attrs["demo_feature"] is True


class TestHelloWorldBinarySensor:
    """Test cases for HelloWorldBinarySensor."""

    def test_init(self, hass):
        """Test initialization."""
        config = HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]
        sensor = HelloWorldBinarySensor(hass, "32:123456", "hello_world_status", config)
        assert sensor.device_id == "32:123456"
        assert sensor.is_on is False

    def test_set_state(self, hass):
        """Test set_state method."""
        config = HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]
        sensor = HelloWorldBinarySensor(hass, "32:123456", "hello_world_status", config)
        sensor.async_write_ha_state = MagicMock()

        sensor.set_state(True)
        assert sensor.is_on is True
        sensor.async_write_ha_state.assert_called_once()

        sensor.set_state(False)
        assert sensor.is_on is False
        assert sensor.async_write_ha_state.call_count == 2

    def test_extra_state_attributes(self, hass):
        """Test extra state attributes."""
        config = HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]
        sensor = HelloWorldBinarySensor(hass, "32:123456", "hello_world_status", config)
        attrs = sensor.extra_state_attributes
        assert attrs["automation_controlled"] is True
        assert "switch_entity" in attrs


async def test_create_hello_world_switch(hass):
    """Test create_hello_world_switch factory."""
    entities = await create_hello_world_switch(
        hass, "32:123456", HELLO_WORLD_SWITCH_CONFIGS
    )
    assert len(entities) == 1
    assert isinstance(entities[0], HelloWorldSwitch)


async def test_create_hello_world_binary_sensor(hass):
    """Test create_hello_world_binary_sensor factory."""
    entities = await create_hello_world_binary_sensor(
        hass, "32:123456", HELLO_WORLD_BINARY_SENSOR_CONFIGS
    )
    assert len(entities) == 1
    assert isinstance(entities[0], HelloWorldBinarySensor)
