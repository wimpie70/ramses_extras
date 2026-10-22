"""Marker and SVG rendering for the floorplan.

Emits the ``floorplan.markers`` overlay (positioned device markers +
zone defs + toolbar) spliced into a user's drawing, and the standalone
``ramses-elements.svg`` grid used by the generated-svg mode. Element
id / icon resolution live here too — everything that decides *what a
device looks like on the plan*.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from .const import (
    DEFAULT_EDITOR_URL,
    DEFAULT_ICON,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_ICON_MDI,
    OPTION_AREA_OVERRIDES,
    OPTION_DEVICE_ZONES,
    OPTION_EDITOR_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_ICON_OVERRIDES,
    OPTION_MARKER_STYLE_OVERRIDES,
    TOOLBAR_ELEMENT_EDITOR,
    TOOLBAR_ELEMENT_EXPORT,
    TOOLBAR_ELEMENT_UPLOAD,
    split_top_level_commas,
)
from .domains import get_domain
from .importer import _point_in_polygon, _polygon_area, _svg_parse, rooms_from_svg
from .svg_utils import (
    load_icon_symbol,
    marker_svg,
    set_element_style,
    slugify,
    strip_element,
    svg_button,
    svg_viewbox_size,
    xml_id,
    xml_text,
)
from .zones import model_entity_ids, standalone_members, zone_defs

# Grid layout constants for the generated elements SVG.
_COLS = 4
_CELL_W = 220
_CELL_H = 96
_GROUP_PAD_X = 40
_GROUP_PAD_Y = 56
_GROUP_GAP = 48
_ICON_SIZE = 24

# Marker presentation defaults — fill sits on the <g> so rx-* state
# classes override it; `color` feeds currentColor for captions.
DEFAULT_MARKER_COLOR = "#ffc107"
DEFAULT_TEXT_COLOR = "#334155"

# mdi icon name (studio marker style.icon) → our icon key — inverse of
# FLOORPLAN_ICON_MDI, so a studio marker keeps its chosen icon.
_MDI_TO_ICON_KEY = {v: k for k, v in FLOORPLAN_ICON_MDI.items()}

# Domain-based icons for standalone zone members (non-ramses entities).
_ENTITY_DOMAIN_ICONS = {
    "cover": "pipe-valve",
    "valve": "pipe-valve",
    "sensor": "gauge",
    "binary_sensor": "thermometer",
}


def binding_maps(
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


def element_id_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the SVG element id a device's rules/elements target."""
    entity_element_map, _ = binding_maps(options)
    primary = device.get("primary_entity")
    if not primary:
        return f"device.{device['device_id']}"
    return str(entity_element_map.get(primary, primary))


def icon_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the icon key for a device.

    Precedence: per-entity override → per-class override → element
    binding icon → domain default → device-class table → DEFAULT_ICON.
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
    return get_domain(device).default_icon or FLOORPLAN_DEVICE_ICON_MAP.get(
        device_class, DEFAULT_ICON
    )


def parse_marker_style(raw: Any) -> dict[str, str]:
    """Normalise a marker-style override value into ``{part: colour}``.

    Accepts the stored dict form or the config-menu string
    ``"disc:#22c55e,glyph:#fff,ring:rgba(0,0,0,0.4),opacity:0.8"``.
    Unknown parts are dropped.
    """
    if isinstance(raw, dict):
        return {p: str(v) for p, v in raw.items() if p in _STYLE_PARTS and v}
    out: dict[str, str] = {}
    for item in split_top_level_commas(str(raw or "")):
        part, _, value = item.strip().partition(":")
        if part.strip() in _STYLE_PARTS and value.strip():
            out[part.strip()] = value.strip()
    return out


_STYLE_PARTS = ("disc", "glyph", "ring", "opacity")


def marker_style_for_key(
    device: dict[str, Any], options: dict[str, Any]
) -> dict[str, str]:
    """Badge style overrides for a device — device id → class →
    primary entity, same precedence as icon/caption overrides."""
    overrides: dict[str, Any] = options.get(OPTION_MARKER_STYLE_OVERRIDES) or {}
    for key in (
        device.get("device_id"),
        device.get("device_class"),
        device.get("primary_entity"),
    ):
        if key is not None and str(key) in overrides:
            return parse_marker_style(overrides[str(key)])
    return {}


def apply_area_overrides(model: dict[str, Any], options: dict[str, Any]) -> None:
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


def group_devices(
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


def standalone_icon(entity_id: str) -> str:
    """Icon key for a non-ramses zone member, based on entity domain."""
    return _ENTITY_DOMAIN_ICONS.get(entity_id.split(".", 1)[0], DEFAULT_ICON)


def dock_anchor(
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


def short_label(dev: dict[str, Any]) -> str:
    """Compact marker caption — display_name (or device_id) trimmed."""
    name = str(dev.get("display_name") or dev["device_id"])
    return name if len(name) <= 24 else name[:22] + "…"


def marker_meta_for_device(
    dev: dict[str, Any],
    marker_meta: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Find a device's studio-marker entry in a positions map.

    Matches the marker bound to the primary entity first, then any of
    the device's entities — same lookup as the overlay placement.
    ``marker_meta`` is the value map of
    :func:`importer.studio_marker_positions`.
    """
    if not marker_meta:
        return None
    candidates = [dev.get("primary_entity")] + [
        e.get("entity_id") for e in dev.get("entities") or []
    ]
    for ent in candidates:
        if ent and ent in marker_meta:
            return marker_meta[ent]
    return None


def _studio_style(
    pos: dict[str, Any] | None, overrides: dict[str, Any]
) -> dict[str, Any]:
    """Merge studio marker style fields over menu style overrides.

    The studio project is the single source of truth: ``style.color``
    owns the badge disc, and our extra keys ``style.glyph`` /
    ``style.ring`` / ``style.opacity`` (unknown to studio, but
    round-tripped untouched) beat the option-level overrides. Menu
    overrides remain the fallback for elements without a studio
    marker.
    """
    if not pos:
        return overrides
    style = dict(overrides)
    for key in ("glyph", "ring", "opacity"):
        if pos.get(key) is not None:
            style[key] = pos[key]
    if pos.get("color"):
        style["disc"] = pos["color"]
    return style


def effective_zones(
    model: dict[str, Any],
    options: dict[str, Any],
    marker_meta: dict[str, dict[str, Any]] | None = None,
    room_fills: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Zone config, project-first.

    ``marker.ramsesZone`` in the studio project is the single source
    of truth — the ``device_zones`` option only fills in devices that
    have no marker zone yet (back-compat for pre-project zones).

    ``zone.color`` is the highlight/outline colour only — room base
    fills stay whatever studio's inspector set. When a zone has no
    explicit colour, the fill of its first studio room
    (``room_fills`` from :func:`importer.studio_room_fills`) is the
    adaptive fallback.
    """
    zones = dict(options.get(OPTION_DEVICE_ZONES) or {})
    for dev in model.get("devices") or []:
        meta = marker_meta_for_device(dev, marker_meta)
        rz = (meta or {}).get("ramses_zone")
        if isinstance(rz, dict) and dev.get("device_id"):
            zones[str(dev["device_id"])] = rz
    if room_fills:
        for dev_id, z in list(zones.items()):
            if not isinstance(z, dict) or z.get("color"):
                continue
            for area in z.get("areas") or []:
                fill = room_fills.get(slugify(str(area)))
                if fill:
                    z = dict(z)
                    z["color"] = fill
                    zones[dev_id] = z
                    break
    return zones


def build_overlay_fragment(
    model: dict[str, Any],
    options: dict[str, Any],
    positions: dict[str, dict[str, Any]],
    svg_text: str,
    room_fills: dict[str, str] | None = None,
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
    vb_w, vb_h = svg_viewbox_size(svg_text)
    zones = effective_zones(model, options, positions, room_fills)
    warnings: list[str] = []
    used_icons: set[str] = set()
    body: list[str] = []
    dock_x, dock_y = dock_anchor(svg_rooms, vb_w)
    unplaced = 0

    def _dock_pos() -> tuple[float, float]:
        nonlocal unplaced
        i = unplaced
        return dock_x + (i % 8) * 30.0, dock_y + (i // 8) * 30.0

    # standalone zone members get markers too — a one-way zone link
    # must stay reachable on the plan even when the entity isn't a
    # ramses model device (DIY valves, zigbee area sensors…)
    extra_entities = standalone_members(model, zones)

    for dev in model.get("devices", []):
        element_id = element_id_for_device(dev, options)
        icon_key = icon_for_device(dev, options)
        pos = marker_meta_for_device(dev, positions)
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
        color = (pos.get("color") if pos else None) or DEFAULT_MARKER_COLOR
        body.append(
            marker_svg(
                element_id,
                x,
                y,
                size,
                icon_key,
                # a label typed into studio wins over the generated
                # slug; it persists with the project
                label=str((pos or {}).get("label") or short_label(dev)),
                color=color,
                text_color=DEFAULT_TEXT_COLOR,
                style=_studio_style(pos, marker_style_for_key(dev, options)),
            )
        )

    for ent in extra_entities:
        pos = positions.get(ent)
        if pos is not None:
            x, y, size = pos["x"], pos["y"], float(pos.get("size") or 20)
            icon_key = _MDI_TO_ICON_KEY.get(str(pos.get("icon")), standalone_icon(ent))
            color = pos.get("color") or DEFAULT_MARKER_COLOR
        else:
            x, y = _dock_pos()
            unplaced += 1
            size = 20.0
            icon_key, color = standalone_icon(ent), DEFAULT_MARKER_COLOR
        used_icons.add(icon_key)
        body.append(
            marker_svg(
                ent,
                x,
                y,
                size,
                icon_key,
                label=str(
                    (pos or {}).get("label")
                    or short_label(
                        {"device_id": ent, "display_name": ent.split(".", 1)[-1]}
                    )
                ),
                color=color,
                text_color=DEFAULT_TEXT_COLOR,
                # standalone members have no device — entity_id is the key
                style=_studio_style(
                    pos,
                    parse_marker_style(
                        (options.get(OPTION_MARKER_STYLE_OVERRIDES) or {}).get(ent)
                    ),
                ),
            )
        )
    if unplaced:
        warnings.append(
            f"{unplaced} device(s)/entit(ies) have no studio marker or area "
            "room on this floor — parked in the dock (outside room or "
            "top-right strip)"
        )

    symbols = [s for s in (load_icon_symbol(k) for k in sorted(used_icons)) if s]
    parts = [
        zone_defs(model, zones),
        "<defs>",
        *symbols,
        "</defs>",
        '<g id="floorplan.markers">',
        *body,
        "</g>",
    ]
    return "\n".join(p for p in parts if p), warnings


def strip_toolbar(svg_text: str) -> str:
    """Remove a previously injected toolbar group (and its translate
    wrapper) so a fresh one — current button set + tooltips — can be
    re-injected."""
    return strip_element(svg_text, "floorplan.toolbar")


_LABEL_CLASSES = {"label", "label-sm"}
_TRANSLATE_RE = re.compile(r"translate\(\s*(-?[\d.eE+-]+)[,\s]+(-?[\d.eE+-]+)\s*\)")


def apply_room_labels(svg_text: str, rooms: list[dict[str, Any]] | None) -> str:
    """Rewrite ``label``/``label-sm`` text contents to the studio room
    containing each label's anchor point.

    The project's room names are the single source of truth for what a
    room is called — the drawing's baked ``<text>`` only contributes a
    hand-placed position. When several texts land in one room (a
    fixture note beside the room name), only the label nearest the
    room's centroid is renamed; other in-room texts and labels outside
    every room (scale legend, detached notes) keep their content.
    Studio room polygons are in combined-floor space, so ancestor
    ``translate()`` offsets are composed per element (floor-2 content
    sits inside a wrapper group).
    """
    if not rooms:
        return svg_text
    polys = [
        (r, r.get("polygon") or [], _polygon_area(r.get("polygon") or []))
        for r in rooms
    ]

    def _room_at(x: float, y: float) -> dict[str, Any] | None:
        hits = [t for t in polys if t[1] and _point_in_polygon(x, y, t[1])]
        # overlapping fills happen — the smallest containing room is
        # the most specific label target (mirrors room_for_point)
        return min(hits, key=lambda t: t[2])[0] if hits else None

    root = _svg_parse(svg_text)
    found: list[tuple[ET.Element, dict[str, Any], float, float]] = []

    def _walk(el: ET.Element, dx: float, dy: float) -> None:
        m = _TRANSLATE_RE.search(el.get("transform") or "")
        if m:
            dx += float(m.group(1))
            dy += float(m.group(2))
        if el.tag.rsplit("}", 1)[-1] == "text" and (
            set((el.get("class") or "").split()) & _LABEL_CLASSES
        ):
            x = float(el.get("x") or 0) + dx
            y = float(el.get("y") or 0) + dy
            room = _room_at(x, y)
            if room is not None:
                found.append((el, room, x, y))
        for child in list(el):
            _walk(child, dx, dy)

    _walk(root, 0.0, 0.0)

    # several texts may land in one room (a fixture note beside the
    # room name) — only the label nearest the centroid takes the room
    # name; the rest keep their authored content
    by_room: dict[int, list[tuple[ET.Element, dict[str, Any], float]]] = {}
    for el, room, x, y in found:
        pts = room.get("polygon") or []
        cx = sum(float(p.get("x") or 0) for p in pts) / len(pts)
        cy = sum(float(p.get("y") or 0) for p in pts) / len(pts)
        by_room.setdefault(id(room), []).append(
            (el, room, (x - cx) ** 2 + (y - cy) ** 2)
        )
    for entries in by_room.values():
        el, room, _ = min(entries, key=lambda t: t[2])
        if room.get("name"):
            el.text = str(room["name"])
    return ET.tostring(root, encoding="unicode")


def apply_room_styles(svg_text: str, rooms: list[dict[str, Any]] | None) -> str:
    """Patch ``area.<slug>`` elements with the studio room fill/opacity.

    Studio is the source of truth for room appearance; the inline
    style wins over the SVG's embedded ``.room`` class rules.
    """
    for room in rooms or []:
        slug = slugify(room.get("name"))
        decl: dict[str, Any] = {}
        if room.get("fill"):
            decl["fill"] = room["fill"]
        if room.get("opacity") is not None:
            decl["fill-opacity"] = room["opacity"]
        if slug and decl:
            svg_text = set_element_style(svg_text, f"area.{slug}", decl)
    return svg_text


def build_elements_svg(model: dict[str, Any], options: dict[str, Any]) -> str:
    """Render the generated elements SVG — devices in a grid grouped by
    HA area (topology group when no area), each element named after its
    primary entity so rules auto-bind. Doubles as the symbol sheet:
    copy a ``<g>`` into a custom drawing and it keeps working.
    """
    groups = group_devices(model)
    icon_keys = {icon_for_device(dev, options) for _, _, devs in groups for dev in devs}
    symbols = [sym for sym in (load_icon_symbol(k) for k in sorted(icon_keys)) if sym]

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
        parts.append(f'<g id="{xml_id(group_key)}">')
        parts.append(
            f'<text class="rx-group-label" x="{_GROUP_PAD_X}" '
            f'y="{y}">{xml_text(label)}</text>'
        )
        row_y = y + 16
        for idx, dev in enumerate(devs):
            col = idx % _COLS
            row = idx // _COLS
            x = _GROUP_PAD_X + col * _CELL_W
            cy = row_y + row * _CELL_H
            element_id = element_id_for_device(dev, options)
            icon_key = icon_for_device(dev, options)
            parts.append(
                f'<g id="{xml_id(element_id)}" '
                f'transform="translate({x},{cy})">'
                f'<rect class="rx-cell" width="{_CELL_W - 16}" '
                f'height="{_CELL_H - 16}" rx="8"/>'
                f'<g class="rx-rotor">'
                f'<use href="#icon.{icon_key}" '
                f'xlink:href="#icon.{icon_key}" x="12" y="14" '
                f'width="{_ICON_SIZE}" height="{_ICON_SIZE}"/></g>'
                f'<text class="rx-label" x="44" y="30">'
                f"{xml_text(short_label(dev))}</text>"
                f'<text class="rx-state" x="44" y="52"></text>'
                "</g>"
            )
        rows = (len(devs) + _COLS - 1) // _COLS
        y = row_y + rows * _CELL_H + _GROUP_GAP
        parts.append("</g>")

    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts)


def editor_url(options: dict[str, Any]) -> str:
    """The floorplan-studio view URL — the in-SVG `⛓` button target.

    A stored value equal to the old external-editor default is treated
    as unset: it was written before studio became the editor.
    """
    url = str(options.get(OPTION_EDITOR_URL) or "")
    if not url or url == "https://qaddodi.github.io/ha-floorplan-editor/":
        return DEFAULT_EDITOR_URL
    return url


def build_toolbar_svg(options: dict[str, Any] | None = None) -> str:
    """Return the toolbar ``<g>`` snippet — paste once into a custom SVG.

    Three 26px glyph buttons spaced 34px apart, styled via the
    ``rx-toolbar*`` classes in ramses-floorplan.css; each carries a
    ``<title>`` tooltip. Wrap coordinates with a
    ``transform="translate(x,y)"`` to position it.
    """
    glyphs = [
        (TOOLBAR_ELEMENT_EXPORT, "↻", "Export bundle (merged SVGs + card yamls)"),
        (TOOLBAR_ELEMENT_UPLOAD, "⇡", "Upload an SVG to the floorplan folder"),
        (TOOLBAR_ELEMENT_EDITOR, "⛓", "Open floorplan studio"),
    ]
    parts = ['<g id="floorplan.toolbar">']
    for idx, (element_id, glyph, tooltip) in enumerate(glyphs):
        parts.append(svg_button(element_id, glyph, tooltip, idx * 34))
    parts.append("</g>")
    return "\n".join(parts)


__all__ = [
    "apply_area_overrides",
    "apply_room_labels",
    "apply_room_styles",
    "binding_maps",
    "build_elements_svg",
    "build_overlay_fragment",
    "build_toolbar_svg",
    "dock_anchor",
    "editor_url",
    "element_id_for_device",
    "group_devices",
    "icon_for_device",
    "effective_zones",
    "marker_meta_for_device",
    "short_label",
    "standalone_icon",
    "strip_toolbar",
]
