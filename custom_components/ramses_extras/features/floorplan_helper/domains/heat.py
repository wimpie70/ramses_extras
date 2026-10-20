"""Heating domain — controllers, TRVs, boiler, DHW, UFH.

Registered now so heat device classes resolve to a domain instead of
the generic fallback; behaviour (demand colouring, setpoint tap
semantics, circuit-zone highlights) lands here incrementally instead
of growing generator code.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .base import DeviceDomain

# Evohome-style heat classes: controller + zone thermostats, TRVs,
# opentherm bridge, DHW sensor, UFH controller, boiler relays,
# programmer and round thermostats.
HEAT_DOMAIN = DeviceDomain(
    device_classes=(
        "CTL",
        "DTS",
        "DT2",
        "TRV",
        "TR0",
        "OTB",
        "DHW",
        "UFC",
        "BDR",
        "PRG",
        "OUT",
        "APP",
        "HCW",
    ),
    popup_card="",  # plain more-info until a heat card exists
)

__all__ = ["HEAT_DOMAIN"]
