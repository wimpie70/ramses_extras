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

# The fan itself — the only marker that spins.
FAN_DOMAIN = DeviceDomain(
    device_classes=("FAN", "HVAC"),
    can_spin=True,
    popup_card="hvac-fan",
)

# Bound devices of a fan (remotes, displays, co2/sensors) — generic
# marker behaviour; registered explicitly so future per-class
# behaviour (battery icon etc.) has a home.
BOUND_DOMAIN = DeviceDomain(
    device_classes=("REM", "DIS", "CO2", "THM", "SEN", "SWI", "RND", "SW2"),
)

# Transport-layer devices — visible on the plan but never part of a
# zone highlight: they serve the whole house, not a room.
INFRA_DOMAIN = DeviceDomain(
    device_classes=("HGI", "RFG", "RFS"),
    zone_eligible=False,
)

__all__ = ["BOUND_DOMAIN", "FAN_DOMAIN", "INFRA_DOMAIN"]
