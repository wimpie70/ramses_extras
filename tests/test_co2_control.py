"""Tests for CO2 Control feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.config import CO2Config
from custom_components.ramses_extras.features.co2_control.zone_manager import (
    CO2Zone,
    CO2ZoneManager,
)


class TestCO2Config:
    """Test CO2Config class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {})

        assert config.enabled is True
        assert config.automation_enabled is False
        assert config.default_threshold == 1000
        assert config.activation_hysteresis == 100
        assert config.deactivation_hysteresis == -100

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        hass = Mock()
        custom_config = {
            "enabled": False,
            "automation_enabled": True,
            "default_threshold": 1200,
            "activation_hysteresis": 150,
            "deactivation_hysteresis": -150,
        }
        config = CO2Config(hass, "32:153289", custom_config)

        assert config.enabled is False
        assert config.automation_enabled is True
        assert config.default_threshold == 1200
        assert config.activation_hysteresis == 150
        assert config.deactivation_hysteresis == -150

    def test_validate_valid_config(self):
        """Test validation with valid configuration."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {})

        is_valid, errors = config.validate()

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid_threshold(self):
        """Test validation with invalid threshold."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {"default_threshold": 3000})

        is_valid, errors = config.validate()

        assert is_valid is False
        assert len(errors) > 0
        assert any("threshold" in error.lower() for error in errors)

    def test_validate_invalid_hysteresis(self):
        """Test validation with invalid hysteresis."""
        hass = Mock()
        config = CO2Config(
            hass,
            "32:153289",
            {"activation_hysteresis": -50, "deactivation_hysteresis": 50},
        )

        is_valid, errors = config.validate()

        assert is_valid is False
        assert len(errors) >= 2


class TestCO2Zone:
    """Test CO2Zone dataclass."""

    def test_zone_creation(self):
        """Test zone creation with basic parameters."""
        zone = CO2Zone(
            zone_id="zone_1",
            zone_name="Living Room",
            sensor_entity="sensor.living_room_co2",
            threshold=1000,
            enabled=True,
        )

        assert zone.zone_id == "zone_1"
        assert zone.zone_name == "Living Room"
        assert zone.sensor_entity == "sensor.living_room_co2"
        assert zone.threshold == 1000
        assert zone.enabled is True
        assert zone.current_co2 is None
        assert zone.is_triggered is False


class TestCO2ZoneManager:
    """Test CO2ZoneManager class."""

    def test_init_with_zones(self):
        """Test initialization with zone configuration."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)

        assert len(manager.zones) == 1
        assert "zone_1" in manager.zones
        assert manager.zones["zone_1"].zone_name == "Living Room"

    @pytest.mark.asyncio
    async def test_update_zone_co2(self):
        """Test updating zone CO2 value."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        await manager.update_zone_co2("zone_1", 1200)

        assert manager.zones["zone_1"].current_co2 == 1200
        assert manager.zones["zone_1"].last_update is not None

    @pytest.mark.asyncio
    async def test_check_zone_triggers_activation(self):
        """Test zone trigger activation."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        await manager.update_zone_co2("zone_1", 1150)

        triggered = await manager.check_zone_triggers(
            activation_hysteresis=100, deactivation_hysteresis=-100
        )

        assert len(triggered) == 1
        assert "zone_1" in triggered
        assert manager.zones["zone_1"].is_triggered is True

    @pytest.mark.asyncio
    async def test_check_zone_triggers_deactivation(self):
        """Test zone trigger deactivation."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)

        # First activate
        await manager.update_zone_co2("zone_1", 1150)
        await manager.check_zone_triggers(
            activation_hysteresis=100, deactivation_hysteresis=-100
        )
        assert manager.zones["zone_1"].is_triggered is True

        # Then deactivate
        await manager.update_zone_co2("zone_1", 850)
        triggered = await manager.check_zone_triggers(
            activation_hysteresis=100, deactivation_hysteresis=-100
        )

        assert len(triggered) == 0
        assert manager.zones["zone_1"].is_triggered is False

    @pytest.mark.asyncio
    async def test_get_worst_zone(self):
        """Test getting worst zone."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                },
                {
                    "zone_id": "zone_2",
                    "zone_name": "Bedroom",
                    "sensor_entity": "sensor.bedroom_co2",
                    "threshold": 1000,
                    "enabled": True,
                },
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        await manager.update_zone_co2("zone_1", 1200)
        await manager.update_zone_co2("zone_2", 1500)

        worst_zone = await manager.get_worst_zone()

        assert worst_zone is not None
        assert worst_zone.zone_id == "zone_2"
        assert worst_zone.current_co2 == 1500

    @pytest.mark.asyncio
    async def test_calculate_combined_fan_speed(self):
        """Test fan speed calculation."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        await manager.update_zone_co2("zone_1", 1250)
        await manager.check_zone_triggers(
            activation_hysteresis=100, deactivation_hysteresis=-100
        )

        fan_speed = await manager.calculate_combined_fan_speed(
            base_speed=2, max_speed=5
        )

        assert fan_speed >= 2
        assert fan_speed <= 5

    def test_add_zone(self):
        """Test adding a zone."""
        hass = Mock()
        manager = CO2ZoneManager(hass, "32:153289", {"zones": []})

        zone_config = {
            "zone_id": "zone_1",
            "zone_name": "Living Room",
            "sensor_entity": "sensor.living_room_co2",
            "threshold": 1000,
            "enabled": True,
        }

        manager.add_zone(zone_config)

        assert len(manager.zones) == 1
        assert "zone_1" in manager.zones

    def test_remove_zone(self):
        """Test removing a zone."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        result = manager.remove_zone("zone_1")

        assert result is True
        assert len(manager.zones) == 0

    def test_update_zone_config(self):
        """Test updating zone configuration."""
        hass = Mock()
        config = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "Living Room",
                    "sensor_entity": "sensor.living_room_co2",
                    "threshold": 1000,
                    "enabled": True,
                }
            ]
        }

        manager = CO2ZoneManager(hass, "32:153289", config)
        result = manager.update_zone_config(
            "zone_1", {"threshold": 1200, "zone_name": "Main Living Room"}
        )

        assert result is True
        assert manager.zones["zone_1"].threshold == 1200
        assert manager.zones["zone_1"].zone_name == "Main Living Room"
