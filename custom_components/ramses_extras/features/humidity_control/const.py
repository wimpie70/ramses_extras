"""Humidity control feature - feature-specific entity definitions."""

from homeassistant.helpers.entity import EntityCategory

# Feature-specific entities (prefixed with feature name)
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
    },
}

HUMIDITY_NUMBER_CONFIGS = {
    "relative_humidity_minimum": {
        "name_template": "Min Humidity {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-minus",
        "device_class": None,
        "min_value": 30,
        "max_value": 80,
        "step": 1,
        "default_value": 40,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_minimum_{device_id}",
    },
    "relative_humidity_maximum": {
        "name_template": "Max Humidity {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-plus",
        "device_class": None,
        "min_value": 50,
        "max_value": 90,
        "step": 1,
        "default_value": 60,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_maximum_{device_id}",
    },
    "absolute_humidity_offset": {
        "name_template": "Humidity Offset {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "g/m³",
        "icon": "mdi:swap-horizontal",
        "device_class": None,
        "min_value": -3.0,
        "max_value": 3.0,
        "step": 0.1,
        "default_value": 0.4,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "absolute_humidity_offset_{device_id}",
    },
}

HUMIDITY_BOOLEAN_CONFIGS = {
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
    },
}

# Feature-specific device mapping (inherits base sensors, adds feature-specific)
HUMIDITY_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Inherited from default
        "switches": ["dehumidify"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "binary_sensors": ["dehumidifying_active"],
    },
}

# Feature-specific logic constants
HUMIDITY_DECISION_THRESHOLDS = {
    "activation": 1.0,  # g/m³
    "deactivation": -1.0,  # g/m³
    "high_confidence": 2.0,  # g/m³
}

HUMIDITY_DECISION_ACTIONS = {
    "ACTIVATE": "dehumidify",
    "DEACTIVATE": "stop",
    "MAINTAIN": "maintain",
}

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

__all__ = [
    "FEATURE_ID_HUMIDITY_CONTROL",
    "HUMIDITY_CONTROL_CONST",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
    "HUMIDITY_DECISION_THRESHOLDS",
    "HUMIDITY_DECISION_ACTIONS",
]
