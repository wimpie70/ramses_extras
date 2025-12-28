# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Core constants for Ramses Extras integration."""

from pathlib import Path
from typing import Any, Callable

DOMAIN = "ramses_extras"

# Get the integration directory
INTEGRATION_DIR = Path(__file__).parent

# GitHub and documentation URLs
GITHUB_URL = "https://github.com/wimpie70/ramses_extras"
GITHUB_WIKI_URL = f"{GITHUB_URL}/wiki"

# Configuration constants
CONF_NAME = "name"
CONF_ENABLED_FEATURES = "enabled_features"
CONF_ENABLED_WEB_SOCKETS = "enabled_web_sockets"
CONF_MESSAGE_EVENTS = "message_events"

# UI/Frontend constants (still needed for backward compatibility)
CARD_FOLDER = "www"
CARD_HELPERS_FOLDER = "framework/www"
FEATURE_FOLDER = "features"

# Web assets path constants (for reorganization)
WEB_ASSETS_BASE = "www"
FEATURE_WEB_BASE = "features"
CARD_DEPLOYMENT_PATH = "www/ramses_extras"
HELPERS_DEPLOYMENT_PATH = "www/ramses_extras/helpers"

# Feature identifiers
FEATURE_ID_DEFAULT = "default"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"
FEATURE_ID_hello_world = "hello_world"

# Event system constants
EVENT_DEVICE_READY_FOR_ENTITIES = "ramses_device_ready_for_entities"
EVENT_DEVICES_UPDATED = "ramses_extras_devices_updated"

# Platform registry for dynamic feature platform discovery
PLATFORM_REGISTRY: dict[str, dict[str, Callable]] = {}


def register_feature_platform(
    platform: str, feature_name: str, setup_func: Callable
) -> None:
    """Register a feature platform setup function."""
    if platform not in PLATFORM_REGISTRY:
        PLATFORM_REGISTRY[platform] = {}
    PLATFORM_REGISTRY[platform][feature_name] = setup_func


def get_feature_platform_setups(platform: str) -> list[Callable]:
    """Get all registered setup functions for a platform."""
    return list(PLATFORM_REGISTRY.get(platform, {}).values())


# Available features registry - simplified for new architecture
AVAILABLE_FEATURES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default",
        "description": "Base humidity sensor available for fan devices",
        "feature_module": "features.default",
        "handler": "handle_hvac_ventilator",
        "default_enabled": True,
        # Use FAN slug to match ventilation devices, in line with the
        # main menu specification.
        "allowed_device_slugs": ["FAN"],
        "has_device_config": True,
    },
    "humidity_control": {
        "name": "Humidity Control",
        "description": "Automatic humidity control and dehumidification management",
        "feature_module": "features.humidity_control",
        "handler": "handle_hvac_ventilator",
        "default_enabled": True,
        "allowed_device_slugs": ["FAN"],
        "has_device_config": True,
    },
    "hvac_fan_card": {
        "name": "HVAC Fan Card",
        "description": "Advanced fan card for control and configuration",
        "feature_module": "features.hvac_fan_card",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
        "allowed_device_slugs": ["FAN"],
        "has_device_config": True,
    },
    "hello_world": {
        "name": "Hello World Switch Card",
        "description": (
            "Template feature demonstrating complete Ramses Extras architecture"
        ),
        "feature_module": "features.hello_world",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
        "allowed_device_slugs": ["*"],
        "has_device_config": True,
    },
    "sensor_control": {
        "name": "Sensor Control",
        "description": (
            "Central sensor source selection (indoor/outdoor/CO2 + abs humidity)"
        ),
        "feature_module": "features.sensor_control",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
        "allowed_device_slugs": ["FAN", "CO2"],
        "has_device_config": True,
    },
}
