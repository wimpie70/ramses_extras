"""Editor adapter base — the seam between our compiler and a plan editor.

Floorplan Helper supports pluggable plan editors. Each adapter owns:

- **storage** — where the plan lives (studio: browser IndexedDB mirrored
  to ``latest.json``; hfs: ``.storage/floorplan_studio.layout``)
- **translation** — the editor's native format ⇄ the canonical plan dict
- **capabilities** — what the editor's schema can express, which drives
  the actions card's menu rows and how much of a seed survives

The canonical plan dict is studio-shaped::

    {
        "name": "Floorplan",
        "floors": [{
            "id": "…", "name": "Plattegrond",
            "canvas": {"width": 1440, "height": 560},
            "background": {"dataUri": "data:image/…" | None, "x": 0,
                           "y": 0, "scale": 1, "opacity": 1, …},
            "walls": [{"id", "points": [{x, y}…], "color", "thickness"}],
            "openings": [{"id", "wallId", "t", "width", "kind"}],
            "rooms": [{"id", "name", "areaId", "polygon": [{x, y}…],
                       "fill", "opacity"}],
            "markers": [{"id", "x", "y", "entities": […], "elementId",
                         "style": {"icon", "color", "size", "label",
                                   "showState", "glyph", "ring",
                                   "opacity"},
                         "actions": {"tap", "hold", "double"},
                         "stateRules": [], "ramsesZone", "ramsesCaption"}],
        }],
    }

Adapters translate their native plan into this shape on load and back
on store — every consumer (``studio_marker_positions``,
``project_drawing_svg``, ``dedupe_rooms``, the merge/stamp helpers)
works on the canonical shape only.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True)
class EditorCapabilities:
    """What the editor's own data model can express.

    Drives the actions card's menu rows (``browser_side`` gates the
    pull/push buttons) and how seeding degrades (an editor without
    ``marker_actions`` still gets devices, just not gestures).
    """

    marker_icons: bool = True  # per-marker icon choice
    marker_colors: bool = True  # per-marker colour
    marker_actions: bool = True  # tap/hold/double per marker
    multi_entity: bool = True  # one marker binds several entities
    stamp_extras: bool = True  # unknown keys survive editor saves
    browser_side: bool = True  # plan lives in the browser → pull/push
    editor_url: str = ""  # where "Open editor" points
    card_element: str = ""  # custom element to find on the dashboard
    panel_element: str = ""  # element the embed card mounts (editor UI)
    panel_module: str = ""  # JS module to import for it ("" = already loaded)


class EditorAdapter(ABC):
    """Base class for a pluggable plan editor."""

    key: str = ""
    name: str = ""
    capabilities = EditorCapabilities()

    # ---- detection ---------------------------------------------------
    @abstractmethod
    async def async_detect(self, hass: HomeAssistant) -> bool:
        """Return True when the editor is installed/available."""

    # ---- storage (async — may hit the filesystem) --------------------
    @abstractmethod
    async def async_load(self, hass: HomeAssistant) -> dict[str, Any] | None:
        """Load the editor's plan, translated to the canonical dict."""

    @abstractmethod
    async def async_store(self, hass: HomeAssistant, plan: dict[str, Any]) -> str:
        """Persist a canonical plan into the editor's native store.

        :return: a locator for status messages (file path, storage key)
        """

    @abstractmethod
    async def async_backup(self, hass: HomeAssistant, plan_text: str) -> str:
        """Write a timestamped backup copy; returns the path."""

    async def async_plan_backups(self, hass: HomeAssistant) -> list[dict[str, Any]]:
        """Older canonical plans, newest first — used by
        combine-floors to re-merge an already-folded plan."""
        return []

    # ---- translation -------------------------------------------------
    def parse(self, raw: str | dict[str, Any]) -> dict[str, Any]:
        """Native text/dict → canonical plan dict.

        ``floorplan_store_project``/``floorplan_seed_studio`` receive
        raw text from the card; each adapter validates its own shape.
        """
        plan = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(plan, dict):
            raise ValueError("plan is not an object")
        return plan

    def to_native(self, plan: dict[str, Any]) -> Any:
        """Canonical plan → the editor's native format (identity for
        editors whose native format *is* the canonical one)."""
        return plan


__all__ = ["EditorAdapter", "EditorCapabilities"]
