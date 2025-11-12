"""Default feature - shared entity definitions that all features can inherit from."""

from .const import (
    DEFAULT_BOOLEAN_CONFIGS,
    DEFAULT_DEVICE_ENTITY_MAPPING,
    DEFAULT_NUMBER_CONFIGS,
    DEFAULT_SENSOR_CONFIGS,
    DEFAULT_SWITCH_CONFIGS,
)

# Export all definitions for EntityRegistry aggregation
__all__ = [
    "DEFAULT_SENSOR_CONFIGS",
    "DEFAULT_SWITCH_CONFIGS",
    "DEFAULT_NUMBER_CONFIGS",
    "DEFAULT_BOOLEAN_CONFIGS",
    "DEFAULT_DEVICE_ENTITY_MAPPING",
]
