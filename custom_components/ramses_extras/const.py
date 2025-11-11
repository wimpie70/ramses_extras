# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#

from pathlib import Path
from typing import Any

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

# WebSocket features registry
# Define all available WebSocket features here
WEB_SOCKET_FEATURES = {
    "get_bound_rem": {
        "name": "Get Bound REM",
        "description": "Get the REMote that was BOUND to this FAN  in Ramses RF. ",
        "default_enabled": False,
    },
}

# Feature identifier constants
FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"

# Lightweight feature registry (metadata only)
# Entity definitions are now in feature-specific const.py files
# Framework entity registry aggregates all definitions from features
AVAILABLE_FEATURES: dict[str, dict[str, Any]] = {
    FEATURE_ID_HUMIDITY_SENSORS: {
        "name": "Absolute Humidity Sensors",
        "description": "Calculates absolute humidity from relative "
        "indoor&outdoor sensor entities.",
        "category": "sensors",
        "default_enabled": False,
        "feature_module": "custom_components.ramses_extras.features.humidity_sensors",
    },
    FEATURE_ID_HVAC_FAN_CARD: {
        "name": "HVAC Fan Control Card",
        "description": "Advanced control card for Orcon or other ventilation systems",
        "category": "cards",
        "default_enabled": False,
        "feature_module": "custom_components.ramses_extras.features.hvac_fan_card",
    },
    FEATURE_ID_HUMIDITY_CONTROL: {
        "name": "Humidity Control",
        "description": "Automatic humidity control and dehumidification management",
        "category": "automations",
        "default_enabled": False,
        "feature_module": "custom_components.ramses_extras.features.humidity_control",
    },
}

# Entity definitions have been moved to feature modules
# This is part of the constant consolidation to eliminate duplication
# Each feature now owns its own entity configurations
# Framework entity registry collects all definitions dynamically

# Entity definitions now managed exclusively by framework entity registry
# All definitions loaded from feature modules via EntityRegistry
# Default feature is loaded first, then enabled features
# No need for legacy compatibility constants
