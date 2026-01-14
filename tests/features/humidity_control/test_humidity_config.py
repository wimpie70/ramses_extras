"""Tests for Humidity Control Configuration."""

from unittest.mock import MagicMock

from custom_components.ramses_extras.features.humidity_control.config import (
    HumidityConfig,
)


class TestHumidityConfig:
    """Test cases for HumidityConfig class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        # Mock options and data for the config entry
        self.config_entry.options = {}
        self.config_entry.data = {}

        self.config = HumidityConfig(self.hass, self.config_entry)

    def test_get_humidity_thresholds(self):
        """Test getting humidity threshold values."""
        # Test defaults
        thresholds = self.config.get_humidity_thresholds()
        assert thresholds["min_humidity"] == 40.0
        assert thresholds["max_humidity"] == 60.0
        assert thresholds["activation"] == 1.0

    def test_get_safety_settings(self):
        """Test getting safety settings."""
        # Test defaults
        safety = self.config.get_safety_settings()
        assert safety["max_runtime_minutes"] == 120
        assert safety["cooldown_period_minutes"] == 15

    def test_validate_config_valid(self):
        """Test validation with valid config."""
        # Mock get_all to return valid values
        self.config.get_all = MagicMock(
            return_value={
                "default_min_humidity": 40.0,
                "default_max_humidity": 60.0,
                "activation_threshold": 1.0,
            }
        )
        assert self.config.validate_config() is True

    def test_validate_config_invalid_range(self):
        """Test validation with invalid humidity range."""
        # min > max
        self.config.get_all = MagicMock(
            return_value={"default_min_humidity": 70.0, "default_max_humidity": 60.0}
        )
        # Note: validate_range_relationship handles the comparison
        assert self.config.validate_config() is False

    def test_get_config_schema(self):
        """Test generating config schema."""
        schema = self.config.get_config_schema_dict()
        assert schema["type"] == "object"
        assert "enabled" in schema["properties"]
        assert "automation_enabled" in schema["properties"]
        assert "default_min_humidity" in schema["properties"]
        assert "default_max_humidity" in schema["properties"]
