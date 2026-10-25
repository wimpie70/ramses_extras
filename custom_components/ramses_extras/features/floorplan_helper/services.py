"""Floorplan Helper services.

Managed-regeneration surface for the ha-floorplan bundle:

- ``floorplan_export`` — regenerate files + rules, return the bundle
  (response-only service).
- ``floorplan_set_element`` — upsert/remove an element binding in the
  stored mapping.
- ``floorplan_set_icon`` — icon override per device class or entity.
- ``floorplan_assign_area`` — bind a device/zone to an HA area.
- ``floorplan_set_svg`` — switch between generated and custom SVG.
- ``floorplan_import`` — parse pasted floorplan YAML (e.g. from the
  external floorplan-editor) into stored bindings and extra rules.
- ``floorplan_upload_svg`` — write an SVG file into
  ``config/www/ramses_extras/floorplan/`` and optionally activate it —
  the file bridge external browser tools cannot perform themselves.
- ``floorplan_sync_areas`` — import a floorplan-studio project JSON:
  creates HA areas for room names and assigns marker entities to the
  room they sit in (real ``entity_registry`` area ids).

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .bundle import async_generate_bundle
from .const import (
    DEFAULT_ICON,
    DEVICE_VIEW_SERVICE,
    EVENT_DEVICE_VIEW,
    EVENT_ZONE_TOGGLE,
    FEATURE_ID,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_ICON_MDI,
    FLOORPLAN_ICONS,
    FLOORPLAN_UPLOAD_DIR_NAME,
    OPTION_CAPTION_OVERRIDES,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_DEVICE_VIEW_URL,
    OPTION_DEVICE_ZONES,
    OPTION_EDITOR,
    OPTION_EDITOR_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
    ZONE_TOGGLE_SERVICE,
    is_generated_rule,
)
from .domains import caption_suffix_for, get_domain
from .editors import resolve_editor
from .editors.base import EditorAdapter
from .editors.hfs import hfs_type_for_device
from .importer import (
    build_studio_project,
    combine_svgs,
    dedupe_rooms,
    merge_project_floors,
    parse_floorplan_yaml,
    parse_studio_project,
    room_for_point,
    rooms_from_svg,
    studio_actions_for_device,
    studio_floor,
    studio_marker,
    studio_marker_positions,
    studio_marker_zone,
    svg_viewbox,
)
from .mapping import (
    get_floorplan_options,
    persist_floorplan_options,
    set_area_override,
    set_caption_override,
    set_device_zone,
    set_element_binding,
    set_icon_override,
    set_svg_mode,
)
from .markers import (
    dock_anchor,
    effective_zones,
    element_id_for_device,
    icon_for_device,
    standalone_icon,
    strip_toolbar,
)
from .rules import stale_managed_rule
from .svg_utils import slugify
from .topology import build_floorplan_model
from .zones import (
    device_of_entity,
    model_entity_ids,
    resolve_bound,
    seed_heat_zones,
    standalone_members,
    zone_toggle_specs,
)

_LOGGER = logging.getLogger(__name__)

SVC_EXPORT = "floorplan_export"
SVC_SET_ELEMENT = "floorplan_set_element"
SVC_SET_ICON = "floorplan_set_icon"
SVC_ASSIGN_AREA = "floorplan_assign_area"
SVC_SET_DEVICE_ZONE = "floorplan_set_device_zone"
SVC_SET_DEVICE_CAPTION = "floorplan_set_device_caption"
SVC_SET_SVG = "floorplan_set_svg"
SVC_IMPORT = "floorplan_import"
SVC_UPLOAD_SVG = "floorplan_upload_svg"
SVC_SYNC_AREAS = "floorplan_sync_areas"
SVC_SEED_STUDIO = "floorplan_seed_studio"
SVC_COMBINE_FLOORS = "floorplan_combine_floors"
SVC_STORE_PROJECT = "floorplan_store_project"
SVC_RESET = "floorplan_reset"
SVC_ZONE_TOGGLE = "floorplan_zone_toggle"
SVC_DEVICE_VIEW = "floorplan_device_view"

# Canonical server-side location for the "current" studio project
# (written by floorplan_store_project; read when services get no
# project_json). Timestamped copies go alongside for history.
PROJECT_LATEST_NAME = "latest.json"

NOTIFICATION_ID = "ramses_extras_floorplan_export"


async def _adapter(hass: HomeAssistant, editor: str | None = None) -> EditorAdapter:
    """Resolve the editor adapter for this call.

    ``editor`` comes from a service field the actions card sets from
    its yaml ``editor:`` option; absent it falls back to the stored
    ``editor`` option / auto-detection (see ``editors.resolve_editor``).
    """
    try:
        options = get_floorplan_options(_config_entry(hass))
    except RuntimeError:
        options = None
    return await resolve_editor(hass, options, editor)


async def _load_plan(hass: HomeAssistant, editor: str | None = None) -> dict[str, Any]:
    """Load the resolved editor's plan, or raise when none is stored."""
    adapter = await _adapter(hass, editor)
    if not await adapter.async_detect(hass):
        raise vol.Invalid(
            f"The '{adapter.key}' plan editor is not installed — pick "
            "another editor in the actions card yaml or the floorplan "
            "helper options"
        )
    plan = await adapter.async_load(hass)
    if plan is None:
        raise vol.Invalid(
            f"No stored {adapter.name} plan — pass project_json or store "
            "one first (floorplan_store_project / the actions card)"
        )
    return plan


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
            floor, (ox, oy) = _host_floor(project["floors"], new_floor)
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
            floors_for = (
                project["floors"] if dev.get("standalone") else project["floors"][:1]
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
                )
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
    device_id: str,
    zone: dict[str, Any] | None,
    editor: str | None = None,
) -> None:
    """Write/clear ``marker.ramsesZone`` in the editor's stored plan.

    The plan is the single source of truth for zone config —
    option-level zones only fill in devices without a marker zone
    (see ``markers.effective_zones``). Editors that round-trip unknown
    fields (``capabilities.stamp_extras``) keep the marker stamp; for
    the rest the option level *is* the store.
    """
    adapter = await _adapter(hass, editor)
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
    device_id: str,
    items: list[str] | None,
    editor: str | None = None,
) -> None:
    """Write/clear ``marker.ramsesCaption`` in the editor's stored plan.

    Same SSOT pattern as :func:`_write_zone_to_project` — the option
    override is only the fallback for markers without the field.
    ``items=None`` removes the field (marker returns to defaults).
    """
    adapter = await _adapter(hass, editor)
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
    target: str,
    icon_key: str | None,
    editor: str | None = None,
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
    adapter = await _adapter(hass, editor)
    if not adapter.capabilities.stamp_extras:
        return
    project = await adapter.async_load(hass)
    if not isinstance(project, dict):
        return
    model = await build_floorplan_model(hass)
    options = get_floorplan_options(_config_entry(hass))

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


async def _floorplan_model(hass: HomeAssistant) -> dict[str, Any]:
    """The topology model, or ``{}`` when registries aren't ready —
    gesture bridges degrade to no toggles / no card rather than fail."""
    try:
        return await build_floorplan_model(hass)
    except Exception as err:  # pragma: no cover - registry timing
        _LOGGER.debug("floorplan model unavailable: %s", err)
        return {}


def _config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the integration's config entry."""
    entry = hass.data.get(DOMAIN, {}).get("config_entry")
    if not isinstance(entry, ConfigEntry):
        raise RuntimeError("ramses_extras config entry not found")
    return entry


def notify_export(hass: HomeAssistant, bundle: dict[str, Any]) -> None:
    """Raise a persistent_notification summarising an export.

    Needed because tap_action service calls (the in-SVG export button)
    can't display a service response.
    """
    changes = bundle.get("changes") or {}
    lines = [
        f"{len(bundle.get('rules', []))} rules, "
        f"{len(bundle.get('files_written', []))} files written.",
    ]
    if changes.get("first_export"):
        lines.append("First export — snapshot stored.")
    else:
        for key in ("devices_added", "devices_removed", "devices_changed"):
            if changes.get(key):
                lines.append(f"{key.replace('_', ' ')}: {', '.join(changes[key])}")
    for warning in bundle.get("warnings", []):
        lines.append(f"⚠ {warning}")
    persistent_notification.async_create(
        hass,
        "\n".join(lines),
        title="Floorplan bundle regenerated",
        notification_id=NOTIFICATION_ID,
    )


async def _async_ensure_hfs_entry(hass: HomeAssistant) -> None:
    """Create the floorplan_studio config entry when hfs is installed but
    never added — its user step is a one-click ``async_create_entry``, so
    "install hfs + enable this feature" is all the setup the card needs.
    Skipped when the user pinned ``editor: studio`` (legacy tinkersoder).
    """
    try:
        from .editors.hfs import HfsAdapter  # noqa: PLC0415

        options = get_floorplan_options(_config_entry(hass))
        if options.get(OPTION_EDITOR) == "studio":
            return
        if not await HfsAdapter().async_detect(hass):
            return
        if hass.config_entries.async_entries("floorplan_studio"):
            return
        result = await hass.config_entries.flow.async_init(
            "floorplan_studio", context={"source": "user"}, data={}
        )
        _LOGGER.info(
            "floorplan_studio config entry auto-created (flow %s)",
            result.get("type"),
        )
    except Exception:  # noqa: BLE001 — hfs setup must never break ours
        _LOGGER.debug("Could not auto-create floorplan_studio entry")


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register floorplan helper services."""

    hass.async_create_task(_async_ensure_hfs_entry(hass))

    async def _apply_cards_to_dashboards(
        cards: dict[str, dict[str, Any]],
        match: str | None = None,
        url_path: str | None = None,
    ) -> dict[str, int]:
        """Replace generated floorplan card(s) on storage dashboards.

        A card is matched by the map file it displays: exact
        ``config.image.location`` against each generated card — so
        several floorplan cards with different maps each get their own
        update and hand-made cards stay untouched — or the ``match``
        substring override. ``url_path`` limits the scan to one
        dashboard; yaml-mode dashboards can't be patched.
        """
        try:
            from homeassistant.components.lovelace import LOVELACE_DATA
            from homeassistant.components.lovelace.const import ConfigNotFound
            from homeassistant.components.lovelace.dashboard import (
                LovelaceStorage,
            )
        except ImportError:
            return {"dashboards": 0, "cards": 0}

        data = hass.data.get(LOVELACE_DATA)
        if data is None:
            return {"dashboards": 0, "cards": 0}

        def _image_of(card: Any) -> str:
            if not isinstance(card, dict):
                return ""
            img = (card.get("config") or {}).get("image") or {}
            return str(img.get("location") or "")

        def _replacement(card: Any) -> dict[str, Any] | None:
            if not isinstance(card, dict):
                return None
            if card.get("type") != "custom:floorplan-card":
                return None
            if match:
                return next(iter(cards.values())) if match in _image_of(card) else None
            for cfg in cards.values():
                img = (cfg.get("config") or {}).get("image") or {}
                if img.get("location") == _image_of(card):
                    return cfg
            return None

        n_cards = 0
        n_dashes = 0
        for path, dash in (data.dashboards or {}).items():
            if url_path is not None and path != url_path:
                continue
            if not isinstance(dash, LovelaceStorage):
                continue  # yaml-mode dashboards can't be patched
            try:
                conf = await dash.async_load(False)
            except ConfigNotFound:
                continue
            except Exception:  # noqa: BLE001 — one bad dashboard must
                _LOGGER.debug(  # not fail the export
                    "floorplan apply: skipping dashboard %s", path, exc_info=True
                )
                continue
            n = 0
            for view in (conf or {}).get("views", []) or []:
                for i, card in enumerate(view.get("cards") or []):
                    rep = _replacement(card)
                    if rep:
                        view["cards"][i] = rep
                        n += 1
                for sec in view.get("sections") or []:
                    for i, card in enumerate(sec.get("cards") or []):
                        rep = _replacement(card)
                        if rep:
                            sec["cards"][i] = rep
                            n += 1
            if n:
                await dash.async_save(conf)
                n_cards += n
                n_dashes += 1
        return {"dashboards": n_dashes, "cards": n_cards}

    async def _async_export(call: ServiceCall) -> dict[str, Any]:
        """Regenerate the floorplan bundle and return it."""
        bundle = await async_generate_bundle(
            hass, _config_entry(hass), editor=call.data.get("editor")
        )
        notify_export(hass, bundle)
        if call.data.get("apply", True) and bundle.get("cards"):
            bundle["applied"] = await _apply_cards_to_dashboards(
                bundle["cards"],
                match=call.data.get("apply_match"),
                url_path=call.data.get("apply_dashboard"),
            )
        _LOGGER.info(
            "Floorplan export complete: %d rules, %d files",
            len(bundle.get("rules", [])),
            len(bundle.get("files_written", [])),
        )
        return bundle

    async def _async_set_element(call: ServiceCall) -> dict[str, Any]:
        """Upsert an element binding (or remove it)."""
        element_id: str = call.data["element_id"]
        remove = call.data.get("remove", False)
        binding = None
        if not remove:
            binding = {
                "entity_id": call.data.get("entity_id"),
                "icon": call.data.get("icon"),
            }
            extra_rules = call.data.get("extra_rules")
            if extra_rules:
                binding["extra_rules"] = extra_rules
        section = set_element_binding(hass, _config_entry(hass), element_id, binding)
        return {
            "element_id": element_id,
            "binding": section.get("element_bindings", {}).get(element_id),
            "removed": remove,
        }

    async def _async_set_icon(call: ServiceCall) -> dict[str, Any]:
        """Set or clear an icon override."""
        target: str = call.data["target"]
        icon: str | None = call.data.get("icon") or None
        if icon is not None and icon not in FLOORPLAN_ICONS:
            raise vol.Invalid(
                f"Unknown icon '{icon}'. Available: {', '.join(FLOORPLAN_ICONS)}"
            )
        section = set_icon_override(hass, _config_entry(hass), target, icon)
        # the plan is the source of truth — stamp the icon onto
        # matching markers too (round-trips untouched through studio,
        # like marker.ramsesZone)
        await _write_icon_to_project(hass, target, icon, call.data.get("editor"))
        return {
            "target": target,
            "icon": icon,
            "icon_overrides": section.get("icon_overrides", {}),
        }

    async def _async_assign_area(call: ServiceCall) -> dict[str, Any]:
        """Bind a ramses device/zone to an HA area."""
        source: str = call.data["source"]
        area_id: str | None = call.data.get("area_id") or None
        section = set_area_override(hass, _config_entry(hass), source, area_id)
        return {
            "source": source,
            "area_id": area_id,
            "area_overrides": section.get("area_overrides", {}),
        }

    async def _async_set_device_zone(call: ServiceCall) -> dict[str, Any]:
        """Set or clear which rooms a device serves (its 'zone').

        The actions card highlights these rooms when the device's
        studio marker is selected; double-clicking the marker opens the
        device card.
        """
        device_id: str = call.data["device_id"]
        remove = call.data.get("remove", False)
        zone = None
        if not remove:
            # merge with the existing zone — omitted keys keep their
            # stored value (pass an explicit empty list to clear one)
            entry = _config_entry(hass)
            prev = (
                get_floorplan_options(entry).get(OPTION_DEVICE_ZONES, {}).get(device_id)
                or {}
            )
            zone = {
                "areas": (
                    list(call.data["areas"])
                    if "areas" in call.data
                    else list(prev.get("areas") or [])
                ),
                "devices": (
                    list(call.data["devices"])
                    if "devices" in call.data
                    else list(prev.get("devices") or [])
                ),
                "color": call.data.get("color") or prev.get("color"),
            }
        section = set_device_zone(hass, _config_entry(hass), device_id, zone)
        # the plan is the source of truth — write the zone onto the
        # marker too (round-trips untouched through studio)
        await _write_zone_to_project(
            hass, device_id, None if remove else zone, call.data.get("editor")
        )
        return {
            "device_id": device_id,
            "zone": section.get(OPTION_DEVICE_ZONES, {}).get(device_id),
            "removed": remove,
        }

    async def _async_set_device_caption(call: ServiceCall) -> dict[str, Any]:
        """Set or clear which entity states a marker's caption shows.

        The actions card's caption editor calls this with the checked
        entity ids; each gets a display suffix resolved from the
        device domain's caption groups (then name heuristics). The
        resolved ``eid|suffix`` items are stored as the option-level
        override AND stamped onto the marker as ``ramsesCaption`` —
        the project stays the single source of truth. ``remove``
        clears both, returning the device to class defaults.
        """
        device_id: str = call.data["device_id"]
        remove = call.data.get("remove", False)
        items: list[str] | None = None
        if not remove:
            model = await build_floorplan_model(hass)
            dev = next(
                (
                    d
                    for d in model.get("devices") or []
                    if d.get("device_id") == device_id
                ),
                None,
            )
            domain = get_domain(dev or {})
            items = [
                f"{e}|{caption_suffix_for(str(e), domain)}"
                for e in (call.data.get("entities") or [])
            ]
        entry = _config_entry(hass)
        section = set_caption_override(hass, entry, device_id, items)
        await _write_caption_to_project(hass, device_id, items, call.data.get("editor"))
        return {
            "device_id": device_id,
            "caption": items,
            "removed": remove,
            "caption_overrides": section.get(OPTION_CAPTION_OVERRIDES, {}),
        }

    async def _async_set_svg(call: ServiceCall) -> dict[str, Any]:
        """Switch SVG mode and/or set the toolbar's tool URLs."""
        entry = _config_entry(hass)
        section = get_floorplan_options(entry)
        if "custom_svg_path" in call.data:
            custom_path = call.data.get("custom_svg_path") or None
            if custom_path:
                section[OPTION_SVG_MODE] = SVG_MODE_CUSTOM
                section[OPTION_CUSTOM_SVG_PATH] = custom_path
            else:
                section[OPTION_SVG_MODE] = SVG_MODE_GENERATED
                section[OPTION_CUSTOM_SVG_PATH] = ""
        if "editor_url" in call.data:
            section[OPTION_EDITOR_URL] = call.data["editor_url"] or ""
        if "planner_url" in call.data:
            section[OPTION_PLANNER_URL] = call.data["planner_url"] or ""
        if "toolbar_enabled" in call.data:
            section[OPTION_TOOLBAR_ENABLED] = bool(call.data["toolbar_enabled"])
        persist_floorplan_options(hass, entry, section)
        return {
            "svg_mode": section.get(OPTION_SVG_MODE),
            "custom_svg_path": section.get(OPTION_CUSTOM_SVG_PATH),
            "editor_url": section.get(OPTION_EDITOR_URL),
            "planner_url": section.get(OPTION_PLANNER_URL),
            "toolbar_enabled": section.get(OPTION_TOOLBAR_ENABLED),
        }

    async def _async_import(call: ServiceCall) -> dict[str, Any]:
        """Import pasted floorplan YAML into the stored mapping."""
        parsed = parse_floorplan_yaml(call.data["yaml_text"])
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))

        entry = _config_entry(hass)
        section = get_floorplan_options(entry)

        bindings = section.setdefault(OPTION_ELEMENT_BINDINGS, {})
        for element_id, binding in parsed["bindings"].items():
            existing = bindings.get(element_id)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(binding)
            bindings[element_id] = merged

        extra = section.setdefault(OPTION_EXTRA_RULES, [])
        # Drop stale generated rules stored by earlier imports — they are
        # rebuilt from the model on every export and old copies (e.g.
        # outdated ${} class expressions) would shadow the fresh ones.
        model = await build_floorplan_model(hass)
        managed = model_entity_ids(model) | set(
            standalone_members(model, section.get(OPTION_DEVICE_ZONES) or {})
        )
        extra[:] = [
            rule
            for rule in extra
            if not is_generated_rule(rule) and not stale_managed_rule(rule, managed)
        ]
        if call.data.get("replace"):
            section[OPTION_EXTRA_RULES] = list(parsed["extra_rules"])
        else:
            seen = {repr(rule) for rule in extra}
            extra.extend(
                rule for rule in parsed["extra_rules"] if repr(rule) not in seen
            )

        persist_floorplan_options(hass, entry, section)
        _LOGGER.info(
            "Floorplan import: %d element bindings, %d rules kept",
            len(parsed["bindings"]),
            len(parsed["extra_rules"]),
        )
        return {
            "bindings_imported": len(parsed["bindings"]),
            "rules_kept": len(parsed["extra_rules"]),
            "warnings": parsed["warnings"],
        }

    async def _async_upload_svg(call: ServiceCall) -> dict[str, Any]:
        """Write an SVG into config/www/ramses_extras/floorplan/."""
        filename = Path(str(call.data["filename"])).name
        if not filename.lower().endswith(".svg"):
            filename += ".svg"
        svg_text = str(call.data["svg_text"])
        if "<svg" not in svg_text:
            raise vol.Invalid("svg_text does not look like an SVG document")

        # Strip any stale toolbar group — the card-side toolbar was
        # removed (export/upload/studio live on the actions card), so
        # leftover glyphs from older exports would be dead buttons.
        svg_text = strip_toolbar(svg_text)

        out_dir = (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / FLOORPLAN_UPLOAD_DIR_NAME
        )

        def _write() -> str:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / filename).write_text(svg_text, encoding="utf-8")
            return filename

        written = await hass.async_add_executor_job(_write)
        web_path = f"/local/ramses_extras/{FLOORPLAN_UPLOAD_DIR_NAME}/{written}"
        _LOGGER.info("Floorplan SVG uploaded: %s", web_path)

        activated = False
        if call.data.get("set_as_active"):
            set_svg_mode(hass, _config_entry(hass), web_path)
            activated = True

        return {
            "web_path": web_path,
            "activated": activated,
        }

    async def _async_sync_areas(call: ServiceCall) -> dict[str, Any]:
        """Sync HA areas from a floorplan-studio project export.

        Creates HA areas for room names (optional) and assigns each
        marker's entities to the smallest room containing it — marker
        placement in the studio drives real entity-registry area ids.
        """
        from homeassistant.helpers import area_registry as ar
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import slugify

        adapter = await _adapter(hass, call.data.get("editor"))
        raw = call.data.get("project_json")
        if raw:
            plan = adapter.parse(raw)
        else:
            plan = await _load_plan(hass, call.data.get("editor"))
            raw = json.dumps(plan)
        parsed = parse_studio_project(plan)
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))
        backup_path = await adapter.async_backup(hass, raw)

        create_areas = call.data.get("create_areas", True)
        dry_run = call.data.get("dry_run", False)
        area_reg = ar.async_get(hass)
        ent_reg = er.async_get(hass)

        # Match rooms to HA areas by slugified name (or existing area id).
        def _slug(name: str) -> str:
            return str(slugify(str(name))).replace("-", "_")

        areas = list(area_reg.async_list_areas())
        by_slug = {_slug(a.name): a for a in areas}
        by_slug.update({a.id: a for a in areas})

        created: list[str] = []
        room_area: dict[str, Any] = {}
        for room in parsed["rooms"]:
            slug = _slug(room["name"])
            area = by_slug.get(slug)
            if room.get("area_id"):
                # Studio's room inspector can link a room to an HA area
                # explicitly — prefer that over the name-slug match.
                explicit = by_slug.get(room["area_id"])
                if explicit is not None:
                    area = explicit
                else:
                    parsed["warnings"].append(
                        f"{room['floor']}: room '{room['name']}' links to "
                        f"unknown HA area '{room['area_id']}'"
                    )
            if area is None and create_areas and not dry_run:
                area = area_reg.async_create(str(room["name"]))
            if area is not None:
                by_slug[slug] = area
                room_area[room["id"]] = area
            elif create_areas:
                # dry-run: pretend it exists for the report
                room_area[room["id"]] = None
            else:
                parsed["warnings"].append(
                    f"{room['floor']}: no HA area for room '{room['name']}'"
                )
        if create_areas:
            created = (
                [a.name for a in area_reg.async_list_areas() if a not in areas]
                if not dry_run
                else [
                    r["name"] for r in parsed["rooms"] if room_area.get(r["id"]) is None
                ]
            )

        dev_reg = dr.async_get(hass)
        assignments: dict[str, str] = {}
        via_device: list[str] = []
        skipped: list[str] = []
        outside: list[str] = []
        for marker in parsed["markers"]:
            room = room_for_point(
                parsed["rooms"], marker["x"], marker["y"], marker["floor"]
            )
            area = room_area.get(room["id"]) if room else None
            for entity_id in marker["entities"]:
                if room is None:
                    outside.append(entity_id)
                    continue
                entry = ent_reg.async_get(entity_id)
                if entry is None:
                    skipped.append(entity_id)
                    continue
                target = area.id if area else _slug(room["name"])
                assignments[entity_id] = target
                if area is not None and not dry_run:
                    try:
                        ent_reg.async_update_entity(entity_id, area_id=area.id)
                    except ValueError:
                        # Entities without a name of their own can't hold
                        # an area — set it on the device instead.
                        if entry.device_id:
                            dev_reg.async_update_device(
                                entry.device_id, area_id=area.id
                            )
                            via_device.append(entity_id)
                        else:
                            skipped.append(entity_id)

        _LOGGER.info(
            "Floorplan sync_areas: %d areas created, %d entities assigned",
            len(created),
            len(assignments),
        )
        return {
            "areas_created": created,
            "assignments": assignments,
            "entities_without_area_room": outside,
            "entities_not_in_registry": skipped,
            "assigned_via_device": via_device,
            "dry_run": dry_run,
            "backup_path": backup_path,
            "warnings": parsed["warnings"],
        }

    def _resolve_svg_path(ref: str) -> Path:
        """Map a /local/... URL or bare filename to a config/www path."""
        if ref.startswith("/local/"):
            return Path(hass.config.config_dir) / "www" / ref[len("/local/") :]
        return (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / FLOORPLAN_UPLOAD_DIR_NAME
            / Path(ref).name
        )

    async def _async_store_project(call: ServiceCall) -> dict[str, Any]:
        """Store a studio project export as the canonical 'latest'.

        Written to ``ramses_extras/floorplan/projects/latest.json`` plus a
        timestamped backup — the server-side working copy that
        ``seed_studio``/``sync_areas`` fall back to when no project_json
        is passed. Powers the actions card's drop zone.
        """
        adapter = await _adapter(hass, call.data.get("editor"))
        raw_text = call.data["project_json"]
        plan = adapter.parse(raw_text)
        parsed = parse_studio_project(plan)
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))
        # Stamp the effective gestures into marker.actions so studio's
        # inspector shows what the card will actually do (defaults ->
        # generated zone-toggle / device-view; user edits win).
        model = await build_floorplan_model(hass)
        options = get_floorplan_options(_config_entry(hass))
        zones = effective_zones(model, options, studio_marker_positions(plan))
        _stamp_marker_actions(plan, model, zones, options)
        latest = await adapter.async_store(hass, plan)
        backup = await adapter.async_backup(hass, json.dumps(plan))
        stats: dict[str, dict[str, int]] = {}
        for room in parsed["rooms"]:
            stats.setdefault(room["floor"], {"rooms": 0, "markers": 0})["rooms"] += 1
        for marker in parsed["markers"]:
            stats.setdefault(marker["floor"], {"rooms": 0, "markers": 0})[
                "markers"
            ] += 1
        _LOGGER.info("Floorplan project stored: %s (%s)", latest, stats)
        return {"latest_path": latest, "backup_path": backup, "floors": stats}

    async def _async_reset(call: ServiceCall) -> dict[str, Any]:
        """Reset the stored plan to the first-install (empty) state.

        Writes a canonical backup first, then clears the editor's store.
        For hfs that deletes ``.storage/floorplan_studio.layout`` — the
        editor's own Reset only produces an in-memory blank plan its
        validator refuses to save, so the real minimal state is an
        empty store.
        """
        adapter = await _adapter(hass, call.data.get("editor"))
        backup = ""
        plan = await adapter.async_load(hass)
        if isinstance(plan, dict):
            backup = await adapter.async_backup(hass, json.dumps(plan))
        if not await adapter.async_clear(hass):
            raise vol.Invalid(f"editor '{adapter.key}' cannot clear its plan")
        _LOGGER.info("Floorplan reset to empty (backup: %s)", backup or "none")
        return {"cleared": True, "backup_path": backup}

    async def _async_zone_toggle(call: ServiceCall) -> dict[str, Any]:
        """Bridge service: zone marker tap → class toggles on all cards.

        Emitting a plain ``call-service`` keeps the gesture
        expressible in studio's marker actions (and in studio's own
        ha-floorplan export); the frontend module subscribes to the
        fired event and toggles the classes on every floorplan card.

        Callers that cannot carry the resolved element list — the hfs
        card overlay only knows the tapped entity — pass ``device_id``
        or ``entity`` and the zone resolves here exactly as the export
        computes it for marker actions.
        """
        toggles = call.data.get("toggles") or []
        target = str(
            call.data.get("device_id")
            or call.data.get("entity")
            or call.data.get("entity_id")
            or ""
        )
        if not toggles and target:
            model = await _floorplan_model(hass)
            dev = device_of_entity(model, target)
            if dev is None:
                dev = next(
                    (
                        d
                        for d in model.get("devices") or []
                        if str(d.get("device_id")) == target
                    ),
                    None,
                )
            try:
                options = get_floorplan_options(_config_entry(hass))
            except RuntimeError, KeyError:
                options = {}
            zone = (options.get(OPTION_DEVICE_ZONES) or {}).get(
                str((dev or {}).get("device_id"))
            )
            if dev is not None and zone:
                did = str(dev["device_id"])
                areas, bound = resolve_bound(
                    model,
                    dev,
                    zone,
                    lambda d: element_id_for_device(d, options),
                )
                toggles = zone_toggle_specs(did, areas, bound)
        payload = {
            "toggles": toggles,
            "clear": bool(call.data.get("clear", False)),
        }
        hass.bus.async_fire(EVENT_ZONE_TOGGLE, payload)
        return payload

    async def _async_device_view(call: ServiceCall) -> dict[str, Any]:
        """Bridge service: marker double-tap → device popup event.

        The frontend module clears all zone highlights (a fast second
        tap is eaten as a double tap by ha-floorplan's gesture
        handler, so the clear lives here rather than in the action)
        and opens the device view for the given entity/card.

        With only ``entity`` the device and its popup card are resolved
        from the model — the hfs card overlay sends nothing else.
        """
        entity = str(call.data.get("entity") or call.data.get("entity_id") or "")
        device_id = str(call.data.get("device_id") or "")
        card = str(call.data.get("card") or "")
        if entity and (not device_id or not card):
            dev = device_of_entity(await _floorplan_model(hass), entity)
            if dev is not None:
                device_id = device_id or str(dev.get("device_id") or "")
                card = card or get_domain(dev).popup_card
        payload = {"device_id": device_id, "entity": entity, "card": card}
        hass.bus.async_fire(EVENT_DEVICE_VIEW, payload)
        return payload

    async def _async_seed_studio(call: ServiceCall) -> dict[str, Any]:
        """Emit/merge a plan with markers pre-placed.

        For each floor's SVG the ``area.*`` elements become rooms; every
        topology device whose HA area matches a room slug gets a marker
        at that room's centroid (grid-stacked when a room holds several
        devices). With no ``floors`` the resolved editor's existing
        plan supplies the rooms instead — hfs layouts draw their own.

        The plan is stored through the editor adapter; browser-side
        editors (studio) also get ``project_json`` back so the card can
        push it into the editor's live storage.
        """
        adapter = await _adapter(hass, call.data.get("editor"))
        floor_specs: dict[str, str] = dict(call.data.get("floors") or {})
        if not floor_specs:
            options = get_floorplan_options(_config_entry(hass))
            active = options.get(OPTION_CUSTOM_SVG_PATH)
            paths = active if isinstance(active, list) else [active]
            floor_specs = {Path(p).stem: p for p in paths if p}

        floor_svgs: dict[str, str] = {}
        missing: list[str] = []
        for name, ref in floor_specs.items():
            path = _resolve_svg_path(ref)
            try:
                floor_svgs[name] = await hass.async_add_executor_job(
                    path.read_text, "utf-8"
                )
            except OSError:
                missing.append(f"{name}: {ref}")
        if missing:
            raise vol.Invalid(f"SVG file(s) not found: {', '.join(missing)}")

        model = await build_floorplan_model(hass)
        marker_size: int = int(call.data.get("marker_size") or 20)
        options = get_floorplan_options(_config_entry(hass))
        zones = dict(options.get(OPTION_DEVICE_ZONES) or {})

        def _mdi(dev: dict[str, Any]) -> str:
            if dev.get("standalone"):
                key = standalone_icon(str(dev.get("primary_entity") or ""))
            else:
                key = FLOORPLAN_DEVICE_ICON_MAP.get(
                    dev.get("device_class") or "", DEFAULT_ICON
                )
            return FLOORPLAN_ICON_MDI.get(key, "help-circle")

        # Merging into an existing plan preserves the background image,
        # walls and any editor edits — without it we emit a fresh plan.
        existing: dict[str, Any] | None = None
        raw_project = call.data.get("project_json")
        if raw_project:
            try:
                existing = adapter.parse(raw_project)
            except (ValueError, vol.Invalid) as err:
                raise vol.Invalid(
                    f"project_json is not a valid {adapter.name} plan: {err}"
                ) from err
        else:
            # Fall back to the editor's stored plan — keeps
            # backgrounds/edits when re-seeding.
            existing = await adapter.async_load(hass)

        # Rooms to seed into — from the floor SVGs, or from the
        # editor's own plan floors (hfs draws rooms natively; there is
        # no authored SVG to parse). Plan rooms convert to the
        # ``rooms_from_svg`` shape so centroid placement works either
        # way.
        floor_rooms: dict[str, dict[str, Any]] = {}
        for fname, svg_text in floor_svgs.items():
            width, height = svg_viewbox(svg_text)
            floor_rooms[fname] = {
                "rooms": rooms_from_svg(svg_text),
                "width": width,
                "height": height,
            }
        if not floor_rooms and existing:
            for fl in existing.get("floors") or []:
                canvas = fl.get("canvas") or {}
                floor_rooms[str(fl.get("name") or fl.get("id") or "floor")] = {
                    "rooms": [
                        {
                            "slug": slugify(
                                str(r.get("areaId") or r.get("name") or "")
                            ),
                            "name": str(r.get("name") or ""),
                            "polygon": r.get("polygon") or [],
                            "centroid": _room_centroid(r),
                        }
                        for r in fl.get("rooms") or []
                    ],
                    "width": float(canvas.get("width") or 800),
                    "height": float(canvas.get("height") or 600),
                }

        # Evohome zones → device_zones: the zone sensor (room stat) is
        # the parent, its actuators join as members, and a room whose
        # name matches the zone name pre-fills `areas`. Existing entries
        # are never overwritten.
        room_slugs: set[str] = {
            r["slug"] for spec in floor_rooms.values() for r in spec["rooms"]
        }
        seeded_zones = seed_heat_zones(model.get("heat_zones") or [], room_slugs, zones)
        if seeded_zones:
            persist_floorplan_options(
                hass, _config_entry(hass), {**options, OPTION_DEVICE_ZONES: zones}
            )

        # resolve each zone to concrete toggle specs — written into the
        # marker's serviceData so studio shows (and exports) the real
        # action; the generated rules regenerate it anyway, so the
        # copy here is display, not truth
        zone_toggles: dict[str, list[dict[str, Any]]] = {}
        for zid, zone in zones.items():
            zdev = next(
                (d for d in model.get("devices") or [] if d.get("device_id") == zid),
                None,
            )
            if zdev:
                areas, bound = resolve_bound(
                    model, zdev, zone, lambda d: element_id_for_device(d, options)
                )
                zone_toggles[zid] = zone_toggle_specs(zid, areas, bound)

        placed: dict[str, str] = {}
        placed_entities: set[str] = set()
        floors_json: list[dict[str, Any]] = []
        floor_stats: list[dict[str, Any]] = []
        dock: dict[str, tuple[float, float]] = {}
        for fname, spec in floor_rooms.items():
            rooms = spec["rooms"]
            width, height = spec["width"], spec["height"]
            # same anchor the merged-SVG export parks unplaced markers
            # at — studio staging lands where the card docks them
            dock[fname.lower()] = dock_anchor({r["slug"]: r for r in rooms}, width)
            by_slug = {r["slug"]: r for r in rooms}
            markers: list[dict[str, Any]] = []
            per_room: dict[str, int] = {}
            for dev in model["devices"]:
                area = dev.get("area_id")
                room = by_slug.get(area) if area else None
                primary = dev.get("primary_entity")
                if room is None or not primary:
                    continue
                n = per_room.get(room["slug"], 0)
                per_room[room["slug"]] = n + 1
                cx, cy = room["centroid"]
                marker = studio_marker(
                    primary,
                    cx + (n % 3) * 36 - 36,
                    cy + (n // 3) * 36,
                    _mdi(dev),
                    label=str(dev.get("display_name") or dev["device_id"]),
                    size=marker_size,
                    actions=studio_actions_for_device(
                        dev, zones, zone_toggles.get(dev.get("device_id"))
                    ),
                )
                studio_marker_zone(marker, zones.get(dev.get("device_id")))
                markers.append(marker)
                placed[dev["device_id"]] = f"{fname} / {room['name']}"
                placed_entities.add(primary)
            floors_json.append(studio_floor(fname, width, height, rooms, markers))
            floor_stats.append(
                {"name": fname, "rooms": len(rooms), "markers": len(markers)}
            )

        unplaced = [
            dev
            for dev in model["devices"]
            if dev["device_id"] not in placed and dev.get("primary_entity")
        ]
        # Non-ramses zone members (DIY valves, zigbee sensors…) get
        # markers too — pseudo-devices so they flow through the same
        # staging/merge path; their rules/overlay already key on the
        # entity id.
        unplaced.extend(
            {
                "device_id": ent,
                "primary_entity": ent,
                "display_name": ent.split(".", 1)[-1],
                "standalone": True,
            }
            for ent in standalone_members(model, zones)
        )

        # entity → device map for device-level merge dedup: an old
        # marker may bind e.g. the battery entity while the current
        # primary is the remote — same device, still a dupe
        entity_device: dict[str, str] = {}
        for dev in model.get("devices") or []:
            did = str(dev.get("device_id") or "")
            for e in dev.get("entities") or []:
                if e.get("entity_id"):
                    entity_device[str(e["entity_id"])] = did
            if dev.get("primary_entity"):
                entity_device[str(dev["primary_entity"])] = did

        if existing is not None:
            project = _merge_studio_project(
                existing,
                floors_json,
                staging=call.data.get("staging", True),
                extra_markers=unplaced,
                mdi=_mdi,
                marker_size=marker_size,
                zones=zones,
                zone_toggles=zone_toggles,
                entity_device=entity_device,
                dock=dock,
            )
        else:
            # Park devices with no matching room at the in-canvas dock
            # (same anchor the export uses) — drag them into a room in
            # studio to assign the area.
            if call.data.get("staging", True) and floors_json:
                for i, dev in enumerate(unplaced):
                    # standalone members stage on every floor — no home
                    # floor, and the merged export renders them per
                    # floor anyway; model devices go on the first only
                    floors_for = (
                        floors_json if dev.get("standalone") else floors_json[:1]
                    )
                    for fl in floors_for:
                        anchor = dock.get(
                            str(fl.get("name") or "").lower(),
                            (
                                float(fl["canvas"]["width"]) - 8 * 30.0 - 20.0,
                                44.0,
                            ),
                        )
                        marker = studio_marker(
                            dev["primary_entity"],
                            anchor[0] + (i % 8) * 30.0,
                            anchor[1] + (i // 8) * 30.0,
                            _mdi(dev),
                            label=str(dev.get("display_name") or dev["device_id"]),
                            size=marker_size,
                            actions=studio_actions_for_device(
                                dev, zones, zone_toggles.get(dev.get("device_id"))
                            ),
                        )
                        studio_marker_zone(marker, zones.get(dev.get("device_id")))
                        fl["markers"].append(marker)
            project = build_studio_project(
                call.data.get("name") or "Floorplan", floors_json
            )
        # Reflect the effective gestures into marker.actions — studio's
        # inspector then shows what the generated card will do rather
        # than bare more-info defaults.
        _stamp_marker_actions(
            project,
            model,
            effective_zones(model, options, studio_marker_positions(project)),
            options,
        )
        # ``hfsType`` precomputes the hfs DeviceType so a store into a
        # ha-floorplan-studio layout lands on the right icon — harmless
        # extra key for editors that don't read it.
        dev_by_id = {str(d.get("device_id")): d for d in model.get("devices") or []}
        for fl in project.get("floors") or []:
            for marker in fl.get("markers") or []:
                mdid: str | None = next(
                    (
                        entity_device[e]
                        for e in (marker.get("entities") or [])
                        if e in entity_device
                    ),
                    None,
                )
                dev = dev_by_id.get(mdid) if mdid else None
                if dev is None:
                    dev = {"primary_entity": (marker.get("entities") or [""])[0]}
                marker.setdefault("hfsType", hfs_type_for_device(dev))

        project_out = json.dumps(project)
        backup_path = await adapter.async_backup(hass, project_out)
        stored_at = ""
        if not adapter.capabilities.browser_side:
            # server-side editors (hfs) have no browser store to push
            # into — write the plan straight into theirs.
            stored_at = await adapter.async_store(hass, project)
        _LOGGER.info(
            "Floorplan seed_studio: %d markers across %d floors, %d unplaced, "
            "%d heat zones seeded (editor=%s)",
            len(placed),
            len(floors_json),
            len(unplaced),
            len(seeded_zones),
            adapter.key,
        )
        return {
            "project_json": project_out,
            "backup_path": backup_path,
            "stored_at": stored_at,
            "editor": adapter.key,
            "zones_seeded": seeded_zones,
            "heat_zones": model.get("heat_zones"),
            "placed": placed,
            "unplaced": [
                {
                    "device_id": dev["device_id"],
                    "area_id": dev.get("area_id"),
                    "primary_entity": dev.get("primary_entity"),
                }
                for dev in unplaced
            ],
            "floors": floor_stats,
        }

    async def _combine_svg_files(
        refs: list[str], gap: float
    ) -> tuple[str, list[tuple[str, str]], list[float], list[str]]:
        """Merge floor SVGs into one ``<prefix>-all.svg`` in the upload dir.

        The SVG half of ``floorplan_combine_floors`` — the project fold
        is a one-time structural op and deliberately not done here, so
        this is safe to re-run on every export. Returns the ``/local/…``
        path plus the resolved ``(stem, text)`` pairs, per-floor x
        offsets and warnings for callers that fold the project.
        """
        svg_texts: list[tuple[str, str]] = []
        missing: list[str] = []
        for ref in refs:
            path = _resolve_svg_path(ref)
            try:
                svg_texts.append(
                    (
                        path.stem,
                        await hass.async_add_executor_job(path.read_text, "utf-8"),
                    )
                )
            except OSError:
                missing.append(str(ref))
        if missing:
            raise vol.Invalid(f"SVG file(s) not found: {', '.join(missing)}")

        merged_svg, offsets, warnings = combine_svgs(svg_texts, gap)
        prefix = os.path.commonprefix([Path(r).stem for r in refs]).strip("-_ ")
        out_name = f"{prefix or 'floors'}-all.svg"
        out_dir = (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / FLOORPLAN_UPLOAD_DIR_NAME
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        await hass.async_add_executor_job(
            (out_dir / out_name).write_text, merged_svg, "utf-8"
        )
        web_path = f"/local/ramses_extras/{FLOORPLAN_UPLOAD_DIR_NAME}/{out_name}"
        return web_path, svg_texts, offsets, warnings

    async def _async_combine_floors(call: ServiceCall) -> dict[str, Any]:
        """Merge the configured floor SVGs into one side-by-side drawing.

        Floor N renders to the right of the previous with ``gap`` px in
        between — one drawing, one studio floor, so markers never have
        to live on the "wrong" floor. The stored project is folded the
        same way: rooms/markers keep their (x-offset) positions and the
        floor backgrounds are composited horizontally. Writes the merged
        SVG to the upload dir and points ``custom_svg_path`` at it.
        """
        options = get_floorplan_options(_config_entry(hass))
        refs = call.data.get("sources") or options.get(OPTION_CUSTOM_SVG_PATH) or []
        refs = [r for r in (refs if isinstance(refs, list) else [refs]) if r]
        if len(refs) < 2:
            raise vol.Invalid(
                "Need at least two custom SVGs configured to combine floors"
            )
        gap = float(call.data.get("gap") or 120)
        web_path, svg_texts, offsets, warnings = await _combine_svg_files(refs, gap)
        boxes = [svg_viewbox(t) for _, t in svg_texts]
        width = offsets[-1] + boxes[-1][0]
        height = max(h for _, h in boxes)

        # fold the stored plan into the same single floor —
        # an already-combined plan re-merges from the newest
        # multi-floor backup so a re-run with a different gap stays
        # correct (editor edits to the combined floor are lost then,
        # so it's reported in warnings)
        adapter = await _adapter(hass, call.data.get("editor"))
        project_merged = False
        stored_plan = await adapter.async_load(hass)
        backups = await adapter.async_plan_backups(hass)

        project = next(
            (
                dict(cand)
                for cand in (stored_plan, *backups)
                if isinstance(cand, dict) and len(cand.get("floors") or []) > 1
            ),
            None,
        )
        if project is not None:
            already = (
                stored_plan is not None and len(stored_plan.get("floors") or []) <= 1
            )
            if already:
                warnings.append(
                    "Stored plan was already combined — re-merged from "
                    "the newest multi-floor backup; any editor edits made "
                    "to the combined floor since are lost"
                )
            merge_project_floors(project, offsets, width, height)
            await adapter.async_store(hass, project)
            await adapter.async_backup(hass, json.dumps(project))
            project_merged = True

        section = dict(options)
        section[OPTION_CUSTOM_SVG_PATH] = [web_path]
        section[OPTION_SVG_MODE] = SVG_MODE_CUSTOM
        persist_floorplan_options(hass, _config_entry(hass), section)

        _LOGGER.info(
            "Floorplan floors combined: %d → 1 (%s, %gx%g, gap %g)",
            len(svg_texts),
            web_path,
            width,
            height,
            gap,
        )
        return {
            "svg": web_path,
            "offsets": offsets,
            "project_merged": project_merged,
            "warnings": warnings,
        }

    if not hass.services.has_service(DOMAIN, SVC_EXPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_EXPORT,
            _async_export,
            schema=vol.Schema(
                {
                    vol.Optional("apply", default=True): cv.boolean,
                    vol.Optional("apply_dashboard"): cv.string,
                    vol.Optional("apply_match"): cv.string,
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ELEMENT):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ELEMENT,
            _async_set_element,
            schema=vol.Schema(
                {
                    vol.Required("element_id"): cv.string,
                    vol.Optional("entity_id"): cv.entity_id,
                    vol.Optional("icon"): cv.string,
                    vol.Optional("extra_rules"): [cv.string],
                    vol.Optional("remove", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ICON):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ICON,
            _async_set_icon,
            schema=vol.Schema(
                {
                    vol.Required("target"): cv.string,
                    vol.Optional("icon"): cv.string,
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_ASSIGN_AREA):
        hass.services.async_register(
            DOMAIN,
            SVC_ASSIGN_AREA,
            _async_assign_area,
            schema=vol.Schema(
                {
                    vol.Required("source"): cv.string,
                    vol.Optional("area_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_DEVICE_ZONE):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_DEVICE_ZONE,
            _async_set_device_zone,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Optional("areas"): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional("devices"): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional("color"): cv.string,
                    vol.Optional("editor"): cv.string,
                    vol.Optional("remove", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_DEVICE_CAPTION):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_DEVICE_CAPTION,
            _async_set_device_caption,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Optional("entities"): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional("editor"): cv.string,
                    vol.Optional("remove", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_SVG):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_SVG,
            _async_set_svg,
            schema=vol.Schema(
                {
                    vol.Optional("custom_svg_path"): vol.Any(cv.string, [cv.string]),
                    vol.Optional("editor_url"): cv.string,
                    vol.Optional("planner_url"): cv.string,
                    vol.Optional("toolbar_enabled"): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_IMPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_IMPORT,
            _async_import,
            schema=vol.Schema(
                {
                    vol.Required("yaml_text"): cv.string,
                    vol.Optional("replace", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_UPLOAD_SVG):
        hass.services.async_register(
            DOMAIN,
            SVC_UPLOAD_SVG,
            _async_upload_svg,
            schema=vol.Schema(
                {
                    vol.Required("filename"): cv.string,
                    vol.Required("svg_text"): cv.string,
                    vol.Optional("set_as_active", default=True): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SYNC_AREAS):
        hass.services.async_register(
            DOMAIN,
            SVC_SYNC_AREAS,
            _async_sync_areas,
            schema=vol.Schema(
                {
                    vol.Optional("project_json"): cv.string,
                    vol.Optional("create_areas", default=True): cv.boolean,
                    vol.Optional("dry_run", default=False): cv.boolean,
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_STORE_PROJECT):
        hass.services.async_register(
            DOMAIN,
            SVC_STORE_PROJECT,
            _async_store_project,
            schema=vol.Schema(
                {
                    vol.Required("project_json"): cv.string,
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SEED_STUDIO):
        hass.services.async_register(
            DOMAIN,
            SVC_SEED_STUDIO,
            _async_seed_studio,
            schema=vol.Schema(
                {
                    vol.Optional("floors"): {cv.string: cv.string},
                    vol.Optional("project_json"): cv.string,
                    vol.Optional("staging", default=True): cv.boolean,
                    vol.Optional("marker_size", default=20): cv.positive_int,
                    vol.Optional("name"): cv.string,
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_COMBINE_FLOORS):
        hass.services.async_register(
            DOMAIN,
            SVC_COMBINE_FLOORS,
            _async_combine_floors,
            schema=vol.Schema(
                {
                    vol.Optional("gap", default=120): vol.Coerce(float),
                    vol.Optional("sources"): [cv.string],
                    vol.Optional("editor"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_ZONE_TOGGLE):
        hass.services.async_register(
            DOMAIN,
            SVC_ZONE_TOGGLE,
            _async_zone_toggle,
            # ALLOW_EXTRA: ha-floorplan's call-service injects the
            # rule's own entity_id into service_data automatically —
            # it is ignored; toggles carry the payload.
            schema=vol.Schema(
                {
                    vol.Optional("toggles"): [
                        {
                            vol.Required("class"): cv.string,
                            vol.Required("elements"): [cv.string],
                        }
                    ],
                    # hfs overlay path: the caller knows only what was
                    # tapped; the zone resolves server-side
                    vol.Optional("device_id"): cv.string,
                    vol.Optional("entity"): cv.string,
                    vol.Optional("entity_id"): cv.string,
                    vol.Optional("clear", default=False): cv.boolean,
                },
                extra=vol.ALLOW_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_DEVICE_VIEW):
        hass.services.async_register(
            DOMAIN,
            SVC_DEVICE_VIEW,
            _async_device_view,
            schema=vol.Schema(
                {
                    vol.Optional("device_id"): cv.string,
                    vol.Optional("entity"): cv.string,
                    vol.Optional("card"): cv.string,
                    # ha-floorplan injects entity_id (see zone_toggle)
                    vol.Optional("entity_id"): cv.string,
                },
                extra=vol.ALLOW_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_RESET):
        hass.services.async_register(
            DOMAIN,
            SVC_RESET,
            _async_reset,
            schema=vol.Schema({vol.Optional("editor"): str}, extra=vol.PREVENT_EXTRA),
            supports_response=SupportsResponse.OPTIONAL,
        )

    _LOGGER.info("Registered floorplan_helper services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister floorplan helper services."""
    for service in (
        SVC_EXPORT,
        SVC_SET_ELEMENT,
        SVC_SET_ICON,
        SVC_ASSIGN_AREA,
        SVC_SET_SVG,
        SVC_IMPORT,
        SVC_UPLOAD_SVG,
        SVC_SYNC_AREAS,
        SVC_SEED_STUDIO,
        SVC_COMBINE_FLOORS,
        SVC_RESET,
        SVC_ZONE_TOGGLE,
        SVC_DEVICE_VIEW,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


__all__ = ["async_setup_services", "async_unload_services", "notify_export"]
