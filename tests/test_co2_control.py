"""Tests for CO2 Control feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.ramses_extras.features.co2_control.config import CO2Config


class TestCO2Config:
    """Test CO2Config class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {})

        assert config.enabled is True
        assert config.automation_enabled is False
        assert config.default_threshold == 800
        assert config.activation_hysteresis == 25
        assert config.deactivation_hysteresis == -25

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

    def test_max_runtime_minutes(self):
        """Test max_runtime_minutes property (covers line 72)."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {"max_runtime_minutes": 60})

        assert config.max_runtime_minutes == 60

    def test_cooldown_period_minutes(self):
        """Test cooldown_period_minutes property (covers line 77)."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {"cooldown_period_minutes": 30})

        assert config.cooldown_period_minutes == 30

    def test_priority_over_humidity(self):
        """Test priority_over_humidity property (covers line 82)."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {"priority_over_humidity": False})

        assert config.priority_over_humidity is False

    @pytest.mark.asyncio
    async def test_async_load(self):
        """Test async_load method (covers line 105)."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {})

        result = await config.async_load()
        assert result is True

    def test_to_dict(self):
        """Test to_dict method (covers line 148)."""
        hass = Mock()
        config = CO2Config(hass, "32:153289", {"enabled": False})

        config_dict = config.to_dict()
        assert config_dict["enabled"] is False
