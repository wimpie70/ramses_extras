"""Heating domain — controllers, TRVs, boiler, DHW, UFH.

Behaviour the floorplan gets from here:

- TRVs show valve demand first, then room temperature — "35% / 20.1°"
- the boiler bridge (OTB) shows water temp + modulation — "62.4° / 38%"
- the controller (CTL) is a zone parent like the FAN: its marker is a
  thermostat, tapping it toggles the configured zone's rooms/devices
- heat demand already feeds ``rx-heat-demand`` (badge ring turns
  orange) via the shared ``heat_demand`` class role

No heat-specific spin — nothing in this domain rotates.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .base import DeviceDomain

# Zone parents — the evohome controller (01:*/23:*) and programmer.
# more-info popup until a heat card exists.
CTL_DOMAIN = DeviceDomain(
    device_classes=("CTL", "PRG"),
    default_icon="thermostat",
)

# Room thermostats — display units without a valve.
STAT_DOMAIN = DeviceDomain(
    device_classes=("DTS", "DT2"),
    default_icon="thermostat",
)

# Radiator valves — the demand percentage is the interesting number
# (how far the valve is open), room temperature second: "35% / 20.1°".
TRV_DOMAIN = DeviceDomain(
    device_classes=("TRV", "TR0"),
    default_icon="radiator",
    caption_groups=(
        (("heat_demand",), "%"),
        (("indoor_temp", "temperature", "_temp"), "°"),
    ),
)

# OpenTherm bridge — the boiler: water temperature first, then
# modulation level: "62.4° / 38%".
BOILER_DOMAIN = DeviceDomain(
    device_classes=("OTB",),
    default_icon="water-boiler",
    caption_groups=(
        (("boiler_temp", "_water_temp", "flow_temp", "_temp"), "°"),
        (("modulation",), "%"),
    ),
)

# Hot water cylinder — stored temperature: "55.2°".
DHW_DOMAIN = DeviceDomain(
    device_classes=("DHW", "HCW"),
    default_icon="water-boiler",
    caption_groups=((("temperature", "_temp"), "°"),),
)

# UFH controller + appliance relays — demand when the device reports
# it, otherwise no caption.
AUX_DOMAIN = DeviceDomain(
    device_classes=("UFC", "BDR"),
    default_icon="pipe-valve",
    caption_groups=((("heat_demand",), "%"),),
)

# Appliance modules + outdoor sensor.
APP_DOMAIN = DeviceDomain(
    device_classes=("APP",),
    default_icon="gauge",
)

OUT_DOMAIN = DeviceDomain(
    device_classes=("OUT",),
    default_icon="thermometer",
)

__all__ = [
    "APP_DOMAIN",
    "AUX_DOMAIN",
    "BOILER_DOMAIN",
    "CTL_DOMAIN",
    "DHW_DOMAIN",
    "OUT_DOMAIN",
    "STAT_DOMAIN",
    "TRV_DOMAIN",
]
