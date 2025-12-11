"""Configuration management core for Ramses Extras framework.

This module provides the ExtrasConfigManager base class that can be extended
by features to provide generic configuration management functionality.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENABLED,
    CONF_ID,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class ExtrasConfigManager:
    """Generic configuration manager for Ramses Extras features.

    This base class provides configuration management patterns that are shared
    across all features, including loading, validation, and access patterns.

    Features should extend this class and provide their own default configuration
    and validation rules.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        feature_id: str,
        default_config: dict[str, Any],
    ) -> None:
        """Initialize the configuration manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
            feature_id: Feature identifier (e.g., "humidity_control")
            default_config: Default configuration dictionary
        """
        self.hass = hass
        self.config_entry = config_entry
        self.feature_id = feature_id
        self._default_config = default_config.copy()
        self._config: dict[str, Any] = {}

        _LOGGER.info(f"Initialized {feature_id} configuration manager")

    async def async_load(self) -> None:
        """Load configuration from config entry and defaults.

        Merges default configuration with user configuration from config entry.
        """
        _LOGGER.info(f"Loading {self.feature_id} configuration")

        try:
            # Start with default config
            self._config = self._default_config.copy()

            # Update with config entry options if available
            if self.config_entry.options:
                self._config.update(self.config_entry.options)
                _LOGGER.debug(
                    f"Updated {self.feature_id} config with options: "
                    f"{self.config_entry.options}"
                )

            # Update with config entry data if available
            if self.config_entry.data:
                self._config.update(self.config_entry.data)
                _LOGGER.debug(
                    f"Updated {self.feature_id} config with data: "
                    f"{self.config_entry.data}"
                )

            _LOGGER.info(f"Configuration loaded: {len(self._config)} settings")

        except Exception as e:
            _LOGGER.error(f"Failed to load {self.feature_id} configuration: {e}")
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
            _LOGGER.info(f"{self.feature_id} configuration validation passed")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to save {self.feature_id} configuration: {e}")
            return False

    def validate_config(self) -> bool:
        """Validate current configuration.

        Features should override this method to provide feature-specific validation.
        The base implementation provides general validation patterns.

        Returns:
            True if configuration is valid
        """
        try:
            # Check for basic boolean values if they exist
            if "enabled" in self._config and not isinstance(
                self._config["enabled"], bool
            ):
                _LOGGER.error(
                    f"{self.feature_id} configuration error: 'enabled' must be boolean"
                )
                return False

            # Check for basic numeric ranges if they exist
            if "min_value" in self._config and "max_value" in self._config:
                min_val = self._config["min_value"]
                max_val = self._config["max_value"]
                if not isinstance(min_val, (int, float)) or not isinstance(
                    max_val, (int, float)
                ):
                    _LOGGER.error(
                        f"{self.feature_id} configuration error: "
                        "'min_value' and 'max_value' must be numeric"
                    )
                    return False

                if min_val >= max_val:
                    _LOGGER.error(
                        f"{self.feature_id} configuration error: "
                        "'max_value' must be > 'min_value'"
                    )
                    return False

            _LOGGER.debug(f"{self.feature_id} configuration validation successful")
            return True

        except Exception as e:
            _LOGGER.error(f"{self.feature_id} configuration validation error: {e}")
            return False

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
        _LOGGER.debug(f"{self.feature_id} configuration updated: {key} = {value}")

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
        _LOGGER.info(
            f"{self.feature_id} configuration updated with {len(updates)} values"
        )

    def is_enabled(self) -> bool:
        """Check if feature is enabled.

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

    def reset_to_defaults(self) -> None:
        """Reset configuration to default values.

        Restores all configuration to default values.
        """
        _LOGGER.info(f"Resetting {self.feature_id} configuration to defaults")
        self._config = self._default_config.copy()

    def get_config_schema(self) -> dict[str, Any]:
        """Get configuration schema for UI.

        Features should override this method to provide feature-specific schemas.
        The base implementation provides a generic schema.

        Returns:
            Configuration schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": f"Enable {self.feature_id.title().replace('_', ' ')}",
                    "description": f"Enable or disable the {self.feature_id} feature",
                },
            },
        }

    def get_numeric_validation(self, key: str, min_val: float, max_val: float) -> bool:
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
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be numeric"
            )
            return False

        if not (min_val <= value <= max_val):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be between "
                f"{min_val} and {max_val}"
            )
            return False

        return True

    def get_boolean_validation(self, key: str) -> bool:
        """Validate a boolean configuration value.

        Args:
            key: Configuration key

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, bool):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be boolean"
            )
            return False

        return True

    def get_string_validation(self, key: str, choices: list | None = None) -> bool:
        """Validate a string configuration value.

        Args:
            key: Configuration key
            choices: Optional list of valid choices

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, str):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be string"
            )
            return False

        if choices and value not in choices:
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be one of "
                f"{choices}, got '{value}'"
            )
            return False

        return True


# Configuration factory function
def create_config_manager(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    feature_id: str,
    default_config: dict[str, Any],
) -> ExtrasConfigManager:
    """Create a configuration manager instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        feature_id: Feature identifier
        default_config: Default configuration

    Returns:
        ExtrasConfigManager instance
    """
    return ExtrasConfigManager(hass, config_entry, feature_id, default_config)


__all__ = [
    "ExtrasConfigManager",
    "create_config_manager",
]
