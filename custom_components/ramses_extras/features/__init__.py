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

# TODO: Enable these when the feature modules are complete
# from .fan_control import (
#     FanAutomationManager,
#     FanEntities,
#     FanServices,
#     FanConfig,
#     FAN_CONTROL_CONST,
#     create_fan_control_feature,
# )
#
# from .sensor_management import (
#     SensorAutomationManager,
#     SensorEntities,
#     SensorServices,
#     SensorConfig,
#     SENSOR_MANAGEMENT_CONST,
#     create_sensor_management_feature,
# )
#
# from .websocket_handler import (
#     WebSocketHandler,
#     WebSocketProtocols,
#     create_websocket_handler_feature,
# )

__all__ = [
    # Humidity Control Feature
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_CONTROL_CONST",
    "create_humidity_control_feature",
    # TODO: Enable these when the feature modules are complete
    # "FanAutomationManager",
    # "FanEntities",
    # "FanServices",
    # "FanConfig",
    # "FAN_CONTROL_CONST",
    # "create_fan_control_feature",
    # "SensorAutomationManager",
    # "SensorEntities",
    # "SensorServices",
    # "SensorConfig",
    # "SENSOR_MANAGEMENT_CONST",
    # "create_sensor_management_feature",
    # "WebSocketHandler",
    # "WebSocketProtocols",
    # "create_websocket_handler_feature",
]
