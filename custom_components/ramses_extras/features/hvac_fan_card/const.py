"""HVAC Fan Card feature - Advanced control card for Orcon ventilation systems."""

from typing import Any

# Feature identification
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"

# HVAC Fan Card inherits shared sensors from default feature
# No additional entity configurations needed - uses shared sensors
HVAC_FAN_CARD_SENSOR_CONFIGS: dict[
    str, dict[str, Any]
] = {}  # Inherits from default feature
HVAC_FAN_CARD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific switches
HVAC_FAN_CARD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific numbers
HVAC_FAN_CARD_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific booleans

# Device mapping (inherits shared sensors from default)
HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Inherited from default feature
        "switches": [],
        "numbers": [],
        "binary_sensors": [],
    },
}

# Card-specific configuration constants
HVAC_FAN_CARD_CONFIG = {
    "feature_id": FEATURE_ID_HVAC_FAN_CARD,
    "name": "HVAC Fan Control Card",
    "description": "Advanced control card for Orcon or other ventilation systems",
    "category": "cards",
    "location": "hvac_fan_card/hvac-fan-card.js",
    "editor": "hvac_fan_card/hvac-fan-card-editor.js",
    "translations": "hvac_fan_card/translations",
    "default_enabled": False,
    "supported_device_types": ["HvacVentilator"],
    "required_entities": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": [],
        "binary_sensors": [],
    },
    "optional_entities": {
        "sensors": [],
        "switches": [],
    },
    "web_sockets": ["get_bound_rem"],
    "handle_codes": ["31DA", "10D0"],
    "callback_prefix": "handle_",
}

__all__ = [
    "FEATURE_ID_HVAC_FAN_CARD",
    "HVAC_FAN_CARD_CONFIG",
    "HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING",
]
