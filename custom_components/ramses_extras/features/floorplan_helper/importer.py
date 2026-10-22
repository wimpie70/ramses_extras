"""Floorplan YAML importer — pure parsing for ``floorplan_import``.

Turns pasted floorplan YAML (floorplan-editor output, a full
``type: custom:floorplan-card`` config, a dashboard ``views:`` fragment,
or a bare rules list) into the stored mapping: rules carrying both an
element and an entity become ``element_bindings``; everything else is
kept verbatim in global ``extra_rules`` so it is re-emitted inside the
managed block on the next export.

Kept hass-free so it is unit-testable.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from .const import DEVICE_VIEW_SERVICE, ZONE_TOGGLE_SERVICE, is_generated_rule
from .svg_utils import slugify, xml_id, xml_text

_MISSING = object()

# Keys that mark a dict as a floorplan rule (vs. a view/card container).
_RULE_KEYS = frozenset(
    {
        "entity",
        "entities",
        "element",
        "elements",
        "state_action",
        "tap_action",
        "hold_action",
        "double_tap_action",
        "hover_action",
        "long_press_action",
        "service",
        "services",
    }
)


def _looks_like_rules(items: list[Any]) -> bool:
    """True when ``items`` is a list of dicts with at least one rule key."""
    return all(isinstance(item, dict) for item in items) and any(
        _RULE_KEYS & item.keys() for item in items
    )


def _find_rules_list(node: Any, depth: int = 0) -> list[Any] | None:
    """Locate the floorplan rules list inside a parsed YAML structure.

    Checks the known shapes first (card config, dashboard views, bare
    list) and falls back to a bounded recursive search for a ``rules``
    key holding a list of rule dicts.
    """
    if depth > 6 or node is None:
        return None
    if isinstance(node, list):
        if node and _looks_like_rules(node):
            return node
        for item in node:
            found = _find_rules_list(item, depth + 1)
            if found is not None:
                return found
        return None
    if isinstance(node, dict):
        rules = node.get("rules", _MISSING)
        if isinstance(rules, list) and (not rules or _looks_like_rules(rules)):
            # An explicit empty `rules:` key is a valid (empty) import.
            return rules
        for key in ("config", "cards", "views"):
            child = node.get(key)
            if child is not None:
                found = _find_rules_list(child, depth + 1)
                if found is not None:
                    return found
    return None


def _as_list(value: Any) -> list[str]:
    """Normalise a scalar-or-list YAML value into a string list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def parse_floorplan_yaml(text: str) -> dict[str, Any]:
    """Parse pasted floorplan YAML into bindings + verbatim rules.

    :param text: YAML text — card config, dashboard view, or rules list
    :return: ``{bindings: {element_id: {"entity_id": ...}},
        extra_rules: [rule dicts], warnings: [str]}`` — on failure
        ``{"error": str}``.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        return {"error": f"Invalid YAML: {err}"}
    if data is None:
        return {"error": "Empty input"}

    rules = _find_rules_list(data)
    if rules is None:
        return {"error": "No rules list found in the pasted YAML"}

    bindings: dict[str, dict[str, Any]] = {}
    extra_rules: list[dict[str, Any]] = []
    warnings: list[str] = []

    for rule in rules:
        elements = _as_list(rule.get("element") or rule.get("elements"))
        entities = _as_list(rule.get("entity") or rule.get("entities"))
        if elements and entities:
            # Record the binding so generated rules target the same
            # element on re-export.
            for element_id in elements:
                bindings.setdefault(element_id, {"entity_id": entities[0]})
            if len(entities) > 1:
                warnings.append(
                    f"{elements[0]}: rule binds {len(entities)} entities; "
                    f"stored binding uses {entities[0]}"
                )
        if is_generated_rule(rule):
            # Generated rules are rebuilt from the model/options on
            # every export — storing them would accumulate stale copies
            # that shadow the regenerated ones (e.g. old ${} class
            # expressions). Skip the verbatim copy.
            continue
        extra_rules.append(dict(rule))

    return {
        "bindings": bindings,
        "extra_rules": extra_rules,
        "warnings": warnings,
    }


def _point_in_polygon(x: float, y: float, polygon: list[dict[str, float]]) -> bool:
    """Ray-casting point-in-polygon test on studio ``{x, y}`` points."""
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = float(polygon[i]["x"]), float(polygon[i]["y"])
        xj, yj = float(polygon[j]["x"]), float(polygon[j]["y"])
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polygon_area(polygon: list[dict[str, float]]) -> float:
    """Shoelace area — used to pick the most specific overlapping room."""
    area = 0.0
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = float(polygon[i]["x"]), float(polygon[i]["y"])
        xj, yj = float(polygon[j]["x"]), float(polygon[j]["y"])
        area += (xj + xi) * (yj - yi)
    return abs(area) / 2


def parse_studio_project(text: str) -> dict[str, Any]:
    """Parse a floorplan-studio project export (JSON) for area syncing.

    :param text: project JSON as produced by studio's Projects → Export
    :return: ``{rooms: [{id, name, polygon, floor}],
        markers: [{x, y, entities, floor}], warnings: [str]}`` — on
        failure ``{"error": str}``
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        return {"error": f"Invalid JSON: {err}"}
    if not isinstance(data, dict) or not isinstance(data.get("floors"), list):
        return {"error": "Not a floorplan-studio project (missing 'floors')"}

    rooms: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    warnings: list[str] = []
    for floor in data["floors"]:
        floor_name = str(floor.get("name") or floor.get("id") or "?")
        for room in floor.get("rooms", []):
            polygon = room.get("polygon")
            if not isinstance(polygon, list) or len(polygon) < 3:
                warnings.append(
                    f"{floor_name}: room '{room.get('name')}' has no polygon"
                )
                continue
            rooms.append(
                {
                    "id": room.get("id"),
                    "name": str(room.get("name") or room.get("id")),
                    "polygon": polygon,
                    "area": _polygon_area(polygon),
                    "floor": floor_name,
                    "area_id": room.get("areaId") or None,
                }
            )
        for marker in floor.get("markers", []):
            markers.append(
                {
                    "x": float(marker.get("x", 0)),
                    "y": float(marker.get("y", 0)),
                    "entities": _as_list(marker.get("entities")),
                    "floor": floor_name,
                }
            )
    return {"rooms": rooms, "markers": markers, "warnings": warnings}


def room_for_point(
    rooms: list[dict[str, Any]], x: float, y: float, floor: str | None = None
) -> dict[str, Any] | None:
    """Return the smallest room containing ``(x, y)``.

    Overlapping fills are common (a base 'overloop' fill spanning the
    floor) — smallest containing polygon is the most specific room.
    Floors share the same coordinate space, so ``floor`` must be passed
    to avoid a marker matching a same-shaped room on another storey.
    """
    containing = [
        r
        for r in rooms
        if (floor is None or r["floor"] == floor)
        and _point_in_polygon(x, y, r["polygon"])
    ]
    if not containing:
        return None
    return min(containing, key=lambda r: r["area"])


# ---------------------------------------------------------------------------
# Emitting studio projects (HA → map direction): extract rooms from a user
# SVG and seed a project JSON with markers pre-placed at room centroids.
# ---------------------------------------------------------------------------

_IDENT = (1, 0, 0, 1, 0, 0)


def _compose(t1: tuple, t2: tuple) -> tuple:
    """Compose two affine matrices (a,b,c,d,e,f); result = t1 * t2."""
    a1, b1, c1, d1, e1, f1 = t1
    a2, b2, c2, d2, e2, f2 = t2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(t: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = t
    return a * x + c * y + e, b * x + d * y + f


def _parse_transform(spec: str | None) -> tuple:
    m: tuple = _IDENT
    if not spec:
        return m
    for op, args in re.findall(r"(translate|matrix|scale)\(([^)]*)\)", spec):
        vals = [float(v) for v in re.split(r"[,\s]+", args.strip()) if v]
        t: tuple[float, ...]
        if op == "translate":
            t = (1.0, 0.0, 0.0, 1.0, vals[0], vals[1] if len(vals) > 1 else 0.0)
        elif op == "scale":
            t = (
                vals[0],
                0.0,
                0.0,
                vals[1] if len(vals) > 1 else vals[0],
                0.0,
                0.0,
            )
        else:
            t = tuple(vals[:6])
        m = _compose(m, t)
    return m


def _centroid(polygon: list[dict[str, float]]) -> tuple[float, float]:
    return (
        sum(float(p["x"]) for p in polygon) / len(polygon),
        sum(float(p["y"]) for p in polygon) / len(polygon),
    )


def svg_viewbox(svg_text: str) -> tuple[float, float]:
    """Return ``(width, height)`` from the viewBox, or a sane default."""
    m = re.search(r'viewBox="[^"]*?\s([\d.]+)\s([\d.]+)"', svg_text)
    if not m:
        return 800.0, 600.0
    return float(m.group(1)), float(m.group(2))


def rooms_from_svg(svg_text: str) -> list[dict[str, Any]]:
    """Extract ``id="area.<slug>"`` rect/polygon elements as room polygons.

    Ancestor ``translate``/``matrix``/``scale`` transforms are applied so
    coordinates land in viewBox space (= studio document space when the
    floor canvas is set to the viewBox size).
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return []

    rooms: list[dict[str, Any]] = []

    def walk(el: ET.Element, t: tuple) -> None:
        t = _compose(t, _parse_transform(el.get("transform")))
        tag = el.tag.rsplit("}", 1)[-1]
        el_id = el.get("id", "")
        if el_id.startswith("area.") and tag in ("rect", "polygon"):
            slug = el_id[5:]
            pts: list[dict[str, float]] = []
            if tag == "rect":
                x = float(el.get("x") or 0)
                y = float(el.get("y") or 0)
                w = float(el.get("width") or 0)
                h = float(el.get("height") or 0)
                pts = [
                    {"x": round(px, 2), "y": round(py, 2)}
                    for px, py in (
                        _apply(t, cx, cy)
                        for cx, cy in (
                            (x, y),
                            (x + w, y),
                            (x + w, y + h),
                            (x, y + h),
                        )
                    )
                ]
            else:
                raw = re.split(r"[,\s]+", (el.get("points") or "").strip())
                nums = [float(v) for v in raw if v]
                pts = [
                    {"x": round(px, 2), "y": round(py, 2)}
                    for px, py in (
                        _apply(t, nums[i], nums[i + 1])
                        for i in range(0, len(nums) - 1, 2)
                    )
                ]
            if len(pts) >= 3:
                xs = [p["x"] for p in pts]
                ys = [p["y"] for p in pts]
                rooms.append(
                    {
                        "slug": slug,
                        "name": slug.replace("_", " "),
                        "polygon": pts,
                        "centroid": _centroid(pts),
                        "class": el.get("class") or "",
                        "area": (max(xs) - min(xs)) * (max(ys) - min(ys)),
                    }
                )
        for child in el:
            walk(child, t)

    walk(root, _IDENT)
    return rooms


def build_studio_project(
    name: str,
    floors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Wrap studio ``Floor`` dicts into an importable project JSON."""
    import time
    import uuid

    now = int(time.time() * 1000)
    return {
        "schemaVersion": 1,
        "id": uuid.uuid4().hex[:10],
        "name": name,
        "createdAt": now,
        "updatedAt": now,
        "activeFloorId": floors[0]["id"] if floors else "",
        "floors": floors,
        "settings": {"grid": 20, "snapGrid": False, "snapAngle": True},
    }


def studio_floor(
    name: str,
    width: float,
    height: float,
    rooms: list[dict[str, Any]],
    markers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one studio ``Floor`` dict (empty background, all layers on)."""
    import uuid

    return {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "canvas": {"width": width, "height": height},
        "background": {
            "dataUri": None,
            "naturalW": width,
            "naturalH": height,
            "x": 0,
            "y": 0,
            "scale": 1,
            "rotation": 0,
            "opacity": 1,
            "locked": False,
        },
        "layers": {
            layer: {"visible": True, "locked": False}
            for layer in ("background", "walls", "rooms", "entities", "labels")
        },
        "walls": [],
        "openings": [],
        "rooms": [
            {
                "id": uuid.uuid4().hex[:8],
                "name": r["name"],
                "polygon": r["polygon"],
                "areaId": r["slug"],
                "fill": "#3b82f6",
                "opacity": 0.25,
                "stateRules": [],
                "actions": {
                    "tap": {"kind": "none"},
                    "hold": {"kind": "none"},
                    "double": {"kind": "none"},
                },
            }
            for r in rooms
        ],
        "markers": markers,
    }


def studio_marker(
    entity_id: str,
    x: float,
    y: float,
    icon: str,
    label: str | None = None,
    size: int = 20,
    actions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one studio ``Marker`` (icon type, more-info tap action)."""
    import uuid

    return {
        "id": uuid.uuid4().hex[:8],
        "x": round(x, 1),
        "y": round(y, 1),
        "entities": [entity_id],
        # keeps studio's own rule export bound to the same element ids
        # our generated rules target (elementId wins over the
        # marker_<id> fallback for multi-entity markers)
        "elementId": entity_id,
        "style": {
            "type": "icon",
            "icon": icon,
            "color": "#ffc107",
            "size": size,
            "showState": True,
            **({"label": label} if label else {}),
        },
        "stateRules": [],
        "actions": actions
        or {
            "tap": {"kind": "more-info"},
            "hold": {"kind": "none"},
            "double": {"kind": "none"},
        },
        "visibility": None,
    }


def studio_actions_for_device(
    dev: dict[str, Any],
    zones: dict[str, Any],
    toggles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Marker ``actions`` to write when seeding.

    Everything here is expressed with studio-native action kinds, so
    the marker's right panel shows the real semantics and studio's own
    ha-floorplan export emits working actions — the project stays the
    single source of truth. The service calls are the bridges our
    frontend module handles (see ``const.ZONE_TOGGLE_SERVICE`` /
    ``DEVICE_VIEW_SERVICE``); the rule generator regenerates them from
    live config at export, so a stale ``serviceData`` here can never
    drift the behaviour.
    """
    device_id = str(dev.get("device_id") or "")
    if device_id and device_id in (zones or {}):
        return {
            "tap": {
                "kind": "call-service",
                "service": ZONE_TOGGLE_SERVICE,
                **(
                    {"serviceData": yaml.safe_dump({"toggles": toggles})}
                    if toggles
                    else {}
                ),
            },
            "hold": {"kind": "more-info"},
            "double": {
                "kind": "call-service",
                "service": DEVICE_VIEW_SERVICE,
                "serviceData": yaml.safe_dump(
                    {
                        "device_id": device_id,
                        "entity": dev.get("primary_entity") or "",
                    }
                ),
            },
        }
    return {
        "tap": {"kind": "more-info"},
        "hold": {"kind": "none"},
        "double": {"kind": "none"},
    }


def studio_marker_zone(marker: dict[str, Any], zone: dict[str, Any] | None) -> None:
    """Write (or clear) the zone config on a studio marker.

    ``marker.ramsesZone`` is unknown to studio, which is the point —
    it round-trips untouched through import/edit/export, so the zone
    definition lives *in the project* instead of in our options.
    """
    if zone:
        marker["ramsesZone"] = zone
    else:
        marker.pop("ramsesZone", None)


# ---------------------------------------------------------------------------
# Server-side project storage — the canonical "current" studio project
# (written by floorplan_store_project; read when services get no
# project_json). Timestamped copies go alongside for history.
# ---------------------------------------------------------------------------

PROJECT_LATEST_NAME = "latest.json"


def _projects_dir(hass: Any) -> Path:
    path = Path(hass.config.path("ramses_extras/floorplan/projects"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_project(hass: Any, project_json: str) -> str:
    """Write a timestamped copy of a studio project for backup/history."""
    from homeassistant.util import dt as dt_util

    stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
    path = _projects_dir(hass) / f"project-{stamp}.json"
    path.write_text(project_json, "utf-8")
    return str(path)


def store_latest_project(hass: Any, project_json: str) -> str:
    """Write/overwrite the canonical latest studio project."""
    latest = _projects_dir(hass) / PROJECT_LATEST_NAME
    latest.write_text(project_json, "utf-8")
    return str(latest)


def load_latest_project(hass: Any) -> str | None:
    """Return the stored studio project text, or None if none stored."""
    latest = Path(hass.config.path("ramses_extras/floorplan/projects")) / (
        PROJECT_LATEST_NAME
    )
    try:
        return latest.read_text("utf-8")
    except OSError:
        return None


def project_backups(hass: Any) -> list[str]:
    """Timestamped project backups, newest first (text, unread skipped)."""
    out: list[str] = []
    for path in sorted(_projects_dir(hass).glob("project-*.json"), reverse=True):
        try:
            out.append(path.read_text("utf-8"))
        except OSError:
            continue
    return out


def studio_marker_positions(
    project: dict[str, Any], floor_name: str | None = None
) -> dict[str, dict[str, Any]]:
    """Map entity_id → marker position/style from a studio project.

    :param project: parsed project dict (``{"floors": [...]}``)
    :param floor_name: when given, only markers on that floor are read
    :return: ``{entity_id: {"x", "y", "size", "icon", "color", "label",
        "show_state", "actions", "state_rules", "visibility",
        "ramses_zone", "ramses_caption", "entities", "glyph", "ring",
        "opacity", "element_id", "floor"}}``

    The project is the single source of truth: ``actions`` /
    ``ramsesZone`` / ``state_rules`` / style extras come straight from
    the marker so studio edits are honoured by the rule generator —
    our tweaks only cover what studio can't express. ``ramsesZone``,
    ``ramsesCaption`` and ``style.glyph/ring/opacity`` are our own
    keys; studio round-trips unknown fields untouched.
    """
    positions: dict[str, dict[str, Any]] = {}
    for floor in project.get("floors") or []:
        fname = str(floor.get("name") or floor.get("id") or "")
        if floor_name is not None and fname != floor_name:
            continue
        for marker in floor.get("markers") or []:
            style = marker.get("style") or {}
            for entity_id in marker.get("entities") or []:
                positions.setdefault(
                    str(entity_id),
                    {
                        "x": float(marker.get("x") or 0),
                        "y": float(marker.get("y") or 0),
                        "size": float(style.get("size") or 20),
                        "icon": style.get("icon"),
                        "color": style.get("color"),
                        "label": style.get("label"),
                        "show_state": style.get("showState", True),
                        "actions": marker.get("actions") or {},
                        "state_rules": marker.get("stateRules") or [],
                        "visibility": marker.get("visibility"),
                        "ramses_zone": marker.get("ramsesZone"),
                        "ramses_caption": marker.get("ramsesCaption"),
                        "entities": list(marker.get("entities") or []),
                        "glyph": style.get("glyph"),
                        "ring": style.get("ring"),
                        "opacity": style.get("opacity"),
                        "element_id": marker.get("elementId"),
                        "floor": fname,
                    },
                )
    return positions


def best_floor_for_svg(project: dict[str, Any], svg_text: str) -> dict[str, Any] | None:
    """Pick the project floor whose room names match the SVG's area ids.

    Floors share the same canvas coordinate space, so marker positions
    only make sense for the floor the SVG was seeded from. Scores each
    floor by how many of its room names appear as ``id="area.<slug>"``
    in the SVG; falls back to the floor with the most markers.
    """

    def slug(name: Any) -> str:
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(name).lower())).strip(
            "_"
        )

    area_ids = set(re.findall(r'id="area\.([^"]+)"', svg_text))
    floors = project.get("floors") or []
    best: dict[str, Any] | None = None
    best_score = -1
    for floor in floors:
        score = sum(
            1 for room in floor.get("rooms") or [] if slug(room.get("name")) in area_ids
        )
        if score > best_score:
            best, best_score = floor, score
    if best is None and floors:
        best = max(floors, key=lambda f: len(f.get("markers") or []))
    return best


def dedupe_rooms(rooms: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Collapse same-room duplicates into one entry.

    Earlier merges appended an area-bound clone of a room that already
    existed name-bound (``areaId`` and ``name`` keyed differently), so
    a floor may carry two entries per name — studio shows overlapping
    polygons and export consumers disagree about which copy wins.
    The first entry is the base (its authored fill/opacity/etc. win);
    later copies only fill missing fields (a seeded clone's
    ``areaId`` grafts onto the original).
    """
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for room in rooms or []:
        key = slugify(str(room.get("areaId") or room.get("name") or ""))
        if not key:
            out.append(room)
            continue
        base = by_key.get(key)
        if base is None:
            by_key[key] = room
            out.append(room)
            continue
        for field, value in room.items():
            base.setdefault(field, value)
    return out


def studio_room_fills(rooms: list[dict[str, Any]] | None) -> dict[str, str]:
    """Map slugified room key → ``fill`` for a floor's studio rooms.

    Room fill is the colour studio owns (the inspector edits it), so
    zone highlights derive their colour from it instead of keeping a
    separate zone colour. Keyed by slugified ``name`` — the same key
    ``area.<slug>`` elements and zone ``areas`` entries resolve to —
    plus the room's ``areaId`` when set.
    """
    fills: dict[str, str] = {}
    for room in rooms or []:
        fill = room.get("fill")
        if not fill:
            continue
        if room.get("name"):
            fills.setdefault(slugify(str(room["name"])), str(fill))
        if room.get("areaId"):
            fills.setdefault(str(room["areaId"]), str(fill))
    return fills


# ---------------------------------------------------------------------------
# Side-by-side floor combining — one drawing, one studio floor
# ---------------------------------------------------------------------------


_SVG_NS = "http://www.w3.org/2000/svg"


def _svg_parse(svg_text: str) -> ET.Element:
    """Parse an SVG, registering its namespaces so serialisation keeps
    the original prefixes (inkscape's ``sodipodi:`` etc.).

    The SVG namespace itself stays the *default* prefix — a source that
    declares ``xmlns:svg=`` would otherwise serialise as ``<svg:svg>``,
    which downstream ``</svg>`` splices (and some renderers) choke on.
    """
    import io

    for _, ns in ET.iterparse(io.BytesIO(svg_text.encode()), events=["start-ns"]):
        prefix, uri = str(ns[0] or ""), str(ns[1])
        if uri != _SVG_NS:
            ET.register_namespace(prefix, uri)
    ET.register_namespace("", _SVG_NS)
    return ET.fromstring(svg_text)


def _strip_generated(svg_root: ET.Element) -> None:
    """Remove elements we regenerate at export (``floorplan.*`` ids —
    stale toolbars/markers baked into earlier merged SVGs)."""
    for parent in svg_root.iter():
        for el in list(parent):
            if str(el.get("id") or "").startswith("floorplan."):
                parent.remove(el)


def _rename_ids(root: ET.Element, taken: set[str], prefix: str) -> list[str]:
    """Rename ``id`` collisions in ``root``'s subtree (and fix the
    ``url(#id)``/``href``/``xlink:href`` references inside it)."""
    renamed: list[str] = []
    mapping: dict[str, str] = {}
    for el in root.iter():
        el_id = el.get("id")
        if el_id and el_id in taken:
            new = f"{prefix}.{el_id}"
            mapping[el_id] = new
            el.set("id", new)
            renamed.append(el_id)
        elif el_id:
            taken.add(el_id)
    if not mapping:
        return renamed
    for el in root.iter():
        for attr, value in el.attrib.items():
            new_value = value
            for old, new in mapping.items():
                new_value = new_value.replace(f"url(#{old})", f"url(#{new})")
                if new_value == f"#{old}":
                    new_value = f"#{new}"
            if new_value != value:
                el.set(attr, new_value)
    return renamed


def combine_svgs(
    svg_texts: list[tuple[str, str]], gap: float = 120.0
) -> tuple[str, list[float], list[str]]:
    """Merge per-floor SVGs into one drawing laid out left→right.

    Floor N's content is wrapped in ``<g id="floor.<name>"
    transform="translate(off,0)">`` — ``rooms_from_svg`` composes
    ancestor transforms, so room centroids land in the combined
    viewBox (= studio canvas) space. All floors should share the same
    scale (equal viewBox sizes strongly suggested). Colliding element
    ids are renamed ``<floor>.<id>`` (references rewritten); generated
    ``floorplan.*`` elements are stripped — export re-injects them.

    :param svg_texts: ``[(floor_name, svg_text), …]`` in left→right order
    :param gap: px of breathing room between floors
    :return: ``(merged_svg, offsets, warnings)`` — ``offsets[i]`` is the
        x-shift applied to floor *i*, for translating project contents
    """
    warnings: list[str] = []
    boxes = [svg_viewbox(t) for _, t in svg_texts]
    if len({round(h) for _, h in boxes}) > 1:
        warnings.append(
            "Floor heights differ — floors are top-aligned, "
            "shorter ones leave empty space below"
        )
    offsets: list[float] = []
    off = 0.0
    for w, _ in boxes:
        offsets.append(off)
        off += w + gap
    width, height = off - gap, max(h for _, h in boxes)

    merged = _svg_parse(svg_texts[0][1])
    _strip_generated(merged)
    seen: set[str] = {str(el.get("id")) for el in merged.iter() if el.get("id")}
    for (name, text), off_i in zip(svg_texts[1:], offsets[1:], strict=True):
        root = _svg_parse(text)
        _strip_generated(root)
        renamed = _rename_ids(root, seen, name)
        if renamed:
            warnings.append(
                f"Floor '{name}': {len(renamed)} colliding ids renamed → {name}.<id>"
            )
        group = ET.Element(
            f"{{{_SVG_NS}}}g",
            {"id": f"floor.{name}", "transform": f"translate({off_i:g},0)"},
        )
        group.extend(list(root))
        merged.append(group)
    merged.set("viewBox", f"0 0 {width:g} {height:g}")
    return ET.tostring(merged, encoding="unicode"), offsets, warnings


def merge_project_floors(
    project: dict[str, Any], offsets: list[float], width: float, height: float
) -> dict[str, Any]:
    """Fold a multi-floor project into a single side-by-side floor.

    Floor *i*'s rooms/markers/walls are shifted right by ``offsets[i]``
    — matching :func:`combine_svgs` — so studio positions stay aligned
    with the merged SVG. Backgrounds compose horizontally when they
    carry PNG ``dataUri``s at scale 1 / rotation 0 (see
    :func:`compose_backgrounds`); otherwise floor 1's background wins.

    :return: the same project dict, mutated to a single floor
    """
    floors = list(project.get("floors") or [])
    if len(floors) < 2:
        return project
    merged = dict(floors[0])
    merged["name"] = str(project.get("name") or floors[0].get("name") or "All floors")
    merged["canvas"] = {"width": width, "height": height}

    for i, floor in enumerate(floors[1:], start=1):
        off = offsets[i] if i < len(offsets) else offsets[-1]
        for room in floor.get("rooms") or []:
            for pt in room.get("polygon") or []:
                pt["x"] = round(float(pt.get("x") or 0) + off, 2)
        for wall in floor.get("walls") or []:
            for pt in wall.get("points") or []:
                pt["x"] = round(float(pt.get("x") or 0) + off, 2)
        for marker in floor.get("markers") or []:
            marker["x"] = round(float(marker.get("x") or 0) + off, 2)
        merged.setdefault("rooms", []).extend(floor.get("rooms") or [])
        merged.setdefault("walls", []).extend(floor.get("walls") or [])
        merged.setdefault("openings", []).extend(floor.get("openings") or [])
        merged.setdefault("markers", []).extend(floor.get("markers") or [])

    merged["background"] = _compose_backgrounds(floors, offsets, width, height)
    project["floors"] = [merged]
    project["activeFloorId"] = merged["id"]
    return project


def _compose_backgrounds(
    floors: list[dict[str, Any]], offsets: list[float], width: float, height: float
) -> dict[str, Any]:
    """Horizontally compose per-floor PNG backgrounds (Pillow).

    Falls back to floor 1's background (with the combined canvas as
    natural size) when Pillow is unavailable or a floor uses a
    rotation/non-image background.
    """
    import base64
    import io

    fallback = dict(floors[0].get("background") or {})
    fallback["naturalW"], fallback["naturalH"] = width, height
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:  # pragma: no cover - Pillow ships with HA
        return fallback

    canvas = Image.new("RGBA", (max(1, int(width)), max(1, int(height))), (0, 0, 0, 0))
    composed = False
    for i, floor in enumerate(floors):
        bg = floor.get("background") or {}
        uri = str(bg.get("dataUri") or "")
        if "base64," not in uri or bg.get("rotation"):
            continue
        try:
            img = Image.open(
                io.BytesIO(base64.b64decode(uri.split("base64,", 1)[1]))
            ).convert("RGBA")
        except Exception:  # noqa: BLE001 - un-decodable image
            continue
        # the dataUri may be higher-res than the displayed size —
        # studio renders it at naturalW/H × scale, so composite at
        # that size or the bottom/right gets clipped
        scale = float(bg.get("scale") or 1)
        target = (
            max(1, int(float(bg.get("naturalW") or img.width) * scale)),
            max(1, int(float(bg.get("naturalH") or img.height) * scale)),
        )
        if img.size != target:
            img = img.resize(target)
        opacity = float(bg.get("opacity") or 1)
        if opacity < 1:
            alpha = img.getchannel("A").point(lambda a, o=opacity: int(a * o))
            img.putalpha(alpha)
        canvas.alpha_composite(
            img,
            (
                int(offsets[i] + float(bg.get("x") or 0)),
                int(float(bg.get("y") or 0)),
            ),
        )
        composed = True
    if not composed:
        return fallback
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return {
        **fallback,
        "dataUri": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
    }


def project_drawing_svg(floor: dict[str, Any]) -> str | None:
    """Render a studio floor as the drawing SVG our merge consumes.

    The project is the single source of truth — the drawing is rebuilt
    from it on every export instead of merged from an authored file,
    matching floorplan-studio's own export: the floor's background
    image stretched over the canvas, one ``area.<slug(name)>`` path per
    room (the element ids ``resolve_bound``/zone toggles target) with
    the studio fill/opacity, and a centroid room label. Marker/badge
    groups arrive later via ``build_overlay_fragment``; authored walls
    and fixtures live in the background image already.

    :return: SVG text, or ``None`` when the floor has no usable canvas
    """
    canvas = floor.get("canvas") or {}
    try:
        width = float(canvas.get("width") or 0)
        height = float(canvas.get("height") or 0)
    except TypeError, ValueError:
        return None
    if width <= 0 or height <= 0:
        return None

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">'
    ]
    bg = floor.get("background") or {}
    if bg.get("dataUri"):
        parts.append(
            f'<image href="{xml_text(bg["dataUri"])}" x="0" y="0" '
            f'width="{width:g}" height="{height:g}" '
            f'opacity="{float(bg.get("opacity") or 1):g}"/>'
        )

    for room in floor.get("rooms") or []:
        pts = [
            (float(p["x"]), float(p["y"]))
            for p in (room.get("polygon") or [])
            if isinstance(p, dict) and "x" in p and "y" in p
        ]
        if len(pts) < 3:
            continue
        area_id = f"area.{slugify(room.get('name'))}"
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts) + " Z"
        parts.append(
            f'<path id="{xml_id(area_id)}" class="room" d="{d}" '
            f'fill="{_room_fill(room)}" stroke="rgba(255,255,255,0.3)" '
            f'stroke-width="1"/>'
        )
        name = str(room.get("name") or "")
        if name:
            cx = sum(x for x, _ in pts) / len(pts)
            cy = sum(y for _, y in pts) / len(pts)
            parts.append(
                f'<text id="{xml_id(area_id)}__label" class="room-label" '
                f'x="{cx:g}" y="{cy:g}" font-family="sans-serif" '
                f'font-size="16" font-weight="600" fill="#fff" '
                f'text-anchor="middle" pointer-events="none" '
                f'paint-order="stroke" stroke="rgba(0,0,0,.55)" '
                f'stroke-width="3">{xml_text(name)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _room_fill(room: dict[str, Any]) -> str:
    """``fill`` value for a project room — rgba() for 6-digit hexes."""
    fill = str(room.get("fill") or "").strip()
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", fill)
    if not m:
        return "none"
    n = int(m.group(1), 16)
    opacity = float(room.get("opacity") or 0.25)
    return f"rgba({(n >> 16) & 255},{(n >> 8) & 255},{n & 255},{opacity:g})"


__all__ = [
    "PROJECT_LATEST_NAME",
    "backup_project",
    "best_floor_for_svg",
    "build_studio_project",
    "combine_svgs",
    "dedupe_rooms",
    "merge_project_floors",
    "load_latest_project",
    "parse_floorplan_yaml",
    "parse_studio_project",
    "project_backups",
    "project_drawing_svg",
    "room_for_point",
    "rooms_from_svg",
    "store_latest_project",
    "studio_actions_for_device",
    "studio_floor",
    "studio_marker",
    "studio_marker_positions",
    "studio_room_fills",
    "studio_marker_zone",
    "svg_viewbox",
]
