# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for Hello World  feature.

This module defines all constants, configurations, and entity mappings for the
Hello World feature, including entity configurations, device mappings,
and WebSocket command definitions.

:platform: Home Assistant
:feature: Hello World Constants
:components: Entity Configurations, Device Mappings, WebSocket Commands
:data_types: Dictionaries, Lists, Strings
"""

from typing import Any

DOMAIN = "hello_world"

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
    }
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

HELLO_WORLD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {
    # Placeholder for number platform
}

# Device entity mapping
HELLO_WORLD_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "switch": ["hello_world_switch"],
        "binary_sensor": ["hello_world_status"],
        "sensor": [],  # Placeholder
        "number": [],  # Placeholder
    },
    "HgiController": {
        "switch": ["hello_world_switch"],
        "binary_sensor": ["hello_world_status"],
        "sensor": [],
        "number": [],
    },
}

# WebSocket commands
HELLO_WORLD_WEBSOCKET_COMMANDS = {
    "toggle_switch": "ramses_extras/hello_world/toggle_switch",
    "get_switch_state": "ramses_extras/hello_world/get_switch_state",
    # Note: get_entity_mappings is provided by the default feature for all features
}

# Feature web assets configuration for this feature
FEATURE_WEB_CONFIGS = {
    "hello_world": {
        "web_folder": "hello_world",
        "main_card": "hello-world.js",
        "editor_card": "hello-world-editor.js",
        "has_templates": True,
        "has_translations": True,
    },
}

# Feature deployment configuration
HELLO_WORLD_CONFIG = {
    "hello_world": {
        "card_path": "features/hello_world",
        "main_js": "hello-world.js",
        "editor_js": "hello-world-editor.js",
        "templates_path": "templates/",
        "translations_path": "translations/",
    }
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
HELLO_WORLD_CONST = {
    "required_entities": {
        "switch": ["hello_world_switch"],
        "binary_sensor": ["hello_world_status"],
    },
    # Cards that this feature manages
    "cards": HELLO_WORLD_CARD_CONFIGS,
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
    "FEATURE_NAME",
    "FEATURE_DESCRIPTION",
    "HELLO_WORLD_SWITCH_CONFIGS",
    "HELLO_WORLD_BINARY_SENSOR_CONFIGS",
    "HELLO_WORLD_SENSOR_CONFIGS",
    "HELLO_WORLD_NUMBER_CONFIGS",
    "HELLO_WORLD_DEVICE_ENTITY_MAPPING",
    "HELLO_WORLD_WEBSOCKET_COMMANDS",
    "DEFAULT_CONFIG",
    "FEATURE_WEB_CONFIGS",
    "HELLO_WORLD_CONFIG",
    "load_feature",
]
