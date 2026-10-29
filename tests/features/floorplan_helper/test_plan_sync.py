"""Tests for plan-editor merge helpers (``plan_sync``) and
``dashboard_apply``.

``plan_sync`` works against the canonical studio-shaped plan dict, so
its merge/stamp logic is exercised here without an editor — adapter
translation lives in ``test_editors.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.floorplan_helper import (
    dashboard_apply,
    plan_sync,
)
from custom_components.ramses_extras.features.floorplan_helper.const import (
    DEVICE_VIEW_SERVICE,
    OPTION_DEVICE_VIEW_URL,
    ZONE_TOGGLE_SERVICE,
)


def _room(name, pts=None, **kw):
    room = {"name": name, "polygon": pts or []}
    room.update(kw)
    return room


def _floor(name, **kw):
    floor = {"name": name, "rooms": [], "markers": [], "canvas": {"width": 800}}
    floor.update(kw)
    return floor


def _marker(entities, x=10, y=10, **kw):
    marker = {
        "id": "m1",
        "x": x,
        "y": y,
        "entities": entities,
        "elementId": entities[0],
        "style": {"icon": "mdi:fan"},
        "actions": {
            "tap": {"kind": "more-info"},
            "hold": {"kind": "none"},
            "double": {"kind": "none"},
        },
    }
    marker.update(kw)
    return marker


def _dev(**kw):
    base = {
        "device_id": "32:153289",
        "device_class": "FAN",
        "primary_entity": "sensor.32_153289_fan_rate",
        "display_name": "Fan",
        "area_id": None,
        "entities": [],
    }
    base.update(kw)
    return base


class TestHelpers:
    def test_room_key_slug_normalises(self):
        # a name-bound copy and an area-bound copy of the same room
        # collide instead of duplicating
        assert plan_sync._room_key({"name": "deel bg"}) == "deel_bg"
        assert plan_sync._room_key({"areaId": "deel_bg", "name": "x"}) == "deel_bg"
        assert plan_sync._room_key({}) == ""

    def test_room_centroid(self):
        room = _room("r", pts=[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}])
        cx, cy = plan_sync._room_centroid(room)
        assert (cx, cy) == pytest.approx((20 / 3, 10 / 3))
        assert plan_sync._room_centroid(_room("empty")) == (0.0, 0.0)

    def test_secondary_entities_skips_primary(self):
        dev = _dev(
            entities=[
                {"entity_id": "sensor.32_153289_fan_rate"},
                {"entity_id": "sensor.32_153289_indoor_temp"},
                {"entity_id": "sensor.32_153289_co2_level"},
                {"bogus": True},  # no entity_id — dropped
            ]
        )
        assert plan_sync._secondary_entities(dev, "sensor.32_153289_fan_rate") == [
            "sensor.32_153289_indoor_temp",
            "sensor.32_153289_co2_level",
        ]

    @pytest.mark.parametrize(
        ("cls", "expected"),
        [
            ("CTL", "heater"),
            ("THM", "heater"),
            ("TRV", "heater"),
            ("FAN", "fan"),
            ("COV", "cover"),
            ("HGI", "server"),
            ("REM", "other"),
            ("", "other"),
        ],
    )
    def test_hfs_dev_type(self, cls, expected):
        assert plan_sync._hfs_dev_type({"device_class": cls}) == expected


class TestHostFloor:
    def test_no_match_returns_none(self):
        floors = [_floor("bg", rooms=[_room("woonkamer")])]
        new = _floor("1e", rooms=[_room("slaapkamer")])
        assert plan_sync._host_floor(floors, new) == (None, (0.0, 0.0))

    def test_host_and_offset(self):
        # the combined floor holds the same rooms shifted +800x: the
        # offset translates incoming coords into host space (median of
        # the per-room deltas)
        host = _floor(
            "combined",
            rooms=[
                _room("woonkamer", pts=[{"x": 900, "y": 100}, {"x": 950, "y": 100}]),
                _room("keuken", pts=[{"x": 900, "y": 200}, {"x": 950, "y": 200}]),
            ],
        )
        new = _floor(
            "bg",
            rooms=[
                _room("woonkamer", pts=[{"x": 100, "y": 100}, {"x": 150, "y": 100}]),
                _room("keuken", pts=[{"x": 100, "y": 200}, {"x": 150, "y": 200}]),
            ],
        )
        floor, (ox, oy) = plan_sync._host_floor([host], new)
        assert floor is host
        assert (ox, oy) == pytest.approx((800.0, 0.0))


class TestMergeStudioProject:
    def test_new_floor_appended(self):
        project = {"floors": [_floor("bg")]}
        out = plan_sync._merge_studio_project(
            project,
            [_floor("1e", rooms=[_room("slaapkamer")])],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
        )
        assert [f["name"] for f in out["floors"]] == ["bg", "1e"]

    def test_same_name_floor_adds_missing_rooms_only(self):
        project = {"floors": [_floor("bg", rooms=[_room("woonkamer")])]}
        out = plan_sync._merge_studio_project(
            project,
            [
                _floor(
                    "bg",
                    rooms=[_room("woonkamer"), _room("keuken")],
                    markers=[],
                )
            ],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
        )
        names = [r["name"] for r in out["floors"][0]["rooms"]]
        assert names == ["woonkamer", "keuken"]

    def test_room_dedupe_collapses_area_clone(self):
        # a floor storing both a name-bound and an areaId-bound copy
        # of the same room (an older merge artifact) collapses to one
        # entry — first wins style, the clone fills gaps
        project = {
            "floors": [
                _floor(
                    "bg",
                    rooms=[
                        _room("deel bg"),
                        _room("other", areaId="deel_bg"),
                    ],
                )
            ]
        }
        out = plan_sync._merge_studio_project(
            project,
            [_floor("bg", rooms=[])],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
        )
        rooms = out["floors"][0]["rooms"]
        assert len(rooms) == 1
        assert rooms[0]["areaId"] == "deel_bg"  # grafted from the clone

    def test_incoming_duplicate_room_not_appended(self):
        # an incoming areaId-bound clone of an existing room is
        # filtered by key before extension
        project = {"floors": [_floor("bg", rooms=[_room("deel bg")])]}
        out = plan_sync._merge_studio_project(
            project,
            [_floor("bg", rooms=[_room("other", areaId="deel_bg")])],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
        )
        rooms = out["floors"][0]["rooms"]
        assert len(rooms) == 1
        assert rooms[0]["name"] == "deel bg"

    def test_marker_dedup_by_entity_and_device(self):
        existing = _floor("bg", markers=[_marker(["sensor.old_battery"])])
        project = {"floors": [existing]}
        new_floor = _floor(
            "bg",
            markers=[
                # same device, different bound entity — entity_device
                # resolves both to 32:153289 → skipped
                _marker(["sensor.32_153289_fan_rate"]),
                # genuinely new device → kept
                _marker(["sensor.04_000001_heat_demand"]),
            ],
        )
        out = plan_sync._merge_studio_project(
            project,
            [new_floor],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
            entity_device={
                "sensor.old_battery": "32:153289",
                "sensor.32_153289_fan_rate": "32:153289",
            },
        )
        ents = [e for m in out["floors"][0]["markers"] for e in m["entities"]]
        assert "sensor.32_153289_fan_rate" not in ents
        assert "sensor.04_000001_heat_demand" in ents

    def test_host_fold_translates_geometry(self):
        host = _floor(
            "combined",
            rooms=[_room("woonkamer", pts=[{"x": 900, "y": 0}, {"x": 950, "y": 0}])],
        )
        new = _floor(
            "bg",
            rooms=[_room("woonkamer", pts=[{"x": 100, "y": 0}, {"x": 150, "y": 0}])],
            markers=[_marker(["sensor.a"], x=100, y=50)],
        )
        out = plan_sync._merge_studio_project(
            {"floors": [host]},
            [new],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
            fold_hosts=True,
        )
        assert len(out["floors"]) == 1
        marker = next(
            m for m in out["floors"][0]["markers"] if "sensor.a" in m["entities"]
        )
        assert marker["x"] == pytest.approx(900)
        assert marker["y"] == pytest.approx(50)

    def test_fold_hosts_false_appends_floor(self):
        host = _floor(
            "combined",
            rooms=[_room("woonkamer", pts=[{"x": 900, "y": 0}, {"x": 950, "y": 0}])],
        )
        new = _floor(
            "bg",
            rooms=[_room("woonkamer", pts=[{"x": 100, "y": 0}, {"x": 150, "y": 0}])],
        )
        out = plan_sync._merge_studio_project(
            {"floors": [host]},
            [new],
            staging=False,
            extra_markers=[],
            mdi=lambda d: "mdi:fan",
            fold_hosts=False,
        )
        # server-side editors have real multi-floor plans — the same
        # room on a second floor must not fold it into the first
        assert [f["name"] for f in out["floors"]] == ["combined", "bg"]

    def test_staging_parks_model_device_on_home_floor(self):
        floors = [
            _floor("bg", rooms=[_room("woonkamer", areaId="woonkamer")]),
            _floor("1e", rooms=[_room("slaapkamer", areaId="slaapkamer")]),
        ]
        dev = _dev(area_id="woonkamer")
        out = plan_sync._merge_studio_project(
            {"floors": floors},
            [],
            staging=True,
            extra_markers=[dev],
            mdi=lambda d: "mdi:fan",
        )
        assert len(out["floors"][0]["markers"]) == 1
        assert out["floors"][1]["markers"] == []
        marker = out["floors"][0]["markers"][0]
        assert marker["hfsType"] == "fan"

    def test_staging_standalone_stages_every_floor(self):
        floors = [_floor("bg"), _floor("1e")]
        dev = _dev(
            device_id="cover.klep_wk",
            device_class="",
            primary_entity="cover.klep_wk",
            standalone=True,
        )
        out = plan_sync._merge_studio_project(
            {"floors": floors},
            [],
            staging=True,
            extra_markers=[dev],
            mdi=lambda d: "mdi:valve",
        )
        assert len(out["floors"][0]["markers"]) == 1
        assert len(out["floors"][1]["markers"]) == 1
        # standalone markers carry no hfsType
        assert "hfsType" not in out["floors"][0]["markers"][0]

    def test_staging_respects_dock_anchor(self):
        floors = [_floor("bg")]
        out = plan_sync._merge_studio_project(
            {"floors": floors},
            [],
            staging=True,
            extra_markers=[_dev()],
            mdi=lambda d: "mdi:fan",
            dock={"bg": (700.0, 50.0)},
        )
        marker = out["floors"][0]["markers"][0]
        assert marker["x"] == pytest.approx(700)
        assert marker["y"] == pytest.approx(50)

    def test_staged_marker_skipped_when_already_placed(self):
        existing = _floor("bg", markers=[_marker(["sensor.32_153289_fan_rate"])])
        out = plan_sync._merge_studio_project(
            {"floors": [existing]},
            [],
            staging=True,
            extra_markers=[_dev()],
            mdi=lambda d: "mdi:fan",
        )
        assert len(out["floors"][0]["markers"]) == 1


class TestStampMarkerActions:
    def _model(self):
        return {
            "devices": [_dev(entities=[{"entity_id": "sensor.32_153289_indoor_temp"}])]
        }

    def test_zone_owner_marker_gets_zone_actions(self):
        marker = _marker(["sensor.32_153289_fan_rate"])
        project = {"floors": [_floor("bg", markers=[marker])]}
        zones = {"32:153289": {"areas": ["woonkamer"], "devices": []}}
        plan_sync._stamp_marker_actions(project, self._model(), zones, {})
        tap = marker["actions"]["tap"]
        assert tap["kind"] == "call-service"
        assert tap["service"] == ZONE_TOGGLE_SERVICE
        double = marker["actions"]["double"]
        assert double["kind"] == "call-service"
        assert double["service"] == DEVICE_VIEW_SERVICE

    def test_user_gesture_wins(self):
        custom = {"kind": "navigate", "navPath": "/lovelace/fan"}
        marker = _marker(["sensor.32_153289_fan_rate"])
        marker["actions"]["tap"] = custom
        project = {"floors": [_floor("bg", markers=[marker])]}
        zones = {"32:153289": {"areas": ["woonkamer"], "devices": []}}
        plan_sync._stamp_marker_actions(project, self._model(), zones, {})
        assert marker["actions"]["tap"] is custom

    def test_view_url_maps_to_navigate(self):
        marker = _marker(["sensor.32_153289_fan_rate"])
        project = {"floors": [_floor("bg", markers=[marker])]}
        zones = {"32:153289": {"areas": ["woonkamer"], "devices": []}}
        plan_sync._stamp_marker_actions(
            project,
            self._model(),
            zones,
            {OPTION_DEVICE_VIEW_URL: "/lovelace/fan"},
        )
        assert marker["actions"]["double"] == {
            "kind": "navigate",
            "navPath": "/lovelace/fan",
        }

    def test_non_zone_marker_untouched(self):
        marker = _marker(["sensor.other"])
        project = {"floors": [_floor("bg", markers=[marker])]}
        plan_sync._stamp_marker_actions(project, self._model(), {}, {})
        assert marker["actions"]["tap"] == {"kind": "more-info"}


def _adapter(stamp=True):
    adapter = MagicMock()
    adapter.capabilities.stamp_extras = stamp
    adapter.async_load = AsyncMock()
    adapter.async_store = AsyncMock()
    return adapter


class TestWriteToProject:
    @pytest.mark.asyncio
    async def test_zone_skips_non_stamping_adapter(self):
        adapter = _adapter(stamp=False)
        await plan_sync._write_zone_to_project(
            MagicMock(), adapter, "32:153289", {"areas": ["x"]}
        )
        adapter.async_load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_zone_stamps_matching_marker(self):
        marker = _marker(["sensor.32_153289_fan_rate"])
        other = _marker(["sensor.other"])
        project = {"floors": [_floor("bg", markers=[marker, other])]}
        adapter = _adapter()
        adapter.async_load.return_value = project
        with patch.object(
            plan_sync,
            "build_floorplan_model",
            AsyncMock(return_value={"devices": [_dev()]}),
        ):
            await plan_sync._write_zone_to_project(
                MagicMock(), adapter, "32:153289", {"areas": ["woonkamer"]}
            )
        assert marker["ramsesZone"] == {"areas": ["woonkamer"]}
        assert "ramsesZone" not in other
        adapter.async_store.assert_awaited_once()
        assert adapter.async_store.await_args.args[1] is project

    @pytest.mark.asyncio
    async def test_zone_clear_removes_field(self):
        marker = _marker(["sensor.32_153289_fan_rate"], ramsesZone={"areas": ["x"]})
        project = {"floors": [_floor("bg", markers=[marker])]}
        adapter = _adapter()
        adapter.async_load.return_value = project
        with patch.object(
            plan_sync,
            "build_floorplan_model",
            AsyncMock(return_value={"devices": [_dev()]}),
        ):
            await plan_sync._write_zone_to_project(
                MagicMock(), adapter, "32:153289", None
            )
        assert "ramsesZone" not in marker

    @pytest.mark.asyncio
    async def test_caption_write_and_clear(self):
        marker = _marker(["sensor.32_153289_fan_rate"])
        project = {"floors": [_floor("bg", markers=[marker])]}
        adapter = _adapter()
        adapter.async_load.return_value = project
        with patch.object(
            plan_sync,
            "build_floorplan_model",
            AsyncMock(return_value={"devices": [_dev()]}),
        ):
            await plan_sync._write_caption_to_project(
                MagicMock(), adapter, "32:153289", ["sensor.a", "sensor.b"]
            )
        assert marker["ramsesCaption"] == ["sensor.a", "sensor.b"]
        adapter.async_load.return_value = project
        with patch.object(
            plan_sync,
            "build_floorplan_model",
            AsyncMock(return_value={"devices": [_dev()]}),
        ):
            await plan_sync._write_caption_to_project(
                MagicMock(), adapter, "32:153289", None
            )
        assert "ramsesCaption" not in marker


class TestDashboardApply:
    def test_notify_export_summarises(self):
        hass = MagicMock()
        bundle = {
            "rules": [1, 2, 3],
            "files_written": ["a", "b"],
            "changes": {"devices_added": ["32:153289"]},
            "warnings": ["one warning"],
        }
        with patch.object(
            dashboard_apply.persistent_notification, "async_create"
        ) as create:
            dashboard_apply.notify_export(hass, bundle)
        msg = create.call_args.args[1]
        assert "3 rules, 2 files written." in msg
        assert "devices added: 32:153289" in msg
        assert "⚠ one warning" in msg

    def test_notify_export_first_export_line(self):
        hass = MagicMock()
        with patch.object(
            dashboard_apply.persistent_notification, "async_create"
        ) as create:
            dashboard_apply.notify_export(hass, {"changes": {"first_export": True}})
        assert "First export" in create.call_args.args[1]

    @pytest.mark.asyncio
    async def test_apply_no_lovelace_data(self):
        hass = MagicMock()
        hass.data = {}
        out = await dashboard_apply.apply_cards_to_dashboards(hass, {})
        assert out == {"dashboards": 0, "cards": 0}

    @pytest.mark.asyncio
    async def test_apply_matches_by_image_location(self):
        from homeassistant.components.lovelace import LOVELACE_DATA
        from homeassistant.components.lovelace.dashboard import (
            LovelaceStorage,
        )

        new_card = {
            "type": "custom:floorplan-card",
            "config": {"image": {"location": "/local/plan.svg"}},
        }
        old_card = {
            "type": "custom:floorplan-card",
            "config": {"image": {"location": "/local/plan.svg"}},
            "stale": True,
        }
        handmade = {
            "type": "custom:floorplan-card",
            "config": {"image": {"location": "/local/other.svg"}},
        }
        dash = MagicMock(spec=LovelaceStorage)
        conf = {"views": [{"cards": [old_card, handmade]}]}
        dash.async_load = AsyncMock(return_value=conf)
        dash.async_save = AsyncMock()
        hass = MagicMock()
        hass.data = {LOVELACE_DATA: MagicMock(dashboards={"main": dash})}
        out = await dashboard_apply.apply_cards_to_dashboards(hass, {"c1": new_card})
        assert out == {"dashboards": 1, "cards": 1}
        assert conf["views"][0]["cards"][0] is new_card
        # a floorplan card showing a different map is left alone
        assert conf["views"][0]["cards"][1] is handmade
        dash.async_save.assert_awaited_once_with(conf)

    @pytest.mark.asyncio
    async def test_apply_match_override_and_url_filter(self):
        from homeassistant.components.lovelace import LOVELACE_DATA
        from homeassistant.components.lovelace.dashboard import (
            LovelaceStorage,
        )

        new_card = {
            "type": "custom:floorplan-card",
            "config": {"image": {"location": "/local/new.svg"}},
        }
        old_card = {
            "type": "custom:floorplan-card",
            "config": {"image": {"location": "/local/floor1.svg"}},
        }
        dash = MagicMock(spec=LovelaceStorage)
        conf = {"views": [{"cards": [old_card]}]}
        dash.async_load = AsyncMock(return_value=conf)
        dash.async_save = AsyncMock()
        hass = MagicMock()
        hass.data = {LOVELACE_DATA: MagicMock(dashboards={"plan": dash, "other": dash})}
        # url_path limits the scan to one dashboard even though both
        # would match
        out = await dashboard_apply.apply_cards_to_dashboards(
            hass, {"c1": new_card}, match="floor1", url_path="plan"
        )
        assert out == {"dashboards": 1, "cards": 1}
        assert conf["views"][0]["cards"][0] is new_card
