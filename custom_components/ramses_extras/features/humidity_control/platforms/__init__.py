"""Humidity Control Feature Platforms.

This module provides Home Assistant platform implementations for the
humidity control feature.
Each platform (sensor, switch, number, binary_sensor) contains both the HA integration
and feature-specific business logic.
"""

from .binary_sensor import (
    HumidityControlBinarySensor,
    create_humidity_control_binary_sensor,
)
from .binary_sensor import (
    async_setup_entry as binary_sensor_async_setup_entry,
)
from .number import (
    HumidityControlNumber,
    create_humidity_number,
)
from .number import (
    async_setup_entry as number_async_setup_entry,
)
from .sensor import (
    HumidityAbsoluteSensor,
    create_humidity_sensor,
)
from .sensor import (
    async_setup_entry as sensor_async_setup_entry,
)
from .switch import (
    HumidityControlSwitch,
    create_humidity_switch,
)
from .switch import (
    async_setup_entry as switch_async_setup_entry,
)

__all__ = [
    # Sensor platform
    "HumidityAbsoluteSensor",
    "sensor_async_setup_entry",
    "create_humidity_sensor",
    # Binary sensor platform
    "HumidityControlBinarySensor",
    "binary_sensor_async_setup_entry",
    "create_humidity_control_binary_sensor",
    # Switch platform
    "HumidityControlSwitch",
    "switch_async_setup_entry",
    "create_humidity_switch",
    # Number platform
    "HumidityControlNumber",
    "number_async_setup_entry",
    "create_humidity_number",
]
