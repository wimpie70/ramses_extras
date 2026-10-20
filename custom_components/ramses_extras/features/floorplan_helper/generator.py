"""Floorplan bundle generator.

Produces everything the ha-floorplan card consumes:

- ``ramses-elements.svg`` — a working default floorplan: devices laid
  out in a grid grouped by HA area (topology group when no area), each
  element named after its primary entity so rules auto-bind. Also
  serves as the symbol sheet — copy ``<g>`` elements into a custom
  building SVG and they keep working.
- ``ramses-floorplan-card.yaml`` — a paste-ready
  ``type: custom:floorplan-card`` config with the managed rules block
  wrapped in BEGIN/END markers.
- A change report (``changes``) diffed against the previous export's
  stored snapshot.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...const import INTEGRATION_DIR
from .const import (
    CARD_YAML_STEM,
    DEFAULT_EDITOR_URL,
    DEFAULT_ICON,
    DEFAULT_PLANNER_URL,
    FEATURE_ID,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_GENERATED_BASE,
    FLOORPLAN_GENERATED_DIR_NAME,
    FLOORPLAN_ICON_MDI,
    FLOORPLAN_ICONS,
    FLOORPLAN_STATIC_BASE,
    GENERATED_CARD_YAML,
    GENERATED_ELEMENTS_SVG,
    OPTION_AREA_OVERRIDES,
    OPTION_BACKGROUND,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_DEVICE_VIEW_URL,
    OPTION_DEVICE_ZONES,
    OPTION_EDITOR_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_ICON_OVERRIDES,
    OPTION_LAST_SNAPSHOT,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    RULES_BEGIN_MARKER,
    RULES_END_MARKER,
    STYLESHEET_FILENAME,
    SVG_MODE_CUSTOM,
    TOOLBAR_ELEMENT_EDITOR,
    TOOLBAR_ELEMENT_EXPORT,
    TOOLBAR_ELEMENT_IMPORT,
    TOOLBAR_ELEMENT_PLANNER,
    TOOLBAR_ELEMENT_UPLOAD,
)
from .importer import (
    best_floor_for_svg,
    load_latest_project,
    rooms_from_svg,
    studio_marker_positions,
)
from .mapping import (
    get_floorplan_options,
    model_snapshot,
    persist_floorplan_options,
    snapshot_diff,
)
from .topology import build_floorplan_model

_LOGGER = logging.getLogger(__name__)

_ICONS_DIR = (
    INTEGRATION_DIR
    / "features"
    / "floorplan_helper"
    / "www"
    / "floorplan_helper"
    / "icons"
)

_SVG_PATH_RE = re.compile(r'\bd="([^"]+)"')

# Grid layout constants for the generated elements SVG.
_COLS = 4
_CELL_W = 220
_CELL_H = 96
_GROUP_PAD_X = 40
_GROUP_PAD_Y = 56
_GROUP_GAP = 48
_ICON_SIZE = 24

# Role → rule templates emitted inside the managed block. ``{entity}`` and
# ``{element}`` placeholders are filled per element. Templates mirror the
# floorplan docs' class_set/text_set services.
_ROLE_RULE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "status": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${entity.state === "on" ? "rx-online" : "rx-offline"}')
                },
            }
        }
    ],
    "heat_demand": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${Number(entity.state) > 0 ? "rx-heat-demand" : ""}')
                },
            }
        }
    ],
    "window_open": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${entity.state === "on" ? "rx-window-open" : ""}')
                },
            }
        }
    ],
    "fan_rate": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": (
                        '${["high","boost"].includes('
                        'String(entity.state).toLowerCase()) ? "rx-spin" : ""}'
                    )
                },
            }
        }
    ],
    "temperature": [
        {
            "state_action": {
                "service": "floorplan.text_set",
                "service_data": {"text": "${entity.state}"},
            }
        }
    ],
}


def _binding_maps(
    options: dict[str, Any],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Resolve element bindings into lookup maps.

    Bindings may be keyed by the bound entity id or by a custom element
    id carrying ``entity_id`` — either way the device's output targets
    the bound element.

    :return: ``(entity_id → element_id, entity_id → binding)``
    """
    bindings: dict[str, Any] = options.get(OPTION_ELEMENT_BINDINGS, {}) or {}
    entity_element_map: dict[str, str] = {}
    entity_binding_map: dict[str, dict[str, Any]] = {}
    for element_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        entity_id = binding.get("entity_id")
        if entity_id:
            entity_element_map.setdefault(entity_id, element_id)
            entity_binding_map.setdefault(entity_id, binding)
        else:
            entity_binding_map.setdefault(element_id, binding)
    return entity_element_map, entity_binding_map


def _element_id_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the SVG element id a device's rules/elements target."""
    entity_element_map, _ = _binding_maps(options)
    primary = device.get("primary_entity")
    if not primary:
        return f"device.{device['device_id']}"
    return str(entity_element_map.get(primary, primary))


def _icon_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the icon key for a device.

    Precedence: per-entity override → per-class override → element
    binding icon → device-class default table → DEFAULT_ICON.
    """
    overrides: dict[str, str] = options.get(OPTION_ICON_OVERRIDES, {}) or {}
    bindings: dict[str, Any] = options.get(OPTION_ELEMENT_BINDINGS, {}) or {}
    primary = device.get("primary_entity")
    device_class = device.get("device_class") or ""

    if primary and primary in overrides:
        return overrides[primary]
    if device_class in overrides:
        return overrides[device_class]
    if primary:
        # A binding may be keyed by the entity id itself or by a custom
        # element id carrying an entity_id — check both.
        for element_id, binding in bindings.items():
            if element_id != primary and (
                not isinstance(binding, dict) or binding.get("entity_id") != primary
            ):
                continue
            if isinstance(binding, dict) and binding.get("icon"):
                return str(binding["icon"])
    return FLOORPLAN_DEVICE_ICON_MAP.get(device_class, DEFAULT_ICON)


def _apply_area_overrides(model: dict[str, Any], options: dict[str, Any]) -> None:
    """Mutate device area assignment per user overrides."""
    overrides: dict[str, str] = options.get(OPTION_AREA_OVERRIDES, {}) or {}
    if not overrides:
        return
    areas = model.get("areas", {})
    for dev in model.get("devices", []):
        area = overrides.get(dev["device_id"]) or overrides.get(
            dev.get("primary_entity") or ""
        )
        if area:
            dev["area_id"] = area
            dev["area_name"] = areas.get(area, {}).get("name") or area


def _load_icon_symbol(icon_key: str) -> str | None:
    """Read a shipped icon SVG and return a ``<symbol>`` definition."""
    if icon_key not in FLOORPLAN_ICONS:
        return None
    icon_path = _ICONS_DIR / f"{icon_key}.svg"
    try:
        text = icon_path.read_text(encoding="utf-8")
    except OSError as err:
        _LOGGER.warning("Could not read floorplan icon %s: %s", icon_path, err)
        return None
    paths = _SVG_PATH_RE.findall(text)
    if not paths:
        return None
    inner = "".join(f'<path d="{d}"/>' for d in paths)
    return f'<symbol id="icon.{icon_key}" viewBox="0 0 24 24">{inner}</symbol>'


def _group_devices(
    model: dict[str, Any],
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Group devices for layout.

    :return: ``[(group_key, group_label, [devices])]`` — areas first
        (sorted by floor then name), then topology groups, then
        unassigned.
    """
    areas = model.get("areas", {})
    floors = model.get("floors", {})
    groups: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for dev in model.get("devices", []):
        if dev.get("area_id"):
            key = f"area.{dev['area_id']}"
            label = dev.get("area_name") or areas.get(dev["area_id"], {}).get(
                "name", dev["area_id"]
            )
        else:
            key = f"group.{dev.get('group', 'orphan')}"
            label = str(dev.get("group", "orphan")).title()
        groups.setdefault(key, []).append(dev)
        labels[key] = label

    def sort_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, float, str]:
        key = item[0]
        if key.startswith("area."):
            area_id = key.split(".", 1)[1]
            floor_id = areas.get(area_id, {}).get("floor_id")
            level = floors.get(floor_id, {}).get("level")
            return (0, float(level if level is not None else 99), key)
        return (1, 0.0, key)

    return [(k, labels[k], v) for k, v in sorted(groups.items(), key=sort_key)]


# mdi icon name (studio marker style.icon) → our icon key — inverse of
# FLOORPLAN_ICON_MDI, so a studio marker keeps its chosen icon.
_MDI_TO_ICON_KEY = {v: k for k, v in FLOORPLAN_ICON_MDI.items()}

_VIEWBOX_RE = re.compile(r'viewBox="[^"]*?\s([\d.]+)\s+([\d.]+)"')


def _svg_viewbox_size(svg_text: str) -> tuple[float, float]:
    m = _VIEWBOX_RE.search(svg_text)
    return (float(m.group(1)), float(m.group(2))) if m else (960.0, 640.0)


# Marker presentation defaults — fill sits on the <g> so rx-* state
# classes override it; `color` feeds currentColor for captions.
DEFAULT_MARKER_COLOR = "#ffc107"
DEFAULT_TEXT_COLOR = "#334155"

# Domain-based icons for standalone zone members (non-ramses entities).
_ENTITY_DOMAIN_ICONS = {
    "cover": "pipe-valve",
    "valve": "pipe-valve",
    "sensor": "gauge",
    "binary_sensor": "thermometer",
}


def _standalone_icon(entity_id: str) -> str:
    """Icon key for a non-ramses zone member, based on entity domain."""
    return _ENTITY_DOMAIN_ICONS.get(entity_id.split(".", 1)[0], DEFAULT_ICON)


def _dock_anchor(
    svg_rooms: dict[str, dict[str, Any]], vb_w: float
) -> tuple[float, float]:
    """Anchor (row start) for the unplaced-device dock.

    Centred inside the largest ``outside``-class room when the drawing
    has one — open, non-living space (e.g. terras); otherwise a strip
    along the top-right inside edge of the canvas.
    """
    outside = [r for r in svg_rooms.values() if r.get("class") == "outside"]
    if outside:
        cx, cy = max(outside, key=lambda r: r.get("area") or 0)["centroid"]
        return cx - 3.5 * 30.0, cy
    return vb_w - 8 * 30.0 - 20.0, 44.0


def _model_entity_ids(model: dict[str, Any]) -> set[str]:
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


def _device_of_entity(model: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    """Return the model device owning ``entity_id``, or None."""
    devices: list[dict[str, Any]] = model.get("devices") or []
    for d in devices:
        if d.get("primary_entity") == entity_id:
            return d
        for e in d.get("entities") or []:
            if e.get("entity_id") == entity_id:
                return d
    return None


def build_overlay_fragment(
    model: dict[str, Any],
    options: dict[str, Any],
    positions: dict[str, dict[str, Any]],
    svg_text: str,
) -> tuple[str, list[str]]:
    """Build the marker/toolbar fragment to splice into a user SVG.

    Device markers are placed at their studio-project coordinates
    (studio canvas == SVG viewBox space); devices without a marker fall
    back to the centroid of their area's ``area.*`` element, then to a
    staging strip just below the canvas.

    :param positions: entity_id → ``{x, y, size, icon, color}`` (from
        :func:`importer.studio_marker_positions`)
    :return: ``(fragment, warnings)``
    """
    svg_rooms = {r["slug"]: r for r in rooms_from_svg(svg_text)}
    vb_w, vb_h = _svg_viewbox_size(svg_text)
    zones = options.get(OPTION_DEVICE_ZONES) or {}
    warnings: list[str] = []
    used_icons: set[str] = set()
    body: list[str] = []
    dock_x, dock_y = _dock_anchor(svg_rooms, vb_w)
    unplaced = 0

    def _dock_pos() -> tuple[float, float]:
        nonlocal unplaced
        i = unplaced
        return dock_x + (i % 8) * 30.0, dock_y + (i // 8) * 30.0

    model_devices = model.get("devices", [])
    model_entity_ids = _model_entity_ids(model)
    # standalone zone members: entity ids in a zone's devices list that
    # aren't ramses model devices (DIY valves, zigbee area sensors…).
    # One-way link — the same entity may serve several zones.
    extra_entities: list[str] = []
    for z in zones.values():
        for ent in z.get("devices") or []:
            ent = str(ent)
            if "." in ent and ent not in model_entity_ids and ent not in extra_entities:
                extra_entities.append(ent)

    for dev in model_devices:
        element_id = _xml_id(_element_id_for_device(dev, options))
        icon_key = _icon_for_device(dev, options)
        pos: dict[str, Any] | None = None
        candidates = [dev.get("primary_entity")] + [
            e.get("entity_id") for e in dev.get("entities") or []
        ]
        for ent in candidates:
            if ent and ent in positions:
                pos = positions[ent]
                break
        if pos is not None:
            icon_key = _MDI_TO_ICON_KEY.get(str(pos.get("icon")), icon_key)
            x, y, size = pos["x"], pos["y"], float(pos.get("size") or 20)
        elif dev.get("area_id") and dev["area_id"] in svg_rooms:
            x, y = svg_rooms[dev["area_id"]]["centroid"]
            size = 20.0
        else:
            # no position on this floor — park in the dock (outside
            # room / top-right strip) so the marker stays visible and
            # tappable; zone devices need that since a zone may span
            # floors, and it keeps unassigned devices in view too
            x, y = _dock_pos()
            unplaced += 1
            size = 20.0
        used_icons.add(icon_key)
        # fill on the <g> — presentation attrs lose to the rx-* state
        # classes (a use-level fill would win and break them); the
        # amber default keeps unstyled markers visible. `color` feeds
        # currentColor for the rx-state caption on the light backdrop.
        color = (pos.get("color") if pos else None) or DEFAULT_MARKER_COLOR
        body.append(
            f'<g id="{element_id}" transform="translate({x:.1f},{y:.1f})" '
            f'fill="{color}" color="{DEFAULT_TEXT_COLOR}">'
            f'<use href="#icon.{icon_key}" '
            f'x="{-size / 2:.1f}" y="{-size / 2:.1f}" '
            f'width="{size:.0f}" height="{size:.0f}"/>'
            f'<text class="rx-state" x="0" y="{size / 2 + 9:.0f}" '
            f'text-anchor="middle"></text>'
            "</g>"
        )

    for ent in extra_entities:
        pos = positions.get(ent)
        if pos is not None:
            x, y, size = pos["x"], pos["y"], float(pos.get("size") or 20)
            icon_key = _MDI_TO_ICON_KEY.get(str(pos.get("icon")), _standalone_icon(ent))
            color = pos.get("color") or DEFAULT_MARKER_COLOR
        else:
            x, y = _dock_pos()
            unplaced += 1
            size = 20.0
            icon_key, color = _standalone_icon(ent), DEFAULT_MARKER_COLOR
        used_icons.add(icon_key)
        body.append(
            f'<g id="{_xml_id(ent)}" transform="translate({x:.1f},{y:.1f})" '
            f'fill="{color}" color="{DEFAULT_TEXT_COLOR}">'
            f'<use href="#icon.{icon_key}" '
            f'x="{-size / 2:.1f}" y="{-size / 2:.1f}" '
            f'width="{size:.0f}" height="{size:.0f}"/>'
            f'<text class="rx-state" x="0" y="{size / 2 + 9:.0f}" '
            f'text-anchor="middle"></text>'
            "</g>"
        )
    if unplaced:
        warnings.append(
            f"{unplaced} device(s)/entit(ies) have no studio marker or area "
            "room on this floor — parked in the dock (outside room or "
            "top-right strip)"
        )

    # Zone highlight (toggled by the marker's tap_action rule): the class
    # swaps the room's fill for a translucent diagonal hatch in the zone
    # colour + a solid outline — clearly visible over any base fill.
    zone_css: list[str] = []
    zone_patterns: list[str] = []
    for dev in model.get("devices", []):
        z = zones.get(dev.get("device_id"))
        if not (z and (z.get("areas") or z.get("devices"))):
            continue
        color = z.get("color") or "#22c55e"
        if z.get("areas"):
            pat = f"rx-zonepat-{_slugify(str(dev.get('device_id')))}"
            zone_patterns.append(
                f'<pattern id="{pat}" width="10" height="10" '
                f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                f'<rect width="10" height="10" fill="{color}" '
                f'fill-opacity="0.12"/>'
                f'<line x1="0" y1="0" x2="0" y2="10" stroke="{color}" '
                f'stroke-opacity="0.5" stroke-width="3"/></pattern>'
            )
            zone_css.append(
                f".{_zone_class(str(dev.get('device_id')))} {{ "
                f"fill: url(#{pat}) !important; fill-opacity: 1 !important; "
                f"stroke: {color} !important; stroke-width: 3px !important; }}"
            )
        # same zone, applied to device markers — outline + glow, keep the
        # icon fill (rx-* state classes own that)
        zone_css.append(
            f".{_zone_class(str(dev.get('device_id')) + '-dev')} {{ "
            f"stroke: {color} !important; stroke-width: 3px !important; "
            f"filter: drop-shadow(0 0 5px {color}) !important; }}"
        )
    style_block = f"<style>\n{chr(10).join(zone_css)}\n</style>" if zone_css else ""

    symbols = [s for s in (_load_icon_symbol(k) for k in sorted(used_icons)) if s]
    parts = [
        *([style_block] if style_block else []),
        "<defs>",
        *symbols,
        *zone_patterns,
        "</defs>",
        '<g id="floorplan.markers">',
        *body,
        "</g>",
    ]
    if (
        options.get(OPTION_TOOLBAR_ENABLED, True)
        and "floorplan.toolbar" not in svg_text
    ):
        tx = max(0.0, vb_w - 5 * 34 - 8)
        ty = max(0.0, vb_h - 32)
        parts.append(
            f'<g transform="translate({tx:.0f},{ty:.0f})">{build_toolbar_svg()}</g>'
        )
    return "\n".join(parts), warnings


def _slugify(value: Any) -> str:
    return re.sub(
        r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(value or "").lower())
    ).strip("_")


def _zone_class(device_id: str) -> str:
    """CSS class toggled on zone rooms when the device marker is tapped."""
    return f"rx-zone-{_slugify(device_id)}"


_AREA_ELEMENT_RE = re.compile(
    r"<(?:rect|polygon|path|circle|ellipse|g)\b[^>]*?\bid=\"area\.([a-z0-9_]+)\""
    r"[^>]*?>",
    re.S,
)


def apply_room_styles(svg_text: str, rooms: list[dict[str, Any]] | None) -> str:
    """Patch ``area.<slug>`` elements with the studio room fill/opacity.

    Writes an inline ``style`` attribute — presentation attributes would
    lose to the SVG's embedded ``.room`` class rules, and an injected
    ``<style>`` block with escaped-dot selectors isn't honoured by every
    SVG consumer. Studio is the source of truth for room appearance.
    """
    by_slug: dict[str, dict[str, Any]] = {}
    for room in rooms or []:
        slug = _slugify(room.get("name"))
        if slug and (room.get("fill") or room.get("opacity") is not None):
            by_slug[slug] = room
    if not by_slug:
        return svg_text

    def repl(m: re.Match[str]) -> str:
        room = by_slug.get(m.group(1))
        if not room:
            return m.group(0)
        decl = []
        if room.get("fill"):
            decl.append(f"fill:{room['fill']}")
        if room.get("opacity") is not None:
            decl.append(f"fill-opacity:{room['opacity']}")
        extra = "; ".join(decl)
        tag = m.group(0)
        if 'style="' in tag:
            return re.sub(
                r'style="([^"]*)"',
                lambda sm: f'style="{sm.group(1).rstrip(";")}; {extra}"',
                tag,
                count=1,
            )
        if tag.endswith("/>"):
            return f'{tag[:-2]} style="{extra}"/>'
        return f'{tag[:-1]} style="{extra}">'

    return _AREA_ELEMENT_RE.sub(repl, svg_text)


def merge_svg_overlay(svg_text: str, fragment: str) -> str:
    """Splice an overlay fragment into an SVG document before ``</svg>``."""
    idx = svg_text.rfind("</svg>")
    if idx == -1:
        return svg_text + "\n" + fragment
    return svg_text[:idx] + fragment + "\n" + svg_text[idx:]


def build_elements_svg(model: dict[str, Any], options: dict[str, Any]) -> str:
    """Render the generated elements SVG.

    :param model: floorplan topology model
    :param options: merged floorplan options
    :return: SVG document text
    """
    groups = _group_devices(model)
    icon_keys = {
        _icon_for_device(dev, options) for _, _, devs in groups for dev in devs
    }
    symbols = [sym for sym in (_load_icon_symbol(k) for k in sorted(icon_keys)) if sym]

    parts: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 960 640">',
        "<defs>",
        *symbols,
        "</defs>",
        '<g id="floorplan">',
    ]

    y = _GROUP_PAD_Y
    for group_key, label, devs in groups:
        parts.append(f'<g id="{_xml_id(group_key)}">')
        parts.append(
            f'<text class="rx-group-label" x="{_GROUP_PAD_X}" '
            f'y="{y}">{_xml_text(label)}</text>'
        )
        row_y = y + 16
        for idx, dev in enumerate(devs):
            col = idx % _COLS
            row = idx // _COLS
            x = _GROUP_PAD_X + col * _CELL_W
            cy = row_y + row * _CELL_H
            element_id = _element_id_for_device(dev, options)
            icon_key = _icon_for_device(dev, options)
            parts.append(
                f'<g id="{_xml_id(element_id)}" '
                f'transform="translate({x},{cy})">'
                f'<rect class="rx-cell" width="{_CELL_W - 16}" '
                f'height="{_CELL_H - 16}" rx="8"/>'
                f'<use href="#icon.{icon_key}" '
                f'xlink:href="#icon.{icon_key}" x="12" y="14" '
                f'width="{_ICON_SIZE}" height="{_ICON_SIZE}"/>'
                f'<text class="rx-label" x="44" y="30">'
                f"{_xml_text(_short_label(dev))}</text>"
                f'<text class="rx-state" x="44" y="52"></text>'
                "</g>"
            )
        rows = (len(devs) + _COLS - 1) // _COLS
        y = row_y + rows * _CELL_H + _GROUP_GAP
        parts.append("</g>")

    if options.get(OPTION_TOOLBAR_ENABLED, True):
        parts.append(f'<g transform="translate(770,605)">{build_toolbar_svg()}</g>')

    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts)


def _short_label(dev: dict[str, Any]) -> str:
    name = str(dev.get("display_name") or dev["device_id"])
    return name if len(name) <= 24 else name[:22] + "…"


def _xml_id(raw: str) -> str:
    """Sanitize a string for use as an SVG element id."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(raw))


def _xml_text(raw: str) -> str:
    return str(raw).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_rules(
    model: dict[str, Any], options: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the managed floorplan rules list.

    Element bindings may be keyed by the bound entity id or by a custom
    element id carrying ``entity_id`` — either way the device's rules
    target the bound element.
    """
    _, entity_binding_map = _binding_maps(options)
    zones = options.get(OPTION_DEVICE_ZONES) or {}

    rules: list[dict[str, Any]] = []
    for dev in model.get("devices", []):
        primary = dev.get("primary_entity")
        element_id = _element_id_for_device(dev, options)

        for ent in dev.get("entities", []):
            templates = _ROLE_RULE_TEMPLATES.get(ent.get("role") or "")
            if not templates:
                continue
            for template in templates:
                rule: dict[str, Any] = {"entity": ent["entity_id"]}
                if ent["entity_id"] != element_id:
                    rule["element"] = element_id
                rule.update(deepcopy(template))
                if ent["entity_id"] != primary:
                    # every rule bound to the element fires its tap_action;
                    # suppress it here so the primary-entity rule below is
                    # the one more-info opens ("none" is a no-op action)
                    rule["tap_action"] = {"action": "none"}
                rules.append(rule)

        if primary:
            # tap the marker → more-info on the device's own entity
            # (climate dialog for a FAN), not a secondary stat sensor;
            # zoned devices get tap = highlight served rooms instead,
            # keep the entity dialog on hold
            tap_rule: dict[str, Any] = {"entity": primary}
            if primary != element_id:
                tap_rule["element"] = element_id
            zone = zones.get(dev.get("device_id")) or {}
            area_ids = [a for a in zone.get("areas") or [] if a]
            # markers of devices bound to this device get the same
            # treatment — binding comes from the ramses schema
            # (remotes/sensors under the FAN = parent link), not from
            # which room they sit in; gateways/HGI excluded (they serve
            # the whole house, not a zone). Extra device ids or plain
            # entity ids (non-ramses DIY/zigbee members) can be added
            # via the zone's "devices" list — a one-way link, so the
            # same entity may serve several zones.
            bound_ids = {
                str(d.get("device_id"))
                for d in model.get("devices", [])
                if d.get("parent") == dev.get("device_id")
                and d.get("device_class") != "HGI"
            }
            bound_ids.update(str(b) for b in zone.get("devices") or [])
            bound_ids.add(str(dev.get("device_id")))
            bound = [
                _element_id_for_device(d, options)
                for d in model.get("devices", [])
                if str(d.get("device_id")) in bound_ids
                and d.get("device_class") != "HGI"
            ]
            # entity-id entries (a member entity of a model device, or
            # a non-ramses zone member) map to the owning device's
            # element, or land on their own marker rendered for them
            for b in sorted(bound_ids):
                if "." not in b or b in bound:
                    continue
                owner = _device_of_entity(model, b)
                if owner is not None:
                    if owner.get("device_class") == "HGI":
                        continue
                    el = _element_id_for_device(owner, options)
                else:
                    el = b
                if el not in bound:
                    bound.append(el)
            if area_ids or (zone.get("devices") and bound):
                device_id = str(dev.get("device_id"))
                toggles: list[dict[str, Any]] = []
                if area_ids:
                    toggles.append(
                        {
                            "class": _zone_class(device_id),
                            "elements": [f"area.{_slugify(a)}" for a in area_ids],
                        }
                    )
                if bound:
                    toggles.append(
                        {
                            "class": _zone_class(f"{device_id}-dev"),
                            "elements": bound,
                        }
                    )
                zone_actions: list[dict[str, Any]] = [
                    {
                        "action": "call-service",
                        "service": "floorplan.class_toggle",
                        "service_data": t,
                    }
                    for t in toggles
                ]
                # floorplan.* actions are scoped to the card that fired
                # them — broadcast the same toggles so the module-level
                # listener applies them to every other floorplan card on
                # the dashboard too (a zone may span floors)
                zone_actions.append(
                    {
                        "action": "fire-dom-event",
                        "ramses_zone_sync": toggles,
                    }
                )
                tap_rule["tap_action"] = zone_actions
                tap_rule["hold_action"] = {"action": "more-info"}
                view_url = options.get(OPTION_DEVICE_VIEW_URL) or ""
                if view_url:
                    # self-contained: navigate to a view with the device
                    # card — no listener card needed on this dashboard
                    tap_rule["double_tap_action"] = {
                        "action": "navigate",
                        "navigation_path": view_url,
                    }
                else:
                    tap_rule["double_tap_action"] = {
                        "action": "fire-dom-event",
                        # picked up by the ramses-floorplan-actions module
                        # (loaded as a Lovelace resource → works on any
                        # view) to open the device popup
                        "ramses_device_id": dev.get("device_id"),
                        "ramses_entity": primary,
                        "ramses_card": "hvac-fan"
                        if dev.get("device_class") in ("FAN", "HVAC")
                        else "",
                    }
            else:
                tap_rule["tap_action"] = {"action": "more-info"}
            rules.append(tap_rule)

        binding = entity_binding_map.get(primary or "")
        if isinstance(binding, dict):
            rules.extend(_parse_extra_rules(binding.get("extra_rules")))

    # Standalone zone members (non-ramses entities like DIY valves or
    # zigbee sensors listed in a zone's devices) get a plain more-info
    # on tap; their marker is rendered by build_overlay_fragment.
    model_entities = _model_entity_ids(model)
    standalone: set[str] = set()
    for z in zones.values():
        for ent in z.get("devices") or []:
            ent = str(ent)
            if "." in ent and ent not in model_entities:
                standalone.add(ent)
    for ent in sorted(standalone):
        rules.append({"entity": ent, "tap_action": {"action": "more-info"}})

    # Global extra rules appended last.
    rules.extend(_parse_extra_rules(options.get(OPTION_EXTRA_RULES)))
    rules.extend(_build_toolbar_rules(options))
    return rules


def _link_action(target: str) -> dict[str, Any]:
    """Build a tap_action opening ``target``.

    Internal paths (leading ``/``) navigate inside HA; anything else is
    an external URL opened in a new tab.
    """
    if str(target).startswith("/"):
        return {"action": "navigate", "navigation_path": target}
    return {"action": "url", "url_path": target}


def _build_toolbar_rules(options: dict[str, Any]) -> list[dict[str, Any]]:
    """Rules for the in-SVG toolbar glyphs (see :func:`build_toolbar_svg`).

    Emitted inside the managed block so bindings stay managed; harmless
    for SVGs that don't contain the toolbar elements.
    """
    if not options.get(OPTION_TOOLBAR_ENABLED, True):
        return []
    domain_action = "ramses_extras"
    return [
        {
            "element": TOOLBAR_ELEMENT_EXPORT,
            "tap_action": {
                "action": "call-service",
                "service": f"{domain_action}.floorplan_export",
            },
        },
        {
            "element": TOOLBAR_ELEMENT_IMPORT,
            "tap_action": {
                "action": "navigate",
                "navigation_path": (
                    f"/developer-tools/action?action={domain_action}.floorplan_import"
                ),
            },
        },
        {
            "element": TOOLBAR_ELEMENT_UPLOAD,
            "tap_action": {
                "action": "navigate",
                "navigation_path": (
                    "/developer-tools/action?"
                    f"action={domain_action}.floorplan_upload_svg"
                ),
            },
        },
        {
            "element": TOOLBAR_ELEMENT_EDITOR,
            "tap_action": _link_action(
                options.get(OPTION_EDITOR_URL) or DEFAULT_EDITOR_URL
            ),
        },
        {
            "element": TOOLBAR_ELEMENT_PLANNER,
            "tap_action": _link_action(
                options.get(OPTION_PLANNER_URL) or DEFAULT_PLANNER_URL
            ),
        },
    ]


def build_toolbar_svg() -> str:
    """Return the toolbar ``<g>`` snippet — paste once into a custom SVG.

    Five 26px glyph buttons spaced 34px apart, styled via the
    ``rx-toolbar*`` classes in ramses-floorplan.css. Wrap coordinates
    with a ``transform="translate(x,y)"`` to position it.
    """
    glyphs = (
        (TOOLBAR_ELEMENT_EXPORT, "↻"),
        (TOOLBAR_ELEMENT_IMPORT, "⇣"),
        (TOOLBAR_ELEMENT_UPLOAD, "⇡"),
        (TOOLBAR_ELEMENT_EDITOR, "⛓"),
        (TOOLBAR_ELEMENT_PLANNER, "✎"),
    )
    parts = ['<g id="floorplan.toolbar">']
    for idx, (element_id, glyph) in enumerate(glyphs):
        x = idx * 34
        parts.append(
            f'<g id="{element_id}" class="rx-toolbar-btn" '
            f'transform="translate({x},0)">'
            f'<rect class="rx-toolbar-bg" width="26" height="26" rx="4"/>'
            f'<text class="rx-toolbar-glyph" x="13" y="18">{glyph}</text>'
            "</g>"
        )
    parts.append("</g>")
    return "\n".join(parts)


def _parse_extra_rules(raw: Any) -> list[dict[str, Any]]:
    """Parse extra_rules entries (dicts or YAML blobs) into rule dicts."""
    rules: list[dict[str, Any]] = []
    for extra in raw or []:
        parsed: Any = None
        if isinstance(extra, dict):
            parsed = deepcopy(extra)
        elif isinstance(extra, str):
            try:
                parsed = yaml.safe_load(extra)
            except yaml.YAMLError:
                parsed = None
        if isinstance(parsed, dict):
            rules.append(parsed)
    return rules


def _custom_svg_refs(options: dict[str, Any]) -> list[str]:
    """Normalize ``custom_svg_path`` — a single path or a list (one per
    floor — each gets its own ``<stem>.merged.svg`` on export)."""
    raw = options.get(OPTION_CUSTOM_SVG_PATH)
    if isinstance(raw, str):
        raw = [raw]
    return [str(r) for r in (raw or []) if r]


async def _build_merged_svg(
    hass: HomeAssistant,
    model: dict[str, Any],
    options: dict[str, Any],
    ref: str,
) -> tuple[str | None, list[str], str | None]:
    """Splice device markers + toolbar into the user's custom SVG.

    Marker positions come from the stored studio project (latest.json),
    read from the floor whose room names match the SVG's ``area.*`` ids.

    :return: ``(merged filename, warnings, merged SVG text or None)``
    """
    if ref.startswith("/local/"):
        src = Path(hass.config.config_dir) / "www" / ref[len("/local/") :]
    else:
        src = (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / "floorplan"
            / Path(ref).name
        )

    def _read() -> str | None:
        try:
            return src.read_text(encoding="utf-8")
        except OSError:
            return None

    svg_text = await hass.async_add_executor_job(_read)
    if svg_text is None:
        return (
            None,
            [f"Custom SVG not readable: {ref} — image left unchanged"],
            None,
        )

    # Inkscape drawings are authored on a transparent page — without a
    # backdrop the HA theme shows through and translucent room fills
    # render dark. The rect goes first so any drawing elements stay on
    # top (namedview/defs render nothing, so position is irrelevant).
    background = str(options.get(OPTION_BACKGROUND) or "")
    if background:
        svg_text = re.sub(
            r"<svg\b[^>]*>",
            rf'\g<0><rect id="rx.background" width="100%" height="100%" '
            f'fill="{background}"/>',
            svg_text,
            count=1,
        )

    positions: dict[str, dict[str, Any]] = {}
    rooms: list[dict[str, Any]] | None = None
    warnings: list[str] = []
    project_json = await hass.async_add_executor_job(load_latest_project, hass)
    project: dict[str, Any] | None = None
    if project_json:
        try:
            project = json.loads(project_json)
        except json.JSONDecodeError:
            project = None
    if project:
        floor = best_floor_for_svg(project, svg_text)
        if floor:
            rooms = floor.get("rooms") or []
        positions = studio_marker_positions(
            project, str(floor.get("name")) if floor else None
        )
    else:
        warnings.append("No stored studio project — markers placed at area centroids")

    fragment, frag_warnings = build_overlay_fragment(
        model, options, positions, svg_text
    )
    warnings.extend(frag_warnings)
    # Studio room fill/opacity win over the SVG's embedded .room classes —
    # patch the elements' inline style directly (survives every consumer,
    # unlike a <style> block with escaped-id selectors).
    svg_text = apply_room_styles(svg_text, rooms)
    return f"{src.stem}.merged.svg", warnings, merge_svg_overlay(svg_text, fragment)


def _build_card_yaml(
    rules: list[dict[str, Any]],
    options: dict[str, Any],
    image_path: str | None = None,
) -> str:
    """Render the paste-ready floorplan card config.

    The generated rules sit inside BEGIN/END markers so a re-export can
    replace just that block; user rules outside the markers survive.
    """
    svg_mode = options.get(OPTION_SVG_MODE, "generated")
    if image_path is None:
        if svg_mode == SVG_MODE_CUSTOM and _custom_svg_refs(options):
            image_path = _custom_svg_refs(options)[0]
        else:
            image_path = f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}"

    card = {
        "type": "custom:floorplan-card",
        "config": {
            "image": {"location": image_path, "cache": False},
            "stylesheet": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
            "defaults": {"hover_action": "hover-info", "tap_action": "more-info"},
            # rules must stay the last config key — the END marker is
            # appended after it.
            "rules": rules,
        },
    }

    # no aliases — shared dicts (zone toggles reused as service_data and
    # in ramses_zone_sync) must render as repeated blocks, not anchors
    class _NoAliasDumper(yaml.Dumper):
        def ignore_aliases(self, data: Any) -> bool:
            return True

    text = yaml.dump(
        card,
        sort_keys=False,
        default_flow_style=False,
        Dumper=_NoAliasDumper,
    )

    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("  rules:"):
            out.append(f"  {RULES_BEGIN_MARKER}")
        out.append(line)
    out.append(f"  {RULES_END_MARKER}")
    return "\n".join(out) + "\n"


async def _write_generated_files(
    hass: HomeAssistant, files: dict[str, str]
) -> list[str]:
    """Write generated files under <config>/www/ramses_extras/floorplan/generated/.

    :return: list of ``/local/...`` URLs written
    """
    out_dir = (
        Path(hass.config.config_dir)
        / "www"
        / "ramses_extras"
        / FLOORPLAN_GENERATED_DIR_NAME
    )

    def _write() -> list[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, content in files.items():
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(f"{FLOORPLAN_GENERATED_BASE}/{name}")
        return written

    written: list[str] = await hass.async_add_executor_job(_write)
    return written


async def _floorplan_resource_present(hass: HomeAssistant) -> bool:
    """Check whether a floorplan.js lovelace resource is registered."""
    store: Store[dict[str, Any]] = Store(hass, 1, "lovelace_resources")
    try:
        data = await store.async_load()
    except Exception:  # noqa: BLE001
        return False
    for item in (data or {}).get("items", []):
        if "floorplan" in str(item.get("url", "")).lower():
            return True
    return False


async def async_generate_bundle(
    hass: HomeAssistant, config_entry: Any
) -> dict[str, Any]:
    """Generate the complete floorplan bundle.

    Writes generated files, persists the new model snapshot, and
    returns everything a caller needs to finish setup.

    :param hass: Home Assistant instance
    :param config_entry: Integration config entry
    :return: ``{card_yaml, rules, files_written, changes, warnings}``
    """
    model = await build_floorplan_model(hass)
    options = get_floorplan_options(config_entry)
    _apply_area_overrides(model, options)

    rules = _build_rules(model, options)
    svg_text = build_elements_svg(model, options)

    files: dict[str, str] = {}
    warnings: list[str] = []
    merged_names: list[str] = []
    if options.get(OPTION_SVG_MODE) == SVG_MODE_CUSTOM:
        # custom_svg_path may list one SVG per floor — each is merged
        # against the matching project floor and gets its own card yaml
        for ref in _custom_svg_refs(options):
            merged_name, merged_warnings, merged_text = await _build_merged_svg(
                hass, model, options, ref
            )
            warnings.extend(merged_warnings)
            if merged_text is not None and merged_name:
                files[merged_name] = merged_text
                merged_names.append(merged_name)

    # One card yaml per merged floor; the un-suffixed file keeps the
    # first floor for backwards compatibility.
    card_yamls: dict[str, str] = {}
    for i, merged_name in enumerate(merged_names):
        stem = Path(merged_name).stem.removesuffix(".merged")
        yml = _build_card_yaml(
            rules, options, f"{FLOORPLAN_GENERATED_BASE}/{merged_name}"
        )
        card_yamls[stem] = yml
        files[GENERATED_CARD_YAML if i == 0 else f"{CARD_YAML_STEM}-{stem}.yaml"] = yml
    if not card_yamls:
        card_yamls["default"] = _build_card_yaml(rules, options)

    card_yaml = next(iter(card_yamls.values()))
    files[GENERATED_ELEMENTS_SVG] = svg_text
    files.setdefault(GENERATED_CARD_YAML, card_yaml)

    files_written = await _write_generated_files(hass, files)

    new_snapshot = model_snapshot(model)
    previous = options.get(OPTION_LAST_SNAPSHOT) or {}
    changes = snapshot_diff(previous, new_snapshot)
    options[OPTION_LAST_SNAPSHOT] = new_snapshot
    persist_floorplan_options(hass, config_entry, options)

    if not await _floorplan_resource_present(hass):
        warnings.append(
            "No floorplan.js lovelace resource detected — install "
            "ha-floorplan via HACS before adding the card."
        )

    return {
        "card_yaml": card_yaml,
        "card_yamls": card_yamls,
        "rules": rules,
        "elements_svg_url": f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}",
        "stylesheet_url": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
        "toolbar_svg": build_toolbar_svg(),
        "files_written": files_written,
        "changes": changes,
        "warnings": warnings,
    }


__all__ = [
    "async_generate_bundle",
    "build_elements_svg",
    "build_overlay_fragment",
    "build_toolbar_svg",
    "merge_svg_overlay",
]
