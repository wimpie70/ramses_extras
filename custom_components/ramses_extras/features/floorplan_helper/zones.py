"""Zone semantics for the floorplan.

A *zone* attaches a device (usually the FAN) to the rooms it serves
plus the devices bound to it — bound via the ramses schema's parent
link (remotes/sensors under the FAN), not by which room a marker sits
in. Non-ramses entities (DIY valves, zigbee sensors) join through the
zone's ``devices`` list — a one-way link, so one entity may serve
several zones.

Tapping a zone marker toggles ``rx-zone-*`` classes: a translucent
hatch + outline on the served ``area.*`` rooms, and a glow on the
bound device markers. ``floorplan.class_toggle`` only reaches the
card that fired it, so the action set also broadcasts the toggles for
the module-level listener to apply on every other floorplan card.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from typing import Any

from .const import ZONE_TOGGLE_SERVICE
from .domains import zone_eligible
from .svg_utils import slugify


def zone_class(device_id: str) -> str:
    """CSS class toggled on a zone's rooms when the marker is tapped."""
    return f"rx-zone-{slugify(device_id)}"


def zone_dev_class(device_id: str) -> str:
    """CSS class toggled on a zone's bound device markers."""
    return zone_class(f"{device_id}-dev")


def resolve_bound(
    model: dict[str, Any],
    dev: dict[str, Any],
    zone: dict[str, Any],
    element_id_for_device: Any,
) -> tuple[list[str], list[str]]:
    """Resolve a zone into ``(room element ids, bound element ids)``.

    :param element_id_for_device: callable ``(dev) -> element id`` —
        passed in because element resolution lives with the marker
        renderers
    """
    device_id = str(dev.get("device_id") or "")
    devices: list[dict[str, Any]] = model.get("devices") or []

    area_elements = [f"area.{slugify(a)}" for a in (zone.get("areas") or []) if a]

    bound_ids = {
        str(d.get("device_id"))
        for d in devices
        if d.get("parent") == device_id and zone_eligible(d)
    }
    bound_ids.update(str(b) for b in zone.get("devices") or [])
    bound_ids.add(device_id)

    bound = [
        element_id_for_device(d)
        for d in devices
        if str(d.get("device_id")) in bound_ids and zone_eligible(d)
    ]
    # entity-id entries (a member entity of a model device, or a
    # non-ramses zone member) map to the owning device's element, or
    # land on the standalone marker rendered for them
    for b in sorted(bound_ids):
        if "." not in b or b in bound:
            continue
        owner = device_of_entity(model, b)
        el = (
            element_id_for_device(owner)
            if owner is not None and zone_eligible(owner)
            else (None if owner is not None else b)
        )
        if el and el not in bound:
            bound.append(el)
    return area_elements, bound


def device_of_entity(model: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    """Return the model device owning ``entity_id``, or None."""
    for d in model.get("devices") or []:
        dev: dict[str, Any] = d
        if dev.get("primary_entity") == entity_id:
            return dev
        for e in dev.get("entities") or []:
            if e.get("entity_id") == entity_id:
                return dev
    return None


def model_entity_ids(model: dict[str, Any]) -> set[str]:
    """All entity ids belonging to model devices (primary + members)."""
    ids: set[str] = set()
    for d in model.get("devices", []):
        if d.get("primary_entity"):
            ids.add(str(d["primary_entity"]))
        ids.update(
            str(e.get("entity_id"))
            for e in d.get("entities") or []
            if e.get("entity_id")
        )
    return ids


def standalone_members(model: dict[str, Any], zones: dict[str, Any]) -> list[str]:
    """Entity ids listed in zones' ``devices`` that aren't ramses model
    devices — DIY valves, zigbee area sensors… — plus the non-ramses
    entities _extras features wire up (paired-valve zones, zone
    sensors/actuators), carried on the model as ``extras_entities``
    (deduped, sorted)."""
    ids = model_entity_ids(model)
    out: set[str] = set()
    for z in zones.values():
        for ent in z.get("devices") or []:
            ent = str(ent)
            if "." in ent and ent not in ids:
                out.add(ent)
    for ent in model.get("extras_entities") or []:
        ent = str(ent)
        if "." in ent and ent not in ids:
            out.add(ent)
    return sorted(out)


def zone_defs(model: dict[str, Any], zones: dict[str, Any]) -> str:
    """``<style>`` + hatch ``<pattern>`` defs for every configured zone.

    The room class swaps the fill for a translucent diagonal hatch in
    the zone colour plus a solid outline — visible over any base fill.
    The ``-dev`` variant rings the bound markers' badge in the zone
    colour and leaves their disc/glyph to the rx-* state classes.
    """
    css: list[str] = []
    patterns: list[str] = []
    for dev in model.get("devices", []):
        z = zones.get(dev.get("device_id"))
        if not (z and (z.get("areas") or z.get("devices"))):
            continue
        color = z.get("color") or "#22c55e"
        device_id = str(dev.get("device_id"))
        if z.get("areas"):
            pat = f"rx-zonepat-{slugify(device_id)}"
            patterns.append(
                f'<pattern id="{pat}" width="10" height="10" '
                f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                f'<rect width="10" height="10" fill="{color}" '
                f'fill-opacity="0.12"/>'
                f'<line x1="0" y1="0" x2="0" y2="10" stroke="{color}" '
                f'stroke-opacity="0.5" stroke-width="3"/></pattern>'
            )
            css.append(
                f".{zone_class(device_id)} {{ "
                f"fill: url(#{pat}) !important; fill-opacity: 1 !important; "
                f"stroke: {color} !important; stroke-width: 3px !important; }}"
            )
        # bound markers show membership on the badge ring — a crisp
        # circle outline in the zone colour (a glow/stroke on fill-path
        # icons just reads as blur); !important wins over the rx-*
        # status ring classes (membership beats status while lit)
        css.append(
            f".{zone_dev_class(device_id)} .rx-ring {{ stroke: {color} !important; }}"
        )
    if not css and not patterns:
        return ""
    parts = [f"<style>\n{chr(10).join(css)}\n</style>", "<defs>", *patterns, "</defs>"]
    return "\n".join(parts)


def zone_toggle_specs(
    device_id: str, area_elements: list[str], bound: list[str]
) -> list[dict[str, Any]]:
    """``{class, elements}`` toggle specs for the tap/sync/clear payloads."""
    toggles: list[dict[str, Any]] = []
    if area_elements:
        toggles.append({"class": zone_class(device_id), "elements": area_elements})
    if bound:
        toggles.append({"class": zone_dev_class(device_id), "elements": bound})
    return toggles


def zone_tap_action(
    toggles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Single-tap action: one ``call-service`` to the zone bridge.

    ``ramses_extras.floorplan_zone_toggle`` fires an HA event the
    frontend module turns into class toggles on every floorplan card —
    so the action is a plain service call (fully expressible in
    studio's marker actions and surviving studio's own export),
    instead of a client-side list mixing class_toggle + ll-custom.
    """
    return {
        "action": "call-service",
        "service": ZONE_TOGGLE_SERVICE,
        "service_data": {"toggles": toggles},
    }


def zone_tap_actions(
    toggles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Backwards-compatible alias for :func:`zone_tap_action`.

    Older exports emitted an action *list*; the current shape is a
    single call-service dict — same return value either way.
    """
    return zone_tap_action(toggles)


def zone_clear_action(toggles: list[dict[str, Any]]) -> dict[str, Any]:
    """Legacy ll-custom clear spec — kept for previously exported yaml.

    New exports clear zones inside the device-view event handler
    instead; the module's ll-custom listener still honours this so
    old generated cards keep working.
    """
    return {"action": "fire-dom-event", "ramses_zone_clear": toggles}


__all__ = [
    "device_of_entity",
    "model_entity_ids",
    "resolve_bound",
    "standalone_members",
    "zone_class",
    "zone_clear_action",
    "zone_defs",
    "zone_dev_class",
    "zone_tap_action",
    "zone_tap_actions",
    "zone_toggle_specs",
]
