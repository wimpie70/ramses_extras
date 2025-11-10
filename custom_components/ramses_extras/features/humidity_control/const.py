"""Humidity Control Constants.

This module defines constants and configuration for the humidity control feature.
"""

# Feature identification
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"

# Configuration constants
HUMIDITY_CONTROL_CONST = {
    "feature_id": FEATURE_ID_HUMIDITY_CONTROL,
    "name": "Humidity Control",
    "description": "Automatic humidity control and dehumidification management",
    "version": "1.0.0",
    # Entity configurations
    "entity_mappings": {
        "indoor_rh": "sensor.{device_id}_indoor_humidity",
        "indoor_abs": "sensor.indoor_absolute_humidity_{device_id}",
        "outdoor_abs": "sensor.outdoor_absolute_humidity_{device_id}",
        "max_humidity": "number.relative_humidity_maximum_{device_id}",
        "min_humidity": "number.relative_humidity_minimum_{device_id}",
        "offset": "number.absolute_humidity_offset_{device_id}",
        "dehumidify": "switch.dehumidify_{device_id}",
        "dehumidifying_active": "binary_sensor.dehumidifying_active_{device_id}",
    },
    # Required entities
    "required_entities": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": ["dehumidify"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "binary_sensors": ["dehumidifying_active"],
    },
    # Decision thresholds
    "decision_thresholds": {
        "activation": 1.0,  # g/m³ - moderate activation
        "deactivation": -1.0,  # g/m³ - stop when humidity differential is too low
        "high_confidence": 2.0,  # g/m³ - high confidence activation
    },
    # Performance limits
    "limits": {
        "max_runtime_minutes": 120,
        "cooldown_period_minutes": 15,
        "max_decision_history": 100,
    },
    # Default values
    "defaults": {
        "min_humidity": 40.0,  # %
        "max_humidity": 60.0,  # %
        "offset": 0.4,  # g/m³
        "debounce_seconds": 30,
        "decision_interval": 60,  # seconds
    },
    # WebSocket message types (if applicable)
    "websocket_messages": {
        "HUMIDITY_STATUS": "humidity_control.status",
        "HUMIDITY_DECISION": "humidity_control.decision",
        "HUMIDITY_THRESHOLD_UPDATE": "humidity_control.threshold_update",
    },
    # Logging categories
    "logging_categories": {
        "automation": "ramses_extras.humidity_control.automation",
        "services": "ramses_extras.humidity_control.services",
        "entities": "ramses_extras.humidity_control.entities",
        "config": "ramses_extras.humidity_control.config",
    },
}

# Entity type constants
ENTITY_TYPES = {
    "SENSORS": "sensors",
    "SWITCHES": "switches",
    "NUMBERS": "numbers",
    "BINARY_SENSORS": "binary_sensors",
}

# Sensor type constants
SENSOR_TYPES = {
    "INDOOR_ABSOLUTE_HUMIDITY": "indoor_absolute_humidity",
    "OUTDOOR_ABSOLUTE_HUMIDITY": "outdoor_absolute_humidity",
}

# Switch type constants
SWITCH_TYPES = {
    "DEHUMIDIFY": "dehumidify",
}

# Number type constants
NUMBER_TYPES = {
    "RELATIVE_HUMIDITY_MINIMUM": "relative_humidity_minimum",
    "RELATIVE_HUMIDITY_MAXIMUM": "relative_humidity_maximum",
    "ABSOLUTE_HUMIDITY_OFFSET": "absolute_humidity_offset",
}

# Binary sensor type constants
BINARY_SENSOR_TYPES = {
    "DEHUMIDIFYING_ACTIVE": "dehumidifying_active",
}

# Decision constants
DECISION_ACTIONS = {
    "ACTIVATE": "dehumidify",
    "DEACTIVATE": "stop",
    "MAINTAIN": "maintain",
}

# Service names
SERVICE_NAMES = {
    "ACTIVATE_DEHUMIDIFICATION": "async_activate_dehumidification",
    "DEACTIVATE_DEHUMIDIFICATION": "async_deactivate_dehumidification",
    "SET_MIN_HUMIDITY": "async_set_min_humidity",
    "SET_MAX_HUMIDITY": "async_set_max_humidity",
    "SET_OFFSET": "async_set_offset",
    "GET_STATUS": "async_get_status",
}

# Configuration keys
CONFIG_KEYS = {
    "ENABLED": "enabled",
    "AUTO_START": "auto_start",
    "AUTOMATION_ENABLED": "automation_enabled",
    "DEBOUNCE_SECONDS": "automation_debounce_seconds",
    "DECISION_INTERVAL": "decision_interval_seconds",
    "MIN_HUMIDITY": "default_min_humidity",
    "MAX_HUMIDITY": "default_max_humidity",
    "OFFSET": "default_offset",
}

# Error codes
ERROR_CODES = {
    "ENTITY_NOT_FOUND": "entity_not_found",
    "INVALID_THRESHOLD": "invalid_threshold",
    "AUTOMATION_DISABLED": "automation_disabled",
    "DEVICE_OFFLINE": "device_offline",
    "SERVICE_FAILED": "service_failed",
}

# State values
STATE_VALUES = {
    "DEHUMIDIFYING": "dehumidifying",
    "IDLE": "idle",
    "ERROR": "error",
    "MANUAL": "manual",
}

__all__ = [
    "FEATURE_ID_HUMIDITY_CONTROL",
    "HUMIDITY_CONTROL_CONST",
    "ENTITY_TYPES",
    "SENSOR_TYPES",
    "SWITCH_TYPES",
    "NUMBER_TYPES",
    "BINARY_SENSOR_TYPES",
    "DECISION_ACTIONS",
    "SERVICE_NAMES",
    "CONFIG_KEYS",
    "ERROR_CODES",
    "STATE_VALUES",
]
