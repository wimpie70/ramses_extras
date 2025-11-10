"""Humidity Control Configuration.

This module provides configuration management for humidity control functionality,
including settings, preferences, and feature-specific configurations.
"""

import logging
from typing import Any, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENABLED,
    CONF_ID,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HumidityConfig:
    """Manages humidity control configuration.

    This class handles all configuration aspects of the humidity control feature,
    including user settings, automation parameters, and feature preferences.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize humidity configuration manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        self.hass = hass
        self.config_entry = config_entry

        # Configuration storage
        self._config: dict[str, Any] = {}
        self._default_config = self._get_default_config()

        _LOGGER.info("HumidityControl config initialized")

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration values.

        Returns:
            Default configuration dictionary
        """
        return {
            # General settings
            "enabled": True,
            "auto_start": True,
            # Automation settings
            "automation_enabled": True,
            "automation_debounce_seconds": 15,
            "decision_interval_seconds": 60,
            # Thresholds
            "default_min_humidity": 40.0,
            "default_max_humidity": 60.0,
            "default_offset": 0.4,
            # Decision thresholds
            "activation_threshold": 1.0,  # g/m³
            "deactivation_threshold": -1.0,  # g/m³
            "high_confidence_threshold": 2.0,  # g/m³
            # Performance settings
            "max_decision_history": 100,
            "enable_performance_logging": True,
            "enable_automation_status": True,
            # Entity settings
            "auto_create_entities": True,
            "entity_update_interval": 5,  # seconds
            # Safety settings
            "max_runtime_minutes": 120,
            "cooldown_period_minutes": 15,
            "emergency_stop_enabled": True,
        }

    async def async_load(self) -> None:
        """Load configuration from config entry and defaults.

        Merges default configuration with user configuration from config entry.
        """
        _LOGGER.info("Loading humidity control configuration")

        try:
            # Start with default config
            self._config = self._default_config.copy()

            # Update with config entry options
            if self.config_entry.options:
                self._config.update(self.config_entry.options)

            # Update with config entry data
            if self.config_entry.data:
                self._config.update(self.config_entry.data)

            _LOGGER.info(f"Configuration loaded: {len(self._config)} settings")

        except Exception as e:
            _LOGGER.error(f"Failed to load configuration: {e}")
            # Fall back to defaults
            self._config = self._default_config.copy()

    async def async_save(self) -> bool:
        """Save current configuration.

        This would update the config entry with current settings.
        For now, it just validates the configuration.

        Returns:
            True if successful
        """
        try:
            # Validate configuration
            if not self.validate_config():
                return False

            # This would update the config entry
            # Implementation depends on HA's config entry update mechanism
            _LOGGER.info("Configuration validation passed")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to save configuration: {e}")
            return False

    def validate_config(self) -> bool:
        """Validate current configuration.

        Returns:
            True if configuration is valid
        """
        try:
            # Check required boolean values
            if not isinstance(self._config.get("enabled"), bool):
                _LOGGER.error("Configuration error: 'enabled' must be boolean")
                return False

            # Check numeric ranges
            if not self._validate_numeric_range("default_min_humidity", 0, 100):
                return False

            if not self._validate_numeric_range("default_max_humidity", 0, 100):
                return False

            if not self._validate_numeric_range("automation_debounce_seconds", 1, 300):
                return False

            if not self._validate_numeric_range("max_runtime_minutes", 1, 1440):
                return False

            # Check dependencies
            if self._config.get("max_humidity", 0) <= self._config.get(
                "min_humidity", 0
            ):
                _LOGGER.error(
                    "Configuration error: max_humidity must be > min_humidity"
                )
                return False

            _LOGGER.debug("Configuration validation successful")
            return True

        except Exception as e:
            _LOGGER.error(f"Configuration validation error: {e}")
            return False

    def _validate_numeric_range(self, key: str, min_val: float, max_val: float) -> bool:
        """Validate a numeric configuration value is within range.

        Args:
            key: Configuration key
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, (int, float)):
            _LOGGER.error(f"Configuration error: '{key}' must be numeric")
            return False

        if not (min_val <= value <= max_val):
            _LOGGER.error(
                f"Configuration error: '{key}' must be between {min_val} and {max_val}"
            )
            return False

        return True

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        self._config[key] = value
        _LOGGER.debug(f"Configuration updated: {key} = {value}")

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values.

        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()

    def update(self, updates: dict[str, Any]) -> None:
        """Update multiple configuration values.

        Args:
            updates: Dictionary of updates
        """
        self._config.update(updates)
        _LOGGER.info(f"Configuration updated with {len(updates)} values")

    def is_enabled(self) -> bool:
        """Check if humidity control is enabled.

        Returns:
            True if enabled
        """
        return bool(self.get("enabled", False))

    def is_automation_enabled(self) -> bool:
        """Check if automation is enabled.

        Returns:
            True if automation is enabled
        """
        return self.is_enabled() and self.get("automation_enabled", False)

    def get_debounce_seconds(self) -> int:
        """Get automation debounce duration.

        Returns:
            Debounce duration in seconds
        """
        return int(self.get("automation_debounce_seconds", 30))

    def get_decision_interval(self) -> int:
        """Get decision evaluation interval.

        Returns:
            Decision interval in seconds
        """
        return int(self.get("decision_interval_seconds", 60))

    def get_thresholds(self) -> dict[str, float]:
        """Get humidity thresholds.

        Returns:
            Dictionary of threshold values
        """
        return {
            "min_humidity": self.get("default_min_humidity", 40.0),
            "max_humidity": self.get("default_max_humidity", 60.0),
            "offset": self.get("default_offset", 0.4),
            "activation": self.get("activation_threshold", 1.0),
            "deactivation": self.get("deactivation_threshold", -1.0),
            "high_confidence": self.get("high_confidence_threshold", 2.0),
        }

    def get_performance_settings(self) -> dict[str, Any]:
        """Get performance-related settings.

        Returns:
            Dictionary of performance settings
        """
        return {
            "max_decision_history": self.get("max_decision_history", 100),
            "enable_logging": self.get("enable_performance_logging", True),
            "entity_update_interval": self.get("entity_update_interval", 5),
        }

    def get_safety_settings(self) -> dict[str, Any]:
        """Get safety-related settings.

        Returns:
            Dictionary of safety settings
        """
        return {
            "max_runtime_minutes": self.get("max_runtime_minutes", 120),
            "cooldown_period_minutes": self.get("cooldown_period_minutes", 15),
            "emergency_stop_enabled": self.get("emergency_stop_enabled", True),
        }

    def reset_to_defaults(self) -> None:
        """Reset configuration to default values.

        Restores all configuration to default values.
        """
        _LOGGER.info("Resetting configuration to defaults")
        self._config = self._default_config.copy()

    def get_config_schema(self) -> dict[str, Any]:
        """Get configuration schema for UI.

        Returns:
            Configuration schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Humidity Control",
                    "description": "Enable or disable the humidity control feature",
                },
                "automation_enabled": {
                    "type": "boolean",
                    "title": "Enable Automation",
                    "description": "Enable automatic humidity control",
                },
                "default_min_humidity": {
                    "type": "number",
                    "title": "Minimum Humidity",
                    "description": "Default minimum humidity threshold (%)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "default_max_humidity": {
                    "type": "number",
                    "title": "Maximum Humidity",
                    "description": "Default maximum humidity threshold (%)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "activation_threshold": {
                    "type": "number",
                    "title": "Activation Threshold",
                    "description": "Humidity differential threshold (g/m³)",
                    "minimum": 0,
                    "maximum": 10,
                },
            },
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
