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

# Device type to entity type mapping
# Each feature defines a card/automation with specific requirements


# Feature identifier constants
FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"

AVAILABLE_FEATURES = {
    FEATURE_ID_HUMIDITY_SENSORS: {
        "name": "Absolute Humidity Sensors",
        "description": (
            "Calculates Abs humidity from relative indoor&outdoor sensor entities."
        ),
        "category": "sensors",
        "default_enabled": False,
        "supported_device_types": [
            "HvacVentilator"
        ],  # Can be extended for other device types
        "required_entities": {
            "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
            "switches": [],
            "binary_sensors": [],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
    FEATURE_ID_HVAC_FAN_CARD: {
        "name": "Hvac Fan Control Card",
        "description": "Advanced control card for Orcon or other ventilation systems",
        "category": "cards",
        "location": "hvac_fan_card/hvac-fan-card.js",
        "editor": "hvac_fan_card/hvac-fan-card-editor.js",
        "translations": "hvac_fan_card/translations",
        "default_enabled": False,
        "supported_device_types": [
            "HvacVentilator"
        ],  # Can be extended for other device types
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
        # Message handling configuration for real-time updates
        "handle_codes": ["31DA", "10D0"],
        "callback_prefix": "handle_",
    },
    FEATURE_ID_HUMIDITY_CONTROL: {
        "name": "Humidity Control",
        "description": "Hardcoded humidity automation for ventilation control",
        "category": "automations",
        "automation_type": "hardcoded",  # NEW: indicates hardcoded vs template
        "location": "automations/humidity_automation.py",  # NEW: points to Python class
        "default_enabled": False,
        "supported_device_types": [
            "HvacVentilator"
        ],  # Can be extended for other device types
        "required_entities": {
            "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
            "switches": ["dehumidify"],
            "numbers": [
                "relative_humidity_minimum",
                "relative_humidity_maximum",
                "absolute_humidity_offset",
            ],
            "binary_sensors": ["dehumidifying_active"],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
}

# Device type to entity type mapping
# Maps each device type to the entities it can provide
# Add new device types here as they are supported
DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": ["dehumidify"],
        "binary_sensors": ["dehumidifying_active"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
    },
    # Future device types can be added here:
    # "CO2Remote": {
    #     "sensors": ["co2_level"],
    #     "numbers": ["co2_threshold"],
    # },
}

# Sensor configurations with improved naming templates
# Format: {name_template}_{device_id} -> generates "Indoor Absolute Humidity_32_153289"
SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        # NEW: Template for entity generation
        "entity_template": "indoor_absolute_humidity_{device_id}",
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        # NEW: Template for entity generation
        "entity_template": "outdoor_absolute_humidity_{device_id}",
    },
}

# Switch configurations
SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        # NEW: Template for entity generation
        "entity_template": "dehumidify_{device_id}",
    },
}

BOOLEAN_CONFIGS = {
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        # NEW: Template for entity generation
        "entity_template": "dehumidifying_active_{device_id}",
    },
}

# Number configurations for threshold values
NUMBER_CONFIGS = {
    "relative_humidity_minimum": {
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
        # NEW: Template for entity generation
        "entity_template": "relative_humidity_minimum_{device_id}",
    },
    "relative_humidity_maximum": {
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
        # NEW: Template for entity generation
        "entity_template": "relative_humidity_maximum_{device_id}",
    },
    "absolute_humidity_offset": {
        "name_template": "Absolute Humidity Offset",
        "entity_category": EntityCategory.CONFIG,
        "unit": "g/m³",
        "icon": "mdi:swap-horizontal",
        "device_class": None,
        "min_value": -3.0,  # for testing
        "max_value": 3.0,
        "step": 0.1,
        "default_value": 0.4,
        "supported_device_types": ["HvacVentilator"],
        # NEW: Template for entity generation
        "entity_template": "absolute_humidity_offset_{device_id}",
    },
}

# Entity type to config mapping
ENTITY_TYPE_CONFIGS = {
    "sensor": SENSOR_CONFIGS,
    "switch": SWITCH_CONFIGS,
    "binary_sensor": BOOLEAN_CONFIGS,
    "number": NUMBER_CONFIGS,
}

# Service registry - maps device types to their available services
# and registration handlers
# Defines which services are available for each device type and how to register them
SERVICE_REGISTRY = {
    "HvacVentilator": {
        "set_fan_speed_mode": {
            "module": ".services.fan_services",
            "function": "register_fan_services",
        },
        # Future device types can be added here
        # "CO2Remote": {
        #     "set_co2_mode": {
        #         "module": ".services.co2_services",
        #         "function": "register_co2_services"
        #     },
        #     "calibrate_sensor": {
        #         "module": ".services.co2_services",
        #         "function": "register_calibration_services"
        #     },
        # },
    },
}

# Backward compatibility alias
DEVICE_SERVICE_MAPPING = {
    device_type: list(services.keys())
    for device_type, services in SERVICE_REGISTRY.items()
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
