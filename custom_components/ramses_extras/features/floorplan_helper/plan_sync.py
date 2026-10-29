"""Plan-editor merge and marker-stamping helpers for Floorplan Helper.

Works against the canonical plan shape exposed by :class:`EditorAdapter`
so any registered plan editor can reuse the same room/marker merge and
metadata-stamping pipeline.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .const import (
    DEVICE_VIEW_SERVICE,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_ICON_MDI,
    OPTION_DEVICE_VIEW_URL,
    ZONE_TOGGLE_SERVICE,
)
from .importer import (
    dedupe_rooms,
    studio_actions_for_device,
    studio_marker,
    studio_marker_zone,
)
from .mapping import get_floorplan_options
from .markers import element_id_for_device, icon_for_device
from .svg_utils import slugify
from .topology import build_floorplan_model
from .zones import resolve_bound, zone_toggle_specs

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .editors.base import EditorAdapter


def _room_key(room: dict[str, Any]) -> str:
    """Stable identity for a studio room — slug of ``areaId`` else of
    ``name``. Both sides slug-normalised so a name-bound copy
    (``deel bg``) and an area-bound copy (``deel_bg``) of the same
    room collide instead of duplicating."""
    return slugify(str(room.get("areaId") or room.get("name") or ""))


def _room_centroid(room: dict[str, Any]) -> tuple[float, float]:
    """Centroid of a studio room's ``[{x, y}, …]`` polygon."""
    pts = room.get("polygon") or []
    if not pts:
        return 0.0, 0.0
    return (
        sum(float(p.get("x") or 0) for p in pts) / len(pts),
        sum(float(p.get("y") or 0) for p in pts) / len(pts),
    )


def _secondary_entities(dev: dict[str, Any], primary: str) -> list[str]:
    """The device's remaining entities — hfs renders them as the
    marker's attached sensors/valves (tempSensors/trvs) by type."""
    return [
        str(e["entity_id"])
        for e in dev.get("entities") or []
        if e.get("entity_id") and str(e["entity_id"]) != primary
    ]


# hfs only allows trvs/tempSensors on 'heater' devices — a CTL is the
# zone's heater in hfs terms; THM/TRV are heater types too
_HFS_DEV_TYPE = {
    "CTL": "heater",
    "THM": "heater",
    "TRV": "heater",
    "FAN": "fan",
    "COV": "cover",
    "HGI": "server",
}


def _hfs_dev_type(dev: dict[str, Any]) -> str:
    """Model device_class → hfs device type — governs how attached
    entities map (climate → tempSensors, heater → trvs)."""
    return _HFS_DEV_TYPE.get(str(dev.get("device_class") or "").upper(), "other")


def _host_floor(
    floors: list[dict[str, Any]], new_floor: dict[str, Any]
) -> tuple[dict[str, Any] | None, tuple[float, float]]:
    """Find the existing floor already holding *new_floor*'s rooms.

    A combined drawing folds every source floor into one studio floor,
    so an incoming ``begane grond``/``1e verdieping`` must merge into
    the combined host rather than append a duplicate floor. Returns
    ``(floor, (ox, oy))`` where the offset translates the incoming
    floor's coordinates into the host's (e.g. ``+800`` for a folded
    upper floor); ``(None, (0, 0))`` when no existing floor holds any
    of the incoming rooms — the caller appends it as genuinely new.
    """
    new_rooms = new_floor.get("rooms") or []
    best: dict[str, Any] | None = None
    best_hits: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for fl in floors:
        have = {_room_key(r): r for r in fl.get("rooms") or []}
        hits = [(have[_room_key(r)], r) for r in new_rooms if _room_key(r) in have]
        if len(hits) > len(best_hits):
            best, best_hits = fl, hits
    if not best_hits:
        return None, (0.0, 0.0)
    dx = sorted(_room_centroid(h)[0] - _room_centroid(n)[0] for h, n in best_hits)
    dy = sorted(_room_centroid(h)[1] - _room_centroid(n)[1] for h, n in best_hits)
    mid = len(best_hits) // 2
    return best, (dx[mid], dy[mid])


def _merge_studio_project(
    existing: dict[str, Any],
    floors_json: list[dict[str, Any]],
    staging: bool,
    extra_markers: list[dict[str, Any]],
    mdi: Any,
    marker_size: int = 20,
    zones: dict[str, Any] | None = None,
    zone_toggles: dict[str, list[dict[str, Any]]] | None = None,
    entity_device: dict[str, str] | None = None,
    dock: dict[str, tuple[float, float]] | None = None,
    fold_hosts: bool = True,
    marker_type_fn: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Merge generated floors into an existing studio project.

    Floors match by name; when the name misses, a floor whose rooms
    already live inside another floor (a combined drawing) merges into
    that host, translated by the room offset — only floors with zero
    matching rooms are appended as genuinely new. Rooms are added when
    missing; markers whose *device* is already present anywhere in the
    project are skipped (user's own placement wins) — dedup is by
    device via ``entity_device``, since an older marker may bind a
    different entity of the same device (e.g. ``*_battery_low`` from an
    older primary-entity choice). ``extra_markers`` are devices without
    a matching room — parked at the in-canvas dock (same anchor the
    merged-SVG export uses) so they stay visible in studio.
    """
    project = dict(existing)
    project["floors"] = list(existing.get("floors") or [])
    by_name = {str(f.get("name", "")).lower(): f for f in project["floors"]}
    entity_device = entity_device or {}
    dock = dock or {}
    type_fn = marker_type_fn or _hfs_dev_type

    def _placed() -> tuple[set[str], set[str]]:
        ents = {
            e
            for f in project["floors"]
            for m in f.get("markers", [])
            for e in (m.get("entities") or [])
        }
        return ents, {entity_device[e] for e in ents if e in entity_device}

    def _new_marker(m: dict[str, Any], placed_e: set[str], placed_d: set[str]) -> bool:
        ents = set(m.get("entities") or [])
        if ents & placed_e:
            return False
        return not ({entity_device.get(e) for e in ents} & placed_d)

    for new_floor in floors_json:
        floor = by_name.get(str(new_floor["name"]).lower())
        ox = oy = 0.0
        if floor is None:
            # host-floor folding only makes sense for browser-side
            # studio's combined single-floor drawings — a server-side
            # editor (hfs) has real multi-floor plans where folding
            # dupes one floor's rooms into another
            floor, (ox, oy) = (
                _host_floor(project["floors"], new_floor)
                if fold_hosts
                else (None, (0.0, 0.0))
            )
            if floor is None:
                project["floors"].append(new_floor)
                by_name[str(new_floor["name"]).lower()] = new_floor
                continue
            # host-floor merge: shift incoming geometry into host space
            for m in new_floor.get("markers") or []:
                m["x"], m["y"] = (
                    float(m.get("x") or 0) + ox,
                    float(m.get("y") or 0) + oy,
                )
            for r in new_floor.get("rooms") or []:
                for p in r.get("polygon") or []:
                    p["x"], p["y"] = p.get("x", 0) + ox, p.get("y", 0) + oy
        have_rooms = {_room_key(r) for r in floor.get("rooms", [])}
        floor.setdefault("rooms", []).extend(
            r for r in new_floor["rooms"] if _room_key(r) not in have_rooms
        )
        # collapse pre-existing same-room duplicates (name-bound vs
        # area-bound copies) — first entry wins style, later copies
        # fill gaps like a seeded clone's areaId
        floor["rooms"] = dedupe_rooms(floor["rooms"])
        placed_e, placed_d = _placed()
        floor.setdefault("markers", []).extend(
            m for m in new_floor["markers"] if _new_marker(m, placed_e, placed_d)
        )

    if staging and project["floors"]:
        placed_e, placed_d = _placed()
        slot = 0
        for dev in extra_markers:
            primary = dev.get("primary_entity")
            if not primary or primary in placed_e or dev.get("device_id") in placed_d:
                continue
            # standalone members (DIY valves, zigbee sensors…) have no
            # home floor — stage a marker on every floor so the user
            # can drag the copy on the floor the device lives on; the
            # merged export already renders them per floor anyway.
            # Model devices stage on the first floor only. The dock
            # sits inside the canvas so studio actually shows it.
            # a device with a matching room on one floor parks on that
            # floor's dock only; with no match it stages on EVERY floor
            # (same as standalone) — the user keeps the copy on the
            # right floor and deletes the rest; entity dedupe means a
            # kept copy is never re-seeded
            home = [
                f
                for f in project["floors"]
                if dev.get("area_id")
                and str(dev["area_id"])
                in {
                    slugify(str(r.get("areaId") or r.get("name") or ""))
                    for r in f.get("rooms") or []
                }
            ]
            floors_for = (
                project["floors"]
                if dev.get("standalone")
                else (home or project["floors"])
            )
            for fl in floors_for:
                anchor = dock.get(str(fl.get("name") or "").lower())
                if anchor is None:
                    width = float(fl.get("canvas", {}).get("width") or 800)
                    anchor = (width - 8 * 30.0 - 20.0, 44.0)
                marker = studio_marker(
                    primary,
                    anchor[0] + (slot % 8) * 30.0,
                    anchor[1] + (slot // 8) * 30.0,
                    mdi(dev),
                    label=str(dev.get("display_name") or dev["device_id"]),
                    size=marker_size,
                    actions=studio_actions_for_device(
                        dev,
                        zones or {},
                        (zone_toggles or {}).get(str(dev.get("device_id") or "")),
                    ),
                    entities=[primary, *_secondary_entities(dev, primary)],
                )
                if not dev.get("standalone"):
                    mtype = type_fn(dev)
                    if mtype:
                        marker["hfsType"] = mtype
                studio_marker_zone(
                    marker, (zones or {}).get(str(dev.get("device_id") or ""))
                )
                fl.setdefault("markers", []).append(marker)
            placed_e.add(primary)
            slot += 1
    return project


def _stamp_marker_actions(
    project: dict[str, Any],
    model: dict[str, Any],
    zones: dict[str, Any],
    options: dict[str, Any],
) -> None:
    """Write the effective gestures into ``marker.actions`` (in place).

    Studio's inspector reads ``actions.tap/hold/double`` straight from
    the marker — a default ``more-info`` hides that the generated card
    will zone-toggle on tap and open the device view on double-tap.
    For each zone-owner marker, gestures that are still default
    (``none``/``more-info``) or point at our bridge services get the
    freshly generated action — same shorthand/detection precedence as
    ``rules._device_rules``, so a deliberate user gesture always wins
    and stale ``serviceData`` is regenerated from live zone config.
    """
    entity_device: dict[str, dict[str, Any]] = {}
    for dev in model.get("devices") or []:
        for e in dev.get("entities") or []:
            if e.get("entity_id"):
                entity_device[str(e["entity_id"])] = dev
        if dev.get("primary_entity"):
            entity_device[str(dev["primary_entity"])] = dev

    def _is_default(action: Any, shorthand: set[str]) -> bool:
        if not isinstance(action, dict):
            return True
        kind = action.get("kind")
        if kind in (None, "none", "more-info"):
            return True
        return kind == "call-service" and action.get("service") in shorthand

    zone_shorthand = {ZONE_TOGGLE_SERVICE, "floorplan.class_toggle"}
    view_shorthand = {DEVICE_VIEW_SERVICE}
    view_url = str(options.get(OPTION_DEVICE_VIEW_URL) or "")

    for floor in project.get("floors") or []:
        for marker in floor.get("markers") or []:
            dev = next(
                (
                    entity_device[e]
                    for e in (marker.get("entities") or [])
                    if e in entity_device
                ),
                None,
            )
            if dev is None:
                continue
            device_id = str(dev.get("device_id") or "")
            zone = zones.get(device_id)
            if not zone:
                continue
            areas, bound = resolve_bound(
                model, dev, zone, lambda d: element_id_for_device(d, options)
            )
            seeded = studio_actions_for_device(
                dev, {device_id: zone}, zone_toggle_specs(device_id, areas, bound)
            )
            if view_url:
                seeded["double"] = {"kind": "navigate", "navPath": view_url}
            actions = marker.setdefault("actions", {})
            if _is_default(actions.get("tap"), zone_shorthand):
                actions["tap"] = seeded["tap"]
            if _is_default(actions.get("hold"), set()):
                actions["hold"] = seeded["hold"]
            if _is_default(actions.get("double"), view_shorthand):
                actions["double"] = seeded["double"]


async def _write_zone_to_project(
    hass: HomeAssistant,
    adapter: EditorAdapter,
    device_id: str,
    zone: dict[str, Any] | None,
) -> None:
    """Write/clear ``marker.ramsesZone`` in the editor's stored plan.

    The plan is the single source of truth for zone config —
    option-level zones only fill in devices without a marker zone
    (see ``markers.effective_zones``). Editors that round-trip unknown
    fields (``capabilities.stamp_extras``) keep the marker stamp; for
    the rest the option level *is* the store.
    """
    if not adapter.capabilities.stamp_extras:
        return
    project = await adapter.async_load(hass)
    if not isinstance(project, dict):
        return
    model = await build_floorplan_model(hass)
    dev = next(
        (d for d in model.get("devices") or [] if d.get("device_id") == device_id),
        None,
    )
    targets = {dev.get("primary_entity")} if dev else set()
    targets.update(e.get("entity_id") for e in (dev or {}).get("entities") or [])
    targets.discard(None)
    changed = False
    for floor in project.get("floors") or []:
        for marker in floor.get("markers") or []:
            if set(marker.get("entities") or []) & targets:
                studio_marker_zone(marker, zone)
                changed = True
    if changed:
        await adapter.async_store(hass, project)


async def _write_caption_to_project(
    hass: HomeAssistant,
    adapter: EditorAdapter,
    device_id: str,
    items: list[str] | None,
) -> None:
    """Write/clear ``marker.ramsesCaption`` in the editor's stored plan.

    Same SSOT pattern as :func:`_write_zone_to_project` — the option
    override is only the fallback for markers without the field.
    ``items=None`` removes the field (marker returns to defaults).
    """
    if not adapter.capabilities.stamp_extras:
        return
    project = await adapter.async_load(hass)
    if not isinstance(project, dict):
        return
    model = await build_floorplan_model(hass)
    dev = next(
        (d for d in model.get("devices") or [] if d.get("device_id") == device_id),
        None,
    )
    targets = {dev.get("primary_entity")} if dev else {device_id}
    targets.update(e.get("entity_id") for e in (dev or {}).get("entities") or [])
    targets.discard(None)
    changed = False
    for floor in project.get("floors") or []:
        for marker in floor.get("markers") or []:
            if not set(marker.get("entities") or []) & targets:
                continue
            if items is None:
                marker.pop("ramsesCaption", None)
            else:
                marker["ramsesCaption"] = items
            changed = True
    if changed:
        await adapter.async_store(hass, project)


async def _write_icon_to_project(
    hass: HomeAssistant,
    adapter: EditorAdapter,
    config_entry: ConfigEntry,
    target: str,
    icon_key: str | None,
) -> None:
    """Write/clear ``marker.style.icon`` in the editor's stored plan.

    ``floorplan_set_icon`` still stores the option-level override (the
    fallback for elements without a marker), but the marker is the
    single source of truth — stamping the mdi name here keeps studio
    showing the same icon we render. On clear, the marker falls back
    to the device's domain default so studio never sees a missing
    icon. Editors without per-marker icons (hfs's fixed type enum)
    skip the stamp — the option override stays the fallback.

    :param target: device id, device class, or entity id — the same
        keys the option-level override resolves against
    """
    if not adapter.capabilities.stamp_extras:
        return
    project = await adapter.async_load(hass)
    if not isinstance(project, dict):
        return
    model = await build_floorplan_model(hass)
    options = get_floorplan_options(config_entry)

    def icon_for(dev: dict[str, Any]) -> str | None:
        key = icon_key or icon_for_device(dev, options)
        return FLOORPLAN_ICON_MDI.get(str(key))

    targets: dict[str, str] = {}
    for dev in model.get("devices") or []:
        keys = {str(dev.get("device_id")), str(dev.get("device_class"))}
        keys.add(str(dev.get("primary_entity") or ""))
        keys.update(str(e.get("entity_id")) for e in dev.get("entities") or [])
        if target in keys:
            mdi = icon_for(dev)
            for eid in keys:
                if eid:
                    targets[eid] = mdi or ""
    changed = False
    for floor in project.get("floors") or []:
        for marker in floor.get("markers") or []:
            ents = [str(e) for e in marker.get("entities") or []]
            hit = next((e for e in ents if e in targets), None)
            if hit and targets[hit]:
                marker.setdefault("style", {})["icon"] = targets[hit]
                changed = True
    if changed:
        await adapter.async_store(hass, project)


_RAMSES_ENT_ID_RE = re.compile(r"(?<!\d)(\d{2})_(\d{6})(?!\d)")


def _rebind_or_prune_migrated_markers(
    project: dict[str, Any],
    model: dict[str, Any],
    entity_device: dict[str, str],
) -> None:
    """Rebind 1:1 foreign RAMSES markers or prune dead ones before seed.

    When migrating a layout across instances or profiles, markers bound
    to foreign RAMSES entities (containing ``XX_XXXXXX`` not in the
    local ``entity_device`` map) either rebind in-place when there is a
    unique unplaced local device of the same class/prefix (keeping room
    coordinates), or are removed so local devices stage cleanly.
    Non-RAMSES markers (e.g. Shelly valve covers) are untouched.
    """
    if not entity_device:
        return
    devices: list[dict[str, Any]] = [
        d for d in (model.get("devices") or []) if d.get("primary_entity")
    ]
    placed_dids: set[str] = {
        entity_device[e]
        for fl in project.get("floors") or []
        for m in fl.get("markers") or []
        for e in (m.get("entities") or [])
        if e in entity_device
    }

    def _marker_hint(m: dict[str, Any], match: re.Match[str]) -> tuple[str, str]:
        prefix = match.group(1)
        label = str((m.get("style") or {}).get("label") or "").strip()
        head = label.split(" ", 1)[0].upper() if label else ""
        cls = head if head in FLOORPLAN_DEVICE_ICON_MAP else ""
        return cls, prefix

    # Count foreign markers per (cls, prefix) so we only rebind 1:1
    foreign_counts: dict[tuple[str, str], int] = {}
    for fl in project.get("floors") or []:
        for m in fl.get("markers") or []:
            ents = [str(e) for e in (m.get("entities") or []) if e]
            if not ents or any(e in entity_device for e in ents):
                continue
            rm = _RAMSES_ENT_ID_RE.search(ents[0])
            if rm is None:
                continue
            key = _marker_hint(m, rm)
            foreign_counts[key] = foreign_counts.get(key, 0) + 1

    for fl in project.get("floors") or []:
        kept: list[dict[str, Any]] = []
        for m in fl.get("markers") or []:
            ents = [str(e) for e in (m.get("entities") or []) if e]
            if not ents or any(e in entity_device for e in ents):
                kept.append(m)
                continue
            rm = _RAMSES_ENT_ID_RE.search(ents[0])
            if rm is None:
                # Non-RAMSES entity (e.g. DIY cover/sensor) — keep as-is
                kept.append(m)
                continue
            cls, prefix = _marker_hint(m, rm)
            cands = [
                d
                for d in devices
                if str(d.get("device_id") or "") not in placed_dids
                and (
                    (cls and str(d.get("device_class") or "").upper() == cls)
                    or (
                        not cls
                        and str(d.get("device_id") or "").startswith(f"{prefix}:")
                    )
                )
            ]
            if len(cands) == 1 and foreign_counts.get((cls, prefix), 0) == 1:
                cand = cands[0]
                primary = str(cand["primary_entity"])
                m["entities"] = [primary]
                m["elementId"] = primary
                style = dict(m.get("style") or {})
                style["label"] = str(cand.get("display_name") or cand["device_id"])
                m["style"] = style
                placed_dids.add(str(cand["device_id"]))
                kept.append(m)
            # else: ambiguous or obsolete foreign RAMSES marker — prune
        fl["markers"] = kept


__all__ = [
    "_hfs_dev_type",
    "_host_floor",
    "_rebind_or_prune_migrated_markers",
    "_merge_studio_project",
    "_room_centroid",
    "_room_key",
    "_secondary_entities",
    "_stamp_marker_actions",
    "_write_caption_to_project",
    "_write_icon_to_project",
    "_write_zone_to_project",
]
