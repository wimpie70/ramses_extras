"""Humidity Control Configuration.

This module provides configuration management for humidity control functionality,
including settings, preferences, and feature-specific configurations.

Now uses the framework's ExtrasConfigManager for reusable configuration patterns.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.config import (
    ConfigValidator,
    ExtrasConfigManager,
)

from .const import HUMIDITY_CONTROL_DEFAULTS

_LOGGER = logging.getLogger(__name__)


class HumidityConfig(ExtrasConfigManager):
    """Manages humidity control configuration using the framework.

    This class extends ExtrasConfigManager to provide humidity control
    specific configuration management with sensible defaults and validation.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize humidity configuration manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        # Use the feature-specific template for humidity control
        default_config = HUMIDITY_CONTROL_DEFAULTS

        super().__init__(
            hass=hass,
            config_entry=config_entry,
            feature_id="humidity_control",
            default_config=default_config,
        )

        # Add humidity-specific configuration utilities
        self._validator = ConfigValidator("humidity_control")

    def validate_config(self) -> bool:
        """Validate humidity control configuration.

        Returns:
            True if configuration is valid
        """
        try:
            # Use framework validation patterns
            config = self.get_all()

            # Validate numeric ranges
            if not self._validator.validate_numeric_range(
                config, "default_min_humidity", 0, 100
            )[0]:
                return False

            if not self._validator.validate_numeric_range(
                config, "default_max_humidity", 0, 100
            )[0]:
                return False

            # Validate thresholds relationship
            if not self._validator.validate_range_relationship(
                config, "default_min_humidity", "default_max_humidity"
            )[0]:
                return False

            # Call parent validation
            return super().validate_config()

        except Exception as e:
            _LOGGER.error("Configuration validation error: %s", e)
            return False

    def get_config_schema(self) -> dict[str, Any]:
        """Get humidity control configuration schema for UI.

        Returns:
            Configuration schema dictionary
        """
        return self.get_config_schema_dict()

    def get_config_schema_dict(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Humidity Control",
                    "description": "Enable or disable the humidity control feature",
                    "default": True,
                },
                "automation_enabled": {
                    "type": "boolean",
                    "title": "Enable Automation",
                    "description": "Enable automatic humidity control",
                    "default": False,
                },
                "default_min_humidity": {
                    "type": "numeric",
                    "title": "Minimum Humidity",
                    "description": "Default minimum humidity threshold (%)",
                    "min": 0,
                    "max": 100,
                    "default": 40,
                },
                "default_max_humidity": {
                    "type": "numeric",
                    "title": "Maximum Humidity",
                    "description": "Default maximum humidity threshold (%)",
                    "min": 0,
                    "max": 100,
                    "default": 60,
                },
                "activation_threshold": {
                    "type": "numeric",
                    "title": "Activation Threshold",
                    "description": "Humidity differential threshold (g/m³)",
                    "min": 0.1,
                    "max": 10.0,
                    "default": 1.0,
                },
            },
        }

    # Inherited methods from ExtrasConfigManager:
    # - async_load()
    # - async_save()
    # - get(), set(), get_all(), update()
    # - is_enabled(), is_automation_enabled()
    # - reset_to_defaults()
    # - get_numeric_validation(), get_boolean_validation(), get_string_validation()

    # Additional humidity-specific convenience methods
    def get_humidity_thresholds(self) -> dict[str, float]:
        """Get humidity threshold values.

        Returns:
            Dictionary of humidity threshold values
        """
        return {
            "min_humidity": self.get("default_min_humidity", 40.0),
            "max_humidity": self.get("default_max_humidity", 60.0),
            "activation": self.get("activation_threshold", 1.0),
            "deactivation": self.get("deactivation_threshold", -1.0),
        }

    def get_safety_settings(self) -> dict[str, Any]:
        """Get safety-related settings.

        Returns:
            Dictionary of safety settings
        """
        return {
            "max_runtime_minutes": self.get("max_runtime_minutes", 120),
            "cooldown_period_minutes": self.get("cooldown_period_minutes", 15),
        }


# Configuration factory function
def create_humidity_config(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> HumidityConfig:
    """Create humidity configuration instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HumidityConfig instance
    """
    return HumidityConfig(hass, config_entry)


__all__ = [
    "HumidityConfig",
    "create_humidity_config",
]
