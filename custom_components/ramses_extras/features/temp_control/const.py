"""Temperature control feature (bypass + optional speed request).

This feature manages FAN bypass mode to keep indoor temperature near the FAN's
comfort temperature, and may request ventilation speed increases during cooling
when humidity and CO2 conditions allow it.

`FEATURE_DEFINITION` is the canonical structure consumed by the framework.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import EntityCategory

FEATURE_ID = "temp_control"

TEMP_CONTROL_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {
    "temp_control": {
        "name_template": "Temp control {device_id}",
        "icon": "mdi:thermometer-auto",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "temp_control_{device_id}",
    },
}

TEMP_CONTROL_SELECT_CONFIGS: dict[str, dict[str, Any]] = {
    "temp_control_desired_speed": {
        "name_template": "Temp control desired speed {device_id}",
        "icon": "mdi:fan-chevron-up",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "temp_control_desired_speed_{device_id}",
        "options": ["low", "medium", "high"],
        "default_option": "high",
    },
}

TEMP_CONTROL_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {
    "temp_control_active": {
        "name_template": "Temp control active {device_id}",
        "icon": "mdi:valve",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "temp_control_active_{device_id}",
    },
}

TEMP_CONTROL_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {
    "temp_control_status": {
        "name_template": "Temp control status {device_id}",
        "icon": "mdi:thermostat",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "temp_control_status_{device_id}",
    },
}

TEMP_CONTROL_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {
    "HvacVentilator": {
        "switch": ["temp_control"],
        "select": ["temp_control_desired_speed"],
        "binary_sensor": ["temp_control_active"],
        "sensor": ["temp_control_status"],
    }
}

TEMP_CONTROL_WEBSOCKET_COMMANDS: dict[str, str] = {
    "get_device_config": "ramses_extras/temp_control/get_device_config",
    "set_device_config": "ramses_extras/temp_control/set_device_config",
}

TEMP_CONTROL_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "comfort_delta_activate": 1.0,
    "comfort_delta_deactivate": 0.5,
    "cooling_delta_activate": 1.0,
    "cooling_delta_deactivate": 0.5,
    "min_outdoor_temp": 10.0,
    "min_bypass_mode_interval_seconds": 180,
    "default_desired_speed": "high",
    "dewpoint_guard_enabled": False,
    "dewpoint_margin_c": 1.0,
    "supply_cooler_delta_activate": 1.0,
    "supply_cooler_delta_deactivate": 0.5,
    "min_supply_temp": 10.0,
    "reevaluation_interval_seconds": 300,
}

FEATURE_DEFINITION: dict[str, Any] = {
    "feature_id": FEATURE_ID,
    "sensor_configs": TEMP_CONTROL_SENSOR_CONFIGS,
    "switch_configs": TEMP_CONTROL_SWITCH_CONFIGS,
    "number_configs": {},
    "select_configs": TEMP_CONTROL_SELECT_CONFIGS,
    "boolean_configs": TEMP_CONTROL_BOOLEAN_CONFIGS,
    "device_entity_mapping": TEMP_CONTROL_DEVICE_ENTITY_MAPPING,
    "websocket_commands": TEMP_CONTROL_WEBSOCKET_COMMANDS,
    "required_entities": {
        "switch": ["temp_control"],
        "select": ["temp_control_desired_speed"],
        "binary_sensor": ["temp_control_active"],
        "sensor": ["temp_control_status"],
    },
    "entity_mappings": {
        # temp_control (self)
        "temp_control": "switch.temp_control_{device_id}",
        "desired_speed": "select.temp_control_desired_speed_{device_id}",
        "temp_control_active": "binary_sensor.temp_control_active_{device_id}",
        # Inputs (provided by ramses_cc / other features)
        "indoor_temp": "sensor.{device_id}_indoor_temp",
        "outdoor_temp": "sensor.{device_id}_outdoor_temp",
        "supply_temp": "sensor.{device_id}_supply_temp",
        "comfort_temp": "number.{device_id}_param_75",
        "indoor_rh": "sensor.{device_id}_indoor_humidity",
        "min_rh": "number.relative_humidity_minimum_{device_id}",
        "max_rh": "number.relative_humidity_maximum_{device_id}",
        "dehumidifying_active": "binary_sensor.dehumidifying_active_{device_id}",
        "co2_active": "binary_sensor.co2_active_{device_id}",
    },
}


def load_feature() -> None:
    """Load temp_control feature into the registry."""

    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_switch_configs(TEMP_CONTROL_SWITCH_CONFIGS)
    extras_registry.register_select_configs(TEMP_CONTROL_SELECT_CONFIGS)
    extras_registry.register_boolean_configs(TEMP_CONTROL_BOOLEAN_CONFIGS)
    extras_registry.register_sensor_configs(TEMP_CONTROL_SENSOR_CONFIGS)
    extras_registry.register_device_mappings(TEMP_CONTROL_DEVICE_ENTITY_MAPPING)

    extras_registry.register_websocket_commands(
        FEATURE_ID, TEMP_CONTROL_WEBSOCKET_COMMANDS
    )
    extras_registry.register_feature(FEATURE_ID)


__all__ = [
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "TEMP_CONTROL_SWITCH_CONFIGS",
    "TEMP_CONTROL_SELECT_CONFIGS",
    "TEMP_CONTROL_BOOLEAN_CONFIGS",
    "TEMP_CONTROL_SENSOR_CONFIGS",
    "TEMP_CONTROL_DEVICE_ENTITY_MAPPING",
    "TEMP_CONTROL_DEFAULTS",
    "load_feature",
]
