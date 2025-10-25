# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#

from pathlib import Path

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
DESCRIPTION_PLACEHOLDER_INFO = (
    "Ramses Extras provides additional functionality on top of Ramses RF."
)
CARD_FOLDER = "www"

# Device type to entity type mapping
# Each feature defines a card/automation with specific requirements
AVAILABLE_FEATURES = {
    "hvac_fan_card": {
        "name": "Hvac Fan Control Card",
        "description": "Advanced control card for Orcon or other ventilation systems",
        "category": "cards",
        "location": "hvac_fan_card/hvac-fan-card.js",
        "editor": "hvac_fan_card/hvac-fan-card-editor.js",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
            "switches": [],
            "binary_sensors": [],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
    "humidity_control": {
        "name": "Humidity Control",
        "description": "Creates dehumidify control entities and automation",
        "category": "automations",
        "location": "automations/humidity_control_template.yaml",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
            "switches": ["dehumidify"],
            "numbers": ["rel_humid_min", "rel_humid_max"],
            "binary_sensors": ["dehumidifying"],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
}

# Device type to entity type mapping
DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
        "switches": ["dehumidify"],
        "binary_sensors": ["dehumidifying"],
        "numbers": ["rel_humid_min", "rel_humid_max"],
    },
}

# Entity configurations for different sensor types
ENTITY_CONFIGS = {
    "indoor_abs_humid": {
        "name_template": "Indoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
    },
    "outdoor_abs_humid": {
        "name_template": "Outdoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
    },
}

# Switch configurations
SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
    },
}

BOOLEAN_CONFIGS = {
    "dehumidifying": {
        "name_template": "Dehumidifying Active",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
    },
}

# Number configurations for threshold values
NUMBER_CONFIGS = {
    "rel_humid_min": {
        "name_template": "Relative Humidity Minimum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-minus",
        "device_class": None,
        "min_value": 30,
        "max_value": 80,
        "step": 1,
        "default_value": 40,
        "supported_device_types": ["HvacVentilator"],
    },
    "rel_humid_max": {
        "name_template": "Relative Humidity Maximum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-plus",
        "device_class": None,
        "min_value": 50,
        "max_value": 90,
        "step": 1,
        "default_value": 60,
        "supported_device_types": ["HvacVentilator"],
    },
}

# Entity type to config mapping
ENTITY_TYPE_CONFIGS = {
    "sensor": ENTITY_CONFIGS,
    "switch": SWITCH_CONFIGS,
    "binary_sensor": BOOLEAN_CONFIGS,
    "number": NUMBER_CONFIGS,
}

# Device type to service mapping
# Defines which services are available for each device type
DEVICE_SERVICE_MAPPING = {
    "HvacVentilator": [
        "set_fan_speed_mode",
    ],
    # Future device types can be added here
    # "CO2Remote": [
    #     "set_co2_mode",
    #     "calibrate_sensor",
    # ],
}

# Service configuration schemas
SERVICE_SCHEMAS = {
    "set_fan_speed_mode": {
        "device_id": {"required": True, "type": "string"},
        "mode": {
            "required": True,
            "type": "string",
            "valid_values": ["low", "medium", "high", "auto", "away", "boost"],
        },
        "duration": {
            "required": False,
            "type": "integer",
            "min": 1,
            "max": 1440,
        },  # minutes
        "reason": {"required": False, "type": "string"},
    },
}
