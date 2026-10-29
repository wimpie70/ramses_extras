"""Device domains for the floorplan helper.

Import order registers the domain adapters in the base registry —
:func:`get_domain` then resolves any device class to its behaviour.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .base import (
    DeviceDomain,
    caption_group_key,
    caption_group_label,
    caption_suffix_for,
    device_class_from_id,
    get_domain,
    register_domain,
    zone_eligible,
)
from .heat import (
    APP_DOMAIN,
    AUX_DOMAIN,
    BOILER_DOMAIN,
    CTL_DOMAIN,
    DHW_DOMAIN,
    OUT_DOMAIN,
    STAT_DOMAIN,
    TRV_DOMAIN,
)
from .hvac import BOUND_DOMAIN, FAN_DOMAIN, INFRA_DOMAIN

for _domain in (
    FAN_DOMAIN,
    BOUND_DOMAIN,
    INFRA_DOMAIN,
    CTL_DOMAIN,
    STAT_DOMAIN,
    TRV_DOMAIN,
    BOILER_DOMAIN,
    DHW_DOMAIN,
    AUX_DOMAIN,
    APP_DOMAIN,
    OUT_DOMAIN,
):
    register_domain(_domain)

__all__ = [
    "APP_DOMAIN",
    "AUX_DOMAIN",
    "BOILER_DOMAIN",
    "BOUND_DOMAIN",
    "CTL_DOMAIN",
    "DHW_DOMAIN",
    "DeviceDomain",
    "caption_group_key",
    "caption_group_label",
    "caption_suffix_for",
    "FAN_DOMAIN",
    "INFRA_DOMAIN",
    "OUT_DOMAIN",
    "STAT_DOMAIN",
    "TRV_DOMAIN",
    "device_class_from_id",
    "get_domain",
    "register_domain",
    "zone_eligible",
]
