# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Core constants for Ramses Extras integration."""

from pathlib import Path
from typing import Any, Callable

DOMAIN = "ramses_extras"

# Import shared path constants
try:
    from .framework.helpers.paths import DEPLOYMENT_PATHS, HELPER_PATHS
    from .framework.helpers.paths import PATHS as WEB_PATHS
except ImportError:
    # Fallback constants if paths module is not available
    WEB_PATHS = None  # type: ignore[assignment]
    HELPER_PATHS = None  # type: ignore[assignment]
    DEPLOYMENT_PATHS = None  # type: ignore[assignment]

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

# Command framework constants
COMMAND_MIN_INTERVAL = 0.5  # Minimum interval between commands (seconds)

# UI/Frontend constants
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
FEATURE_ID_HELLO_WORLD_CARD = "hello_world_card"

# Event system constants
EVENT_DEVICE_READY_FOR_ENTITIES = "ramses_device_ready_for_entities"

# Device Type Handler Mapping - Central registry for device type handlers
DEVICE_TYPE_HANDLERS: dict[str, Callable] = {}


def register_device_handler(device_type: str) -> Callable[[Callable], Callable]:
    """Decorator to register device type handlers."""

    def decorator(handler: Callable) -> Callable:
        DEVICE_TYPE_HANDLERS[device_type] = handler
        return handler

    return decorator


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


# Description placeholder for configuration
DESCRIPTION_PLACEHOLDER_INFO = (
    "Ramses Extras provides additional functionality on top of Ramses RF."
)

# WebSocket command registry for feature-centric organization
WS_COMMAND_REGISTRY: dict[str, dict[str, str]] = {}


def register_ws_commands(feature_name: str, command_configs: dict[str, str]) -> None:
    """Register WebSocket commands for a feature.

    Args:
        feature_name: Name of the feature
        command_configs: Dictionary mapping command names to command types
    """
    WS_COMMAND_REGISTRY[feature_name] = command_configs


def get_ws_commands_for_feature(feature_name: str) -> dict[str, str]:
    """Get WebSocket commands for a feature.

    Args:
        feature_name: Name of the feature

    Returns:
        Dictionary mapping command names to command types
    """
    return WS_COMMAND_REGISTRY.get(feature_name, {})


def get_all_ws_commands() -> dict[str, dict[str, str]]:
    """Get all registered WebSocket commands.

    Returns:
        Dictionary of feature name to command mappings
    """
    return WS_COMMAND_REGISTRY.copy()


def discover_ws_commands() -> list[str]:
    """Discover all features that have WebSocket commands registered.

    Returns:
        List of feature names with WebSocket commands
    """
    return list(WS_COMMAND_REGISTRY.keys())


# Available features registry - dynamically populated by feature discovery
AVAILABLE_FEATURES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default sensor",
        "description": "Base humidity sensor available for all devices",
        "feature_module": "features.default",
        "handler": "handle_hvac_ventilator",
        "default_enabled": True,
    },
    "humidity_control": {
        "name": "Humidity Control",
        "description": "Automatic humidity control and dehumidification management",
        "feature_module": "features.humidity_control",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
    },
    "hvac_fan_card": {
        "name": "HVAC Fan Card",
        "description": "Advanced fan card for control and configuration",
        "feature_module": "features.hvac_fan_card",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
    },
    "hello_world_card": {
        "name": "Hello World Switch Card",
        "description": (
            "Template feature demonstrating complete Ramses Extras architecture"
        ),
        "feature_module": "features.hello_world_card",
        "handler": "handle_hvac_ventilator",
        "default_enabled": False,
    },
}
