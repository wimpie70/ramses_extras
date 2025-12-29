"""Tests for Humidity Control Entities."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control.entities import (
    HumidityEntities,
    create_humidity_entities,
)


class TestHumidityEntities:
    """Test cases for HumidityEntities class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock()
        self.entities_manager = HumidityEntities(self.hass, self.config_entry)

    def test_init(self):
        """Test initialization."""
        assert self.entities_manager.hass == self.hass
        assert self.entities_manager.config_entry == self.config_entry
        assert self.entities_manager._entities == {}
        assert "sensor" in self.entities_manager._entity_configs

    async def test_async_setup_entities(self):
        """Test setting up all entities for a device."""
        device_id = "32_123456"

        # Test setup
        created = await self.entities_manager.async_setup_entities(device_id)

        assert "sensor" in created
        assert "switch" in created
        assert "number" in created
        assert "binary_sensor" in created

        # Check that entities were actually stored in the manager
        all_entities = self.entities_manager.get_all_entities()
        assert len(all_entities) > 0

        # Check specific entity format
        expected_sensor_id = f"sensor.indoor_absolute_humidity_{device_id}"
        assert expected_sensor_id in all_entities
        assert all_entities[expected_sensor_id]["device_id"] == device_id

    async def test_async_remove_entities(self):
        """Test removing entities for a device."""
        device_id = "32_123456"
        await self.entities_manager.async_setup_entities(device_id)

        assert len(self.entities_manager.get_all_entities()) > 0

        await self.entities_manager.async_remove_entities(device_id)
        assert len(self.entities_manager.get_all_entities()) == 0

    def test_get_entity_config(self):
        """Test getting configuration for a specific entity type."""
        config = self.entities_manager.get_entity_config(
            "sensor", "indoor_absolute_humidity"
        )
        assert config is not None
        assert config["name"] == "Indoor Absolute Humidity"

        # Test non-existent config
        assert self.entities_manager.get_entity_config("invalid", "type") is None

    def test_get_device_entities(self):
        """Test getting all entities for a specific device."""
        device_1 = "32_111111"
        device_2 = "32_222222"

        # Setup entities for both devices
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.entities_manager.async_setup_entities(device_1))
        loop.run_until_complete(self.entities_manager.async_setup_entities(device_2))

        entities_1 = self.entities_manager.get_device_entities(device_1)
        entities_2 = self.entities_manager.get_device_entities(device_2)

        assert len(entities_1["sensor"]) > 0
        assert len(entities_2["sensor"]) > 0

        # Check that they are different entities
        assert entities_1["sensor"][0] != entities_2["sensor"][0]
        assert device_1 in entities_1["sensor"][0]
        assert device_2 in entities_2["sensor"][0]

    async def test_get_entity_statistics(self):
        """Test getting entity statistics."""
        device_id = "32_123456"
        await self.entities_manager.async_setup_entities(device_id)

        stats = self.entities_manager.get_entity_statistics()
        assert stats["total"] > 0
        assert stats["sensor"] == 2
        assert stats["switch"] == 1
        assert stats["number"] == 3
        assert stats["binary_sensor"] == 1


def test_create_humidity_entities():
    """Test the factory function."""
    hass = MagicMock(spec=HomeAssistant)
    config_entry = MagicMock()
    manager = create_humidity_entities(hass, config_entry)
    assert isinstance(manager, HumidityEntities)
