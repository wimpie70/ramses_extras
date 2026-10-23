"""Device-domain registry for the floorplan helper.

A *domain* groups ramses device classes that share floorplan
behaviour — which class rules their markers emit, whether the marker
may spin, whether it may be bound into another device's zone, which
popup card a double tap opens. Adding support for a new device family
(heat valves, boiler, ufh) means registering a domain here, not
growing ``if device_class in (…)`` checks across the renderers.

Class detection by device *id* reuses ramses_rf's canonical
``DEVICE_ID_REGEX`` patterns (``^18:`` = gateway/HGI, ``^07:`` = DHW…)
so id-based inference stays in one place and can't drift from the
protocol library.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

try:  # canonical patterns live in the protocol library
    from ramses_rf.const import DEVICE_ID_REGEX
except Exception:  # pragma: no cover - ramses_rf is always installed

    class _Fallback:  # minimal copy of the patterns we use
        HGI = re.compile(r"^18:[0-9]{6}$")
        CTL = re.compile(r"^(01|23):[0-9]{6}$")
        DHW = re.compile(r"^07:[0-9]{6}$")
        APP = re.compile(r"^(10|13):[0-9]{6}$")
        UFC = re.compile(r"^02:[0-9]{6}$")
        SEN = re.compile(r"^(01|03|04|12|22|34):[0-9]{6}$")
        BDR = re.compile(r"^13:[0-9]{6}$")

    DEVICE_ID_REGEX = _Fallback()

# id-prefix → device class, derived from DEVICE_ID_REGEX — used when
# the rf device object isn't available to supply its own class.
_ID_CLASS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (getattr(DEVICE_ID_REGEX, name), cls)
    for name, cls in (
        ("HGI", "HGI"),
        ("CTL", "CTL"),
        ("DHW", "DHW"),
        # BDR (^13:) before APP (^(10|13):) — the relay prefix is a
        # subset of the appliance one, first match wins
        ("BDR", "BDR"),
        ("APP", "APP"),
        ("UFC", "UFC"),
        ("SEN", "SEN"),
    )
    if hasattr(DEVICE_ID_REGEX, name)
)


def device_class_from_id(device_id: str) -> str:
    """Infer a ramses device class from its id prefix, or ``""``.

    Uses ramses_rf's canonical ``DEVICE_ID_REGEX`` — e.g. ``18:*`` is
    always a gateway (HGI), ``07:*`` always a DHW sensor — so callers
    don't carry their own prefix tables.
    """
    dev_id = str(device_id or "")
    for pattern, cls in _ID_CLASS_PATTERNS:
        if pattern.match(dev_id):
            return cls
    return ""


@dataclass(frozen=True)
class DeviceDomain:
    """Floorplan behaviour for a family of ramses device classes.

    :param device_classes: ramses ``_SLUG`` classes this domain handles
    :param can_spin: markers may rotate with a speed/demand state
    :param zone_eligible: may appear inside another device's zone
        highlight — house-wide infra (HGI) is never zone-bound
    :param popup_card: ramses-card name a double tap opens ("" = plain
        more-info popup)
    :param default_icon: icon key when no override/binding/studio
        choice applies
    :param class_roles: entity roles that produce class rules —
        ``None`` = the shared default set; domains may restrict or
        extend it (heat will add its own demand roles)
    :param caption_groups: entity-name patterns + suffixes that make
        up the marker's state caption, e.g.
        ``((("indoor_temp",), "°"), (("outdoor_temp",), "°"))`` →
        ``"12.9° / 9.1°"``. One entity per group (first match); groups
        with no match are dropped. The element has a single caption
        text — combining at the source keeps rules from clobbering
        each other.
    """

    device_classes: tuple[str, ...] = ()
    key: str = ""
    can_spin: bool = False
    zone_eligible: bool = True
    popup_card: str = ""
    default_icon: str = ""
    class_roles: tuple[str, ...] | None = None
    # default: first temperature-ish entity, shown with a degree mark
    caption_groups: tuple[tuple[tuple[str, ...], str], ...] = (
        (("indoor_temp", "temperature", "_temp"), "°"),
    )
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_classes", tuple(self.device_classes or ()))

    def caption_entities(
        self,
        entities: list[dict[str, Any]],
        groups: tuple[tuple[tuple[str, ...], str], ...] | None = None,
    ) -> list[tuple[str, str]]:
        """``[(entity_id, suffix)]`` contributing to the marker caption,
        in display order — one per group; patterns take priority over
        entity order (``indoor_temp`` beats ``supply_temp`` even when
        the registry lists it later). ``groups`` restricts which
        caption_groups are used (config-flow per-class selection)."""
        out: list[tuple[str, str]] = []
        for patterns, suffix in groups if groups is not None else self.caption_groups:
            eid = next(
                (
                    str(e["entity_id"])
                    for p in patterns
                    for e in entities
                    if e.get("entity_id") and p in str(e["entity_id"])
                ),
                None,
            )
            if eid:
                out.append((eid, suffix))
        return out


def caption_group_key(group: tuple[tuple[str, ...], str]) -> str:
    """Stable key for a caption group — its first name pattern."""
    return str(group[0][0]) if group and group[0] else ""


def caption_group_label(group: tuple[tuple[str, ...], str]) -> str:
    """Human label for the config-flow multi-select, e.g. ``indoor_temp °``."""
    key = caption_group_key(group)
    suffix = str(group[1]).strip() if group and len(group) > 1 else ""
    return f"{key} {suffix}".rstrip()


def caption_suffix_for(entity_id: str, domain: DeviceDomain) -> str:
    """Display suffix for a caption entity id.

    Domain caption-group patterns win (they know ``indoor_temp`` is a
    temperature and ``co2_level`` is ppm); entity-name heuristics cover
    entities the groups don't mention — a manually attached
    ``sensor.x_indoor_humidity`` still renders as a percentage.
    """
    for patterns, suffix in domain.caption_groups:
        if any(p in entity_id for p in patterns):
            return str(suffix)
    for needle, suffix in (
        ("temp", "°"),
        ("co2", " ppm"),
        ("humidity", "%"),
        ("moisture", "%"),
        ("demand", "%"),
        ("modulation", "%"),
        ("percent", "%"),
    ):
        if needle in entity_id:
            return suffix
    return ""


# Generic fallback — every class not claimed by a registered domain.
GENERIC_DOMAIN = DeviceDomain()

_REGISTRY: dict[str, DeviceDomain] = {}


def register_domain(domain: DeviceDomain) -> None:
    """Register ``domain`` for its ``device_classes``."""
    for cls in domain.device_classes:
        _REGISTRY[str(cls)] = domain


def get_domain(device_or_class: Any) -> DeviceDomain:
    """Look up the domain for a device dict or a class string."""
    if isinstance(device_or_class, dict):
        cls = str(device_or_class.get("device_class") or "")
    else:
        cls = str(device_or_class or "")
    return _REGISTRY.get(cls, GENERIC_DOMAIN)


def zone_eligible(device_or_class: Any) -> bool:
    """Whether the device may appear inside a zone highlight."""
    return get_domain(device_or_class).zone_eligible


__all__ = [
    "DEVICE_ID_REGEX",
    "DeviceDomain",
    "caption_group_key",
    "caption_group_label",
    "caption_suffix_for",
    "GENERIC_DOMAIN",
    "device_class_from_id",
    "get_domain",
    "register_domain",
    "zone_eligible",
]
