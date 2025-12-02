# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Configuration management for Hello World Switch Card feature."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DEFAULT_CONFIG, DOMAIN

# Configuration schema for the feature
FEATURE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("default_name", default="Hello World"): cv.string,
        vol.Optional("icon", default="mdi:lightbulb"): cv.string,
        vol.Optional("auto_discovery", default=True): cv.boolean,
    }
)

# Options schema for the config entry
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("default_name", default="Hello World"): cv.string,
        vol.Optional("icon", default="mdi:lightbulb"): cv.string,
        vol.Optional("auto_discovery", default=True): cv.boolean,
    }
)


class HelloWorldConfig:
    """Manages configuration for Hello World feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize configuration manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._feature_config = self._load_feature_config()

    def _load_feature_config(self) -> dict[str, Any]:
        """Load feature configuration from config entry options."""
        options = self.config_entry.options if self.config_entry.options else {}
        return {**DEFAULT_CONFIG, **options}

    def get_feature_config(self) -> dict[str, Any]:
        """Get feature configuration."""
        return self._feature_config.copy()

    def is_enabled(self) -> bool:
        """Check if feature is enabled."""
        return bool(self._feature_config.get("enabled", True))

    def get_default_name(self) -> str:
        """Get default name for entities."""
        return str(self._feature_config.get("default_name", "Hello World"))

    def get_icon(self) -> str:
        """Get default icon for entities."""
        return str(self._feature_config.get("icon", "mdi:lightbulb"))

    def is_auto_discovery_enabled(self) -> bool:
        """Check if auto discovery is enabled."""
        return bool(self._feature_config.get("auto_discovery", True))

    def update_config(self, new_config: dict[str, Any]) -> None:
        """Update feature configuration."""
        # Validate the new configuration
        validated_config = FEATURE_CONFIG_SCHEMA(new_config)
        self._feature_config.update(validated_config)

    @staticmethod
    def get_config_flow_schema() -> dict[str, Any]:
        """Get configuration flow schema for UI setup."""
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Hello World Feature",
                    "default": True,
                },
                "default_name": {
                    "type": "string",
                    "title": "Default Entity Name",
                    "default": "Hello World",
                },
                "icon": {
                    "type": "string",
                    "title": "Default Icon",
                    "default": "mdi:lightbulb",
                },
                "auto_discovery": {
                    "type": "boolean",
                    "title": "Enable Auto Discovery",
                    "default": True,
                },
            },
            "required": ["enabled"],
        }

    @staticmethod
    def validate_config(config: dict[str, Any]) -> tuple[bool, str]:
        """Validate feature configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Validate against schema
            FEATURE_CONFIG_SCHEMA(config)
            return True, ""
        except vol.Invalid as err:
            return False, f"Invalid configuration: {err}"

    def get_entity_config(self, entity_type: str, entity_key: str) -> dict[str, Any]:
        """Get configuration for a specific entity.

        Args:
            entity_type: Type of entity (switch, binary_sensor, etc.)
            entity_key: Key identifying the specific entity

        Returns:
            Entity configuration dictionary
        """
        base_config = self._feature_config.copy()

        # Add entity-specific defaults
        if entity_type == "switch":
            base_config.update(
                {
                    "icon": self.get_icon(),
                    "name_prefix": self.get_default_name(),
                }
            )
        elif entity_type == "binary_sensor":
            base_config.update(
                {
                    "device_class": "connectivity",
                    "name_prefix": f"{self.get_default_name()} Status",
                }
            )

        return base_config


def create_hello_world_config(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> HelloWorldConfig:
    """Factory function to create Hello World configuration manager.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Hello World configuration manager instance
    """
    return HelloWorldConfig(hass, config_entry)


__all__ = [
    "HelloWorldConfig",
    "create_hello_world_config",
    "FEATURE_CONFIG_SCHEMA",
    "OPTIONS_SCHEMA",
]
