"""HVAC Fan Card feature - Advanced control card for Orcon ventilation systems."""

from typing import Any

# HVAC Fan Card inherits shared sensor from default feature
# No additional entity configurations needed - uses shared sensor
HVAC_FAN_CARD_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

# Device mapping (inherits shared sensor from default)
HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensor": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switch": [],
        "number": [],
        "binary_sensor": [],
    },
}


def load_feature() -> None:
    """Load hvac_fan_card feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations (mostly inherits from default)
    extras_registry.register_device_mappings(HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("hvac_fan_card")


__all__ = [
    "HVAC_FAN_CARD_SENSOR_CONFIGS",
    "HVAC_FAN_CARD_SWITCH_CONFIGS",
    "HVAC_FAN_CARD_NUMBER_CONFIGS",
    "HVAC_FAN_CARD_BOOLEAN_CONFIGS",
    "HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING",
    "load_feature",
]
