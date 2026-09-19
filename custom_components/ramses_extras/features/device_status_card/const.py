# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for the Device Status Card feature.

This feature provides a fleet overview card listing all RAMSES devices
with their communication status (online/offline) and signal quality
(RSSI, per-HGI breakdown for pooled gateways).

The feature is global — it lists all known devices, so it creates no
per-device entities and requires no device-scoped configuration.

:platform: Home Assistant
:feature: Device Status Card
:components: Card Configuration, WebSocket Commands
"""

from typing import Any

DOMAIN = "device_status_card"

# Feature identification
FEATURE_ID = "device_status_card"

FEATURE_NAME = "Device Status Card"
FEATURE_DESCRIPTION = (
    "Fleet overview: all RAMSES devices with status and communication quality"
)

# The feature creates no entities — it reads ramses_cc per-device
# status entities (binary_sensor.<device>_status, ramses_cc issue 1210)
# and falls back to the ramses_rf device's own signals.
DEVICE_STATUS_CARD_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
DEVICE_STATUS_CARD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
DEVICE_STATUS_CARD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
DEVICE_STATUS_CARD_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}
DEVICE_STATUS_CARD_BINARY_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}

# WebSocket commands
DEVICE_STATUS_CARD_WEBSOCKET_COMMANDS: dict[str, str] = {
    "get_device_status": "ramses_extras/device_status_card/get_device_status",
}

# Global card — no per-device entity mapping.
DEVICE_STATUS_CARD_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {}

# Card configurations for feature-centric card management
DEVICE_STATUS_CARD_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "device-status-card",
        "card_name": "Device Status Card",
        "description": (
            "All RAMSES devices with online status and communication quality"
        ),
        "location": "device_status_card",
        "preview": True,
        "documentation_url": ("https://github.com/wimpie70/ramses_extras/issues/227"),
        "supported_device_types": ["*"],
        "javascript_file": "device-status-card.js",
    },
]

# Entity structure for SimpleEntityManager
FEATURE_DEFINITION = {
    "feature_id": FEATURE_ID,
    "sensor_configs": DEVICE_STATUS_CARD_SENSOR_CONFIGS,
    "switch_configs": DEVICE_STATUS_CARD_SWITCH_CONFIGS,
    "number_configs": DEVICE_STATUS_CARD_NUMBER_CONFIGS,
    "boolean_configs": DEVICE_STATUS_CARD_BOOLEAN_CONFIGS,
    "binary_sensor_configs": DEVICE_STATUS_CARD_BINARY_SENSOR_CONFIGS,
    "device_entity_mapping": DEVICE_STATUS_CARD_DEVICE_ENTITY_MAPPING,
    "websocket_commands": DEVICE_STATUS_CARD_WEBSOCKET_COMMANDS,
    "card_config": (
        DEVICE_STATUS_CARD_CARD_CONFIGS[0] if DEVICE_STATUS_CARD_CARD_CONFIGS else {}
    ),
    "card_configs": DEVICE_STATUS_CARD_CARD_CONFIGS,
    "required_entities": {},
    "entity_mappings": {},
}
