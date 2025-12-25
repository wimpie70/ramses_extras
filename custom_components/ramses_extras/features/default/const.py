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

# Default feature constant configuration for EntityManager
DEFAULT_CONST = {
    "required_entities": {
        "sensor": ["indoor_absolute_humidity", "outdoor_absolute_humidity"]
    }
}

# Entity patterns for absolute humidity sensors
# Maps sensor types to their required underlying temperature and humidity entities
ENTITY_PATTERNS = {
    "indoor_absolute_humidity": ("indoor_temp", "indoor_humidity"),
    "outdoor_absolute_humidity": ("outdoor_temp", "outdoor_humidity"),
}

# WebSocket command constants for the default feature
WS_CMD_GET_AVAILABLE_DEVICES = "ramses_extras/get_available_devices"
WS_CMD_GET_BOUND_REM = "ramses_extras/get_bound_rem"
WS_CMD_GET_2411_SCHEMA = "ramses_extras/get_2411_schema"
WS_CMD_SEND_FAN_COMMAND = "ramses_extras/default/send_fan_command"
WS_CMD_GET_ENABLED_FEATURES = "ramses_extras/default/get_enabled_features"
WS_CMD_GET_CARDS_ENABLED = "ramses_extras/default/get_cards_enabled"
WS_CMD_GET_ENTITY_MAPPINGS = "ramses_extras/get_entity_mappings"
WS_CMD_GET_ALL_FEATURE_ENTITIES = "ramses_extras/get_all_feature_entities"

# WebSocket commands for the default feature
DEFAULT_WEBSOCKET_COMMANDS = {
    "get_available_devices": WS_CMD_GET_AVAILABLE_DEVICES,
    "get_bound_rem": WS_CMD_GET_BOUND_REM,
    "get_2411_schema": WS_CMD_GET_2411_SCHEMA,
    "get_enabled_features": WS_CMD_GET_ENABLED_FEATURES,
    "get_cards_enabled": WS_CMD_GET_CARDS_ENABLED,
    "get_entity_mappings": WS_CMD_GET_ENTITY_MAPPINGS,
    "get_all_feature_entities": WS_CMD_GET_ALL_FEATURE_ENTITIES,
}


def load_feature() -> None:
    """Load default feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_sensor_configs(DEFAULT_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(DEFAULT_SWITCH_CONFIGS)
    extras_registry.register_number_configs(DEFAULT_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(DEFAULT_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(DEFAULT_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    extras_registry.register_websocket_commands("default", DEFAULT_WEBSOCKET_COMMANDS)

    # Also register the websocket_commands module for auto-discovery
    from custom_components.ramses_extras.features.default import websocket_commands

    extras_registry.register_feature("default")


__all__ = [
    "FEATURE_ID_DEFAULT",
    "DEFAULT_CONST",
    "DEFAULT_SENSOR_CONFIGS",
    "DEFAULT_SWITCH_CONFIGS",
    "DEFAULT_NUMBER_CONFIGS",
    "DEFAULT_BOOLEAN_CONFIGS",
    "DEFAULT_DEVICE_ENTITY_MAPPING",
    "ENTITY_PATTERNS",
    "WS_CMD_GET_AVAILABLE_DEVICES",
    "WS_CMD_GET_BOUND_REM",
    "WS_CMD_GET_2411_SCHEMA",
    "WS_CMD_SEND_FAN_COMMAND",
    "WS_CMD_GET_ENABLED_FEATURES",
    "WS_CMD_GET_CARDS_ENABLED",
    "WS_CMD_GET_ENTITY_MAPPINGS",
    "WS_CMD_GET_ALL_FEATURE_ENTITIES",
    "DEFAULT_WEBSOCKET_COMMANDS",
    "load_feature",
]
