# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#

from pathlib import Path
from typing import Any, Callable

from homeassistant.helpers.entity import EntityCategory

# Get the integration directory
INTEGRATION_DIR = Path(__file__).parent

DOMAIN = "ramses_extras"

GITHUB_URL = "https://github.com/wimpie70/ramses_extras"
GITHUB_WIKI_URL = f"{GITHUB_URL}/wiki"

WS_CMD_GET_BOUND_REM = f"{DOMAIN}/get_bound_rem"

# Configuration constants
CONF_NAME = "name"
CONF_ENABLED_FEATURES = "enabled_features"
CONF_ENABLED_WEB_SOCKETS = "enabled_web_sockets"
CONF_MESSAGE_EVENTS = "message_events"  # Import from ramses_cc for enabling events
DESCRIPTION_PLACEHOLDER_INFO = (
    "Ramses Extras provides additional functionality on top of Ramses RF."
)
CARD_FOLDER = "www"
CARD_HELPERS_FOLDER = "www/helpers"
FEATURE_FOLDER = "features"

# Feature identifiers
# FEATURE_ID_FAN_CONTROL = "fan_control"
# FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"
FEATURE_ID_DEFAULT = "default"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"


# Feature registry (minimal metadata - actual config in feature modules)
# Entity definitions are in feature-specific const.py files
# Framework entity registry aggregates all definitions from features
AVAILABLE_FEATURES: dict[str, dict[str, Any]] = {
    FEATURE_ID_DEFAULT: {
        "name": "Default Sensors",
        "description": "Base humidity sensors available for all devices",
        "category": "sensors",
        "default_enabled": True,
        "feature_module": "features.default",
        "supported_device_types": ["HvacVentilator"],
        "handler": "handle_hvac_ventilator",
    },
    FEATURE_ID_HUMIDITY_CONTROL: {
        "name": "Humidity Control",
        "description": "Automatic humidity control and dehumidification management",
        "category": "automations",
        "default_enabled": False,
        "feature_module": "features.humidity_control",
        "supported_device_types": ["HvacVentilator"],
        "handler": "handle_hvac_ventilator",
    },
    FEATURE_ID_HVAC_FAN_CARD: {
        "name": "HVAC Fan Card",
        "description": "Advanced fan card for control and configuration",
        "category": "cards",
        "default_enabled": False,
        "feature_module": "features.hvac_fan_card",
        "supported_device_types": ["HvacVentilator"],
        "handler": "handle_hvac_ventilator",
    },
}

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


# Import global EntityRegistry - standalone to avoid circular imports
# Moved inside functions to avoid import issues during testing
# from .extras_registry import extras_registry  # noqa: E402
