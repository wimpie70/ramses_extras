# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for Hello World  feature.

This module defines all constants, configurations, and entity mappings for the
Hello World feature, including entity configurations, device mappings,
and WebSocket command definitions.

`FEATURE_DEFINITION` is the canonical structure consumed by the framework.

Semantics:
- `*_configs` (e.g. `switch_configs`) define how an entity is constructed.
- `required_entities` defines which entities must exist for a feature/device.
  - If `required_entities` is omitted, the framework derives it from `*_configs`.
  - Derivation excludes any entity config where `optional: True`.
- `entity_mappings` (when present) is for frontend/automation mapping and may
  include entities that are created elsewhere.

:platform: Home Assistant
:feature: Hello World Constants
:components: Entity Configurations, Device Mappings, WebSocket Commands
:data_types: Dictionaries, Lists, Strings
"""

from typing import Any

DOMAIN = "hello_world"

# Feature identification
FEATURE_ID = "hello_world"

# Feature configuration
FEATURE_NAME = "Hello World"
FEATURE_DESCRIPTION = (
    "Template feature demonstrating complete Ramses Extras architecture"
)

# Entity configurations
HELLO_WORLD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {
    "hello_world_switch": {
        "name_template": "Hello World Switch {device_id}",
        "entity_template": "hello_world_switch_{device_id}",
        "icon": "mdi:lightbulb",
        "device_types": ["HvacVentilator", "HgiController"],
        # "default_enabled": True,
    },
    "hello_world_optional_switch": {  # optional example
        "name_template": "Hello World Optional Switch {device_id}",
        "entity_template": "hello_world_optional_switch_{device_id}",
        "icon": "mdi:toggle-switch-variant",
        "device_types": ["HvacVentilator", "HgiController"],
        "optional": True,
    },
}

HELLO_WORLD_BINARY_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {
    "hello_world_status": {
        "name_template": "Hello World Status {device_id}",
        "entity_template": "hello_world_status_{device_id}",
        "device_class": "connectivity",
        "device_types": ["HvacVentilator", "HgiController"],
        # "default_enabled": True,
    }
}

HELLO_WORLD_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {
    # Placeholder for sensor platform
}

# Device entity mapping
HELLO_WORLD_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "switch": ["hello_world_switch"],
        "binary_sensor": ["hello_world_status"],
        "sensor": [],  # Placeholder
    },
    "HgiController": {
        "switch": ["hello_world_switch"],
        "binary_sensor": ["hello_world_status"],
        "sensor": [],
    },
}

# WebSocket commands
HELLO_WORLD_WEBSOCKET_COMMANDS = {
    "toggle_switch": "ramses_extras/hello_world/toggle_switch",
    "get_switch_state": "ramses_extras/hello_world/get_switch_state",
    # Note: get_entity_mappings is provided by the default feature for all features
}

# Default configuration
DEFAULT_CONFIG = {
    "enabled": True,
    "auto_discovery": True,
}

# Card configurations for feature-centric card management
# To add new cards, simply add another dictionary to this list
HELLO_WORLD_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "hello-world",
        "card_name": "Hello World Card",
        "description": "A simple demonstration card for "
        "Ramses Extras Hello World feature",
        "location": "hello_world",
        "preview": True,
        "documentation_url": "https://github.com/wimpie70/ramses_extras/wiki/Hello-World-Card",
        "supported_device_types": ["HvacVentilator"],
        "javascript_file": "hello-world.js",
    },
]

# Entity structure for SimpleEntityManager
FEATURE_DEFINITION = {
    "feature_id": FEATURE_ID,
    "sensor_configs": HELLO_WORLD_SENSOR_CONFIGS,
    "switch_configs": HELLO_WORLD_SWITCH_CONFIGS,
    "boolean_configs": HELLO_WORLD_BINARY_SENSOR_CONFIGS,
    "device_entity_mapping": HELLO_WORLD_DEVICE_ENTITY_MAPPING,
    "websocket_commands": HELLO_WORLD_WEBSOCKET_COMMANDS,
    "entity_mappings": {
        "switch_state": "switch.hello_world_switch_{device_id}",
        "sensor_state": "binary_sensor.hello_world_status_{device_id}",
    },
    # Cards that this feature manages
    "card_config": HELLO_WORLD_CARD_CONFIGS[0] if HELLO_WORLD_CARD_CONFIGS else {},
}


def load_feature() -> None:
    """Load hello world feature into the registry.

    This function registers all components of the Hello World feature with the
    Ramses Extras framework, including entity configurations, device mappings,
    WebSocket commands, and the feature itself.

    The registration process includes:
    - Switch entity configurations
    - Binary sensor entity configurations
    - Device to entity mappings
    - WebSocket command handlers
    - Feature registration with the global registry

    This function should be called during integration setup to make the feature
    available to the Ramses Extras framework.
    """
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_switch_configs(HELLO_WORLD_SWITCH_CONFIGS)
    extras_registry.register_boolean_configs(HELLO_WORLD_BINARY_SENSOR_CONFIGS)
    extras_registry.register_device_mappings(HELLO_WORLD_DEVICE_ENTITY_MAPPING)

    # Register WebSocket commands
    extras_registry.register_websocket_commands(
        "hello_world", HELLO_WORLD_WEBSOCKET_COMMANDS
    )

    # Card registration now handled by CardRegistry - no legacy configs needed

    extras_registry.register_feature("hello_world")


__all__ = [
    "DOMAIN",
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "FEATURE_NAME",
    "FEATURE_DESCRIPTION",
    "HELLO_WORLD_SWITCH_CONFIGS",
    "HELLO_WORLD_BINARY_SENSOR_CONFIGS",
    "HELLO_WORLD_SENSOR_CONFIGS",
    "HELLO_WORLD_DEVICE_ENTITY_MAPPING",
    "HELLO_WORLD_WEBSOCKET_COMMANDS",
    "DEFAULT_CONFIG",
    "load_feature",
]
