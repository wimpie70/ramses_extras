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
import re
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .bundle import async_generate_bundle
from .const import (
    DEFAULT_ICON,
    FEATURE_ID,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_ICON_MDI,
    FLOORPLAN_ICONS,
    FLOORPLAN_UPLOAD_DIR_NAME,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_DEVICE_ZONES,
    OPTION_EDITOR_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
    is_generated_rule,
)
from .importer import (
    backup_project,
    build_studio_project,
    load_latest_project,
    parse_floorplan_yaml,
    parse_studio_project,
    room_for_point,
    rooms_from_svg,
    store_latest_project,
    studio_floor,
    studio_marker,
    svg_viewbox,
)
from .mapping import (
    get_floorplan_options,
    persist_floorplan_options,
    set_area_override,
    set_device_zone,
    set_element_binding,
    set_icon_override,
    set_svg_mode,
)
from .markers import build_toolbar_svg, strip_toolbar
from .topology import build_floorplan_model

_LOGGER = logging.getLogger(__name__)

SVC_EXPORT = "floorplan_export"
SVC_SET_ELEMENT = "floorplan_set_element"
SVC_SET_ICON = "floorplan_set_icon"
SVC_ASSIGN_AREA = "floorplan_assign_area"
SVC_SET_DEVICE_ZONE = "floorplan_set_device_zone"
SVC_SET_SVG = "floorplan_set_svg"
SVC_IMPORT = "floorplan_import"
SVC_UPLOAD_SVG = "floorplan_upload_svg"
SVC_SYNC_AREAS = "floorplan_sync_areas"
SVC_SEED_STUDIO = "floorplan_seed_studio"
SVC_STORE_PROJECT = "floorplan_store_project"

# Canonical server-side location for the "current" studio project
# (written by floorplan_store_project; read when services get no
# project_json). Timestamped copies go alongside for history.
PROJECT_LATEST_NAME = "latest.json"

NOTIFICATION_ID = "ramses_extras_floorplan_export"

_TOOLBAR_W = 5 * 34  # five 26px buttons spaced 34px


def _inject_toolbar(svg_text: str, options: dict[str, Any] | None = None) -> str:
    """Append the toolbar ``<g>`` before ``</svg>``, placed bottom-right.

    Position derives from the viewBox when present; falls back to a fixed
    offset matching the generated SVG's 800-wide canvas.
    """
    x, y = 770.0, 605.0
    m = re.search(r'viewBox="[^"]*?\s([\d.]+)\s([\d.]+)"', svg_text)
    if m:
        vb_w, vb_h = float(m.group(1)), float(m.group(2))
        x = max(0, vb_w - _TOOLBAR_W - 8)
        y = max(0, vb_h - 32)
    snippet = f'<g transform="translate({x:g},{y:g})">{build_toolbar_svg(options)}</g>'
    if "</svg>" in svg_text:
        return svg_text.replace("</svg>", snippet + "\n</svg>", 1)
    return svg_text + "\n" + snippet


def _backup_project(hass: HomeAssistant, project_json: str) -> str:
    """Write a timestamped copy of a studio project for backup/history."""
    return backup_project(hass, project_json)


def _store_latest_project(hass: HomeAssistant, project_json: str) -> str:
    """Write/overwrite the canonical latest studio project."""
    return store_latest_project(hass, project_json)


def _load_latest_project(hass: HomeAssistant) -> str:
    """Return the stored studio project, or raise if none was stored."""
    text = load_latest_project(hass)
    if text is None:
        raise vol.Invalid(
            "No stored studio project — pass project_json or store one "
            "first (floorplan_store_project / the actions card drop zone)"
        )
    return text


def _merge_studio_project(
    existing: dict[str, Any],
    floors_json: list[dict[str, Any]],
    staging: bool,
    extra_markers: list[dict[str, Any]],
    mdi: Any,
    marker_size: int = 20,
) -> dict[str, Any]:
    """Merge generated floors into an existing studio project.

    Floors match by name; rooms are added when missing (by name);
    markers whose entity is already present anywhere in the project are
    skipped (user's own placement wins). ``extra_markers`` are devices
    without a matching room — parked in a strip below the first floor's
    canvas so they can be dragged into place.
    """
    project = dict(existing)
    project["floors"] = list(existing.get("floors") or [])
    by_name = {str(f.get("name", "")).lower(): f for f in project["floors"]}

    def _placed_entities() -> set[str]:
        return {
            e
            for f in project["floors"]
            for m in f.get("markers", [])
            for e in (m.get("entities") or [])
        }

    for new_floor in floors_json:
        floor = by_name.get(str(new_floor["name"]).lower())
        if floor is None:
            project["floors"].append(new_floor)
            by_name[str(new_floor["name"]).lower()] = new_floor
            continue
        have_rooms = {str(r.get("name", "")).lower() for r in floor.get("rooms", [])}
        floor.setdefault("rooms", []).extend(
            r for r in new_floor["rooms"] if str(r["name"]).lower() not in have_rooms
        )
        have_entities = _placed_entities()
        floor.setdefault("markers", []).extend(
            m
            for m in new_floor["markers"]
            if not (set(m.get("entities") or []) & have_entities)
        )

    if staging and project["floors"]:
        first = project["floors"][0]
        height = float(first.get("canvas", {}).get("height") or 560)
        have_entities = _placed_entities()
        x = 30.0
        for dev in extra_markers:
            primary = dev.get("primary_entity")
            if not primary or primary in have_entities:
                continue
            first.setdefault("markers", []).append(
                studio_marker(
                    primary,
                    x,
                    height + 30,
                    mdi(dev),
                    label=str(dev.get("display_name") or dev["device_id"]),
                    size=marker_size,
                )
            )
            x += 44
    return project


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


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register floorplan helper services."""

    async def _async_export(call: ServiceCall) -> dict[str, Any]:
        """Regenerate the floorplan bundle and return it."""
        bundle = await async_generate_bundle(hass, _config_entry(hass))
        notify_export(hass, bundle)
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
        return {
            "device_id": device_id,
            "zone": section.get(OPTION_DEVICE_ZONES, {}).get(device_id),
            "removed": remove,
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
        extra[:] = [rule for rule in extra if not is_generated_rule(rule)]
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

        # External tools (e.g. floorplan-studio) rebuild the SVG from their
        # own model, so our toolbar elements are lost — re-inject them
        # bottom-right so the export/import/upload round-trip survives.
        # An existing toolbar is stripped first so the current button
        # set + tooltips replace any stale copy.
        section = get_floorplan_options(_config_entry(hass))
        if section.get(OPTION_TOOLBAR_ENABLED, True):
            svg_text = _inject_toolbar(strip_toolbar(svg_text), section)

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

        project_json = call.data.get("project_json") or (
            await hass.async_add_executor_job(_load_latest_project, hass)
        )
        parsed = parse_studio_project(project_json)
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))
        backup_path = await hass.async_add_executor_job(
            _backup_project, hass, project_json
        )

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
        project_json = call.data["project_json"]
        parsed = parse_studio_project(project_json)
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))
        latest = await hass.async_add_executor_job(
            _store_latest_project, hass, project_json
        )
        backup = await hass.async_add_executor_job(_backup_project, hass, project_json)
        stats: dict[str, dict[str, int]] = {}
        for room in parsed["rooms"]:
            stats.setdefault(room["floor"], {"rooms": 0, "markers": 0})["rooms"] += 1
        for marker in parsed["markers"]:
            stats.setdefault(marker["floor"], {"rooms": 0, "markers": 0})[
                "markers"
            ] += 1
        _LOGGER.info("Floorplan project stored: %s (%s)", latest, stats)
        return {"latest_path": latest, "backup_path": backup, "floors": stats}

    async def _async_seed_studio(call: ServiceCall) -> dict[str, Any]:
        """Emit a studio project JSON with markers pre-placed.

        For each floor's SVG the ``area.*`` elements become studio rooms;
        every topology device whose HA area matches a room slug gets a
        marker at that room's centroid (grid-stacked when a room holds
        several devices). Paste the returned JSON into studio's
        Projects → Import JSON.
        """
        floor_specs: dict[str, str] = dict(call.data.get("floors") or {})
        if not floor_specs:
            options = get_floorplan_options(_config_entry(hass))
            active = options.get(OPTION_CUSTOM_SVG_PATH)
            if not active:
                raise vol.Invalid("No 'floors' given and no custom SVG is active")
            floor_specs = {Path(active).stem: active}

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

        def _mdi(dev: dict[str, Any]) -> str:
            key = FLOORPLAN_DEVICE_ICON_MAP.get(
                dev.get("device_class") or "", DEFAULT_ICON
            )
            return FLOORPLAN_ICON_MDI.get(key, "help-circle")

        # Merging into an existing project preserves the background image,
        # walls and any studio edits — without it we emit a fresh project.
        existing: dict[str, Any] | None = None
        raw_project = call.data.get("project_json")
        if not raw_project:
            # Fall back to the stored project — keeps backgrounds/edits
            # when re-seeding; silently ignored if none was ever stored.
            latest_path = (
                Path(hass.config.path("ramses_extras/floorplan/projects"))
                / PROJECT_LATEST_NAME
            )
            try:
                raw_project = await hass.async_add_executor_job(
                    latest_path.read_text, "utf-8"
                )
            except OSError:
                raw_project = None
        if raw_project:
            try:
                existing = json.loads(raw_project)
            except json.JSONDecodeError:
                raise vol.Invalid("project_json is not valid JSON") from None
            if not isinstance(existing.get("floors"), list):
                raise vol.Invalid("project_json is not a studio project")

        placed: dict[str, str] = {}
        placed_entities: set[str] = set()
        floors_json: list[dict[str, Any]] = []
        floor_stats: list[dict[str, Any]] = []
        for fname, svg_text in floor_svgs.items():
            rooms = rooms_from_svg(svg_text)
            width, height = svg_viewbox(svg_text)
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
                markers.append(
                    studio_marker(
                        primary,
                        cx + (n % 3) * 36 - 36,
                        cy + (n // 3) * 36,
                        _mdi(dev),
                        label=str(dev.get("display_name") or dev["device_id"]),
                        size=marker_size,
                    )
                )
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

        if existing is not None:
            project = _merge_studio_project(
                existing,
                floors_json,
                staging=call.data.get("staging", True),
                extra_markers=unplaced,
                mdi=_mdi,
                marker_size=marker_size,
            )
        else:
            # Park devices with no matching room below the first floor's
            # canvas — drag them into a room in studio to assign the area.
            if call.data.get("staging", True) and floors_json:
                staging_markers = [
                    studio_marker(
                        dev["primary_entity"],
                        30 + i * 44,
                        float(floors_json[0]["canvas"]["height"]) + 30,
                        _mdi(dev),
                        label=str(dev.get("display_name") or dev["device_id"]),
                        size=marker_size,
                    )
                    for i, dev in enumerate(unplaced)
                ]
                floors_json[0]["markers"].extend(staging_markers)
            project = build_studio_project(
                call.data.get("name") or "Floorplan", floors_json
            )
        project_out = json.dumps(project)
        backup_path = await hass.async_add_executor_job(
            _backup_project, hass, project_out
        )
        _LOGGER.info(
            "Floorplan seed_studio: %d markers across %d floors, %d unplaced",
            len(placed),
            len(floors_json),
            len(unplaced),
        )
        return {
            "project_json": project_out,
            "backup_path": backup_path,
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

    if not hass.services.has_service(DOMAIN, SVC_EXPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_EXPORT,
            _async_export,
            schema=vol.Schema({}, extra=vol.PREVENT_EXTRA),
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
                {vol.Required("project_json"): cv.string},
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
                },
                extra=vol.PREVENT_EXTRA,
            ),
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
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


__all__ = ["async_setup_services", "async_unload_services", "notify_export"]
