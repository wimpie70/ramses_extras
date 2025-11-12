"""Ramses Extras Features Package.

This package contains feature-centric modules that implement specific functionality
using the framework foundation. Each feature is self-contained with its own
automation, services, entities, and configuration.
"""

# Import from the correct feature-centric structure
from .humidity_control import (
    HUMIDITY_CONTROL_CONST,
    HumidityAutomationManager,
    HumidityConfig,
    HumidityEntities,
    HumidityServices,
    create_humidity_control_feature,
)

# Add more below for future features


__all__ = [
    # Humidity Control Feature
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_CONTROL_CONST",
    "create_humidity_control_feature",
    # Add more below for future features
]
