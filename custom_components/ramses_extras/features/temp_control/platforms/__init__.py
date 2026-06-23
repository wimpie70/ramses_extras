"""Temp control platforms."""

from .binary_sensor import (
    TempControlActiveBinarySensor,
    create_temp_control_active_binary_sensor,
)
from .binary_sensor import (
    async_setup_entry as binary_sensor_async_setup_entry,
)
from .select import (
    TempControlDesiredSpeedSelect,
    create_temp_control_desired_speed_select,
)
from .select import (
    async_setup_entry as select_async_setup_entry,
)
from .sensor import (
    TempControlStatusSensor,
    create_temp_control_status_sensor,
)
from .sensor import (
    async_setup_entry as sensor_async_setup_entry,
)
from .switch import (
    TempControlSwitch,
    create_temp_control_switch,
)
from .switch import (
    async_setup_entry as switch_async_setup_entry,
)

__all__ = [
    "TempControlSwitch",
    "TempControlDesiredSpeedSelect",
    "TempControlActiveBinarySensor",
    "TempControlStatusSensor",
    "create_temp_control_switch",
    "create_temp_control_desired_speed_select",
    "create_temp_control_active_binary_sensor",
    "create_temp_control_status_sensor",
    "switch_async_setup_entry",
    "select_async_setup_entry",
    "binary_sensor_async_setup_entry",
    "sensor_async_setup_entry",
]
