"""HVAC Fan Card feature - Advanced control card for Orcon ventilation systems."""

from typing import Any

# HVAC Fan Card inherits shared sensor from default feature
# No additional entity configurations needed - uses shared sensor
HVAC_FAN_CARD_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

# Feature web assets configuration for this feature
FEATURE_WEB_CONFIGS = {
    "hvac_fan_card": {
        "web_folder": "hvac_fan_card",
        "main_card": "hvac-fan-card.js",
        "editor_card": "hvac-fan-card-editor.js",
        "has_templates": True,
        "has_translations": True,
    },
}

# Feature deployment configuration
FEATURE_CARD_CONFIG = {
    "hvac_fan_card": {
        "card_path": "features/hvac_fan_card",  # Updated path
        "main_js": "hvac-fan-card.js",
        "editor_js": "hvac-fan-card-editor.js",
        "templates_path": "templates/",
        "translations_path": "translations/",
    }
}

# WebSocket commands for the HVAC fan card feature
HVAC_FAN_CARD_WEBSOCKET_COMMANDS: dict[str, str] = {}

# HVAC Fan Card is a dashboard card feature
# The device mapping indicates which device types the card supports,
# but the card doesn't create any entities - it uses existing ones from default feature
# The empty lists indicate no entities are created by this feature
HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {
    "HvacVentilator": {
        "sensor": [],  # Uses sensors from default feature
        "switch": [],
        "number": [],
        "binary_sensor": [],
    },
}

# Card configurations for feature-centric card management
# To add new cards, simply add another dictionary to this list
HVAC_FAN_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "hvac-fan-card",
        "card_name": "HVAC Fan Card",
        "description": "Advanced fan card for control and configuration",
        "location": "hvac_fan_card",
        "preview": True,
        "documentation_url": "https://github.com/wimpie70/ramses_extras/wiki/HVAC-Fan-Card",
        "supported_device_types": ["HvacVentilator"],
        "javascript_file": "hvac-fan-card.js",
    },
    # Example: Uncomment and modify to add a second card
    # {
    #     "card_id": "hvac-status-card",
    #     "card_name": "HVAC Status Card",
    #     "description": "Status monitoring card for HVAC systems",
    #     "location": "hvac_fan_card",
    #     "preview": True,
    #     "documentation_url": "https://github.com/wimpie70/ramses_extras/wiki/HVAC-Status-Card",
    #     "supported_device_types": ["HvacVentilator"],
    #     "javascript_file": "hvac-status-card.js",
    # },
]

# Feature-specific constants for HVAC Fan Card management
HVAC_FAN_CARD_CONST = {
    "feature_id": "hvac_fan_card",
    # Cards that this feature manages
    "cards": HVAC_FAN_CARD_CONFIGS,
    # Device mappings for the feature
    "device_mappings": HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING,
}


def load_feature() -> None:
    """Load hvac_fan_card feature into the registry."""
    from custom_components.ramses_extras.const import register_ws_commands
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register device mappings (indicates card is available for HvacVentilator devices)
    extras_registry.register_device_mappings(HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    register_ws_commands("hvac_fan_card", HVAC_FAN_CARD_WEBSOCKET_COMMANDS)

    # Register each card configuration for feature-centric card management
    for card_config in HVAC_FAN_CARD_CONFIGS:
        extras_registry.register_card_config("hvac_fan_card", card_config)

    extras_registry.register_feature("hvac_fan_card")


__all__ = [
    "HVAC_FAN_CARD_SENSOR_CONFIGS",
    "HVAC_FAN_CARD_SWITCH_CONFIGS",
    "HVAC_FAN_CARD_NUMBER_CONFIGS",
    "HVAC_FAN_CARD_BOOLEAN_CONFIGS",
    "HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING",
    "HVAC_FAN_CARD_WEBSOCKET_COMMANDS",
    "HVAC_FAN_CARD_CONFIGS",
    "HVAC_FAN_CARD_CONST",
    "FEATURE_WEB_CONFIGS",
    "FEATURE_CARD_CONFIG",
    "load_feature",
]
