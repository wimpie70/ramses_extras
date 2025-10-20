from homeassistant.helpers.entity import EntityCategory

DOMAIN = "ramses_extras"

WS_CMD_GET_BOUND_REM = f"{DOMAIN}/get_bound_rem"


SENSOR_TYPES = {
    "indoor_abs_humid": "Indoor Absolute Humidity",
    "outdoor_abs_humid": "Outdoor Absolute Humidity",
}

SWITCH_TYPES = {
    "dehumidify": "Dehumidify",
}

# Available features/cards configuration
# Each feature defines a card/automation with specific requirements
AVAILABLE_FEATURES = {
    "humidity_monitoring_card": {
        "name": "Humidity Monitoring Dashboard Card",
        "description": "Dashboard card for monitoring humidity levels",
        "category": "cards",
        "folder": "dashboard_cards/humidity_monitoring",
        "default_enabled": True,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
            "switches": [],
        },
        "optional_entities": {
            "sensors": [],
            "switches": ["dehumidify"],
        },
    },
    "dehumidifier_control_card": {
        "name": "Dehumidifier Control Card",
        "description": "Control card for dehumidification settings",
        "category": "cards",
        "folder": "dashboard_cards/dehumidifier_control",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid"],
            "switches": ["dehumidify"],
        },
        "optional_entities": {
            "sensors": ["outdoor_abs_humid"],
            "switches": [],
        },
    },
    "humidity_alert_automation": {
        "name": "Humidity Alert Automation",
        "description": "Automation that alerts when humidity is too high",
        "category": "automations",
        "folder": "automations/humidity_alerts",
        "default_enabled": False,
        "supported_device_types": ["HvacVentilator"],
        "required_entities": {
            "sensors": ["indoor_abs_humid"],
            "switches": [],
        },
        "optional_entities": {
            "sensors": ["outdoor_abs_humid"],
            "switches": ["dehumidify"],
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
        "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
        "switches": ["dehumidify"],
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

# Entity type to config mapping
ENTITY_TYPE_CONFIGS = {
    "sensor": ENTITY_CONFIGS,
    "switch": SWITCH_CONFIGS,
}
