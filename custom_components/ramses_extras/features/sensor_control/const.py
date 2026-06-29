"""Constants for the sensor_control feature.

This module contains all constants and schemas for the sensor_control feature.
Feature-specific validation logic is in sensor_control_yaml.py.
"""

from __future__ import annotations

from typing import Any

DOMAIN = "sensor_control"

# Feature identification
FEATURE_ID = "sensor_control"

# Supported metrics for sensor control
SUPPORTED_METRICS = [
    "indoor_temperature",
    "indoor_humidity",
    "co2",
    "co2_zone_1",
    "co2_zone_2",
    "co2_zone_3",
    "outdoor_temperature",
    "outdoor_humidity",
    "indoor_abs_humidity",
    "outdoor_abs_humidity",
]

# Internal sensor mappings for supported device types
INTERNAL_SENSOR_MAPPINGS = {
    "FAN": {
        "indoor_temperature": "sensor.{device_id}_temperature",
        "indoor_humidity": "sensor.{device_id}_humidity",
        "co2": "sensor.{device_id}_co2",
        "co2_zone_1": "sensor.co2_zone_1_{device_id}",
        "co2_zone_2": "sensor.co2_zone_2_{device_id}",
        "co2_zone_3": "sensor.co2_zone_3_{device_id}",
        "outdoor_temperature": "sensor.{device_id}_outdoor_temperature",
        "outdoor_humidity": "sensor.{device_id}_outdoor_humidity",
    },
}

# Configuration keys used in YAML and internal config
SENSOR_CONTROL_SOURCES_KEY = "sources"
SENSOR_CONTROL_AREA_SENSORS_KEY = "area_sensors"
SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY = "abs_humidity_inputs"

SENSOR_CONTROL_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

SENSOR_CONTROL_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {}

SENSOR_CONTROL_WEBSOCKET_COMMANDS: dict[str, str] = {
    "get_device_config": "ramses_extras/sensor_control/get_device_config",
    "set_comfort_temp_entity": ("ramses_extras/sensor_control/set_comfort_temp_entity"),
}

SENSOR_CONTROL_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "ramses-fan-map",
        "card_name": "FAN Map",
        "description": "Observability and test bench for FAN configuration",
        "location": "sensor_control",
        "preview": True,
        "documentation_url": "",
        "supported_device_types": ["HvacVentilator"],
        "javascript_file": "ramses-fan-map.js",
    },
]

FEATURE_DEFINITION: dict[str, Any] = {
    "feature_id": FEATURE_ID,
    "sensor_configs": SENSOR_CONTROL_SENSOR_CONFIGS,
    "switch_configs": SENSOR_CONTROL_SWITCH_CONFIGS,
    "number_configs": SENSOR_CONTROL_NUMBER_CONFIGS,
    "boolean_configs": SENSOR_CONTROL_BOOLEAN_CONFIGS,
    "device_entity_mapping": SENSOR_CONTROL_DEVICE_ENTITY_MAPPING,
    "websocket_commands": SENSOR_CONTROL_WEBSOCKET_COMMANDS,
    "card_config": (
        SENSOR_CONTROL_CARD_CONFIGS[0] if SENSOR_CONTROL_CARD_CONFIGS else {}
    ),
    "card_configs": SENSOR_CONTROL_CARD_CONFIGS,
}


def load_feature() -> None:
    """Load the sensor_control feature and register its components."""
    # Import here to avoid circular imports
    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_websocket_commands(
        DOMAIN, SENSOR_CONTROL_WEBSOCKET_COMMANDS
    )

    for card_config in SENSOR_CONTROL_CARD_CONFIGS:
        extras_registry.register_card_config(DOMAIN, card_config)

    extras_registry.register_feature(DOMAIN)

    # Load YAML validator and import/export functions
    from .sensor_control_yaml import load_validator as load_sensor_validator
    from .zones_yaml import load_validator as load_zones_validator

    load_sensor_validator()
    load_zones_validator()


__all__ = [
    "DOMAIN",
    "FEATURE_DEFINITION",
    "SUPPORTED_METRICS",
    "INTERNAL_SENSOR_MAPPINGS",
    "SENSOR_CONTROL_SOURCES_KEY",
    "SENSOR_CONTROL_AREA_SENSORS_KEY",
    "SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY",
    "SENSOR_CONTROL_SENSOR_CONFIGS",
    "SENSOR_CONTROL_SWITCH_CONFIGS",
    "SENSOR_CONTROL_NUMBER_CONFIGS",
    "SENSOR_CONTROL_BOOLEAN_CONFIGS",
    "SENSOR_CONTROL_DEVICE_ENTITY_MAPPING",
    "SENSOR_CONTROL_WEBSOCKET_COMMANDS",
    "SENSOR_CONTROL_CARD_CONFIGS",
    "load_feature",
]
