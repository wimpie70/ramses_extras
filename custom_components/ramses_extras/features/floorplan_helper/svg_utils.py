"""Low-level SVG helpers for the floorplan bundle.

Everything here operates on raw SVG text/fragments — the small,
reusable building blocks the renderers (markers.py, toolbar, zones)
compose. Additive changes to a user's drawing should go through these
helpers instead of re-implementing regex edits per call site.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...const import INTEGRATION_DIR
from .const import FLOORPLAN_ICONS

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
_VIEWBOX_RE = re.compile(r'viewBox="[^"]*?\s([\d.]+)\s+([\d.]+)"')
_ELEMENT_TAG_RE = r"<(?:rect|polygon|path|circle|ellipse|g)\b[^>]*?\bid=\"{id}\"[^>]*?>"


def xml_id(raw: Any) -> str:
    """Sanitize a string for use as an SVG element id."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(raw))


def xml_text(raw: Any) -> str:
    """Escape a string for use as XML text content."""
    return str(raw).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slugify(value: Any) -> str:
    """Lowercase ``[a-z0-9_]`` slug — used for room ids and zone classes."""
    return re.sub(
        r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(value or "").lower())
    ).strip("_")


def svg_viewbox_size(svg_text: str) -> tuple[float, float]:
    """Return ``(width, height)`` of the svg viewBox, or a 960x640 default."""
    m = _VIEWBOX_RE.search(svg_text)
    return (float(m.group(1)), float(m.group(2))) if m else (960.0, 640.0)


def load_icon_symbol(icon_key: str) -> str | None:
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


def marker_svg(
    element_id: str,
    x: float,
    y: float,
    size: float,
    icon_key: str,
    *,
    label: str = "",
    color: str,
    text_color: str,
    style: dict[str, str] | None = None,
) -> str:
    """Emit one positioned device marker group — badge style.

    Studio renders markers as a coloured disc + light glyph; matching
    that keeps markers readable on any room fill. Structure:

      ``rx-disc``   filled circle in the marker colour
      ``rx-rotor``  wrapper around the icon — spin animation target
                    (a CSS rotate on the outer group would clobber the
                    translate)
      ``rx-ring``   unfilled circle — the status/zone indicator. A
                    crisp stroke beats recolouring the glyph fill
                    (which just read as blur on path icons)

    The outer ``<g>`` carries the translate + ``color`` for captions
    (currentColor). ``rx-*`` classes restyle disc/ring via descendant
    selectors — never the outer fill.

    Caption font sizes scale with the marker ``size`` (studio-resized
    markers keep proportional text); the rx-name/rx-state CSS classes
    remain the fallback for elements that don't set font-size.

    ``style`` overrides badge parts — ``disc`` (fill colour, default
    ``color``), ``glyph`` (icon colour, default ``#f8fafc``), ``ring``
    (always-on border stroke, default transparent so only rx-* status
    classes colour it), ``opacity`` (whole marker). Any CSS colour
    including alpha forms (``rgba()``/8-digit hex) or ``none``.
    """
    st = style or {}
    disc_fill = st.get("disc") or color
    glyph_fill = st.get("glyph") or "#f8fafc"
    ring_stroke = st.get("ring") or "transparent"
    opacity = st.get("opacity")
    disc_r = size * 0.62
    icon = size * 0.8
    name_fs = max(6.0, size * 0.45)
    state_fs = max(7.0, size * 0.55)
    name = (
        f'<text class="rx-name" x="0" y="{-disc_r - 3:.0f}" '
        f'font-size="{name_fs:.0f}" '
        f'text-anchor="middle">{xml_text(label)}</text>'
        if label
        else ""
    )
    return (
        f'<g id="{xml_id(element_id)}" '
        f'transform="translate({x:.1f},{y:.1f})" '
        f'fill="{color}" color="{text_color}"'
        + (f' opacity="{xml_text(opacity)}"' if opacity else "")
        + ">"
        + f'<circle class="rx-disc" r="{disc_r:.1f}" fill="{xml_text(disc_fill)}"/>'
        + f'<circle class="rx-ring" r="{disc_r:.1f}" fill="none" '
        + f'stroke="{xml_text(ring_stroke)}" '
        + f'stroke-width="{max(1.5, size * 0.07):.1f}"/>'
        + '<g class="rx-rotor">'
        + f'<use href="#icon.{icon_key}" fill="{xml_text(glyph_fill)}" '
        + f'x="{-icon / 2:.1f}" y="{-icon / 2:.1f}" '
        + f'width="{icon:.0f}" height="{icon:.0f}"/></g>'
        f"{name}"
        f'<text class="rx-state" x="0" y="{disc_r + state_fs - 2:.0f}" '
        f'font-size="{state_fs:.0f}" '
        f'text-anchor="middle"></text>'
        "</g>"
    )


def svg_button(
    element_id: str,
    glyph: str,
    tooltip: str,
    x: float = 0,
    *,
    size: int = 26,
) -> str:
    """Emit one toolbar button group (bg rect + centred glyph + title)."""
    return (
        f'<g id="{element_id}" class="rx-toolbar-btn" '
        f'transform="translate({x:.0f},0)">'
        f"<title>{xml_text(tooltip)}</title>"
        f'<rect class="rx-toolbar-bg" width="{size}" height="{size}" rx="4"/>'
        f'<text class="rx-toolbar-glyph" x="{size // 2}" y="{size - 8}">'
        f"{glyph}</text>"
        "</g>"
    )


def set_element_style(
    svg_text: str, element_id: str, declarations: dict[str, Any]
) -> str:
    """Patch one element's inline ``style`` attribute in place.

    Inline style survives every consumer — unlike a ``<style>`` block
    with escaped-id selectors — and wins over the drawing's embedded
    class rules, which is what we want for generated patches.
    """
    extra = "; ".join(f"{k}:{v}" for k, v in declarations.items())
    tag_re = re.compile(_ELEMENT_TAG_RE.format(id=re.escape(element_id)), re.S)

    def repl(m: re.Match[str]) -> str:
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

    return tag_re.sub(repl, svg_text)


def merge_svg_overlay(svg_text: str, fragment: str) -> str:
    """Splice an overlay fragment into an SVG document before ``</svg>``."""
    idx = svg_text.rfind("</svg>")
    if idx == -1:
        return svg_text + "\n" + fragment
    return svg_text[:idx] + fragment + "\n" + svg_text[idx:]


def strip_element(svg_text: str, element_id: str) -> str:
    """Remove a ``<g id="…">`` group (and its translate wrapper).

    Balances ``<g …>/</g>`` pairs since the group may contain nested
    groups. Used to drop a previously injected block before emitting a
    fresh one.
    """
    out = svg_text
    needle = f'<g id="{element_id}"'
    while True:
        i = out.find(needle)
        if i < 0:
            return out
        depth, j = 1, i
        while depth:
            nxt_open = out.find("<g ", j)
            nxt_close = out.find("</g>", j)
            if nxt_close < 0:
                return out  # malformed — leave untouched
            if 0 <= nxt_open < nxt_close:
                depth += 1
                j = nxt_open + 1
            else:
                depth -= 1
                j = nxt_close + 4
        end = j
        start = i
        before = out[:i]
        m = re.search(r'<g transform="[^"]*">\s*$', before)
        if m:
            start = m.start()
            while end < len(out) and out[end] in " \t\n":
                end += 1
        out = out[:start] + out[end:]


__all__ = [
    "load_icon_symbol",
    "marker_svg",
    "merge_svg_overlay",
    "set_element_style",
    "slugify",
    "strip_element",
    "svg_button",
    "svg_viewbox_size",
    "xml_id",
    "xml_text",
]
