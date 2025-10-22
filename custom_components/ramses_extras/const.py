# Part of the Ramses Extra integration

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

SENSOR_TYPES = {
    "test1": "test1 text",
    "test2": "test2 text",
    "indoor_abs_humid": "Indoor Absolute Humidity",
    "outdoor_abs_humid": "Outdoor Absolute Humidity",
}

BOOLEAN_TYPES = {
    "dehumidifying": "Dehumidifying Active",
}

SWITCH_TYPES = {
    "dehumidify": "Activate Dehumidify Automation",
}

# Available features/cards configuration
# Each feature defines a card/automation with specific requirements
AVAILABLE_FEATURES = {
    "test1": {
        "name": "test1",
        "description": "TEST 1",
        "category": "cards",
        "folder": "",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["test1"],
            "switches": [],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
    "test2": {
        "name": "test2",
        "description": "TEST 2",
        "category": "cards",
        "folder": "",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["test2"],
            "switches": ["test2"],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
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
            "switches": ["dehumidify"],
            "booleans": ["dehumidifying"],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
    "humidity_automation": {
        "name": "Humidity Automation",
        "description": "Automation for improved humidity maintenance",
        "category": "automations",
        "location": "automations/humidity_automation",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
            "switches": ["dehumidify"],
            "booleans": ["dehumidifying"],
        },
        "optional_entities": {
            "sensors": [],
            "switches": [],
        },
    },
}

# Categories for organizing features
FEATURE_CATEGORIES = {
    "cards": "Dashboard Cards",
    "automations": "Automations",
    "scripts": "Scripts",
}

# Device type to entity type mapping
DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_abs_humid", "outdoor_abs_humid", "test1", "test2"],
        "switches": ["dehumidify"],
        "booleans": ["dehumidifying"],
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

# Entity type to config mapping
ENTITY_TYPE_CONFIGS = {
    "sensor": ENTITY_CONFIGS,
    "switch": SWITCH_CONFIGS,
    "binary_sensor": BOOLEAN_CONFIGS,
}
