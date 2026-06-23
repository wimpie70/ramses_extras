"""Tests for Temp Control Configuration."""

from unittest.mock import MagicMock

from custom_components.ramses_extras.features.temp_control.config import (
    TempControlConfig,
    TempControlSettings,
)


class TestTempControlConfig:
    """Test cases for TempControlConfig class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.options = {}
        self.config_entry.data = {}

        self.config = TempControlConfig(self.hass, self.config_entry)

    def test_get_settings_defaults(self):
        """Test getting default settings when no config is present."""
        settings = self.config.get_settings()

        assert isinstance(settings, TempControlSettings)
        assert settings.comfort_delta_activate == 1.0
        assert settings.comfort_delta_deactivate == 0.5
        assert settings.cooling_delta_activate == 1.0
        assert settings.cooling_delta_deactivate == 0.5
        assert settings.min_outdoor_temp == 10.0
        assert settings.min_bypass_mode_interval_seconds == 180
        assert settings.default_desired_speed == "high"

    def test_get_settings_from_options(self):
        """Test getting settings from config entry options."""
        self.config_entry.options = {
            "ramses_extras": {
                "features": {
                    "temp_control": {
                        "comfort_delta_activate": 2.0,
                        "comfort_delta_deactivate": 1.0,
                        "cooling_delta_activate": 3.0,
                        "cooling_delta_deactivate": 1.5,
                        "min_outdoor_temp": 5.0,
                        "min_bypass_mode_interval_seconds": 300,
                        "default_desired_speed": "medium",
                    }
                }
            }
        }

        settings = self.config.get_settings()

        assert settings.comfort_delta_activate == 2.0
        assert settings.comfort_delta_deactivate == 1.0
        assert settings.cooling_delta_activate == 3.0
        assert settings.cooling_delta_deactivate == 1.5
        assert settings.min_outdoor_temp == 5.0
        assert settings.min_bypass_mode_interval_seconds == 300
        assert settings.default_desired_speed == "medium"

    def test_get_settings_from_legacy_section(self):
        """Test getting settings from legacy top-level temp_control section."""
        self.config_entry.options = {
            "temp_control": {
                "comfort_delta_activate": 1.5,
                "min_outdoor_temp": 8.0,
            }
        }

        settings = self.config.get_settings()

        assert settings.comfort_delta_activate == 1.5
        assert settings.min_outdoor_temp == 8.0
        # Others should be defaults
        assert settings.comfort_delta_deactivate == 0.5

    def test_get_settings_invalid_values_fall_back(self):
        """Test that invalid config values fall back to defaults."""
        self.config_entry.options = {
            "temp_control": {
                "comfort_delta_activate": "not_a_number",
                "min_bypass_mode_interval_seconds": "bad",
            }
        }

        settings = self.config.get_settings()

        assert settings.comfort_delta_activate == 1.0
        assert settings.min_bypass_mode_interval_seconds == 180

    def test_settings_is_frozen(self):
        """Test that TempControlSettings is frozen (immutable)."""
        settings = self.config.get_settings()

        try:
            settings.comfort_delta_activate = 99.0  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # dataclass(frozen=True) raises AttributeError on set
