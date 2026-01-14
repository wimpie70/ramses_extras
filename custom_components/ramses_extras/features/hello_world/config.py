# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Configuration management for Hello World Switch Card feature.

This module provides configuration management for the Hello World feature.

Since entities are defined in const.py, this config class focuses solely on
runtime configuration management without overriding entity definitions.

:platform: Home Assistant
:feature: Hello World Configuration
:components: Configuration Management, Validation
"""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from custom_components.ramses_extras.framework.helpers.config import ExtrasConfigManager

from .const import DEFAULT_CONFIG, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Configuration schema for the feature
FEATURE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=DEFAULT_CONFIG["enabled"]): cv.boolean,
        vol.Optional(
            "auto_discovery", default=DEFAULT_CONFIG["auto_discovery"]
        ): cv.boolean,
    }
)

# Options schema for the config entry
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=DEFAULT_CONFIG["enabled"]): cv.boolean,
        vol.Optional(
            "auto_discovery", default=DEFAULT_CONFIG["auto_discovery"]
        ): cv.boolean,
    }
)


class HelloWorldConfig(ExtrasConfigManager):
    """Manages configuration for Hello World feature.

    This class extends ExtrasConfigManager to provide Hello World specific
    configuration management. Unlike some other features, this config class
    does NOT override entity definitions - those are managed entirely in const.py.

    The configuration includes runtime settings such as:
    - Feature enable/disable status
    - Auto discovery settings

    Entity definitions (icons, templates, etc.) are managed in const.py and
    should not be overridden here.

    Attributes:
        hass (HomeAssistant): Home Assistant instance
        config_entry (ConfigEntry): Configuration entry for the integration
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize configuration manager.

        :param hass: Home Assistant instance
        :type hass: HomeAssistant
        :param config_entry: Configuration entry for the integration
        :type config_entry: ConfigEntry
        """
        super().__init__(
            hass=hass,
            config_entry=config_entry,
            feature_id=DOMAIN,
            default_config=DEFAULT_CONFIG,
        )

        _LOGGER.info("Initialized %s configuration manager", DOMAIN)

    def validate_config(self) -> bool:
        """Validate Hello World feature configuration.

        :return: True if configuration is valid
        :rtype: bool
        """
        try:
            # Validate against schema
            FEATURE_CONFIG_SCHEMA(self.get_all())

            # Call parent validation for basic checks
            return super().validate_config()

        except vol.Invalid as err:
            _LOGGER.error("Hello World configuration validation error: %s", err)
            return False
        except Exception as e:
            _LOGGER.error("Hello World configuration validation failed: %s", e)
            return False

    def get_config_schema(self) -> dict[str, Any]:
        """Get Hello World configuration schema for UI.

        TODO: This is not fully implemented yet
        Note: This schema is for runtime configuration only. Entity definitions
        (icons, templates, etc.) are managed in const.py and not exposed here.

        :return: Configuration schema dictionary
        :rtype: dict[str, Any]
        """
        return self.get_config_schema_dict()

    def get_config_schema_dict(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "Default state for the Switch",
                    "description": "Example how to use configs in the submenu",
                    "default": DEFAULT_CONFIG["enabled"],
                },
                "auto_discovery": {
                    "type": "boolean",
                    "title": "Enable Auto Discovery",
                    "description": "Enable automatic discovery of Hello World entities",
                    "default": DEFAULT_CONFIG["auto_discovery"],
                },
            },
            "required": ["enabled"],
        }

    def is_auto_discovery_enabled(self) -> bool:
        """Check if auto discovery is enabled in configuration.

        :return: True if auto discovery is enabled, False otherwise
        :rtype: bool
        """
        return bool(self.get("auto_discovery", DEFAULT_CONFIG["auto_discovery"]))


# Inherited methods from ExtrasConfigManager (most commonly used):
# - async_load() - Load configuration from config entry and defaults
# - async_save() - Save current configuration
# - get(key, default) - Get configuration value
# - set(key, value) - Set configuration value
# - get_all() - Get all configuration values
# - update(updates) - Update multiple configuration values
# - is_enabled() - Check if feature is enabled
# - reset_to_defaults() - Reset configuration to default values
# - validate_config() - Validate current configuration


def create_hello_world_config(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> HelloWorldConfig:
    """Factory function to create Hello World configuration manager.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param config_entry: Configuration entry
    :type config_entry: ConfigEntry
    :return: Hello World configuration manager instance
    :rtype: HelloWorldConfig
    """
    return HelloWorldConfig(hass, config_entry)


__all__ = [
    "HelloWorldConfig",
    "create_hello_world_config",
    "FEATURE_CONFIG_SCHEMA",
    "OPTIONS_SCHEMA",
]
