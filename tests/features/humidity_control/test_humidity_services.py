"""Tests for Humidity Control Services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control.services import (
    HumidityServices,
)


class TestHumidityServices:
    """Test cases for HumidityServices class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        # Ensure hass.states and hass.services exist as mocks
        self.hass.states = MagicMock()
        self.hass.services = MagicMock()
        self.config_entry = MagicMock()

        # Patch RamsesCommands
        with patch(
            "custom_components.ramses_extras.features.humidity_control.services.RamsesCommands"
        ) as mock_ramses:
            self.mock_ramses = mock_ramses.return_value
            self.mock_ramses.send_command = AsyncMock()
            self.services = HumidityServices(self.hass, self.config_entry)

    @patch(
        "custom_components.ramses_extras.features.humidity_control.services.EntityHelpers"
    )
    async def test_async_activate_dehumidification(self, mock_helpers):
        """Test activating dehumidification."""
        device_id = "32_123456"
        entity_id = "switch.dehumidify_32_123456"

        # Mock entity finding
        mock_helpers.generate_entity_name_from_template.return_value = entity_id
        mock_state = MagicMock()
        mock_state.entity_id = entity_id
        self.hass.states.async_all.return_value = [mock_state]

        # Mock fan speed setting
        self.mock_ramses.send_command.return_value = MagicMock(success=True)

        # Mock HA service call
        self.hass.services.async_call = AsyncMock()

        result = await self.services.async_activate_dehumidification(device_id)

        assert result is True
        self.hass.services.async_call.assert_called_with(
            "switch", SERVICE_TURN_ON, {"entity_id": entity_id}
        )
        self.mock_ramses.send_command.assert_called_with(device_id, "high")

    @patch(
        "custom_components.ramses_extras.features.humidity_control.services.EntityHelpers"
    )
    async def test_async_deactivate_dehumidification(self, mock_helpers):
        """Test deactivating dehumidification."""
        device_id = "32_123456"
        entity_id = "switch.dehumidify_32_123456"

        # Mock entity finding
        mock_helpers.generate_entity_name_from_template.return_value = entity_id
        mock_state = MagicMock()
        mock_state.entity_id = entity_id
        self.hass.states.async_all.return_value = [mock_state]

        # Mock fan speed setting
        self.mock_ramses.send_command.return_value = MagicMock(success=True)

        # Mock HA service call
        self.hass.services.async_call = AsyncMock()

        result = await self.services.async_deactivate_dehumidification(device_id)

        assert result is True
        self.hass.services.async_call.assert_called_with(
            "switch", SERVICE_TURN_OFF, {"entity_id": entity_id}
        )
        self.mock_ramses.send_command.assert_called_with(device_id, "auto")

    async def test_async_set_fan_speed(self):
        """Test setting fan speed."""
        device_id = "32_123456"
        speed = "low"

        self.mock_ramses.send_command.return_value = MagicMock(success=True)

        result = await self.services.async_set_fan_speed(device_id, speed)

        assert result is True
        self.mock_ramses.send_command.assert_called_with(device_id, speed)

    @patch(
        "custom_components.ramses_extras.features.humidity_control.services.EntityHelpers"
    )
    async def test_async_set_thresholds(self, mock_helpers):
        """Test setting humidity thresholds (min, max, offset)."""
        device_id = "32_123456"

        # Mock entity names
        mock_helpers.generate_entity_name_from_template.side_effect = [
            "number.relative_humidity_minimum_32_123456",
            "number.relative_humidity_maximum_32_123456",
            "number.absolute_humidity_offset_32_123456",
        ]

        # Mock states
        mock_states = [
            MagicMock(entity_id="number.relative_humidity_minimum_32_123456"),
            MagicMock(entity_id="number.relative_humidity_maximum_32_123456"),
            MagicMock(entity_id="number.absolute_humidity_offset_32_123456"),
        ]
        self.hass.states.async_all.return_value = mock_states
        self.hass.services.async_call = AsyncMock()

        # Test set min
        assert await self.services.async_set_min_humidity(device_id, 45.0) is True
        # Test set max
        assert await self.services.async_set_max_humidity(device_id, 65.0) is True
        # Test set offset
        assert await self.services.async_set_offset(device_id, 0.6) is True

        assert self.hass.services.async_call.call_count == 3

    @patch(
        "custom_components.ramses_extras.features.humidity_control.services.EntityHelpers"
    )
    async def test_async_get_status(self, mock_helpers):
        """Test getting humidity status."""
        device_id = "32_123456"

        # Mock EntityHelpers to return predictable entity IDs
        def mock_gen_name(domain, template, **kwargs):
            return f"{domain}.{template.format(**kwargs)}"

        mock_helpers.generate_entity_name_from_template.side_effect = mock_gen_name

        # Mock HA states.get with side_effect to return different values
        def side_effect(entity_id):
            if not isinstance(entity_id, str):
                return None
            mock = MagicMock()
            mock.entity_id = entity_id
            mock.attributes = {"friendly_name": "Test"}
            if "dehumidifying_active" in entity_id:
                mock.state = "off"
            elif "dehumidify" in entity_id:
                mock.state = "on"
            else:
                mock.state = "50.0"
            return mock

        self.hass.states.get.side_effect = side_effect

        result = await self.services.async_get_status(device_id)

        assert result["device_id"] == device_id
        assert "entities" in result
        assert result["automation_state"] == "manual"
