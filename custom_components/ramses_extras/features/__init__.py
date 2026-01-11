"""Ramses Extras Features Package.

This package contains feature-centric modules that implement specific functionality
using the framework foundation. Each feature is self-contained with its own
automation, services, entities, and configuration.
"""

# Import from the correct feature-centric structure
from .hello_world import (
    create_hello_world_feature,
)
from .humidity_control import (
    HumidityAutomationManager,
    HumidityConfig,
    HumidityEntities,
    HumidityServices,
    create_humidity_control_feature,
)
from .hvac_fan_card import (
    HvacFanCardManager,
    create_hvac_fan_card_feature,
)

# Add more below for future features


__all__ = [
    # Humidity Control Feature
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "create_humidity_control_feature",
    # Hello World Card Feature
    "create_hello_world_feature",
    # HVAC Fan Card Feature
    "HvacFanCardManager",
    "create_hvac_fan_card_feature",
    # Add more below for future features
]
