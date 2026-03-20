"""CO2 Control Platform Implementations."""

from .binary_sensor import (
    CO2ControlBinarySensor,
    binary_sensor_async_setup_entry,
    create_co2_binary_sensor_entities,
    create_co2_control_binary_sensor,
)
from .number import (
    CO2ControlNumber,
    create_co2_number,
    create_co2_number_entities,
    number_async_setup_entry,
)
from .sensor import (
    CO2ControlSensor,
    create_co2_sensor,
    create_co2_sensor_entities,
    sensor_async_setup_entry,
)
from .switch import (
    CO2ControlSwitch,
    switch_async_setup_entry,
)

__all__ = [
    # Binary Sensor
    "CO2ControlBinarySensor",
    "binary_sensor_async_setup_entry",
    "create_co2_control_binary_sensor",
    "create_co2_binary_sensor_entities",
    # Number
    "CO2ControlNumber",
    "create_co2_number",
    "create_co2_number_entities",
    "number_async_setup_entry",
    # Sensor
    "CO2ControlSensor",
    "create_co2_sensor",
    "create_co2_sensor_entities",
    "sensor_async_setup_entry",
    # Switch
    "CO2ControlSwitch",
    "switch_async_setup_entry",
]
