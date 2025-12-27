"""HVAC Fan Card feature - Advanced control card for Orcon ventilation systems."""

from typing import Any

DOMAIN = "hvac_fan_card"

# Feature identification
FEATURE_ID = "hvac_fan_card"

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
HVAC_FAN_CARD_CARD_CONFIG = {
    "hvac_fan_card": {
        "card_path": "features/hvac_fan_card",  # Updated path
        "main_js": "hvac-fan-card.js",
        "editor_js": "hvac-fan-card-editor.js",
        "templates_path": "templates/",
        "translations_path": "translations/",
    }
}

# WebSocket commands for the HVAC fan card feature
# Note: Fan commands are now provided by the default feature for all cards to use
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
    "required_entities": {},  # No entities created by this feature
    # Cards that this feature manages
    "cards": HVAC_FAN_CARD_CONFIGS,
    "websocket_commands": HVAC_FAN_CARD_WEBSOCKET_COMMANDS,
    # Device mappings for the feature
    "device_mappings": HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING,
    # Entity mappings for frontend cards
    "entity_mappings": {
        # Absolute humidity sensors provided by integration
        "indoor_abs_humid_entity": "sensor.indoor_absolute_humidity_{device_id}",
        "outdoor_abs_humid_entity": "sensor.outdoor_absolute_humidity_{device_id}",
        # Temperature sensors
        "indoor_temp_entity": "sensor.{device_id}_indoor_temp",
        "outdoor_temp_entity": "sensor.{device_id}_outdoor_temp",
        "supply_temp_entity": "sensor.{device_id}_supply_temp",
        "exhaust_temp_entity": "sensor.{device_id}_exhaust_temp",
        # Humidity sensors
        "indoor_humidity_entity": "sensor.{device_id}_indoor_humidity",
        "outdoor_humidity_entity": "sensor.{device_id}_outdoor_humidity",
        # Fan / airflow sensors
        "fan_speed_entity": "sensor.{device_id}_fan_rate",
        "fan_mode_entity": "sensor.{device_id}_fan_mode",
        "flow_entity": "sensor.{device_id}_supply_flow",
        # CO2 sensor
        "co2_entity": "sensor.{device_id}_co2_level",
        # Bypass position
        "bypass_entity": "binary_sensor.{device_id}_bypass_position",
        # Dehumidify controls
        "dehum_mode_entity": "switch.dehumidify_{device_id}",
        "dehum_active_entity": "binary_sensor.dehumidifying_active_{device_id}",
        # Comfort temperature parameter
        "comfort_temp_entity": "number.{device_id}_param_75",
    },
}


def load_feature() -> None:
    """Load hvac_fan_card feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register device mappings (indicates card is available for HvacVentilator devices)
    extras_registry.register_device_mappings(HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    extras_registry.register_websocket_commands(
        "hvac_fan_card", HVAC_FAN_CARD_WEBSOCKET_COMMANDS
    )

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
    "HVAC_FAN_CARD_CARD_CONFIG",
    "load_feature",
]
