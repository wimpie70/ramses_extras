"""Humidity Sensors feature - Calculates absolute humidity from
relative indoor & outdoor sensor entities."""

from typing import Any

# Feature identification
FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"

# Humidity Sensors inherits shared sensors from default feature
# No additional entity configurations needed - uses shared sensors
HUMIDITY_SENSORS_SENSOR_CONFIGS: dict[
    str, dict[str, Any]
] = {}  # Inherits from default feature
HUMIDITY_SENSORS_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific switches
HUMIDITY_SENSORS_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific numbers
HUMIDITY_SENSORS_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}  # No specific booleans

# Device mapping (inherits shared sensors from default)
HUMIDITY_SENSORS_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Inherited from default feature
        "switches": [],
        "numbers": [],
        "binary_sensors": [],
    },
}

# Sensor-specific configuration constants
HUMIDITY_SENSORS_CONFIG = {
    "feature_id": FEATURE_ID_HUMIDITY_SENSORS,
    "name": "Absolute Humidity Sensors",
    "description": "Calculates absolute humidity from relative "
    "indoor&outdoor sensor entities.",
    "category": "sensors",
    "default_enabled": False,
    "supported_device_types": ["HvacVentilator"],
    "required_entities": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": [],
        "binary_sensors": [],
    },
    "optional_entities": {
        "sensors": [],
        "switches": [],
    },
}

__all__ = [
    "FEATURE_ID_HUMIDITY_SENSORS",
    "HUMIDITY_SENSORS_CONFIG",
    "HUMIDITY_SENSORS_DEVICE_ENTITY_MAPPING",
]
