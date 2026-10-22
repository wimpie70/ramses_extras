"""Tests for the pluggable plan-editor adapters (``editors/``).

The canonical plan dict is studio-shaped; the hfs adapter translates
the ``floorplan_studio`` v2 layout both ways. These tests pin the
translation tables and the registry's selection precedence — the
storage layer itself (``LayoutStore``, ``latest.json``) is exercised
against ha-sim, not here.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.floorplan_helper.editors import (
    EDITOR_AUTO,
    adapter_for,
    editor_keys,
    resolve_editor,
)
from custom_components.ramses_extras.features.floorplan_helper.editors.base import (
    EditorCapabilities,
)
from custom_components.ramses_extras.features.floorplan_helper.editors.hfs import (
    HfsAdapter,
    hfs_type_for_device,
)
from custom_components.ramses_extras.features.floorplan_helper.editors.studio import (
    StudioAdapter,
)


class TestRegistry:
    def test_keys_and_adapter_for(self):
        assert editor_keys() == ["studio", "hfs"]
        assert adapter_for("studio").key == "studio"
        assert adapter_for("hfs").key == "hfs"
        with pytest.raises(KeyError):
            adapter_for("nope")

    def test_capabilities_shape(self):
        studio, hfs = adapter_for("studio"), adapter_for("hfs")
        assert isinstance(studio.capabilities, EditorCapabilities)
        # browser-side studio pulls/pushes; server-side hfs does not
        assert studio.capabilities.browser_side is True
        assert hfs.capabilities.browser_side is False
        # studio's own card element is probe-able; hfs's editor is a
        # panel (its card is only a live renderer)
        assert studio.capabilities.card_element == "floorplan-studio-card"
        assert hfs.capabilities.card_element == ""

    @pytest.mark.asyncio
    async def test_resolve_explicit_wins(self):
        hass = MagicMock()
        resolved = await resolve_editor(hass, {}, requested="hfs")
        assert resolved.key == "hfs"
        # an explicit-but-unknown key falls through to detection/auto
        resolved = await resolve_editor(hass, {}, requested="bogus")
        assert resolved.key in editor_keys()

    @pytest.mark.asyncio
    async def test_resolve_option_then_auto(self, monkeypatch):
        hass = MagicMock()
        # stored option beats detection entirely
        monkeypatch.setattr(
            "custom_components.ramses_extras.features.floorplan_helper"
            ".editors.detect_editors",
            AsyncMock(return_value=["hfs"]),
        )
        resolved = await resolve_editor(hass, {"editor": "studio"})
        assert resolved.key == "studio"
        # auto → the first installed adapter that already holds a plan
        monkeypatch.setattr(
            StudioAdapter,
            "async_load",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            HfsAdapter,
            "async_load",
            AsyncMock(return_value={"floors": []}),
        )
        resolved = await resolve_editor(hass, {"editor": EDITOR_AUTO})
        assert resolved.key == "hfs"
        # nothing stored → the first *installed* adapter wins
        # (detection is mocked to hfs-only, so that's hfs)
        monkeypatch.setattr(HfsAdapter, "async_load", AsyncMock(return_value=None))
        resolved = await resolve_editor(hass, {})
        assert resolved.key == "hfs"
        # with both installed and nothing stored, registry order wins
        monkeypatch.setattr(
            "custom_components.ramses_extras.features.floorplan_helper"
            ".editors.detect_editors",
            AsyncMock(return_value=["studio", "hfs"]),
        )
        resolved = await resolve_editor(hass, {})
        assert resolved.key == "studio"
        # nothing detected at all → studio keeps the status quo
        monkeypatch.setattr(
            "custom_components.ramses_extras.features.floorplan_helper"
            ".editors.detect_editors",
            AsyncMock(return_value=[]),
        )
        resolved = await resolve_editor(hass, {"editor": EDITOR_AUTO})
        assert resolved.key == "studio"


class TestStudioAdapter:
    def test_parse_accepts_project(self):
        plan = {"schemaVersion": 1, "floors": []}
        assert StudioAdapter().parse(json.dumps(plan)) == plan
        assert StudioAdapter().parse(plan) == plan

    def test_parse_rejects_garbage(self):
        with pytest.raises(vol.Invalid):
            StudioAdapter().parse({"floors": "not-a-list"})
        with pytest.raises(vol.Invalid):
            StudioAdapter().parse({"floors": {"a": {}}})  # hfs shape


_LAYOUT = {
    "version": 2,
    "unit": "cm",
    "north": 0,
    "catalog": [
        {
            "id": "c1",
            "floor": "bg",
            "type": "other",
            "name": "spare",
            "entity": "sensor.spare",
        }
    ],
    "floors": {
        "bg": {
            "title": "Begane grond",
            "outline": [[0, 0], [1440, 0], [1440, 560], [0, 560]],
            "owk": ["external"] * 4,
            "rooms": [
                {
                    "id": "r1",
                    "name": "Woonkamer",
                    "area": "woonkamer",
                    "kind": "room",
                    "pts": [[0, 0], [400, 0], [400, 300], [0, 300]],
                    "wk": ["wall"] * 4,
                    "color": "#22c55e",
                    "temps": ["sensor.dts_1"],
                }
            ],
            "walls": [
                {"id": "w1", "a": [0, 0], "b": [1440, 0], "kind": "external"},
                {"id": "w2", "a": [700, 0], "b": [700, 560], "kind": "wall"},
            ],
            "doors": [{"id": "d1", "kind": "door", "a": [400, 100], "b": [480, 100]}],
            "openings": [{"id": "o1", "a": [800, 200], "b": [900, 200]}],
            "devices": [
                {
                    "id": "dv1",
                    "type": "heater",
                    "entity": "climate.trv_1",
                    "trvs": ["climate.trv_1b"],
                    "x": 200,
                    "y": 150,
                },
                {
                    "id": "dv2",
                    "type": "cover",
                    "entity": "cover.shelly_valve",
                    "a": [700, 300],
                    "b": [740, 300],  # wall-mounted → midpoint
                },
            ],
            "unlinked": [
                {
                    "id": "u1",
                    "type": "other",
                    "name": "battery widget",
                    "x": 30,
                    "y": 30,
                    "attached": ["sensor.diy_valve_battery"],
                },
                {"id": "u2", "type": "other", "x": 60, "y": 30},
            ],
            "stairs": [],
            "extras": [],
            "furniture": [],
            "trace": {
                "src": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
                "x": 10,
                "y": 20,
                "w": 1400,
                "alpha": 0.6,
            },
            "nonnative": {"keep": True},  # unknown floor field — preserved
        }
    },
}


class TestHfsLoad:
    def setup_method(self):
        self.adapter = HfsAdapter()
        self.plan = self.adapter._layout_to_plan(json.loads(json.dumps(_LAYOUT)))

    def test_floor_becomes_canonical(self):
        floor = self.plan["floors"][0]
        assert floor["id"] == "bg"
        assert floor["name"] == "Begane grond"
        # the unknown floor field is not carried into the canonical plan
        # (it survives on the native side — see store round-trip)

    def test_canvas_bbox_keeps_origin(self):
        canvas = self.plan["floors"][0]["canvas"]
        assert canvas["width"] == pytest.approx(1440)
        assert canvas["height"] == pytest.approx(560)

    def test_rooms(self):
        room = self.plan["floors"][0]["rooms"][0]
        assert room["areaId"] == "woonkamer"
        assert room["fill"] == "#22c55e"
        assert room["polygon"][0] == {"x": 0.0, "y": 0.0}
        assert len(room["polygon"]) == 4

    def test_walls_become_points(self):
        walls = self.plan["floors"][0]["walls"]
        assert walls[0]["points"] == [
            {"x": 0.0, "y": 0.0},
            {"x": 1440.0, "y": 0.0},
        ]
        # external walls are heavier than interior ones
        assert walls[0]["thickness"] > walls[1]["thickness"]

    def test_doors_openings_ab_form(self):
        openings = self.plan["floors"][0]["openings"]
        assert len(openings) == 2
        door = next(o for o in openings if o["kind"] == "door")
        assert door["a"] == {"x": 400.0, "y": 100.0}
        assert door["b"] == {"x": 480.0, "y": 100.0}

    def test_devices_fold_multi_entities(self):
        markers = self.plan["floors"][0]["markers"]
        trv = next(m for m in markers if "climate.trv_1" in m["entities"])
        assert trv["entities"] == ["climate.trv_1", "climate.trv_1b"]
        assert trv["hfsType"] == "heater"
        # wall-mounted {a,b} device parks at the span midpoint
        valve = next(m for m in markers if m["entities"] == ["cover.shelly_valve"])
        assert valve["x"] == pytest.approx(720)
        assert valve["y"] == pytest.approx(300)

    def test_unlinked_with_entities_becomes_marker(self):
        markers = self.plan["floors"][0]["markers"]
        ids = {e for m in markers for e in m["entities"]}
        assert "sensor.diy_valve_battery" in ids
        # a decoration-only unlinked piece (no attached entities) is
        # dropped — nothing for the overlay to bind
        assert all("u2" != m["id"] for m in markers)

    def test_trace_becomes_background(self):
        bg = self.plan["floors"][0]["background"]
        assert bg["dataUri"].startswith("data:image/png")
        assert bg["x"] == 10 and bg["y"] == 20
        assert bg["opacity"] == pytest.approx(0.6)

    def test_parse_dispatch(self):
        # native layout in → canonical out; canonical in → passthrough
        parsed = self.adapter.parse(json.dumps(_LAYOUT))
        assert parsed["floors"][0]["name"] == "Begane grond"
        assert self.adapter.parse({"floors": []}) == {"floors": []}
        with pytest.raises(vol.Invalid):
            self.adapter.parse({"not": "either"})


class TestHfsStore:
    def setup_method(self):
        self.adapter = HfsAdapter()
        self.plan = self.adapter._layout_to_plan(json.loads(json.dumps(_LAYOUT)))

    def test_round_trip_preserves_layout_shell(self):
        out = self.adapter._plan_to_layout(self.plan, dict(_LAYOUT))
        assert out["version"] == 2
        assert out["catalog"] == _LAYOUT["catalog"]
        floor = out["floors"]["bg"]
        assert floor["nonnative"] == {"keep": True}
        assert floor["title"] == "Begane grond"
        assert floor["outline"] == _LAYOUT["floors"]["bg"]["outline"]

    def test_rooms_get_wk_and_area(self):
        out = self.adapter._plan_to_layout(self.plan, dict(_LAYOUT))
        room = out["floors"]["bg"]["rooms"][0]
        assert room["area"] == "woonkamer"
        assert room["color"] == "#22c55e"
        assert len(room["wk"]) == len(room["pts"])

    def test_devices_keep_hfs_type(self):
        out = self.adapter._plan_to_layout(self.plan, dict(_LAYOUT))
        devs = out["floors"]["bg"]["devices"]
        trv = next(d for d in devs if d["entity"] == "climate.trv_1")
        assert trv["type"] == "heater"
        # secondary entity folded onto the heater's trvs list
        assert trv.get("trvs") == ["climate.trv_1b"]

    def test_trace_survives(self):
        out = self.adapter._plan_to_layout(self.plan, dict(_LAYOUT))
        assert out["floors"]["bg"]["trace"]["w"] == 1400


class TestHfsTypeMap:
    @pytest.mark.parametrize(
        ("cls", "expected"),
        [
            ("TRV", "heater"),
            ("CTL", "climate"),
            ("OTB", "boiler"),
            ("DHW", "boiler"),
            ("FAN", "fan"),
            ("HVAC", "fan"),
            ("CO2", "other"),
            ("REM", "other"),
            ("DIS", "other"),
            ("UFC", "cover"),
            ("HGI", "server"),
        ],
    )
    def test_class_mapping(self, cls, expected):
        dev = {"device_class": cls, "primary_entity": "sensor.x"}
        assert hfs_type_for_device(dev) == expected

    def test_domain_fallback(self):
        dev = {"device_class": "", "primary_entity": "cover.diy_valve"}
        assert hfs_type_for_device(dev) == "cover"
        dev = {"device_class": "", "primary_entity": "sensor.spare"}
        assert hfs_type_for_device(dev) == "temp"
        dev = {"device_class": "", "primary_entity": "media_player.tv"}
        assert hfs_type_for_device(dev) == "other"


class TestCanonicalRendering:
    """Endpoint openings + non-zero canvas origins render correctly."""

    def test_opening_ab_renders(self):
        from custom_components.ramses_extras.features.floorplan_helper.importer import (
            project_drawing_svg,
        )

        floor = {
            "name": "bg",
            "canvas": {"x": 10, "y": 20, "width": 1000, "height": 600},
            "openings": [
                {
                    "id": "o1",
                    "kind": "door",
                    "a": {"x": 100, "y": 50},
                    "b": {"x": 200, "y": 50},
                }
            ],
            "rooms": [],
            "markers": [],
            "walls": [],
        }
        svg = project_drawing_svg(floor)
        assert svg is not None
        # the viewBox keeps the non-zero origin so stored coordinates
        # stay untouched
        assert 'viewBox="10 20 1000 600"' in svg
        # the {a,b} door span renders as a rotated rect centred on the
        # span midpoint (x150 y50), filled with the door colour
        assert "translate(150 50)" in svg
        assert "#fbbf24" in svg
