"""Compatibility shim — re-exports the bundle pipeline's public API.

The implementation moved to focused modules (see README):

- ``svg_utils.py``  — low-level SVG helpers (ids, styles, markers, buttons)
- ``expressions.py``— ``${…}`` rule expressions (eval5 contract)
- ``zones.py``      — zone classes, bound resolution, toggle payloads
- ``markers.py``    — element/icon resolution, overlay + elements SVG
- ``rules.py``      — ha-floorplan rule assembly
- ``bundle.py``     — merged SVGs, card yaml, file writes, export
- ``domains/``      — per-device-class behaviour registry

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from .bundle import async_generate_bundle, build_card_yaml, custom_svg_refs
from .expressions import element_class_expr, role_class_expr
from .markers import (
    apply_area_overrides,
    apply_room_styles,
    binding_maps,
    build_elements_svg,
    build_overlay_fragment,
    build_toolbar_svg,
    element_id_for_device,
    group_devices,
    icon_for_device,
    short_label,
    strip_toolbar,
)
from .rules import ROLE_RULE_TEMPLATES, build_rules, parse_extra_rules
from .svg_utils import merge_svg_overlay
from .zones import standalone_members, zone_class, zone_defs

# Private names referenced by tests and by earlier call sites — kept
# working so the refactor stays a pure restructuring.
_role_class_expr = role_class_expr
_element_class_expr = element_class_expr
_build_rules = build_rules
_build_card_yaml = build_card_yaml
_parse_extra_rules = parse_extra_rules
_element_id_for_device = element_id_for_device
_icon_for_device = icon_for_device
_apply_area_overrides = apply_area_overrides
_group_devices = group_devices
_short_label = short_label
_zone_class = zone_class

__all__ = [
    "async_generate_bundle",
    "build_elements_svg",
    "build_overlay_fragment",
    "build_toolbar_svg",
    "merge_svg_overlay",
]
