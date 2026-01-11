"""Humidity control feature - feature-specific entity and configuration definitions."""

from typing import Any

from homeassistant.helpers.entity import EntityCategory

# Feature identification
FEATURE_ID = "humidity_control"

# Feature-specific brand customizers configuration
ORCON_DEVICE_MODELS = {
    "HRV400": {
        "max_fan_speed": 5,
        "humidity_range": (30, 80),
        "supported_modes": ["auto", "boost", "eco", "night"],
        "special_entities": ["filter_timer", "boost_timer", "eco_mode"],
    },
    "HRV300": {
        "max_fan_speed": 4,
        "humidity_range": (35, 75),
        "supported_modes": ["auto", "boost", "eco"],
        "special_entities": ["filter_timer", "boost_timer"],
    },
    "HRV200": {
        "max_fan_speed": 3,
        "humidity_range": (40, 70),
        "supported_modes": ["auto", "boost"],
        "special_entities": ["filter_timer"],
    },
}

ZEHNDER_DEVICE_MODELS = {
    "ComfoAir Q350": {
        "max_fan_speed": 4,
        "humidity_range": (30, 75),
        "supported_modes": ["auto", "boost", "eco", "night"],
        "special_entities": ["filter_timer", "co2_sensor", "auto_mode"],
    },
    "ComfoAir Q450": {
        "max_fan_speed": 5,
        "humidity_range": (25, 80),
        "supported_modes": ["auto", "boost", "eco", "night", "away"],
        "special_entities": ["filter_timer", "co2_sensor", "auto_mode", "away_mode"],
    },
}

# Feature-specific switch configurations
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
    },
}

# Feature-specific number configurations
HUMIDITY_NUMBER_CONFIGS = {
    "relative_humidity_minimum": {
        "name_template": "Min Humidity {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-minus",
        "device_class": None,
        "min_value": 30,
        "max_value": 80,
        "step": 1,
        "default_value": 40,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_minimum_{device_id}",
    },
    "relative_humidity_maximum": {
        "name_template": "Max Humidity {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-plus",
        "device_class": None,
        "min_value": 50,
        "max_value": 90,
        "step": 1,
        "default_value": 60,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_maximum_{device_id}",
    },
    "absolute_humidity_offset": {
        "name_template": "Humidity Offset {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "g/m³",
        "icon": "mdi:swap-horizontal",
        "device_class": None,
        "min_value": -3.0,
        "max_value": 3.0,
        "step": 0.1,
        "default_value": 0.4,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "absolute_humidity_offset_{device_id}",
    },
}

# Feature-specific binary sensor configurations
HUMIDITY_BOOLEAN_CONFIGS = {
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
    },
}

# Feature-specific device mapping
HUMIDITY_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "switch": ["dehumidify"],
        "number": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "binary_sensor": ["dehumidifying_active"],
    },
}

# WebSocket commands for the humidity control feature
HUMIDITY_CONTROL_WEBSOCKET_COMMANDS: dict[str, str] = {}

# Enhanced entity configurations with default_enabled flags
ENHANCED_HUMIDITY_SWITCH_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in HUMIDITY_SWITCH_CONFIGS.items()
}

ENHANCED_HUMIDITY_NUMBER_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in HUMIDITY_NUMBER_CONFIGS.items()
}

ENHANCED_HUMIDITY_BOOLEAN_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in HUMIDITY_BOOLEAN_CONFIGS.items()
}

# Default configuration template for humidity control feature
# This provides the baseline configuration that gets merged with user settings
HUMIDITY_CONTROL_DEFAULTS = {
    # Core settings
    "enabled": True,
    "automation_enabled": False,  # Only enable when user explicitly toggles
    "default_min_humidity": 40.0,
    "default_max_humidity": 60.0,
    # Essential thresholds
    "activation_threshold": 1.0,
    "deactivation_threshold": -1.0,
    # Sensor configuration
    "indoor_sensor_entity": None,
    "outdoor_sensor_entity": None,
    # Basic safety
    "max_runtime_minutes": 120,
    "cooldown_period_minutes": 15,
}

FEATURE_DEFINITION = {
    "feature_id": FEATURE_ID,
    "sensor_configs": {},
    "switch_configs": HUMIDITY_SWITCH_CONFIGS,
    "number_configs": HUMIDITY_NUMBER_CONFIGS,
    "boolean_configs": HUMIDITY_BOOLEAN_CONFIGS,
    "device_entity_mapping": HUMIDITY_DEVICE_ENTITY_MAPPING,
    "websocket_commands": HUMIDITY_CONTROL_WEBSOCKET_COMMANDS,
    "required_entities": {
        "number": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "switch": ["dehumidify"],
        "binary_sensor": ["dehumidifying_active"],
    },
    "entity_mappings": {
        "indoor_abs": "sensor.indoor_absolute_humidity_{device_id}",
        "outdoor_abs": "sensor.outdoor_absolute_humidity_{device_id}",
        "indoor_rh": "sensor.{device_id}_indoor_humidity",
        "min_humidity": "number.relative_humidity_minimum_{device_id}",
        "max_humidity": "number.relative_humidity_maximum_{device_id}",
        "offset": "number.absolute_humidity_offset_{device_id}",
        "dehumidify": "switch.dehumidify_{device_id}",
    },
}


def load_feature() -> None:
    """Load humidity control feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_switch_configs(HUMIDITY_SWITCH_CONFIGS)
    extras_registry.register_number_configs(HUMIDITY_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(HUMIDITY_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(HUMIDITY_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    extras_registry.register_websocket_commands(
        "humidity_control", HUMIDITY_CONTROL_WEBSOCKET_COMMANDS
    )

    extras_registry.register_feature("humidity_control")


__all__ = [
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
    "HUMIDITY_CONTROL_WEBSOCKET_COMMANDS",
    "HUMIDITY_CONTROL_DEFAULTS",
    "ORCON_DEVICE_MODELS",
    "ZEHNDER_DEVICE_MODELS",
    "ENHANCED_HUMIDITY_SWITCH_CONFIGS",
    "ENHANCED_HUMIDITY_NUMBER_CONFIGS",
    "ENHANCED_HUMIDITY_BOOLEAN_CONFIGS",
    "load_feature",
]
