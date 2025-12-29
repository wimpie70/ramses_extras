"""Tests for Humidity Control Platforms and Entities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control.platforms.binary_sensor import (  # noqa: E501
    HumidityControlBinarySensor,
    create_humidity_control_binary_sensor,
)
from custom_components.ramses_extras.features.humidity_control.platforms.number import (
    HumidityControlNumber,
    create_humidity_number,
)
from custom_components.ramses_extras.features.humidity_control.platforms.sensor import (
    create_humidity_sensor,
)
from custom_components.ramses_extras.features.humidity_control.platforms.switch import (
    HumidityControlSwitch,
    create_humidity_switch,
)


class TestHumidityPlatforms:
    """Test cases for humidity control platform entities."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        # Mock Home Assistant integrations data to prevent loader KeyError
        self.hass.data = {"integrations": {}}
        # Mock states
        self.hass.states = MagicMock()
        # Mock thread ID for async_write_ha_state
        import threading

        self.hass.loop_thread_id = threading.get_ident()
        self.hass.bus = MagicMock()

        self.config_entry = MagicMock(spec=ConfigEntry)
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.device_id = "32_123456"

    @patch(
        "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device"
    )
    async def test_humidity_switch(self, mock_find_device):
        """Test HumidityControlSwitch."""
        config = {
            "name": "Dehumidify",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidify_{device_id}",
        }
        entity = HumidityControlSwitch(self.hass, self.device_id, "dehumidify", config)

        # Manually set internal state since we're testing the logic
        entity._is_on = False

        assert entity.is_on is False
        assert entity.extra_state_attributes["dehumidifying"] is False

        # Test turn on
        mock_device = MagicMock()
        mock_find_device.return_value = mock_device

        # Mock _set_device_fan_speed to avoid actual side effects or complex mocks
        with patch.object(
            entity, "_set_device_fan_speed", new_callable=AsyncMock
        ) as mock_set_speed:
            await entity.async_turn_on()
            assert entity.is_on is True
            mock_set_speed.assert_called_once_with(mock_device, "high")

        # Test turn off
        with patch.object(
            entity, "_set_device_fan_speed", new_callable=AsyncMock
        ) as mock_set_speed:
            await entity.async_turn_off()
            assert entity.is_on is False
            mock_set_speed.assert_called_once_with(mock_device, "auto")

    async def test_create_humidity_switch(self):
        """Test create_humidity_switch factory."""
        switches = await create_humidity_switch(
            self.hass, self.device_id, self.config_entry
        )
        assert len(switches) == 1
        assert isinstance(switches[0], HumidityControlSwitch)

    async def test_humidity_number(self):
        """Test HumidityControlNumber."""
        config = {
            "name": "Min Humidity",
            "default_value": 45.0,
            "supported_device_types": ["HvacVentilator"],
        }
        entity = HumidityControlNumber(
            self.hass,
            self.device_id,
            "relative_humidity_minimum",
            config,
            self.config_entry,
        )

        # Initialize native value if not already set by constructor
        entity._native_value = 45.0

        assert entity.native_value == 45.0

        # Test setting value
        with patch(
            "custom_components.ramses_extras.framework.base_classes.platform_entities.ExtrasNumberEntity.async_set_native_value",
            new_callable=AsyncMock,
        ) as mock_super_set:
            await entity.async_set_native_value(50.0)
            mock_super_set.assert_called_once_with(50.0)
            # Update value manually for the test since we're mocking the super call
            entity._native_value = 50.0
            assert entity.native_value == 50.0

    async def test_create_humidity_number(self):
        """Test create_humidity_number factory."""
        numbers = await create_humidity_number(
            self.hass, self.device_id, self.config_entry
        )
        assert len(numbers) == 3
        assert any(n._entity_type == "relative_humidity_minimum" for n in numbers)

    async def test_humidity_binary_sensor(self):
        """Test HumidityControlBinarySensor."""
        config = {
            "name": "Dehumidifying Active",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidifying_active_{device_id}",
        }
        entity = HumidityControlBinarySensor(
            self.hass, self.device_id, "dehumidifying_active", config
        )

        # Initialize internal state
        entity._is_on = False

        assert entity.is_on is False

        # Test state setting
        entity.set_state(True)
        assert entity.is_on is True

        # Test turn off
        await entity.async_turn_off()
        assert entity.is_on is False

    async def test_create_humidity_binary_sensor(self):
        """Test create_humidity_control_binary_sensor factory."""
        sensors = await create_humidity_control_binary_sensor(
            self.hass, self.device_id, self.config_entry
        )
        assert len(sensors) == 1
        assert isinstance(sensors[0], HumidityControlBinarySensor)

    async def test_create_humidity_sensor_placeholder(self):
        """Test create_humidity_sensor (placeholder)."""
        # This currently returns empty list as sensors are handled by default feature
        sensors = await create_humidity_sensor(
            self.hass, self.device_id, {}, self.config_entry
        )
        assert isinstance(sensors, list)
        assert len(sensors) == 0
