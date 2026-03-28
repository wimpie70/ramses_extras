"""Tests for CO2 Control entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.co2_control.entities import CO2Entities


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def config():
    """Mock configuration."""
    return {
        "enabled": True,
        "automation_enabled": True,
        "default_threshold": 1000,
    }


def test_co2_entities_init(hass, config):
    """Test CO2Entities initialization."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    assert entities.hass == hass
    assert entities.device_id == device_id
    assert entities.config == config
    assert entities._entities == {}


@pytest.mark.asyncio
async def test_co2_entities_async_setup(hass, config):
    """Test CO2Entities async_setup."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    result = await entities.async_setup()
    assert result is True


def test_co2_entities_get_entity_not_found(hass, config):
    """Test getting entity that doesn't exist."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    entity = entities.get_entity("switch", "test_switch")
    assert entity is None


def test_co2_entities_get_entity_found(hass, config):
    """Test getting entity that exists."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    # Register an entity
    mock_entity = MagicMock()
    entities.register_entity("switch", "test_switch", mock_entity)

    # Get the entity
    entity = entities.get_entity("switch", "test_switch")
    assert entity == mock_entity


def test_co2_entities_register_entity(hass, config):
    """Test registering an entity."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    # Register an entity
    mock_entity = MagicMock()
    entities.register_entity("switch", "test_switch", mock_entity)

    # Check it was registered
    entity_id = "switch.test_switch_test_device"
    assert entity_id in entities._entities
    assert entities._entities[entity_id] == mock_entity


def test_co2_entities_register_multiple_entities(hass, config):
    """Test registering multiple entities."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    # Register multiple entities
    mock_switch = MagicMock()
    mock_number = MagicMock()
    mock_sensor = MagicMock()

    entities.register_entity("switch", "co2_control", mock_switch)
    entities.register_entity("number", "threshold", mock_number)
    entities.register_entity("sensor", "status", mock_sensor)

    # Check all were registered
    assert len(entities._entities) == 3
    assert "switch.co2_control_test_device" in entities._entities
    assert "number.threshold_test_device" in entities._entities
    assert "sensor.status_test_device" in entities._entities


def test_co2_entities_get_different_types(hass, config):
    """Test getting entities of different types."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    # Register entities of different types
    mock_switch = MagicMock()
    mock_binary_sensor = MagicMock()

    entities.register_entity("switch", "control", mock_switch)
    entities.register_entity("binary_sensor", "state", mock_binary_sensor)

    # Get entities
    switch_entity = entities.get_entity("switch", "control")
    binary_sensor_entity = entities.get_entity("binary_sensor", "state")

    assert switch_entity == mock_switch
    assert binary_sensor_entity == mock_binary_sensor


def test_co2_entities_entity_id_format(hass, config):
    """Test entity ID format includes device_id."""
    device_id = "32:123456789ABC"
    entities = CO2Entities(hass, device_id, config)

    # Register an entity
    mock_entity = MagicMock()
    entities.register_entity("switch", "test", mock_entity)

    # Check entity ID format
    expected_id = "switch.test_32:123456789ABC"
    assert expected_id in entities._entities


def test_co2_entities_overwrite_entity(hass, config):
    """Test overwriting an existing entity."""
    device_id = "test_device"
    entities = CO2Entities(hass, device_id, config)

    # Register initial entity
    mock_entity1 = MagicMock()
    entities.register_entity("switch", "test", mock_entity1)

    # Overwrite with new entity
    mock_entity2 = MagicMock()
    entities.register_entity("switch", "test", mock_entity2)

    # Check it was overwritten
    entity_id = "switch.test_test_device"
    assert entities._entities[entity_id] == mock_entity2
    assert entities._entities[entity_id] != mock_entity1
