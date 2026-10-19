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
from typing import Any

import yaml

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
            # Keep the authored rule verbatim AND record the binding so
            # generated rules target the same element on re-export.
            extra_rules.append(dict(rule))
            for element_id in elements:
                bindings.setdefault(element_id, {"entity_id": entities[0]})
            if len(entities) > 1:
                warnings.append(
                    f"{elements[0]}: rule binds {len(entities)} entities; "
                    f"stored binding uses {entities[0]}"
                )
        else:
            # Element-less rules (entity targets its own element) and
            # entity-less rules (pure actions) are kept verbatim.
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
    rooms: list[dict[str, Any]], x: float, y: float
) -> dict[str, Any] | None:
    """Return the smallest room containing ``(x, y)``.

    Overlapping fills are common (a base 'overloop' fill spanning the
    floor) — smallest containing polygon is the most specific room.
    """
    containing = [r for r in rooms if _point_in_polygon(x, y, r["polygon"])]
    if not containing:
        return None
    return min(containing, key=lambda r: r["area"])


__all__ = [
    "parse_floorplan_yaml",
    "parse_studio_project",
    "room_for_point",
]
