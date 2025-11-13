"""Default feature - shared entity definitions that all features can inherit from."""

from typing import Any

from homeassistant.helpers.entity import EntityCategory

# Base entity definitions (shared across features)
DEFAULT_SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
    },
}

# Empty base configs - features will define their own
DEFAULT_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
DEFAULT_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
DEFAULT_BOOLEAN_CONFIGS: dict[str, dict[str, Any]] = {}

# Base device type to entity mapping (only shared sensors)
DEFAULT_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Other entity types will be added by individual features
    },
}


def load_feature() -> None:
    """Load default feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    # Register entity configurations
    extras_registry.register_sensor_configs(DEFAULT_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(DEFAULT_SWITCH_CONFIGS)
    extras_registry.register_number_configs(DEFAULT_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(DEFAULT_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(DEFAULT_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("default")
