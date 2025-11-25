"""Default feature - shared entity definitions that all features can inherit from."""

from typing import Any

from homeassistant.helpers.entity import EntityCategory

# Feature identification
FEATURE_ID_DEFAULT = "default"

# Base entity configurations (shared across features)
DEFAULT_SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
    },
}

# Empty base configs - features will define their own
DEFAULT_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
DEFAULT_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
DEFAULT_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

# Base device type to entity mapping
# Note: Default feature creates absolute humidity sensors for all devices
DEFAULT_DEVICE_ENTITY_MAPPING: dict[str, dict[str, Any]] = {
    "HvacVentilator": {
        "sensor": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Other entity types will be added by individual features
    },
}

# WebSocket command constants for the default feature
WS_CMD_GET_BOUND_REM = "ramses_extras/get_bound_rem"
WS_CMD_GET_2411_SCHEMA = "ramses_extras/get_2411_schema"

# WebSocket commands for the default feature
DEFAULT_WEBSOCKET_COMMANDS = {
    "get_bound_rem": WS_CMD_GET_BOUND_REM,
    "get_2411_schema": WS_CMD_GET_2411_SCHEMA,
}


def load_feature() -> None:
    """Load default feature into the registry."""
    from custom_components.ramses_extras.const import register_ws_commands
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_sensor_configs(DEFAULT_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(DEFAULT_SWITCH_CONFIGS)
    extras_registry.register_number_configs(DEFAULT_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(DEFAULT_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(DEFAULT_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    register_ws_commands("default", DEFAULT_WEBSOCKET_COMMANDS)

    extras_registry.register_feature("default")


__all__ = [
    "FEATURE_ID_DEFAULT",
    "DEFAULT_SENSOR_CONFIGS",
    "DEFAULT_SWITCH_CONFIGS",
    "DEFAULT_NUMBER_CONFIGS",
    "DEFAULT_BOOLEAN_CONFIGS",
    "DEFAULT_DEVICE_ENTITY_MAPPING",
    "WS_CMD_GET_BOUND_REM",
    "WS_CMD_GET_2411_SCHEMA",
    "DEFAULT_WEBSOCKET_COMMANDS",
    "load_feature",
]
