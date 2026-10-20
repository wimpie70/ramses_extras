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

from .const import is_generated_rule

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
) -> dict[str, Any]:
    """Build one studio ``Marker`` (icon type, more-info tap action)."""
    import uuid

    return {
        "id": uuid.uuid4().hex[:8],
        "x": round(x, 1),
        "y": round(y, 1),
        "entities": [entity_id],
        "style": {
            "type": "icon",
            "icon": icon,
            "color": "#ffc107",
            "size": size,
            "showState": True,
            **({"label": label} if label else {}),
        },
        "stateRules": [],
        "actions": {
            "tap": {"kind": "more-info"},
            "hold": {"kind": "none"},
            "double": {"kind": "none"},
        },
        "visibility": None,
    }


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


def studio_marker_positions(
    project: dict[str, Any], floor_name: str | None = None
) -> dict[str, dict[str, Any]]:
    """Map entity_id → marker position/style from a studio project.

    :param project: parsed project dict (``{"floors": [...]}``)
    :param floor_name: when given, only markers on that floor are read
    :return: ``{entity_id: {"x", "y", "size", "icon", "label", "floor"}}``
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


__all__ = [
    "PROJECT_LATEST_NAME",
    "backup_project",
    "best_floor_for_svg",
    "build_studio_project",
    "load_latest_project",
    "parse_floorplan_yaml",
    "parse_studio_project",
    "room_for_point",
    "rooms_from_svg",
    "store_latest_project",
    "studio_floor",
    "studio_marker",
    "studio_marker_positions",
    "svg_viewbox",
]
