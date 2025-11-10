"""Framework Feature Implementations.

This package contains concrete feature implementations that use the framework
helpers and base classes to provide specific functionality.
"""

from .fan_control import (
    FanControlFeature,
    FanMode,
    FanSchedule,
    create_fan_control_feature,
    register_fan_control_feature,
)
from .humidity_control import (
    HumidityControlFeature,
    create_humidity_control_feature,
    register_humidity_control_feature,
)
from .sensor_management import (
    SensorConfig,
    SensorManagementFeature,
    SensorReading,
    create_sensor_management_feature,
    register_sensor_management_feature,
)
from .websocket_handler import (
    EventHandler,
    WebSocketHandlerFeature,
    WebSocketMessage,
    create_websocket_handler_feature,
    register_websocket_handler_feature,
)

__all__ = [
    # Humidity Control Feature
    "HumidityControlFeature",
    "create_humidity_control_feature",
    "register_humidity_control_feature",
    # WebSocket Handler Feature
    "WebSocketHandlerFeature",
    "WebSocketMessage",
    "EventHandler",
    "create_websocket_handler_feature",
    "register_websocket_handler_feature",
    # Fan Control Feature
    "FanControlFeature",
    "FanMode",
    "FanSchedule",
    "create_fan_control_feature",
    "register_fan_control_feature",
    # Sensor Management Feature
    "SensorManagementFeature",
    "SensorConfig",
    "SensorReading",
    "create_sensor_management_feature",
    "register_sensor_management_feature",
]
