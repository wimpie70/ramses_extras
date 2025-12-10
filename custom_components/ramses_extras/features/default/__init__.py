"""Default feature - shared entity definitions."""

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
    "async_step_default_config",
]

# Note: WebSocket commands are now handled directly in websocket_integration.py
# using HA's standard decorator pattern, not through the old class-based system
