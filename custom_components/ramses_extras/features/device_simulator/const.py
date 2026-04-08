# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for the Device Simulator feature."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)

DOMAIN = "device_simulator"

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
