"""ha-floorplan-studio adapter — the vespassassina integration.

Unlike the studio card, ``custom_components/floorplan_studio`` stores its
plan server-side in ``.storage/floorplan_studio.layout`` (``{rev,
layout}``) behind a revision-checked ``LayoutStore`` — the plan already
lives in HA, so there is no browser pull/push: the actions card hides
those rows via ``capabilities.browser_side = False``.

Schema v2 (``src/core/schema.ts``) is centimetre-based; the canonical
plan treats units as opaque user units, so coordinates map 1:1 — a
1440-unit canvas simply means 14.4 m.

Translation notes
-----------------
hfs → canonical (``async_load``/``parse``):

- ``floors`` is a ``Record<key, Floor>`` — the key becomes the floor id.
- The floor has no canvas; ``canvas`` is the bounding box of the floor
  outline (or every geometry point when no outline is drawn) and keeps
  its ``x``/``y`` origin so raw coordinates stay untouched.
- ``trace`` → ``background.dataUri`` with an explicit ``x``/``y``/
  ``width``/``height`` rect (Pillow resolves the aspect ratio) instead
  of the stretched-canvas background studio uses.
- ``rooms`` → canonical rooms (``pts`` → ``polygon``, ``color`` →
  ``fill``, ``area`` → ``areaId``; ``kind``/``temps``/``humidity`` are
  kept on the room for consumers that want them).
- ``walls`` are ``a``/``b`` segments → canonical ``points`` pairs, with
  kind-derived colour/thickness.
- ``doors``/``openings`` are ``a``/``b`` spans → canonical openings in
  ``{a, b, kind}`` form (the renderer rotates the marker along the
  span; the studio ``wallId``+``t`` form is still honoured).
- ``devices`` → markers: ``entity`` + ``trvs``/``tempSensors``/
  ``linked`` fold into ``entities[]`` (multi-entity markers), ``name``
  → ``style.label``; wall-mounted ``{a, b}`` devices take the span
  midpoint.
- ``unlinked`` pieces with ``attached`` entities → markers bound to
  those entities (DIY valves etc. stay visible); the rest are ignored.
- ``stairs``/``furniture``/``extras`` have no canonical counterpart and
  are skipped on read — they survive in the native store untouched.

canonical → hfs (``async_store``):

- rooms get ``kind: "room"`` and a per-edge ``wk`` of ``"wall"`` so the
  hfs card outlines them; ``area`` keeps the HA-area binding.
- markers → ``devices`` (first entity is ``entity``; extras land on
  ``trvs``/``linked`` where the mapped type accepts them). The ramses
  device class maps onto the fixed ``DeviceType`` enum via
  :data:`CLASS_TO_HFS_TYPE` — custom icons/actions do not exist in hfs
  (``capabilities`` says so), so marker ``style``/``actions`` are
  dropped.
- Unknown native fields in the merged-in floors are preserved — the
  store replaces only the floors the canonical plan carries.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import base64
import io
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from ..svg_utils import slugify
from .base import EditorAdapter, EditorCapabilities

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HFS_DOMAIN = "floorplan_studio"
LAYOUT_VERSION = 2

# ramses device class → hfs DeviceType enum
CLASS_TO_HFS_TYPE: dict[str, str] = {
    "TRV": "heater",
    "CTL": "climate",
    "DTS": "temp",
    "DT2": "temp",
    "THM": "temp",
    "SEN": "temp",
    "OTB": "boiler",
    "DHW": "boiler",
    "HCW": "boiler",
    "FAN": "fan",
    "HVAC": "fan",
    "CO2": "other",
    "REM": "other",
    "RND": "other",
    "DIS": "other",
    "SWI": "other",
    "UFC": "cover",
    "BDR": "other",
    "HGI": "server",
}

# entity domain → hfs DeviceType fallback for standalone members
DOMAIN_TO_HFS_TYPE: dict[str, str] = {
    "climate": "climate",
    "fan": "fan",
    "cover": "cover",
    "light": "light",
    "switch": "switch",
    "binary_sensor": "contact",
    "sensor": "temp",
}

# wall kind → canonical colour/thickness (mirrors hfs render weights)
_WALL_STYLE: dict[str, tuple[str, float]] = {
    "external": ("#475569", 10.0),
    "wall": ("#94a3b8", 6.0),
    "boundary": ("#94a3b8", 3.0),
    "fence": ("#94a3b8", 3.0),
    "edge": ("#94a3b8", 2.0),
    "parapet": ("#94a3b8", 4.0),
}

_DOOR_FILL: dict[str, str] = {
    "door": "#fbbf24",
    "glass": "#7dd3fc",
    "window": "#93c5fd",
    "fullwindow": "#93c5fd",
    "slit": "#bae6fd",
    "sealed": "#cbd5e1",
    "open": "#e2e8f0",
}


def _segment_key(
    a: Any, b: Any
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Undirected segment identity — endpoints rounded so shared
    room/outline edges dedupe. Points may be ``[x, y]`` pairs or
    canonical ``{"x", "y"}`` dicts."""

    def _xy(p: Any) -> tuple[float, float] | None:
        try:
            if isinstance(p, dict):
                return (round(float(p["x"]), 1), round(float(p["y"]), 1))
            return (round(float(p[0]), 1), round(float(p[1]), 1))
        except TypeError, IndexError, KeyError:
            return None

    pa, pb = _xy(a), _xy(b)
    if pa is None or pb is None:
        return None
    return (pa, pb) if pa <= pb else (pb, pa)


class HfsAdapter(EditorAdapter):
    """Adapter for the ``floorplan_studio`` integration (v2 layouts)."""

    key = "hfs"
    name = "ha-floorplan-studio"
    capabilities = EditorCapabilities(
        marker_icons=False,  # fixed icon per device type
        marker_colors=False,  # colour is per device *type*, not marker
        marker_actions=False,  # tap → popup, hold → more-info only
        multi_entity=True,  # trvs/tempSensors/linked fold in
        stamp_extras=False,  # editor-side validate may strip unknowns
        browser_side=False,  # plan lives in .storage — no pull/push
        editor_url="/floorplan-studio",
        # the editor is a sidebar panel — the embed card mounts it inline
        panel_element="floorplan-studio-panel",
        panel_module="/floorplan_studio_static/floorplan-studio-panel.js",
    )

    # ---- storage helpers ----------------------------------------------

    def _layout_store(self, hass: HomeAssistant) -> Any:
        """Return the integration's own ``LayoutStore`` (rev-checked)."""
        from custom_components.floorplan_studio.storage import LayoutStore

        return LayoutStore(hass)

    # ---- EditorAdapter -------------------------------------------------

    async def async_detect(self, hass: HomeAssistant) -> bool:
        """Installed when the integration module can be imported."""
        import importlib.util

        def _find() -> bool:
            return (
                importlib.util.find_spec("custom_components.floorplan_studio")
                is not None
            )

        found: bool = await hass.async_add_executor_job(_find)
        return found

    async def async_load(self, hass: HomeAssistant) -> dict[str, Any] | None:
        """Load the hfs layout and translate it to the canonical plan."""
        try:
            store = self._layout_store(hass)
            layout = await store.async_load()
        except Exception:  # noqa: BLE001 — integration absent/broken
            _LOGGER.debug("hfs layout load failed", exc_info=True)
            return None
        if not isinstance(layout, dict):
            return None
        return self._layout_to_plan(layout)

    async def async_store(self, hass: HomeAssistant, plan: dict[str, Any]) -> str:
        """Translate the canonical plan to a v2 layout and save it.

        Starts from the stored layout (when any) so floors, catalog,
        views and metadata the plan does not model survive the write.
        """
        store = self._layout_store(hass)
        current: dict[str, Any] | None = None
        rev = 0
        try:
            current, rev = await store.async_load_with_rev()
        except Exception:  # noqa: BLE001 — no LayoutStore yet
            pass
        layout = self._plan_to_layout(
            plan, current if isinstance(current, dict) else {}
        )
        # expected_rev guards against racing the editor's own autosave —
        # a conflict loses with a clear error rather than overwriting
        try:
            await store.async_save(layout, expected_rev=rev)
        except Exception:  # noqa: BLE001 — RevConflict on concurrent edit
            _LOGGER.info("hfs layout revision conflict — reloading and retrying")
            current, rev = await store.async_load_with_rev()
            layout = self._plan_to_layout(
                plan, current if isinstance(current, dict) else {}
            )
            await store.async_save(layout, expected_rev=rev)
        # mirror the integration's own save path so open editor panels
        # and live cards reload (websocket.py fires this after its save)
        hass.bus.async_fire("floorplan_studio_updated")
        return ".storage/floorplan_studio.layout"

    async def async_backup(self, hass: HomeAssistant, plan_text: str) -> str:
        """Timestamped copy of the *canonical* plan next to studio's."""
        from ..importer import backup_project

        path: str = await hass.async_add_executor_job(backup_project, hass, plan_text)
        return path

    def parse(self, raw: str | dict[str, Any]) -> dict[str, Any]:
        """Accept a native layout or an already-canonical plan."""
        obj = super().parse(raw)
        if obj.get("version") == LAYOUT_VERSION and isinstance(obj.get("floors"), dict):
            return self._layout_to_plan(obj)
        if isinstance(obj.get("floors"), list):
            return obj  # already canonical
        raise vol.Invalid("project_json is neither a hfs layout nor a plan")

    # ---- hfs → canonical -----------------------------------------------

    def _layout_to_plan(self, layout: dict[str, Any]) -> dict[str, Any]:
        floors: list[dict[str, Any]] = []
        for key, floor in (layout.get("floors") or {}).items():
            if isinstance(floor, dict):
                floors.append(self._floor_to_canonical(str(key), floor))
        return {
            "name": str(layout.get("name") or "Floorplan"),
            "floors": floors,
            "_hfs": True,  # provenance marker — stripped on store
        }

    def _floor_to_canonical(self, key: str, floor: dict[str, Any]) -> dict[str, Any]:
        rooms = [
            {
                "id": str(r.get("id") or uuid.uuid4().hex[:8]),
                "name": str(r.get("name") or ""),
                "areaId": str(r.get("area") or slugify(str(r.get("name") or ""))),
                "polygon": [
                    {"x": float(p[0]), "y": float(p[1])}
                    for p in (r.get("pts") or [])
                    if isinstance(p, list) and len(p) >= 2
                ],
                "fill": str(r.get("color") or "#3b82f6"),
                "opacity": 0.25,
                "kind": r.get("kind"),
                "temps": list(r.get("temps") or []),
                "humidity": list(r.get("humidity") or []),
            }
            for r in (floor.get("rooms") or [])
            if isinstance(r, dict)
        ]
        walls: list[dict[str, Any]] = []
        for w in floor.get("walls") or []:
            a, b = w.get("a"), w.get("b")
            if not (isinstance(a, list) and isinstance(b, list)):
                continue
            color, thick = _WALL_STYLE.get(
                str(w.get("kind") or "wall"), _WALL_STYLE["wall"]
            )
            walls.append(
                {
                    "id": str(w.get("id") or uuid.uuid4().hex[:8]),
                    "points": [
                        {"x": float(a[0]), "y": float(a[1])},
                        {"x": float(b[0]), "y": float(b[1])},
                    ],
                    "color": color,
                    "thickness": thick,
                }
            )
        # hfs also carries per-edge wall kinds on the floor outline
        # (`owk`) and every room polygon (`wk`) — plans drawn by tracing
        # often have no explicit `walls[]` at all. Derive canonical
        # walls from those edges too; dedupe shared edges (outline
        # first, so `external` wins over a coinciding room edge).
        seen = {_segment_key(w["points"][0], w["points"][1]) for w in walls}
        edges: list[tuple[list[Any], list[Any]]] = [
            (floor.get("outline") or [], floor.get("owk") or [])
        ]
        edges += [
            (r.get("pts") or [], r.get("wk") or [])
            for r in (floor.get("rooms") or [])
            if isinstance(r, dict)
        ]
        derived: list[tuple[float, dict[str, Any]]] = []
        for pts, wk_kinds in edges:
            ring = list(zip(pts, pts[1:] + pts[:1], strict=False))
            for i, (a, b) in enumerate(ring):
                kind = str(wk_kinds[i]) if i < len(wk_kinds) else "wall"
                if kind == "none":
                    continue
                seg = _segment_key(a, b)
                if seg is None or seg in seen:
                    continue
                seen.add(seg)
                color, thick = _WALL_STYLE.get(kind, _WALL_STYLE["wall"])
                derived.append(
                    (
                        thick,
                        {
                            "id": f"wk-{len(derived)}",
                            "points": [
                                {"x": float(a[0]), "y": float(a[1])},
                                {"x": float(b[0]), "y": float(b[1])},
                            ],
                            "color": color,
                            "thickness": thick,
                        },
                    )
                )
        # thinner kinds first so external strokes paint last — a room
        # edge that partially overlaps an external span must not hide it
        walls.extend(d for _, d in sorted(derived, key=lambda t: t[0]))
        openings = []
        for coll, kinds in (
            (floor.get("doors") or [], _DOOR_FILL),
            (floor.get("openings") or [], None),
        ):
            for d in coll:
                a, b = d.get("a"), d.get("b")
                if not (isinstance(a, list) and isinstance(b, list)):
                    continue
                kind = str(d.get("kind") or "open")
                openings.append(
                    {
                        "id": str(d.get("id") or uuid.uuid4().hex[:8]),
                        "kind": kind,
                        "a": {"x": float(a[0]), "y": float(a[1])},
                        "b": {"x": float(b[0]), "y": float(b[1])},
                    }
                )
        markers = [
            m
            for d in (floor.get("devices") or [])
            if isinstance(d, dict)
            for m in [self._device_to_marker(d)]
            if m is not None
        ]
        for u in floor.get("unlinked") or []:
            if not isinstance(u, dict):
                continue
            attached = [str(e) for e in (u.get("attached") or []) if e]
            if not attached:
                continue  # pure decoration — no entity to bind
            mkr = self._marker(
                str(u.get("id") or uuid.uuid4().hex[:8]),
                attached,
                float(u.get("x") or 0),
                float(u.get("y") or 0),
                label=str(u.get("name") or ""),
                icon=_hfs_icon_for(str(u.get("type") or "other")),
            )
            mkr["hfsType"] = str(u.get("type") or "other")
            markers.append(mkr)

        canvas = self._floor_canvas(floor, rooms, walls, openings, markers)
        canonical: dict[str, Any] = {
            "id": key,
            "name": str(floor.get("title") or key),
            "canvas": canvas,
            "layers": {
                layer: {"visible": True, "locked": False}
                for layer in ("background", "walls", "rooms", "entities", "labels")
            },
            "walls": walls,
            "openings": openings,
            "rooms": rooms,
            "markers": markers,
        }
        trace = floor.get("trace")
        if isinstance(trace, dict) and trace.get("src") and trace.get("on", True):
            canonical["background"] = self._trace_background(trace)
        else:
            canonical["background"] = {"dataUri": None, "opacity": 1}
        return canonical

    def _floor_canvas(
        self,
        floor: dict[str, Any],
        rooms: list[dict[str, Any]],
        walls: list[dict[str, Any]],
        openings: list[dict[str, Any]],
        markers: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Bounding box of every drawn point → canonical canvas.

        Keeps ``x``/``y`` (the viewBox origin) so stored coordinates are
        never rewritten.
        """
        xs: list[float] = []
        ys: list[float] = []

        def add(pt: Any) -> None:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))

        for p in floor.get("outline") or []:
            add(p)
        for r in rooms:
            for p in r["polygon"]:
                xs.append(p["x"])
                ys.append(p["y"])
        for w in walls:
            for p in w["points"]:
                xs.append(p["x"])
                ys.append(p["y"])
        for o in openings:
            for k in ("a", "b"):
                xs.append(float(o[k]["x"]))
                ys.append(float(o[k]["y"]))
        for m in markers:
            xs.append(float(m["x"]))
            ys.append(float(m["y"]))
        if not xs:
            return {"width": 800.0, "height": 600.0, "x": 0.0, "y": 0.0}
        x0, y0 = min(xs), min(ys)
        return {
            "x": x0,
            "y": y0,
            "width": max(max(xs) - x0, 1.0),
            "height": max(max(ys) - y0, 1.0),
        }

    def _trace_background(self, trace: dict[str, Any]) -> dict[str, Any]:
        """hfs trace image → canonical background with explicit rect."""
        src = str(trace.get("src") or "")
        w = float(trace.get("w") or 0)
        h = w  # fallback when the image can't be decoded
        if "base64," in src:
            try:
                from PIL import Image  # noqa: PLC0415 — ships with HA

                img = Image.open(
                    io.BytesIO(base64.b64decode(src.split("base64,", 1)[1]))
                )
                if img.width and w:
                    h = w * img.height / img.width
            except Exception:  # noqa: BLE001
                pass
        return {
            "dataUri": src,
            "x": float(trace.get("x") or 0),
            "y": float(trace.get("y") or 0),
            "width": w,
            "height": h,
            "rotation": float(trace.get("rot") or 0),
            "opacity": float(trace.get("alpha") or 1),
        }

    def _device_to_marker(self, d: dict[str, Any]) -> dict[str, Any] | None:
        entity = str(d.get("entity") or "")
        if not entity:
            return None
        entities = [entity]
        for field in ("trvs", "tempSensors", "linked"):
            entities.extend(
                str(e) for e in (d.get(field) or []) if e and e not in entities
            )
        # wall-mounted devices ({a, b}) take the span midpoint
        if "x" in d:
            x, y = float(d.get("x") or 0), float(d.get("y") or 0)
        elif isinstance(d.get("a"), list) and isinstance(d.get("b"), list):
            x = (float(d["a"][0]) + float(d["b"][0])) / 2
            y = (float(d["a"][1]) + float(d["b"][1])) / 2
        else:
            x = y = 0.0
        # keep the native type on the marker so a store round-trip
        # does not degrade it to "other"
        mkr = self._marker(
            str(d.get("id") or uuid.uuid4().hex[:8]),
            entities,
            x,
            y,
            label=str(d.get("name") or ""),
            icon=_hfs_icon_for(str(d.get("type") or "other")),
        )
        mkr["hfsType"] = str(d.get("type") or "other")
        return mkr

    @staticmethod
    def _marker(
        mid: str,
        entities: list[str],
        x: float,
        y: float,
        label: str = "",
        icon: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": mid,
            "x": round(x, 1),
            "y": round(y, 1),
            "entities": entities,
            "elementId": entities[0] if entities else mid,
            "style": {
                "type": "icon",
                "icon": icon or "help-circle",
                "color": "#ffc107",
                "size": 20,
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

    # ---- canonical → hfs -----------------------------------------------

    def _plan_to_layout(
        self, plan: dict[str, Any], current: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge the canonical plan's floors into the stored layout."""
        layout = dict(current) if isinstance(current, dict) else {}
        layout["version"] = LAYOUT_VERSION
        layout.setdefault("unit", "cm")
        layout.setdefault("north", 0)
        floors = dict(layout.get("floors") or {})
        for pf in plan.get("floors") or []:
            key = str(pf.get("id") or slugify(str(pf.get("name") or "floor")))
            base = dict(floors.get(key) or {})
            floors[key] = self._floor_to_hfs(pf, base)
        layout["floors"] = floors
        layout.setdefault("catalog", [])
        return layout

    def _floor_to_hfs(
        self, floor: dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        out = dict(base)
        out["title"] = str(floor.get("name") or out.get("title") or "Floor")
        rooms = []
        for r in floor.get("rooms") or []:
            pts = [
                [float(p["x"]), float(p["y"])]
                for p in (r.get("polygon") or [])
                if isinstance(p, dict) and "x" in p and "y" in p
            ]
            if len(pts) < 3:
                continue
            room: dict[str, Any] = {
                "id": str(r.get("id") or uuid.uuid4().hex[:8]),
                "name": str(r.get("name") or ""),
                "area": str(r.get("areaId") or ""),
                "kind": str(r.get("kind") or "room"),
                "pts": pts,
                "wk": ["wall"] * len(pts),
            }
            if r.get("fill"):
                room["color"] = str(r["fill"])
            rooms.append(room)
        out["rooms"] = rooms
        out["outline"] = list(out.get("outline") or self._bbox_outline(rooms))
        out.setdefault("owk", ["external"] * len(out["outline"]))
        # canonical walls are polylines — explode each into {a,b}
        # segments; the wall id is kept on its first segment only so a
        # round-trip does not spray duplicate ids
        walls_out: list[dict[str, Any]] = []
        for w in floor.get("walls") or []:
            wpts = [p for p in (w.get("points") or []) if isinstance(p, dict)]
            for i, (p, q) in enumerate(zip(wpts, wpts[1:], strict=False)):
                walls_out.append(
                    {
                        "id": str(w.get("id") or uuid.uuid4().hex[:8])
                        if i == 0
                        else uuid.uuid4().hex[:8],
                        "a": [float(p["x"]), float(p["y"])],
                        "b": [float(q["x"]), float(q["y"])],
                        "kind": "wall",
                    }
                )
        out["walls"] = walls_out
        out["doors"] = [
            {
                "id": str(o.get("id") or uuid.uuid4().hex[:8]),
                "name": str(o.get("kind") or "door"),
                "kind": o.get("kind") if o.get("kind") in _DOOR_FILL else "door",
                "a": [float(o["a"]["x"]), float(o["a"]["y"])],
                "b": [float(o["b"]["x"]), float(o["b"]["y"])],
            }
            for o in (floor.get("openings") or [])
            if isinstance(o.get("a"), dict) and isinstance(o.get("b"), dict)
        ]
        out.setdefault("openings", [])
        out.setdefault("stairs", [])
        out.setdefault("extras", [])
        out["devices"] = [
            dev
            for m in (floor.get("markers") or [])
            for dev in [self._marker_to_device(m)]
            if dev is not None
        ]
        out.setdefault("furniture", [])
        out.setdefault("unlinked", [])
        # preserve a native trace; a canonical background image becomes
        # one so the editor shows the same picture
        bg = floor.get("background") or {}
        if bg.get("dataUri"):
            out["trace"] = {
                "src": str(bg["dataUri"]),
                "x": float(bg.get("x") or 0),
                "y": float(bg.get("y") or 0),
                "w": float(bg.get("width") or self._canvas_w(floor)),
                "rot": float(bg.get("rotation") or 0),
                "alpha": float(bg.get("opacity") or 1),
                "on": True,
            }
        return out

    def _marker_to_device(self, marker: dict[str, Any]) -> dict[str, Any] | None:
        entities = [str(e) for e in (marker.get("entities") or []) if e]
        if not entities:
            return None
        style = marker.get("style") or {}
        dev_type = str(marker.get("hfsType") or "other")
        dev: dict[str, Any] = {
            "id": str(marker.get("id") or uuid.uuid4().hex[:8]),
            "type": dev_type,
            "entity": entities[0],
            "x": round(float(marker.get("x") or 0), 1),
            "y": round(float(marker.get("y") or 0), 1),
        }
        if style.get("label"):
            dev["name"] = str(style["label"])
        extra = entities[1:]
        if extra:
            if dev_type == "heater":
                dev["trvs"] = extra
            elif dev_type in ("climate", "ac"):
                dev["tempSensors"] = extra
            # other types: secondary entities stay caption-level only
        return dev

    @staticmethod
    def _canvas_w(floor: dict[str, Any]) -> float:
        try:
            return float((floor.get("canvas") or {}).get("width") or 800)
        except TypeError, ValueError:
            return 800.0

    @staticmethod
    def _bbox_outline(rooms: list[dict[str, Any]]) -> list[list[float]]:
        xs = [p[0] for r in rooms for p in r.get("pts") or []]
        ys = [p[1] for r in rooms for p in r.get("pts") or []]
        if not xs:
            return [[0, 0], [800, 0], [800, 600], [0, 600]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def hfs_type_for_device(dev: dict[str, Any]) -> str:
    """Map a ramses model device to the hfs ``DeviceType`` enum."""
    cls = str(dev.get("device_class") or "")
    if cls in CLASS_TO_HFS_TYPE:
        return CLASS_TO_HFS_TYPE[cls]
    primary = str(dev.get("primary_entity") or "")
    domain = primary.split(".", 1)[0]
    return DOMAIN_TO_HFS_TYPE.get(domain, "other")


def _hfs_icon_for(dev_type: str) -> str:
    """Stable canonical icon name for an hfs device type — the overlay
    renderer resolves it like any marker icon."""
    return {
        "heater": "radiator",
        "climate": "thermostat",
        "boiler": "water-boiler",
        "fan": "fan",
        "temp": "thermometer",
        "humidity": "water-percent",
        "cover": "window-shutter",
        "contact": "door",
        "motion": "motion-sensor",
        "lock": "lock",
        "light": "lightbulb",
        "camera": "cctv",
        "server": "server",
    }.get(dev_type, "help-circle")


__all__ = ["HfsAdapter", "hfs_type_for_device"]
