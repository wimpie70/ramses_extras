from __future__ import annotations

from typing import Any

DOMAIN = "sensor_control"

SENSOR_CONTROL_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
SENSOR_CONTROL_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

SENSOR_CONTROL_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {}

SENSOR_CONTROL_WEBSOCKET_COMMANDS: dict[str, str] = {}

SENSOR_CONTROL_CONST: dict[str, Any] = {
    "feature_id": DOMAIN,
    "required_entities": {},
}


def load_feature() -> None:
    from custom_components.ramses_extras.const import register_ws_commands
    from custom_components.ramses_extras.extras_registry import extras_registry

    register_ws_commands(DOMAIN, SENSOR_CONTROL_WEBSOCKET_COMMANDS)
    extras_registry.register_feature(DOMAIN)


__all__ = [
    "DOMAIN",
    "SENSOR_CONTROL_SENSOR_CONFIGS",
    "SENSOR_CONTROL_SWITCH_CONFIGS",
    "SENSOR_CONTROL_NUMBER_CONFIGS",
    "SENSOR_CONTROL_BOOLEAN_CONFIGS",
    "SENSOR_CONTROL_DEVICE_ENTITY_MAPPING",
    "SENSOR_CONTROL_WEBSOCKET_COMMANDS",
    "SENSOR_CONTROL_CONST",
    "load_feature",
]
