"""CO2 control feature - feature-specific entity and configuration definitions."""

from typing import Any

from homeassistant.helpers.entity import EntityCategory

# Feature identification
FEATURE_ID = "co2_control"

# Feature-specific switch configurations
CO2_SWITCH_CONFIGS = {
    "co2_control": {
        "name_template": "CO2 Control {device_id}",
        "icon": "mdi:molecule-co2",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_control_{device_id}",
    },
}

# Feature-specific number configurations
CO2_NUMBER_CONFIGS = {
    "co2_threshold": {
        "name_template": "CO2 Threshold {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "ppm",
        "icon": "mdi:molecule-co2",
        "device_class": None,
        "min_value": 400,
        "max_value": 2000,
        "step": 50,
        "default_value": 1000,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_threshold_{device_id}",
    },
    "co2_activation_hysteresis": {
        "name_template": "CO2 Activation Hysteresis {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "ppm",
        "icon": "mdi:delta",
        "device_class": None,
        "min_value": 0,
        "max_value": 500,
        "step": 10,
        "default_value": 100,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_activation_hysteresis_{device_id}",
    },
    "co2_deactivation_hysteresis": {
        "name_template": "CO2 Deactivation Hysteresis {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "ppm",
        "icon": "mdi:delta",
        "device_class": None,
        "min_value": -500,
        "max_value": 0,
        "step": 10,
        "default_value": -100,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_deactivation_hysteresis_{device_id}",
    },
}

# Feature-specific binary sensor configurations
CO2_BINARY_SENSOR_CONFIGS = {
    "co2_active": {
        "name_template": "CO2 Active {device_id}",
        "icon": "mdi:molecule-co2",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_active_{device_id}",
    },
}

# Feature-specific sensor configurations
CO2_SENSOR_CONFIGS = {
    "co2_zone_status": {
        "name_template": "CO2 Zone Status {device_id}",
        "icon": "mdi:home-analytics",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": None,
        "unit": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_zone_status_{device_id}",
    },
}

# Feature-specific device mapping
CO2_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "switch": ["co2_control"],
        "number": [
            "co2_threshold",
            "co2_activation_hysteresis",
            "co2_deactivation_hysteresis",
        ],
        "binary_sensor": ["co2_active"],
        "sensor": ["co2_zone_status"],
    },
}

# WebSocket commands for the CO2 control feature
CO2_CONTROL_WEBSOCKET_COMMANDS: dict[str, str] = {
    "get_co2_status": "ramses_extras/co2/get_status",
    "get_zone_details": "ramses_extras/co2/get_zone_details",
    "update_zone_config": "ramses_extras/co2/update_zone",
    "get_co2_history": "ramses_extras/co2/get_history",
}

# Enhanced entity configurations with default_enabled flags
ENHANCED_CO2_SWITCH_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in CO2_SWITCH_CONFIGS.items()
}

ENHANCED_CO2_NUMBER_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in CO2_NUMBER_CONFIGS.items()
}

ENHANCED_CO2_BINARY_SENSOR_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in CO2_BINARY_SENSOR_CONFIGS.items()
}

ENHANCED_CO2_SENSOR_CONFIGS = {
    key: {**config, "default_enabled": True}
    for key, config in CO2_SENSOR_CONFIGS.items()
}

# Default configuration template for CO2 control feature
CO2_CONTROL_DEFAULTS = {
    # Core settings
    "enabled": True,
    "automation_enabled": False,  # Only enable when user explicitly toggles
    "default_threshold": 1000,  # ppm
    # Hysteresis settings
    "activation_hysteresis": 100,  # ppm above threshold to activate
    "deactivation_hysteresis": -100,  # ppm below threshold to deactivate
    # Zone configuration
    "zones": [],  # List of zone configurations
    # Safety settings
    "max_runtime_minutes": 120,
    "cooldown_period_minutes": 15,
    # Priority settings
    "priority_over_humidity": True,  # CO2 always has priority
}

CO2_CONTROL_VALIDATION_RULES = {
    "enabled": {"type": "boolean", "required": False},
    "automation_enabled": {"type": "boolean", "required": False},
    "default_threshold": {
        "type": "numeric",
        "min": 400,
        "max": 2000,
        "required": False,
    },
    "activation_hysteresis": {
        "type": "numeric",
        "min": 0,
        "max": 500,
        "required": False,
    },
    "deactivation_hysteresis": {
        "type": "numeric",
        "min": -500,
        "max": 0,
        "required": False,
    },
    "max_runtime_minutes": {
        "type": "numeric",
        "min": 10,
        "max": 480,
        "required": False,
    },
}

FEATURE_DEFINITION = {
    "feature_id": FEATURE_ID,
    "sensor_configs": CO2_SENSOR_CONFIGS,
    "switch_configs": CO2_SWITCH_CONFIGS,
    "number_configs": CO2_NUMBER_CONFIGS,
    "boolean_configs": CO2_BINARY_SENSOR_CONFIGS,
    "device_entity_mapping": CO2_DEVICE_ENTITY_MAPPING,
    "websocket_commands": CO2_CONTROL_WEBSOCKET_COMMANDS,
    "required_entities": {
        "number": [
            "co2_threshold",
            "co2_activation_hysteresis",
            "co2_deactivation_hysteresis",
        ],
        "switch": ["co2_control"],
        "binary_sensor": ["co2_active"],
        "sensor": ["co2_zone_status"],
    },
    "entity_mappings": {
        # CO2 control entities (self)
        "co2_control": "switch.co2_control_{device_id}",
        "co2_threshold": "number.co2_threshold_{device_id}",
        "co2_active": "binary_sensor.co2_active_{device_id}",
        "co2_zone_status": "sensor.co2_zone_status_{device_id}",
    },
}


def load_feature() -> None:
    """Load CO2 control feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_sensor_configs(CO2_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(CO2_SWITCH_CONFIGS)
    extras_registry.register_number_configs(CO2_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(CO2_BINARY_SENSOR_CONFIGS)
    extras_registry.register_device_mappings(CO2_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    extras_registry.register_websocket_commands(
        "co2_control", CO2_CONTROL_WEBSOCKET_COMMANDS
    )

    extras_registry.register_feature("co2_control")

    # Load YAML validator and import/export functions
    from .co2_control_yaml import load_validator

    load_validator()


__all__ = [
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "CO2_SWITCH_CONFIGS",
    "CO2_NUMBER_CONFIGS",
    "CO2_BINARY_SENSOR_CONFIGS",
    "CO2_SENSOR_CONFIGS",
    "CO2_DEVICE_ENTITY_MAPPING",
    "CO2_CONTROL_WEBSOCKET_COMMANDS",
    "CO2_CONTROL_DEFAULTS",
    "CO2_CONTROL_VALIDATION_RULES",
    "ENHANCED_CO2_SWITCH_CONFIGS",
    "ENHANCED_CO2_NUMBER_CONFIGS",
    "ENHANCED_CO2_BINARY_SENSOR_CONFIGS",
    "ENHANCED_CO2_SENSOR_CONFIGS",
    "load_feature",
]
