"""HVAC Fan Card feature - Advanced control card for Orcon ventilation systems."""

from typing import Any

# HVAC Fan Card inherits shared sensor from default feature
# No additional entity configurations needed - uses shared sensor
HVAC_FAN_CARD_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
HVAC_FAN_CARD_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

# HVAC Fan Card is a dashboard card feature
# The device mapping indicates which device types the card supports,
# but the card doesn't create any entities - it uses existing ones from default feature
# The empty lists indicate no entities are created by this feature
HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {
    "HvacVentilator": {
        "sensor": [],  # Uses sensors from default feature
        "switch": [],
        "number": [],
        "binary_sensor": [],
    },
}


def load_feature() -> None:
    """Load hvac_fan_card feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register device mappings (indicates card is available for HvacVentilator devices)
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
