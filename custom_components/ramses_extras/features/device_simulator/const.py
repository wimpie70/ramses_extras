# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for the Device Simulator feature."""

from __future__ import annotations

import logging
from typing import Any

LOGGER: logging.Logger = logging.getLogger(__name__)

DOMAIN = "device_simulator"
FEATURE_ID = "device_simulator"

# Simulator HGI (gateway) ID - used for packet routing and identification
SIMULATOR_HGI_ID = "18:001234"

# Simulator topic namespace for MQTT isolation
SIMULATOR_TOPIC_NS = "RAMSES/GATEWAY_SIM"

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

# MQTT topic suffixes for simulator communication
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
SCENARIO_HVAC_DEVICE_LOSS = "hvac_device_loss"
SCENARIO_RUN_CONVERSATION = "run_conversation"
SCENARIO_MANUAL_DEVICE_INJECTION = "autonomous_emissions"
# Legacy alias
SCENARIO_AUTONOMOUS_EMISSIONS = (
    SCENARIO_MANUAL_DEVICE_INJECTION  # Start/stop autonomous I frames
)
SCENARIO_PROFILE_EMISSIONS = "profile_emissions"
SCENARIO_LOAD_PROFILE_YAML = "load_profile_yaml"
SCENARIO_AUTO_ANSWER = "auto_answer"  # Global RQ→RP response toggle

# Parameter schemas for scenario configuration UI
SCENARIO_PARAM_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    SCENARIO_MANUAL_DEVICE_INJECTION: [
        {
            "key": "device_id",
            "label": "Device ID",
            "type": "text",
            "default": "32:150000",
        },
        {
            "key": "device_type",
            "label": "Device slug",
            "type": "text",
            "default": "FAN",
        },
        {
            "key": "variant_id",
            "label": "Variant",
            "type": "text",
            "default": "default",
        },
        {
            "key": "excluded_codes",
            "label": "Excluded codes",
            "type": "csv",
            "default": "1FC9",
        },
    ],
    SCENARIO_DEVICE_PLAYBACK: [
        {
            "key": "conversation",
            "label": "Conversation",
            "type": "text",
            "required": True,
        },
        {
            "key": "scheme",
            "label": "Scheme",
            "type": "text",
        },
        {
            "key": "speed",
            "label": "Speed (×)",
            "type": "number",
            "default": 1.0,
            "step": 0.1,
            "min": 0.1,
        },
        {
            "key": "loops",
            "label": "Loops",
            "type": "number",
            "default": 1,
            "min": 1,
        },
    ],
    SCENARIO_DEVICE_SUITE: [
        {
            "key": "slugs",
            "label": "Device slugs",
            "type": "csv",
            "default": "FAN, CO2, REM",
        },
        {
            "key": "duration",
            "label": "Duration (s)",
            "type": "number",
            "default": 300,
            "min": 0,
        },
        {
            "key": "auto_stop",
            "label": "Auto stop",
            "type": "checkbox",
            "default": True,
        },
    ],
    SCENARIO_DEVICE_UNAVAILABILITY: [
        {
            "key": "device_id",
            "label": "Specific device ID",
            "type": "text",
        },
        {
            "key": "zone_id",
            "label": "Heat zone",
            "type": "select",
            "placeholder": "Select a zone or leave blank",
            "options_source": "zones",
        },
        {
            "key": "silence_after",
            "label": "Silence after (s)",
            "type": "number",
            "default": 30.0,
            "min": 0,
        },
        {
            "key": "resume_after",
            "label": "Resume after (s)",
            "type": "number",
            "default": 60.0,
            "min": 0,
        },
    ],
    SCENARIO_HVAC_DEVICE_LOSS: [
        {
            "key": "device_id",
            "label": "Device ID",
            "type": "text",
            "required": True,
        },
        {
            "key": "loss_after",
            "label": "Silence after (s)",
            "type": "number",
            "default": 30.0,
            "min": 0,
        },
        {
            "key": "restore_after",
            "label": "Restore after (s)",
            "type": "number",
            "min": 0,
        },
    ],
    SCENARIO_DISCOVERY_TEST: [
        {
            "key": "slug",
            "label": "Device slug",
            "type": "text",
            "default": "FAN",
        },
        {
            "key": "device_id",
            "label": "Device ID",
            "type": "text",
        },
        {
            "key": "fingerprint",
            "label": "Fingerprint",
            "type": "text",
        },
        {
            "key": "payload",
            "label": "Payload override",
            "type": "text",
        },
        {
            "key": "count",
            "label": "Frame count",
            "type": "number",
            "default": 3,
            "min": 1,
        },
        {
            "key": "interval",
            "label": "Interval (s)",
            "type": "number",
            "default": 1.0,
            "min": 0,
            "step": 0.1,
        },
        {
            "key": "include_startup_burst",
            "label": "Include startup burst",
            "type": "checkbox",
            "default": True,
        },
    ],
    SCENARIO_TIMEOUT_TEST: [
        {
            "key": "device_id",
            "label": "Device ID",
            "type": "text",
            "required": True,
        },
        {
            "key": "drop_codes",
            "label": "Drop codes",
            "type": "csv",
            "default": "31DA",
        },
        {
            "key": "delay",
            "label": "Delay before drop (s)",
            "type": "number",
            "default": 10.0,
            "min": 0,
        },
        {
            "key": "duration",
            "label": "Hold duration (s)",
            "type": "number",
            "default": 30.0,
            "min": 0,
        },
        {
            "key": "suppress_all_responses",
            "label": "Suppress all responses",
            "type": "checkbox",
            "default": False,
        },
    ],
    SCENARIO_FLOODING_TEST: [
        {
            "key": "slug",
            "label": "Device slug",
            "type": "text",
            "default": "FAN",
        },
        {
            "key": "device_id",
            "label": "Device ID",
            "type": "text",
        },
        {
            "key": "code",
            "label": "Code",
            "type": "text",
            "default": "22F7",
        },
        {
            "key": "count",
            "label": "Frame count",
            "type": "number",
            "default": 200,
            "min": 1,
        },
        {
            "key": "interval",
            "label": "Interval (s)",
            "type": "number",
            "default": 0.05,
            "min": 0,
            "step": 0.01,
        },
        {
            "key": "duration",
            "label": "Max duration (s)",
            "type": "number",
            "default": 0,
            "min": 0,
        },
    ],
    SCENARIO_PROFILE_EMISSIONS: [],
    SCENARIO_LOAD_PROFILE_YAML: [
        {
            "key": "profile_name",
            "label": "Profile name",
            "type": "text",
            "default": "imported_profile",
        },
        {
            "key": "profile_yaml",
            "label": "Profile YAML",
            "type": "textarea",
            "required": True,
            "placeholder": "known_list:\n  32:150000:\n    class: FAN",
        },
        {
            "key": "speed",
            "label": "Profile speed",
            "type": "number",
            "default": 1.0,
            "options": [
                {"label": "1× (normal)", "value": 1.0},
                {"label": "10× faster", "value": 0.1},
                {"label": "100× faster", "value": 0.01},
            ],
        },
        {
            "key": "reload_ramses",
            "label": "Reload RF",
            "type": "checkbox",
            "default": True,
        },
        {
            "key": "preload_schema",
            "label": "Preload schema into RF",
            "type": "checkbox",
            "default": True,
        },
        {
            "key": "reset_rf_cache",
            "label": "Reset RF cache (packets + ramses.db)",
            "type": "checkbox",
            "default": False,
        },
        {
            "key": "remove_database",
            "label": "Remove database file",
            "type": "checkbox",
            "default": False,
            "helper": "Removes the ramses database file for a clean start.",
        },
    ],
}

# Scenario registry: metadata for each scenario type.
# toggleable: True if the scenario can be independently toggled on/off.
# can_run_with: list of scenario IDs that may run concurrently.
#   Use "*" to mean "any".
SCENARIO_REGISTRY: dict[str, dict[str, Any]] = {
    SCENARIO_MANUAL_DEVICE_INJECTION: {
        "label": "Manual Device Injection",
        "description": "Add an ad-hoc simulated device that emits its periodic frames",
        "toggleable": True,
        "can_run_with": [
            SCENARIO_AUTO_ANSWER,
            SCENARIO_DEVICE_UNAVAILABILITY,
            SCENARIO_HVAC_DEVICE_LOSS,
            SCENARIO_RUN_CONVERSATION,
            SCENARIO_PROFILE_EMISSIONS,
        ],
    },
    SCENARIO_AUTO_ANSWER: {
        "label": "Auto Answer (RQ→RP)",
        "description": "Automatically reply to RQ frames with database responses",
        "toggleable": True,
        "can_run_with": ["*"],  # compatible with everything
    },
    SCENARIO_DEVICE_UNAVAILABILITY: {
        "label": "Device Unavailability",
        "description": "Silence all or selected devices after a delay, then resume",
        "toggleable": True,
        "can_run_with": [
            SCENARIO_MANUAL_DEVICE_INJECTION,
            SCENARIO_PROFILE_EMISSIONS,
            SCENARIO_AUTO_ANSWER,
        ],
    },
    SCENARIO_HVAC_DEVICE_LOSS: {
        "label": "HVAC Device Loss",
        "description": "Drop one HVAC device mid-run and optionally restore it",
        "toggleable": True,
        "can_run_with": [
            SCENARIO_MANUAL_DEVICE_INJECTION,
            SCENARIO_PROFILE_EMISSIONS,
            SCENARIO_AUTO_ANSWER,
        ],
    },
    SCENARIO_RUN_CONVERSATION: {
        "label": "Conversation Playback",
        "description": "Replay a captured conversation block end-to-end",
        "toggleable": False,
        "can_run_with": [
            SCENARIO_MANUAL_DEVICE_INJECTION,
            SCENARIO_PROFILE_EMISSIONS,
            SCENARIO_AUTO_ANSWER,
        ],
    },
    SCENARIO_DISCOVERY_TEST: {
        "label": "Discovery Test",
        "description": "Emit 10E0 announcements to validate device discovery",
        "toggleable": False,
        "can_run_with": [SCENARIO_AUTO_ANSWER],
    },
    SCENARIO_TIMEOUT_TEST: {
        "label": "Timeout Test",
        "description": "Delay or drop responses to reproduce timeout handling",
        "toggleable": False,
        "can_run_with": [],  # exclusive
    },
    SCENARIO_FLOODING_TEST: {
        "label": "Flooding Test",
        "description": "Burst-send I frames at a configurable rate",
        "toggleable": False,
        "can_run_with": [],  # exclusive
    },
    SCENARIO_DEVICE_PLAYBACK: {
        "label": "Device Playback",
        "description": "Replay captured device traffic with inferred mapping",
        "toggleable": False,
        "can_run_with": [SCENARIO_AUTO_ANSWER],
    },
    SCENARIO_DEVICE_SUITE: {
        "label": "Device Suite",
        "description": "Activate a curated set of devices for mixed testing",
        "toggleable": False,
        "can_run_with": [SCENARIO_AUTO_ANSWER],
    },
    SCENARIO_PROFILE_EMISSIONS: {
        "label": "Start all profile devices",
        "description": (
            "Manually start or stop autonomous emitters for every "
            "device in the active profile"
        ),
        "toggleable": True,
        "can_run_with": [SCENARIO_AUTO_ANSWER, SCENARIO_MANUAL_DEVICE_INJECTION],
    },
    SCENARIO_LOAD_PROFILE_YAML: {
        "label": "Load Ramses RF profile",
        "description": (
            "Paste a known_list YAML snippet to import and activate a profile"
        ),
        "toggleable": False,
        "can_run_with": [
            SCENARIO_AUTO_ANSWER,
            SCENARIO_MANUAL_DEVICE_INJECTION,
            SCENARIO_PROFILE_EMISSIONS,
        ],
    },
}

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

# Card configurations for feature-centric card management
DEVICE_SIMULATOR_CARD_CONFIGS: list[dict[str, Any]] = [
    {
        "card_id": "device-simulator-card",
        "card_name": "Device Simulator",
        "description": "Control and monitor the RAMSES device simulator",
        "location": "device_simulator",
        "preview": False,
        "documentation_url": "https://github.com/wimpie70/ramses_extras/wiki/Device-Simulator",
        "supported_device_types": [],
        "javascript_file": "device-simulator-card.js",
    },
]

# Feature definition for framework integration
FEATURE_DEFINITION: dict[str, Any] = {
    "feature_id": FEATURE_ID,
    "name": "Device Simulator",
    "description": "Simulates RAMSES RF devices for testing and development",
    "version": "0.1.0",
    "domain": DOMAIN,
    "dependencies": [],
    "has_device_config": True,
    "has_sensors": True,
    "has_binary_sensors": False,
    "has_switches": False,
    "services_module": "services",
    "websocket_commands_module": "websocket",
    # Support both single card_config (backward compat)
    # and card_configs list (multi-card)
    "card_config": DEVICE_SIMULATOR_CARD_CONFIGS[0]
    if DEVICE_SIMULATOR_CARD_CONFIGS
    else {},
    "card_configs": DEVICE_SIMULATOR_CARD_CONFIGS,
}

__all__ = [
    "DOMAIN",
    "FEATURE_ID",
    "FEATURE_DEFINITION",
    "SIMULATOR_HGI_ID",
    "SIMULATOR_TOPIC_NS",
    "DEVICE_SIMULATOR_SENSOR_CONFIGS",
    "DEVICE_SIMULATOR_WEBSOCKET_COMMANDS",
    "DEVICE_SIMULATOR_CARD_CONFIGS",
    "DEFAULT_GATEWAY_ID",
    "LOGGER",
    "SCENARIO_AUTO_ANSWER",
    "SCENARIO_MANUAL_DEVICE_INJECTION",
    "SCENARIO_PROFILE_EMISSIONS",
    "SCENARIO_LOAD_PROFILE_YAML",
    "SCENARIO_PARAM_SCHEMAS",
    "SCENARIO_REGISTRY",
]
