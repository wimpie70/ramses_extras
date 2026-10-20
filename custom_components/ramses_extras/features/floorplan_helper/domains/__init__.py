"""Device domains for the floorplan helper.

Import order registers the domain adapters in the base registry —
:func:`get_domain` then resolves any device class to its behaviour.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .base import (
    DeviceDomain,
    device_class_from_id,
    get_domain,
    register_domain,
    zone_eligible,
)
from .heat import HEAT_DOMAIN
from .hvac import BOUND_DOMAIN, FAN_DOMAIN, INFRA_DOMAIN

for _domain in (FAN_DOMAIN, BOUND_DOMAIN, INFRA_DOMAIN, HEAT_DOMAIN):
    register_domain(_domain)

__all__ = [
    "BOUND_DOMAIN",
    "DeviceDomain",
    "FAN_DOMAIN",
    "HEAT_DOMAIN",
    "INFRA_DOMAIN",
    "device_class_from_id",
    "get_domain",
    "register_domain",
    "zone_eligible",
]
