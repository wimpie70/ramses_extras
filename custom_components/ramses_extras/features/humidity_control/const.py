"""Humidity control feature - feature-specific entity definitions."""

from homeassistant.helpers.entity import EntityCategory

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

# Feature-specific constants for automation
HUMIDITY_CONTROL_CONST = {
    "feature_id": "humidity_control",
    # Entities that this feature creates and manages
    "required_entities": {
        "number": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "switch": ["dehumidify"],
        "binary_sensor": ["dehumidifying_active"],
    },
    # Entity mappings for automation logic
    # Note: Sensor entities are maintained by ramses_rf, not created by this feature
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
    from custom_components.ramses_extras.const import register_ws_commands
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_switch_configs(HUMIDITY_SWITCH_CONFIGS)
    extras_registry.register_number_configs(HUMIDITY_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(HUMIDITY_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(HUMIDITY_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    register_ws_commands("humidity_control", HUMIDITY_CONTROL_WEBSOCKET_COMMANDS)

    extras_registry.register_feature("humidity_control")


__all__ = [
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
    "HUMIDITY_CONTROL_WEBSOCKET_COMMANDS",
    "HUMIDITY_CONTROL_CONST",
    "load_feature",
]
