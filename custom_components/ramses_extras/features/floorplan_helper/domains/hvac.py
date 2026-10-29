"""Ventilation domain — FAN/HVAC units and their bound devices.

Behaviour the floorplan gets from here:

- fan-shaped markers may rotate (``rx-spin*``) with speed/demand —
  a REM's ``fan_mode`` mirrors its parent's speed but its marker is a
  remote, not a fan
- double tap on the fan marker opens the hvac-fan popup card
- house-wide gateways (HGI) are never zone-bound — they serve the
  whole house, not a room

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .base import DeviceDomain

# The fan itself — the only marker that spins. Caption shows the
# inside temperature first, then outside: "12.9° / 9.1°" — exhaust/
# supply duct temps are inside-side fallbacks.
FAN_DOMAIN = DeviceDomain(
    device_classes=("FAN", "HVAC"),
    key="hvac",
    can_spin=True,
    popup_card="hvac-fan",
    caption_groups=(
        (("indoor_temp", "supply_temp", "exhaust_temp"), "°"),
        (("outdoor_temp",), "°"),
    ),
)

# Bound devices of a fan (remotes, displays, co2/sensors). A CO2
# sensor's value is the interesting reading on its marker — "402 ppm";
# a temperature follows when the device reports one (thermostats).
BOUND_DOMAIN = DeviceDomain(
    device_classes=("REM", "DIS", "CO2", "THM", "SEN", "SWI", "RND", "SW2"),
    key="hvac",
    caption_groups=(
        (("co2_level",), " ppm"),
        (("indoor_temp", "temperature", "_temp"), "°"),
    ),
)

# Transport-layer devices — visible on the plan but never part of a
# zone highlight: they serve the whole house, not a room.
INFRA_DOMAIN = DeviceDomain(
    device_classes=("HGI", "RFG", "RFS"),
    key="hvac",
    zone_eligible=False,
)

__all__ = ["BOUND_DOMAIN", "FAN_DOMAIN", "INFRA_DOMAIN"]
