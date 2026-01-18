from typing import Any

DOMAIN = "ramses_debugger"

FEATURE_ID = "ramses_debugger"

RAMSES_DEBUGGER_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
RAMSES_DEBUGGER_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
RAMSES_DEBUGGER_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
RAMSES_DEBUGGER_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

RAMSES_DEBUGGER_WEBSOCKET_COMMANDS: dict[str, str] = {
    "traffic_get_stats": "ramses_extras/ramses_debugger/traffic/get_stats",
    "traffic_reset_stats": "ramses_extras/ramses_debugger/traffic/reset_stats",
    "traffic_subscribe_stats": "ramses_extras/ramses_debugger/traffic/subscribe_stats",
    "log_list_files": "ramses_extras/ramses_debugger/log/list_files",
    "log_get_tail": "ramses_extras/ramses_debugger/log/get_tail",
    "log_search": "ramses_extras/ramses_debugger/log/search",
}

RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {
    "HvacVentilator": {
        "sensor": [],
        "switch": [],
        "number": [],
        "binary_sensor": [],
    },
}

RAMSES_DEBUGGER_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "ramses-traffic-analyser",
        "card_name": "Ramses Traffic Analyser",
        "description": "Spreadsheet-like comms matrix for ramses_cc traffic",
        "location": "ramses_debugger",
        "preview": True,
        "documentation_url": "",
        "supported_device_types": ["HvacVentilator"],
        "javascript_file": "ramses-traffic-analyser.js",
    },
    {
        "card_id": "ramses-log-explorer",
        "card_name": "Ramses Log Explorer",
        "description": "Filter and extract context from the HA log file",
        "location": "ramses_debugger",
        "preview": True,
        "documentation_url": "",
        "supported_device_types": ["HvacVentilator"],
        "javascript_file": "ramses-log-explorer.js",
    },
]

FEATURE_DEFINITION = {
    "feature_id": FEATURE_ID,
    "sensor_configs": RAMSES_DEBUGGER_SENSOR_CONFIGS,
    "switch_configs": RAMSES_DEBUGGER_SWITCH_CONFIGS,
    "number_configs": RAMSES_DEBUGGER_NUMBER_CONFIGS,
    "boolean_configs": RAMSES_DEBUGGER_BOOLEAN_CONFIGS,
    "device_entity_mapping": RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING,
    "websocket_commands": RAMSES_DEBUGGER_WEBSOCKET_COMMANDS,
    "card_config": (
        RAMSES_DEBUGGER_CARD_CONFIGS[0] if RAMSES_DEBUGGER_CARD_CONFIGS else {}
    ),
    "required_entities": {},
}


def load_feature() -> None:
    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_device_mappings(RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING)
    extras_registry.register_websocket_commands(
        FEATURE_ID,
        RAMSES_DEBUGGER_WEBSOCKET_COMMANDS,
    )

    for card_config in RAMSES_DEBUGGER_CARD_CONFIGS:
        extras_registry.register_card_config(FEATURE_ID, card_config)

    extras_registry.register_feature(FEATURE_ID)


__all__ = [
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING",
    "RAMSES_DEBUGGER_WEBSOCKET_COMMANDS",
    "RAMSES_DEBUGGER_CARD_CONFIGS",
    "load_feature",
]
