# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for the Device Simulator feature."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

DOMAIN = "device_simulator"
FEATURE_ID = "device_simulator"

# Sensor configs for simulator status sensors
DEVICE_SIMULATOR_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {
    "simulator_status": {
        "name_template": "Simulator Status",
        "entity_template": "simulator_status",
        "icon": "mdi:play-circle",
    },
    "simulator_messages": {
        "name_template": "Simulator Messages",
        "entity_template": "simulator_messages",
        "icon": "mdi:message-text",
    },
    "simulator_devices": {
        "name_template": "Simulator Active Devices",
        "entity_template": "simulator_active_devices",
        "icon": "mdi:devices",
    },
}

# WebSocket commands for device simulator
DEVICE_SIMULATOR_WEBSOCKET_COMMANDS = {
    "get_simulator_status": "ramses_extras/device_simulator/get_status",
    "list_simulator_devices": "ramses_extras/device_simulator/list_devices",
    "activate_simulator_device": "ramses_extras/device_simulator/activate_device",
    "silence_simulator_device": "ramses_extras/device_simulator/silence_device",
    "run_conversation": "ramses_extras/device_simulator/run_conversation",
    "get_messages": "ramses_extras/device_simulator/get_messages",
}

# MQTT topic base used by ramses_rf MqttTransport
MQTT_TOPIC_BASE = "ramses_gateway"

# Simulator subscribes to /tx (outbound from ramses_rf = inbound to simulator)
# Simulator publishes to /rx  (inbound to ramses_rf = outbound from simulator)
MQTT_TOPIC_SUFFIX_TX = "tx"
MQTT_TOPIC_SUFFIX_RX = "rx"

# Default gateway ID used in the standalone container
# Never collides with real hardware
DEFAULT_GATEWAY_ID = "18:001234"

# Scenario states
SCENARIO_STATE_IDLE = "idle"
SCENARIO_STATE_RUNNING = "running"
SCENARIO_STATE_PAUSED = "paused"
SCENARIO_STATE_COMPLETED = "completed"
SCENARIO_STATE_ERROR = "error"

# Scenario types
SCENARIO_DEVICE_PLAYBACK = "device_playback"
SCENARIO_DEVICE_SUITE = "device_suite"
SCENARIO_DISCOVERY_TEST = "discovery_test"
SCENARIO_TIMEOUT_TEST = "timeout_test"
SCENARIO_FLOODING_TEST = "flooding_test"
SCENARIO_DEVICE_UNAVAILABILITY = "device_unavailability"
SCENARIO_RUN_CONVERSATION = "run_conversation"

# Device DB subfolder names
DB_SUBDIR_HEAT = "heat"
DB_SUBDIR_HVAC = "hvac"
DB_SUBDIR_CONVERSATIONS = "conversations"

# Device behaviour trigger types
TRIGGER_PERIODIC = "periodic"
TRIGGER_STATE_CHANGE = "state_change"

# Verb constants (mirror ramses_rf)
VERB_I = "I"
VERB_RQ = "RQ"
VERB_RP = "RP"
VERB_W = "W"

# Feature definition for framework integration
FEATURE_DEFINITION: dict[str, Any] = {
    "name": "Device Simulator",
    "id": "device_simulator",
    "domain": "ramses_extras",
    "has_sensors": True,
    "has_binary_sensors": False,
    "has_switches": False,
    "services_module": "services",
    "websocket_commands_module": "websocket",
}

__all__ = [
    "DOMAIN",
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "DEVICE_SIMULATOR_SENSOR_CONFIGS",
    "DEVICE_SIMULATOR_WEBSOCKET_COMMANDS",
    "DEFAULT_GATEWAY_ID",
    "LOGGER",
]
