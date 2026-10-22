"""Unit tests for the floorplan_helper feature (pure-logic parts)."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import yaml
from homeassistant.config_entries import ConfigEntry

from custom_components.ramses_extras.features.floorplan_helper import (
    generator,
    importer,
    mapping,
    topology,
)
from custom_components.ramses_extras.features.floorplan_helper.const import (
    DEFAULT_FLOORPLAN_OPTIONS,
    DEFAULT_ICON,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_ICONS,
    OPTION_ELEMENT_BINDINGS,
    OPTION_ICON_OVERRIDES,
    RULES_BEGIN_MARKER,
    RULES_END_MARKER,
    TOOLBAR_ELEMENT_EDITOR,
    TOOLBAR_ELEMENT_EXPORT,
    TOOLBAR_ELEMENT_IMPORT,
    TOOLBAR_ELEMENT_PLANNER,
    TOOLBAR_ELEMENT_UPLOAD,
    ZONE_SEED_PALETTE,
)
from custom_components.ramses_extras.features.floorplan_helper.platforms import (
    binary_sensor as fp_binary_sensor,
)
from custom_components.ramses_extras.framework.helpers.ramses_topology import (
    build_owner_map,
    build_topology,
    collect_device_ids,
)


def _model(devices=None, areas=None, floors=None):
    return {
        "devices": devices or [],
        "areas": areas or {},
        "floors": floors or {},
    }


def _device(**kw):
    base = {
        "device_id": "32:153289",
        "device_class": "FAN",
        "group": "hvac",
        "parent": None,
        "area_id": None,
        "area_name": None,
        "display_name": "Fan",
        "primary_entity": "sensor.32_153289_fan_rate",
        "entities": [],
    }
    base.update(kw)
    return base


def _options(**kw):
    opts = deepcopy(DEFAULT_FLOORPLAN_OPTIONS)
    opts.update(kw)
    return opts


class TestSharedTopology:
    def test_collect_device_ids_nested(self):
        out = set()
        collect_device_ids({"a": "01:123456", "b": ["bad", {"c": "04:654321"}]}, out)
        assert out == {"01:123456", "04:654321"}

    def test_build_topology_heat_and_hvac(self):
        schema = {
            "main_tcs": "01:000001",
            "01:000001": {"system": {}, "zones": {"01": {"sensor": "04:000001"}}},
            "32:153289": {"remotes": ["34:000001"], "sensors": []},
            "orphans_heat": ["13:999999"],
        }
        topo = build_topology(schema)
        assert topo["01:000001"]["group"] == "heat"
        assert topo["04:000001"] == {"group": "heat", "parent": "01:000001"}
        assert topo["32:153289"]["group"] == "hvac"
        assert topo["34:000001"] == {"group": "hvac", "parent": "32:153289"}
        assert topo["13:999999"]["group"] == "orphan"

    def test_build_owner_map_foreign(self):
        coordinator = MagicMock()
        coordinator.options = {
            "schema": {
                "_owner": "18:000730",
                "01:000001": {"_owner": "18:000730"},
                "18:999999": {"_class": "HGI"},
            }
        }
        owners = build_owner_map(coordinator)
        assert owners["01:000001"] == "owned"
        assert owners["18:999999"] == "unowned"


class TestEntityClassification:
    def test_roles(self):
        assert topology._classify_entity("binary_sensor.32_153289_status") == "status"
        assert topology._classify_entity("sensor.04_x_heat_demand") == "heat_demand"
        assert (
            topology._classify_entity("binary_sensor.04_x_window_open") == "window_open"
        )
        assert topology._classify_entity("sensor.32_x_fan_rate") == "fan_rate"
        assert topology._classify_entity("sensor.32_x_outdoor_temp") == "temperature"
        assert topology._classify_entity("switch.x_misc") == "other"


class TestIconResolution:
    def test_device_class_default(self):
        dev = _device()
        assert generator._icon_for_device(dev, _options()) == "fan"

    def test_entity_override_beats_class(self):
        dev = _device()
        opts = _options(
            icon_overrides={
                "sensor.32_153289_fan_rate": "gauge",
                "FAN": "thermostat",
            }
        )
        assert generator._icon_for_device(dev, opts) == "gauge"

    def test_class_override_beats_default(self):
        dev = _device()
        opts = _options(icon_overrides={"FAN": "gauge"})
        assert generator._icon_for_device(dev, opts) == "gauge"

    def test_unknown_class_fallback(self):
        dev = _device(device_class="XYZ")
        assert generator._icon_for_device(dev, _options()) == DEFAULT_ICON

    def test_every_default_icon_shipped(self):
        for icon in set(FLOORPLAN_DEVICE_ICON_MAP.values()) | {DEFAULT_ICON}:
            assert icon in FLOORPLAN_ICONS


class TestElementsSvg:
    def test_svg_contains_element_and_symbol(self):
        dev = _device(
            entities=[
                {
                    "entity_id": "sensor.32_153289_fan_rate",
                    "domain": "sensor",
                    "role": "fan_rate",
                    "area_id": None,
                    "name": "",
                }
            ]
        )
        svg = generator.build_elements_svg(_model(devices=[dev]), _options())
        assert 'id="sensor.32_153289_fan_rate"' in svg
        assert 'id="icon.fan"' in svg
        assert 'id="group.hvac"' in svg

    def test_area_grouping(self):
        dev = _device(area_id="living", area_name="Living")
        model = _model(
            devices=[dev],
            areas={"living": {"name": "Living", "floor_id": "ground"}},
        )
        svg = generator.build_elements_svg(model, _options())
        assert 'id="area.living"' in svg
        assert ">Living<" in svg

    def test_missing_primary_uses_device_id(self):
        dev = _device(primary_entity=None)
        svg = generator.build_elements_svg(_model(devices=[dev]), _options())
        assert 'id="device.32:153289"' in svg


class TestRulesAndCard:
    def test_rules_from_roles(self):
        dev = _device(
            entities=[
                {
                    "entity_id": "binary_sensor.32_153289_status",
                    "domain": "binary_sensor",
                    "role": "status",
                    "area_id": None,
                    "name": "",
                },
                {
                    "entity_id": "sensor.32_153289_fan_rate",
                    "domain": "sensor",
                    "role": "fan_rate",
                    "area_id": None,
                    "name": "",
                },
            ]
        )
        rules = generator._build_rules(_model(devices=[dev]), _options())
        entities = {r["entity"] for r in rules if "entity" in r}
        assert "binary_sensor.32_153289_status" in entities
        assert "sensor.32_153289_fan_rate" in entities
        # status entity differs from element id → explicit element key
        status_rule = next(
            r for r in rules if r["entity"] == "binary_sensor.32_153289_status"
        )
        assert status_rule["element"] == "sensor.32_153289_fan_rate"

    def test_global_extra_rules_appended(self):
        opts = _options(
            extra_rules=[
                '{"entity": "light.kitchen", "tap_action": {"action": "toggle"}}'
            ]
        )
        rules = generator._build_rules(_model(), opts)
        assert any(r.get("entity") == "light.kitchen" for r in rules)
        # extra rules are emitted last so user-authored actions win on
        # conflicting elements
        idx = next(i for i, r in enumerate(rules) if r.get("entity") == "light.kitchen")
        assert idx == len(rules) - 1

    def test_class_exprs_have_no_return_keyword(self):
        # ha-floorplan wraps ${…} bodies in `return …` only when the body
        # has no "return" substring — a JS function()/return in a class
        # expression silently discards the result (class => undefined).
        dev = _device()
        dev["entities"].append(
            {"entity_id": "sensor.32_153289_fan_mode", "role": "fan_rate"}
        )
        expr = generator._element_class_expr(dev)
        assert expr is not None
        assert "return" not in expr
        assert "function(" not in expr
        assert ".includes(" not in expr
        # spin is FAN/HVAC-only — a REM mirroring its parent's fan_mode
        # doesn't rotate its marker
        rem = _device(device_class="REM")
        rem["entities"].append(
            {"entity_id": "sensor.37_168270_fan_mode", "role": "fan_rate"}
        )
        assert "rx-spin" not in (generator._element_class_expr(rem) or "")

    def test_generated_rules_tagged_and_stale_filtered(self):
        rules = generator._build_rules(_model(devices=[_device()]), _options())
        assert all(r.get("rx_gen") for r in rules)
        # stale generated rules (tagged or legacy rx- signature) are
        # dropped from stored extra_rules instead of shadowing fresh ones
        stale = [
            {"entity": "sensor.x", "rx_gen": True},
            {
                "entity": "binary_sensor.y_status",
                "state_action": {
                    "service": "floorplan.class_set",
                    "service_data": {"class": '${"rx-online"}'},
                },
            },
            {
                "element": "floorplan.export",
                "tap_action": {"action": "fire-dom-event"},
            },
        ]
        keep = [{"entity": "light.kitchen", "tap_action": {"action": "toggle"}}]
        rules = generator._build_rules(_model(), _options(extra_rules=stale + keep))
        entities = {r.get("entity") for r in rules}
        assert "sensor.x" not in entities
        assert "binary_sensor.y_status" not in entities
        assert "light.kitchen" in entities
        # the stale untagged toolbar rule is dropped — element rules are
        # generated, not user-authored, and the toolbar was removed
        assert (
            sum(1 for r in rules if str(r.get("element", "")) == "floorplan.export")
            == 0
        )

    def test_card_yaml_markers_and_parse(self):
        rules = [
            {
                "entity": "binary_sensor.a_status",
                "state_action": {
                    "service": "floorplan.class_set",
                    "service_data": {"class": "rx-online"},
                },
            }
        ]
        text = generator._build_card_yaml(rules, _options())
        assert RULES_BEGIN_MARKER in text
        assert RULES_END_MARKER in text
        parsed = yaml.safe_load(text)
        assert parsed["type"] == "custom:floorplan-card"
        assert parsed["config"]["rules"][0]["entity"] == "binary_sensor.a_status"


class TestToolbar:
    def test_no_toolbar_rules_emitted(self):
        # The in-SVG toolbar was removed — export/upload/studio live on
        # the actions card, so no floorplan.* element rules are emitted.
        rules = generator._build_rules(_model(), _options())
        assert not any(
            str(r.get("element", "")).startswith("floorplan.toolbar")
            or str(r.get("element", ""))
            in {
                TOOLBAR_ELEMENT_EXPORT,
                TOOLBAR_ELEMENT_UPLOAD,
                TOOLBAR_ELEMENT_EDITOR,
                TOOLBAR_ELEMENT_IMPORT,
                TOOLBAR_ELEMENT_PLANNER,
            }
            for r in rules
        )

    def test_toolbar_svg_snippet(self):
        snippet = generator.build_toolbar_svg()
        for element_id in (
            TOOLBAR_ELEMENT_EXPORT,
            TOOLBAR_ELEMENT_UPLOAD,
            TOOLBAR_ELEMENT_EDITOR,
        ):
            assert f'id="{element_id}"' in snippet
        # legacy glyphs are not emitted anymore
        assert f'id="{TOOLBAR_ELEMENT_IMPORT}"' not in snippet
        assert f'id="{TOOLBAR_ELEMENT_PLANNER}"' not in snippet

    def test_generated_svg_has_no_toolbar(self):
        svg = generator.build_elements_svg(_model(devices=[_device()]), _options())
        assert 'id="floorplan.toolbar"' not in svg


class TestImporter:
    def test_card_config(self):
        text = (
            "type: custom:floorplan-card\n"
            "config:\n"
            "  rules:\n"
            "    - element: area.kitchen\n"
            "      entity: light.kitchen\n"
            "      tap_action:\n"
            "        action: toggle\n"
        )
        parsed = importer.parse_floorplan_yaml(text)
        assert parsed["bindings"]["area.kitchen"] == {"entity_id": "light.kitchen"}
        assert len(parsed["extra_rules"]) == 1
        assert parsed["extra_rules"][0]["tap_action"]["action"] == "toggle"

    def test_bare_rules_list(self):
        text = (
            "- element: area.living\n"
            "  entity: climate.living\n"
            "- entity: sensor.temp\n"
            "  state_action: {service: floorplan.text_set}\n"
        )
        parsed = importer.parse_floorplan_yaml(text)
        assert parsed["bindings"] == {"area.living": {"entity_id": "climate.living"}}
        # both rules kept verbatim (entity-only rule has no binding)
        assert len(parsed["extra_rules"]) == 2

    def test_views_dashboard(self):
        text = (
            "views:\n"
            "  - title: Plan\n"
            "    cards:\n"
            "      - type: custom:floorplan-card\n"
            "        config:\n"
            "          rules:\n"
            "            - element: area.hall\n"
            "              entity: switch.hall\n"
        )
        parsed = importer.parse_floorplan_yaml(text)
        assert parsed["bindings"]["area.hall"]["entity_id"] == "switch.hall"

    def test_elements_and_entities_lists(self):
        text = "- elements: [area.a, area.b]\n  entities: [light.a, light.b]\n"
        parsed = importer.parse_floorplan_yaml(text)
        assert set(parsed["bindings"]) == {"area.a", "area.b"}
        assert parsed["bindings"]["area.a"]["entity_id"] == "light.a"
        assert parsed["warnings"]

    def test_garbage_input(self):
        assert "error" in importer.parse_floorplan_yaml("not: [valid: yaml")
        assert "error" in importer.parse_floorplan_yaml("")
        assert "error" in importer.parse_floorplan_yaml("just: a dict")


class TestStudioProject:
    """floorplan-studio project JSON parsing + point-in-polygon."""

    _PROJECT = {
        "schemaVersion": 1,
        "id": "abc",
        "floors": [
            {
                "id": "f1",
                "name": "Begane grond",
                "rooms": [
                    {
                        "id": "r1",
                        "name": "overloop",
                        "polygon": [
                            {"x": 0, "y": 0},
                            {"x": 640, "y": 0},
                            {"x": 640, "y": 560},
                            {"x": 0, "y": 560},
                        ],
                    },
                    {
                        "id": "r2",
                        "name": "eetkamer",
                        "polygon": [
                            {"x": 113, "y": 124},
                            {"x": 229, "y": 124},
                            {"x": 229, "y": 288},
                            {"x": 113, "y": 288},
                        ],
                    },
                ],
                "markers": [
                    {"id": "m1", "x": 170, "y": 200, "entities": ["fan.fan1"]},
                    {"id": "m2", "x": 999, "y": 999, "entities": ["light.x"]},
                ],
            }
        ],
    }

    def test_parse(self):
        import json

        parsed = importer.parse_studio_project(json.dumps(self._PROJECT))
        assert len(parsed["rooms"]) == 2
        assert len(parsed["markers"]) == 2
        assert parsed["rooms"][0]["name"] == "overloop"
        assert parsed["warnings"] == []

    def test_room_for_point_prefers_smallest(self):
        import json

        parsed = importer.parse_studio_project(json.dumps(self._PROJECT))
        room = importer.room_for_point(parsed["rooms"], 170, 200)
        assert room["name"] == "eetkamer"  # not the floor-spanning overloop
        assert importer.room_for_point(parsed["rooms"], 999, 999) is None

    def test_room_for_point_scopes_to_marker_floor(self):
        import json

        project = json.loads(json.dumps(self._PROJECT))
        project["floors"].append(
            {
                "id": "f2",
                "name": "1e verdieping",
                # Same coords as bg's eetkamer — smaller, must not win.
                "rooms": [
                    {
                        "id": "r3",
                        "name": "badhal",
                        "polygon": [
                            {"x": 120, "y": 130},
                            {"x": 200, "y": 130},
                            {"x": 200, "y": 250},
                            {"x": 120, "y": 250},
                        ],
                    }
                ],
                "markers": [],
            }
        )
        parsed = importer.parse_studio_project(json.dumps(project))
        marker = parsed["markers"][0]
        room = importer.room_for_point(
            parsed["rooms"], marker["x"], marker["y"], marker["floor"]
        )
        assert room["name"] == "eetkamer"
        # Without floor scoping the smaller upstairs room would win.
        room = importer.room_for_point(parsed["rooms"], marker["x"], marker["y"])
        assert room["name"] == "badhal"

    def test_bad_input(self):
        assert "error" in importer.parse_studio_project("{nope")
        assert "error" in importer.parse_studio_project('{"x": 1}')


class TestStudioSeed:
    """SVG → studio room extraction and project emit helpers."""

    _SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 560">'
        '<g transform="translate(10,20)">'
        '<rect id="area.eetkamer" x="113" y="124" width="100" height="100"/>'
        '<polygon id="area.nook" points="0,0 50,0 50,50"/>'
        '<rect id="other" x="0" y="0" width="5" height="5"/>'
        "</g></svg>"
    )

    def test_rooms_from_svg(self):
        rooms = importer.rooms_from_svg(self._SVG)
        by_slug = {r["slug"]: r for r in rooms}
        assert set(by_slug) == {"eetkamer", "nook"}
        # group translate applied
        assert by_slug["eetkamer"]["polygon"][0] == {"x": 123, "y": 144}
        assert by_slug["eetkamer"]["name"] == "eetkamer"
        cx, cy = by_slug["eetkamer"]["centroid"]
        assert cx == 173 and cy == 194

    def test_svg_viewbox(self):
        assert importer.svg_viewbox(self._SVG) == (640.0, 560.0)
        assert importer.svg_viewbox("<svg></svg>") == (800.0, 600.0)

    def test_project_shape(self):
        rooms = importer.rooms_from_svg(self._SVG)
        markers = [importer.studio_marker("fan.f1", 10, 10, "fan")]
        floor = importer.studio_floor("bg", 640, 560, rooms, markers)
        project = importer.build_studio_project("P", [floor])
        assert project["schemaVersion"] == 1
        assert project["floors"][0]["rooms"][0]["areaId"] == "eetkamer"
        assert project["floors"][0]["markers"][0]["entities"] == ["fan.f1"]
        # parses back through the studio-project importer
        import json

        parsed = importer.parse_studio_project(json.dumps(project))
        assert len(parsed["rooms"]) == 2 and len(parsed["markers"]) == 1


class TestMapping:
    def test_options_defaults(self):
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {}
        opts = mapping.get_floorplan_options(entry)
        assert opts["svg_mode"] == "generated"
        assert opts["icon_overrides"] == {}

    def test_snapshot_diff(self):
        model = _model(devices=[_device()])
        snap = mapping.model_snapshot(model)
        diff = mapping.snapshot_diff({}, snap)
        assert diff["first_export"] is True
        assert diff["devices_added"] == ["32:153289"]
        same = mapping.snapshot_diff(snap, snap)
        assert same["devices_added"] == [] and same["devices_changed"] == []


class TestDomains:
    def test_device_class_from_id(self):
        from custom_components.ramses_extras.features.floorplan_helper.domains import (
            device_class_from_id,
        )

        assert device_class_from_id("18:000730") == "HGI"
        assert device_class_from_id("01:000001") == "CTL"
        assert device_class_from_id("23:000001") == "CTL"
        assert device_class_from_id("07:000001") == "DHW"
        assert device_class_from_id("02:000001") == "UFC"
        assert device_class_from_id("13:000001") == "BDR"
        assert device_class_from_id("34:000001") == "SEN"
        assert device_class_from_id("32:153289") == ""  # FAN ids carry no prefix
        assert device_class_from_id("") == ""

    def test_domain_behaviour(self):
        from custom_components.ramses_extras.features.floorplan_helper.domains import (
            get_domain,
            zone_eligible,
        )

        fan = get_domain(_device())
        assert fan.can_spin and fan.popup_card == "hvac-fan"
        rem = get_domain(_device(device_id="37:168270", device_class="REM"))
        assert not rem.can_spin and rem.popup_card == ""
        hgi = get_domain(_device(device_id="18:000730", device_class="HGI"))
        assert not hgi.zone_eligible
        assert not zone_eligible(_device(device_id="18:1", device_class="HGI"))
        assert zone_eligible(_device())
        # heat classes resolve to their registered heat domains
        assert get_domain("TRV").default_icon == "radiator"
        assert get_domain("CTL").default_icon == "thermostat"
        assert get_domain("OTB").default_icon == "water-boiler"
        assert get_domain("DHW").default_icon == "water-boiler"
        assert get_domain("OUT").default_icon == "thermometer"

    def test_heat_captions(self):
        from custom_components.ramses_extras.features.floorplan_helper.domains import (
            get_domain,
        )

        trv = get_domain("TRV").caption_entities(
            [
                {"entity_id": "number.04_000001_heat_demand"},
                {"entity_id": "sensor.04_000001_temperature"},
            ]
        )
        assert trv == [
            ("number.04_000001_heat_demand", "%"),
            ("sensor.04_000001_temperature", "°"),
        ]
        otb = get_domain("OTB").caption_entities(
            [
                {"entity_id": "sensor.10_000001_rel_modulation_level"},
                {"entity_id": "sensor.10_000001_boiler_water_temp"},
            ]
        )
        assert otb == [
            ("sensor.10_000001_boiler_water_temp", "°"),
            ("sensor.10_000001_rel_modulation_level", "%"),
        ]


class TestSvgUtils:
    def test_marker_and_button(self):
        from custom_components.ramses_extras.features.floorplan_helper import (
            svg_utils,
        )

        m = svg_utils.marker_svg(
            "climate.32_153289",
            10.0,
            20.0,
            20.0,
            "fan",
            label="FAN 32:153289",
            color="#fff",
            text_color="#000",
        )
        assert 'id="climate.32_153289"' in m
        assert "translate(10.0,20.0)" in m
        assert "rx-rotor" in m and "FAN 32:153289" in m and "rx-name" in m
        assert "rx-disc" in m and "rx-ring" in m
        b = svg_utils.svg_button("floorplan.export", "X", "tip", 34)
        assert 'id="floorplan.export"' in b and "<title>tip</title>" in b

    def test_set_element_style_and_strip(self):
        from custom_components.ramses_extras.features.floorplan_helper import (
            svg_utils,
        )

        svg = (
            '<svg viewBox="0 0 100 100">'
            '<rect id="area.lounge" class="room"/>'
            '<g transform="translate(1,2)"><g id="floorplan.toolbar">'
            '<g id="floorplan.export"><rect/></g></g></g>'
            '<rect id="other"/></svg>'
        )
        out = svg_utils.set_element_style(
            svg, "area.lounge", {"fill": "#abc", "fill-opacity": 0.4}
        )
        assert 'style="fill:#abc; fill-opacity:0.4"' in out
        out = svg_utils.strip_element(out, "floorplan.toolbar")
        assert "floorplan.toolbar" not in out and 'id="other"' in out
        assert 'id="area.lounge"' in out  # siblings survive


class TestZones:
    def test_resolve_bound_and_toggle_specs(self):
        from custom_components.ramses_extras.features.floorplan_helper import zones

        fan = _device()
        rem = _device(
            device_id="37:168270",
            device_class="REM",
            parent="32:153289",
            primary_entity="remote.37_168270",
        )
        hgi = _device(
            device_id="18:000730",
            device_class="HGI",
            parent="32:153289",
            primary_entity="binary_sensor.hgi_online",
        )
        model = _model(devices=[fan, rem, hgi])
        zone = {"areas": ["woonkamer"], "devices": ["cover.klep_1"]}
        areas, bound = zones.resolve_bound(
            model, fan, zone, lambda d: d["primary_entity"]
        )
        assert areas == ["area.woonkamer"]
        # fan + rem bound; hgi excluded (zone_eligible=False); valve lands
        # on its own standalone marker
        assert "sensor.32_153289_fan_rate" in bound
        assert "remote.37_168270" in bound
        assert "cover.klep_1" in bound
        assert all("hgi" not in str(b) for b in bound)
        toggles = zones.zone_toggle_specs("32:153289", areas, bound)
        assert toggles[0]["class"] == "rx-zone-32_153289"
        assert toggles[1]["class"] == "rx-zone-32_153289_dev"
        # tap = one call-service to the zone bridge — the shape studio
        # can express, so the action survives studio's own export
        act = zones.zone_tap_actions(toggles)
        assert act["action"] == "call-service"
        assert act["service"] == "ramses_extras.floorplan_zone_toggle"
        assert act["service_data"]["toggles"] == toggles
        # legacy ll-custom clear stays for previously exported yaml
        assert zones.zone_clear_action(toggles)["ramses_zone_clear"] == toggles

    def test_standalone_members_dedupes(self):
        from custom_components.ramses_extras.features.floorplan_helper import zones

        model = _model(devices=[_device()])
        zones_cfg = {
            "32:153289": {
                "devices": [
                    "cover.klep_1",
                    "cover.klep_1",
                    "37:168270",
                    "sensor.32_153289_fan_rate",
                ]
            }
        }
        # model entity ids + device ids are excluded; plain entities kept
        assert zones.standalone_members(model, zones_cfg) == ["cover.klep_1"]

    def test_seed_heat_zones(self):
        from custom_components.ramses_extras.features.floorplan_helper import zones

        heat = [
            {
                "ctl_id": "01:150000",
                "zone_id": "03",
                "name": "Woonkamer",
                "sensor": "01:150003",
                "actuators": ["04:150003", "04:150099"],
                "class": "radiator_valve",
            },
            {
                # no sensor → first actuator parents the zone
                "ctl_id": "01:150000",
                "zone_id": "04",
                "name": "Badkamer",
                "sensor": None,
                "actuators": ["13:150004"],
                "class": "zone_valve",
            },
            {
                # empty zone (no sensor/actuators) is skipped
                "ctl_id": "01:150000",
                "zone_id": "00",
                "name": "CLounge",
                "sensor": None,
                "actuators": [],
                "class": "",
            },
            {
                # unmatched room name → zone still seeded, no areas
                "ctl_id": "01:150000",
                "zone_id": "05",
                "name": "Conservatory",
                "sensor": "01:150005",
                "actuators": ["04:150005"],
                "class": "radiator_valve",
            },
        ]
        rooms = {"woonkamer", "badkamer"}
        cfg = {"32:153289": {"areas": ["keuken"], "devices": []}}
        seeded = zones.seed_heat_zones(heat, rooms, cfg)
        assert seeded == ["01:150003", "13:150004", "01:150005"]
        lounge = cfg["01:150003"]
        assert lounge["areas"] == ["woonkamer"]
        assert lounge["devices"] == ["04:150003", "04:150099"]
        assert lounge["color"] in ZONE_SEED_PALETTE
        assert cfg["13:150004"]["areas"] == ["badkamer"]
        assert cfg["13:150004"]["devices"] == []
        assert cfg["01:150005"]["areas"] == []
        # re-seed never overwrites an existing (possibly user-edited) zone
        seeded2 = zones.seed_heat_zones(heat, rooms, cfg)
        assert seeded2 == []


class TestCaption:
    def _dev(self, **kw):
        kw.setdefault(
            "entities",
            [
                {
                    "entity_id": "sensor.32_153289_indoor_temp",
                    "role": "temperature",
                },
                {
                    "entity_id": "sensor.32_153289_outdoor_temp",
                    "role": "temperature",
                },
                {"entity_id": "sensor.32_153289_co2_level", "role": "co2"},
            ],
        )
        return _device(**kw)

    def test_fan_caption_shows_inside_and_outside(self):
        rules = generator._build_rules(_model(devices=[self._dev()]), _options())
        texts = [
            r
            for r in rules
            if r.get("state_action", {}).get("service") == "floorplan.text_set"
        ]
        # one combined caption per contributing entity — indoor +
        # outdoor, not the co2 sensor (no clobbering)
        assert {r["entity"] for r in texts} == {
            "sensor.32_153289_indoor_temp",
            "sensor.32_153289_outdoor_temp",
        }
        exprs = {r["state_action"]["service_data"]["text"] for r in texts}
        assert len(exprs) == 1
        expr = exprs.pop()
        assert 'states["sensor.32_153289_indoor_temp"]' in expr
        assert 'states["sensor.32_153289_outdoor_temp"]' in expr
        assert "co2" not in expr and "return" not in expr

    def test_co2_marker_caption_is_ppm(self):
        co2 = self._dev(
            device_id="37:126776",
            device_class="CO2",
            primary_entity="remote.rem_37_126776",
            entities=[
                {"entity_id": "sensor.37_126776_co2_level", "role": "co2"},
            ],
        )
        rules = generator._build_rules(_model(devices=[co2]), _options())
        texts = [
            r
            for r in rules
            if r.get("state_action", {}).get("service") == "floorplan.text_set"
        ]
        assert len(texts) == 1
        assert " ppm" in texts[0]["state_action"]["service_data"]["text"]

    def test_caption_fields_per_class_selection(self):
        # caption_fields {class: [group keys]} filters the domain's
        # caption_groups — FAN picking only outdoor_temp drops indoor
        def _texts(rules):
            return [
                r
                for r in rules
                if r.get("state_action", {}).get("service") == "floorplan.text_set"
            ]

        rules = generator._build_rules(
            _model(devices=[self._dev()]),
            _options(caption_fields={"FAN": ["outdoor_temp"]}),
        )
        assert {r["entity"] for r in _texts(rules)} == {"sensor.32_153289_outdoor_temp"}
        expr = _texts(rules)[0]["state_action"]["service_data"]["text"]
        assert "outdoor_temp" in expr and "indoor_temp" not in expr

        # empty list for the class = no caption
        rules = generator._build_rules(
            _model(devices=[self._dev()]),
            _options(caption_fields={"FAN": []}),
        )
        assert not _texts(rules)

        # absent class key keeps the domain default (indoor + outdoor)
        rules = generator._build_rules(
            _model(devices=[self._dev()]), _options(caption_fields={})
        )
        assert {r["entity"] for r in _texts(rules)} == {
            "sensor.32_153289_indoor_temp",
            "sensor.32_153289_outdoor_temp",
        }

    def test_marker_entities_drive_caption(self):
        # a studio marker with more than one entity attached shows
        # those states — "what's on the marker is what it shows";
        # suffixes come from the domain groups, then name heuristics
        from custom_components.ramses_extras.features.floorplan_helper.rules import (
            caption_pairs_for_device,
        )

        dev = self._dev()
        meta = {
            "sensor.32_153289_fan_rate": {
                "entities": [
                    "sensor.32_153289_indoor_temp",
                    "sensor.32_153289_indoor_humidity",
                ]
            }
        }
        pairs = caption_pairs_for_device(
            dev,
            _options(),
            meta["sensor.32_153289_fan_rate"],
        )
        assert pairs == [
            ("sensor.32_153289_indoor_temp", "°"),
            ("sensor.32_153289_indoor_humidity", "%"),
        ]

        # a single-entity marker keeps the group-derived caption
        meta["sensor.32_153289_fan_rate"]["entities"] = ["sensor.32_153289_fan_rate"]
        pairs = caption_pairs_for_device(
            dev,
            _options(),
            meta["sensor.32_153289_fan_rate"],
        )
        assert [e for e, _ in pairs] == [
            "sensor.32_153289_indoor_temp",
            "sensor.32_153289_outdoor_temp",
        ]

        # an explicit ramsesCaption still wins over attached entities
        meta["sensor.32_153289_fan_rate"]["entities"] = [
            "sensor.32_153289_indoor_temp",
            "sensor.32_153289_indoor_humidity",
        ]
        meta["sensor.32_153289_fan_rate"]["ramses_caption"] = [
            "sensor.32_153289_co2_level| ppm"
        ]
        pairs = caption_pairs_for_device(
            dev,
            _options(),
            meta["sensor.32_153289_fan_rate"],
        )
        assert pairs == [("sensor.32_153289_co2_level", "ppm")]

    def test_caption_suffix_heuristics(self):
        from custom_components.ramses_extras.features.floorplan_helper.domains import (
            caption_suffix_for,
            get_domain,
        )

        fan = get_domain("FAN")
        # domain group patterns win over the generic heuristics
        assert caption_suffix_for("sensor.x_indoor_temp", fan) == "°"
        # heuristic fallbacks for entities no group mentions
        assert caption_suffix_for("sensor.x_indoor_humidity", fan) == "%"
        assert caption_suffix_for("sensor.x_co2_level", fan) == " ppm"
        assert caption_suffix_for("number.x_fan_speed", fan) == ""


class TestMarkerStyle:
    def test_parse_and_defaults(self):
        from custom_components.ramses_extras.features.floorplan_helper.markers import (
            marker_style_for_key,
            parse_marker_style,
        )

        assert parse_marker_style("disc:#22c55e,glyph:#fff,ring:rgba(0,0,0,0.4)") == {
            "disc": "#22c55e",
            "glyph": "#fff",
            "ring": "rgba(0,0,0,0.4)",
        }
        assert parse_marker_style("bogus:#000") == {}
        assert parse_marker_style({"disc": "#000", "junk": "x"}) == {"disc": "#000"}
        assert marker_style_for_key(_device(), _options()) == {}

    def test_precedence_device_class_entity(self):
        from custom_components.ramses_extras.features.floorplan_helper.markers import (
            marker_style_for_key,
        )

        dev = _device()
        opts = _options(
            marker_style_overrides={
                "FAN": {"disc": "#111"},
                dev["primary_entity"]: {"glyph": "#222"},
                dev["device_id"]: {"ring": "#333"},
            }
        )
        assert marker_style_for_key(dev, opts) == {"ring": "#333"}
        # no device-id hit → class wins over entity
        assert marker_style_for_key(_device(device_id="99:000000"), opts) == {
            "disc": "#111"
        }
        # entity is the fallback when neither id nor class matches
        assert marker_style_for_key(
            _device(device_id="99:000000", device_class="REM"), opts
        ) == {"glyph": "#222"}

    def test_badge_svg_parts(self):
        from custom_components.ramses_extras.features.floorplan_helper import (
            svg_utils,
        )

        m = svg_utils.marker_svg(
            "climate.01_000001",
            5.0,
            5.0,
            20.0,
            "thermostat",
            color="#ffc107",
            text_color="#334155",
            style={
                "disc": "#22c55e",
                "glyph": "#000",
                "ring": "#f00",
                "opacity": "0.9",
            },
        )
        assert 'class="rx-disc" r="12.4" fill="#22c55e"' in m
        assert 'class="rx-ring" r="12.4" fill="none" stroke="#f00"' in m
        assert 'fill="#000"' in m and 'opacity="0.9"' in m

        plain = svg_utils.marker_svg(
            "climate.01_000001", 0, 0, 20, "fan", color="#ffc107", text_color="#334155"
        )
        assert 'stroke="transparent"' in plain and 'fill="#f8fafc"' in plain


class TestStudioMarkerMeta:
    """Studio edits persist in the project — the rule builder honours
    marker actions / showState instead of regenerating over them."""

    def _meta(self, actions=None, show_state=True):
        return {
            "sensor.32_153289_fan_rate": {
                "actions": actions or {},
                "show_state": show_state,
            }
        }

    def _tap_rule(self, rules, entity="sensor.32_153289_fan_rate"):
        return next(r for r in rules if r.get("entity") == entity and "tap_action" in r)

    def test_studio_tap_action_mapping(self):
        from custom_components.ramses_extras.features.floorplan_helper.rules import (
            studio_tap_action,
        )

        assert studio_tap_action({"kind": "more-info"}) == {"action": "more-info"}
        assert studio_tap_action({"kind": "toggle"}) == {"action": "toggle"}
        assert studio_tap_action({"kind": "navigate", "navPath": "/lovelace/x"}) == {
            "action": "navigate",
            "navigation_path": "/lovelace/x",
        }
        assert studio_tap_action({"kind": "url", "url": "https://x"}) == {
            "action": "url",
            "url_path": "https://x",
        }
        assert studio_tap_action(
            {
                "kind": "call-service",
                "service": "fan.toggle",
                "serviceData": "speed: high",
            }
        ) == {
            "action": "call-service",
            "service": "fan.toggle",
            "service_data": {"speed": "high"},
        }
        assert studio_tap_action({"kind": "none"}) is None
        # missing path → incomplete, inherit our default
        assert studio_tap_action({"kind": "navigate"}) is None
        assert studio_tap_action({"kind": "call-service"}) is None

    def test_zoned_parent_keeps_zone_tap_on_studio_defaults(self):
        dev = _device()
        opts = _options(device_zones={"32:153289": {"areas": ["woonkamer"]}})
        # studio's default kinds + our seeded class_toggle shorthand all
        # mean "keep the zone behaviour"
        for actions in (
            {},
            {"tap": {"kind": "none"}},
            {"tap": {"kind": "more-info"}},
            {
                "tap": {
                    "kind": "call-service",
                    "service": "floorplan.class_toggle",
                    "serviceData": 'class: "rx-zone-32_153289"',
                }
            },
            {
                "tap": {
                    "kind": "call-service",
                    "service": "ramses_extras.floorplan_zone_toggle",
                    "serviceData": "toggles: []",
                }
            },
        ):
            rules = generator._build_rules(
                _model(devices=[dev]), opts, self._meta(actions)
            )
            act = self._tap_rule(rules)["tap_action"]
            assert act["action"] == "call-service"
            assert act["service"] == "ramses_extras.floorplan_zone_toggle"
            toggles = act["service_data"]["toggles"]
            assert toggles[0]["class"] == "rx-zone-32_153289"

    def test_zoned_parent_honours_explicit_studio_gestures(self):
        dev = _device()
        opts = _options(device_zones={"32:153289": {"areas": ["woonkamer"]}})
        meta = self._meta(
            {
                "tap": {"kind": "navigate", "navPath": "/dash/fan"},
                "hold": {"kind": "toggle"},
                "double": {"kind": "url", "url": "https://example.com"},
            }
        )
        rules = generator._build_rules(_model(devices=[dev]), opts, meta)
        tap = self._tap_rule(rules)
        assert tap["tap_action"] == {
            "action": "navigate",
            "navigation_path": "/dash/fan",
        }
        assert tap["hold_action"] == {"action": "toggle"}
        assert tap["double_tap_action"] == {
            "action": "url",
            "url_path": "https://example.com",
        }

    def test_non_zoned_studio_actions_applied(self):
        dev = _device()
        meta = self._meta(
            {
                "tap": {"kind": "toggle"},
                "double": {"kind": "navigate", "navPath": "/x"},
            }
        )
        rules = generator._build_rules(_model(devices=[dev]), _options(), meta)
        tap = self._tap_rule(rules)
        assert tap["tap_action"] == {"action": "toggle"}
        assert tap["double_tap_action"]["navigation_path"] == "/x"

    def test_no_meta_falls_back_to_defaults(self):
        dev = _device()
        rules = generator._build_rules(_model(devices=[dev]), _options(), None)
        assert self._tap_rule(rules)["tap_action"] == {"action": "more-info"}

    def test_show_state_false_hides_caption(self):
        dev = _device(
            entities=[
                {"entity_id": "sensor.32_153289_indoor_temp", "role": "temperature"},
            ]
        )

        def texts(rs):
            return [
                r
                for r in rs
                if r.get("state_action", {}).get("service") == "floorplan.text_set"
            ]

        with_caption = generator._build_rules(
            _model(devices=[dev]), _options(), self._meta()
        )
        assert texts(with_caption)
        hidden = generator._build_rules(
            _model(devices=[dev]), _options(), self._meta(show_state=False)
        )
        assert not texts(hidden)

    def test_studio_actions_for_device(self):
        from custom_components.ramses_extras.features.floorplan_helper.importer import (
            studio_actions_for_device,
        )

        toggles = [{"class": "rx-zone-32_153289", "elements": ["area.a"]}]
        zoned = studio_actions_for_device(_device(), {"32:153289": {}}, toggles)
        assert zoned["tap"]["kind"] == "call-service"
        assert zoned["tap"]["service"] == "ramses_extras.floorplan_zone_toggle"
        assert "rx-zone-32_153289" in zoned["tap"]["serviceData"]
        assert zoned["hold"]["kind"] == "more-info"
        assert zoned["double"]["service"] == "ramses_extras.floorplan_device_view"
        plain = studio_actions_for_device(_device(), {})
        assert plain["tap"]["kind"] == "more-info"

    def test_marker_ramses_zone_is_ssot(self):
        # marker.ramsesZone in the project wins over the option map —
        # studio stores the zone, not our config menu
        dev = _device()
        meta = self._meta()
        meta["sensor.32_153289_fan_rate"]["ramses_zone"] = {"areas": ["vide_wing"]}
        rules = generator._build_rules(
            _model(devices=[dev]),
            _options(device_zones={"32:153289": {"areas": ["woonkamer"]}}),
            meta,
        )
        act = self._tap_rule(rules)["tap_action"]
        elements = act["service_data"]["toggles"][0]["elements"]
        assert elements == ["area.vide_wing"]

    def test_zone_colour_is_highlight_only(self):
        # zone.color is the selected-zone outline colour: an explicit
        # pick wins, and a zone without one inherits its first room's
        # fill — room fills themselves are never rewritten
        from custom_components.ramses_extras.features.floorplan_helper import (
            markers,
        )

        zones = markers.effective_zones(
            _model(devices=[_device()]),
            _options(
                device_zones={
                    "32:153289": {"areas": ["woonkamer"], "color": "#123456"},
                    "37:168270": {"areas": ["woonkamer"]},
                }
            ),
            None,
            {"woonkamer": "#aabbcc"},
        )
        assert zones["32:153289"]["color"] == "#123456"
        assert zones["37:168270"]["color"] == "#aabbcc"

    def test_marker_ramses_caption_is_ssot(self):
        # marker.ramsesCaption in the project wins over caption_overrides
        # — same SSOT rule as ramsesZone
        dev = _device(
            entities=[
                {"entity_id": "sensor.32_153289_indoor_temp", "role": "temperature"},
                {"entity_id": "sensor.32_153289_outdoor_temp", "role": "temperature"},
            ]
        )
        meta = self._meta()
        meta["sensor.32_153289_fan_rate"]["ramses_caption"] = [
            "sensor.32_153289_outdoor_temp|!"
        ]
        rules = generator._build_rules(
            _model(devices=[dev]),
            _options(
                caption_overrides={"32:153289": ["sensor.32_153289_indoor_temp|?"]}
            ),
            meta,
        )
        texts = [
            r
            for r in rules
            if r.get("state_action", {}).get("service") == "floorplan.text_set"
        ]
        assert {r["entity"] for r in texts} == {"sensor.32_153289_outdoor_temp"}
        expr = texts[0]["state_action"]["service_data"]["text"]
        assert "outdoor_temp" in expr and "indoor_temp" not in expr
        # empty list on the marker hides the caption outright
        meta["sensor.32_153289_fan_rate"]["ramses_caption"] = []
        rules = generator._build_rules(_model(devices=[dev]), _options(), meta)
        assert not [
            r
            for r in rules
            if r.get("state_action", {}).get("service") == "floorplan.text_set"
        ]

    def test_migrate_overrides_to_project(self):
        # option-level overrides stamp into marker/project fields once;
        # absent-only — afterwards the project owns them
        from custom_components.ramses_extras.features.floorplan_helper.bundle import (
            migrate_overrides_to_project,
        )
        from custom_components.ramses_extras.features.floorplan_helper.const import (
            FLOORPLAN_ICON_MDI,
        )

        dev = _device()
        marker = importer.studio_marker("sensor.32_153289_fan_rate", 10, 10, "mdi:fan")
        project = importer.build_studio_project(
            "P", [importer.studio_floor("bg", 640, 560, [], [marker])]
        )
        # seeded marker already carries an icon → only absent fields stamp
        marker["style"].pop("icon", None)
        opts = _options(
            icon_overrides={"FAN": "gauge"},
            marker_style_overrides={"32:153289": {"disc": "#111", "glyph": "#222"}},
            caption_overrides={"32:153289": ["sensor.32_153289_fan_rate|%"]},
            device_zones={"32:153289": {"areas": ["woonkamer"]}},
            device_view_url="/dash/fan",
        )
        assert migrate_overrides_to_project(project, _model(devices=[dev]), opts)
        assert marker["style"]["icon"] == FLOORPLAN_ICON_MDI["gauge"]
        # disc→style.color doesn't stamp: studio's colour field already
        # owns the disc (seeded #ffc107) — studio-owned keys only fill
        # gaps, never clobber
        assert marker["style"]["color"] == "#ffc107"
        assert marker["style"]["glyph"] == "#222"
        assert marker["ramsesCaption"] == ["sensor.32_153289_fan_rate|%"]
        assert marker["ramsesZone"] == {"areas": ["woonkamer"]}
        assert project["ramsesDeviceViewUrl"] == "/dash/fan"
        # absent-only: second run is a no-op even if options change
        opts2 = _options(
            caption_overrides={"32:153289": ["sensor.other|x"]},
            device_zones={"32:153289": {"areas": ["other"]}},
        )
        assert not migrate_overrides_to_project(project, _model(devices=[dev]), opts2)
        assert marker["ramsesCaption"] == ["sensor.32_153289_fan_rate|%"]
        assert marker["ramsesZone"] == {"areas": ["woonkamer"]}

    def test_device_view_shorthand_regenerated(self):
        # seeded double-tap bridge call is expanded from live config,
        # so stale serviceData can't drift the popup target
        dev = _device()
        opts = _options(device_zones={"32:153289": {"areas": ["w"]}})
        meta = self._meta(
            {
                "double": {
                    "kind": "call-service",
                    "service": "ramses_extras.floorplan_device_view",
                    "serviceData": "device_id: stale",
                }
            }
        )
        rules = generator._build_rules(_model(devices=[dev]), opts, meta)
        dbl = self._tap_rule(rules)["double_tap_action"]
        assert dbl["service"] == "ramses_extras.floorplan_device_view"
        assert dbl["service_data"]["device_id"] == "32:153289"
        assert dbl["service_data"]["card"]  # domain popup_card filled in


class TestCombineFloors:
    """Side-by-side floor combining (SVG + studio project)."""

    _SVG1 = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 560">'
        '<rect id="area.a" x="10" y="10" width="100" height="80"/></svg>'
    )
    _SVG2 = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 560">'
        '<rect id="area.b" x="20" y="30" width="50" height="40"/>'
        '<circle id="other" cx="5" cy="5" r="2"/></svg>'
    )

    def test_combine_svgs_offsets_and_wraps(self):
        merged, offsets, warnings = importer.combine_svgs(
            [("bg", self._SVG1), ("e1", self._SVG2)], gap=120
        )
        assert offsets == [0.0, 760.0]
        assert 'viewBox="0 0 1400 560"' in merged
        assert '<g id="floor.e1" transform="translate(760,0)">' in merged
        assert warnings == []
        # room extraction follows the wrapping transform
        rooms = {r["slug"]: r for r in importer.rooms_from_svg(merged)}
        assert rooms["a"]["centroid"][0] == pytest.approx(60)
        assert rooms["b"]["centroid"][0] == pytest.approx(760 + 45)

    def test_combine_svgs_renames_colliding_ids(self):
        svg2 = self._SVG2.replace('id="other"', 'id="area.a"')
        merged, _, warnings = importer.combine_svgs(
            [("bg", self._SVG1), ("e1", svg2)], gap=0
        )
        assert any("renamed" in w for w in warnings)
        # nothing is dropped — the colliding rect survives renamed
        assert 'id="e1.area.a"' in merged
        assert merged.count('id="area.a"') == 1

    def test_combine_svgs_strips_generated_floorplan_elements(self):
        svg2 = self._SVG2.replace(
            "</svg>", '<g id="floorplan.toolbar"><rect/></g></svg>'
        )
        merged, _, _ = importer.combine_svgs([("bg", self._SVG1), ("e1", svg2)])
        assert "floorplan.toolbar" not in merged

    def test_merge_project_floors_translates_contents(self):
        project = {
            "name": "Plattegrond",
            "activeFloorId": "f1",
            "floors": [
                {
                    "id": "f1",
                    "name": "Begane grond",
                    "canvas": {"width": 640, "height": 560},
                    "rooms": [{"id": "r1", "polygon": [{"x": 10, "y": 20}]}],
                    "walls": [],
                    "markers": [{"id": "m1", "x": 100, "y": 50}],
                },
                {
                    "id": "f2",
                    "name": "1e verdieping",
                    "canvas": {"width": 640, "height": 560},
                    "rooms": [{"id": "r2", "polygon": [{"x": 30, "y": 40}]}],
                    "walls": [],
                    "markers": [{"id": "m2", "x": 200, "y": 60}],
                },
            ],
        }
        importer.merge_project_floors(project, [0.0, 760.0], 1400, 560)
        assert len(project["floors"]) == 1
        merged = project["floors"][0]
        assert merged["canvas"] == {"width": 1400, "height": 560}
        assert project["activeFloorId"] == "f1"
        assert merged["name"] == "Plattegrond"
        xs = {r["id"]: r["polygon"][0]["x"] for r in merged["rooms"]}
        assert xs == {"r1": 10, "r2": 790}
        xs = {m["id"]: m["x"] for m in merged["markers"]}
        assert xs == {"m1": 100, "m2": 960}

    def test_merge_single_floor_is_noop(self):
        project = {"floors": [{"id": "f1", "rooms": [], "markers": []}]}
        importer.merge_project_floors(project, [0.0], 640, 560)
        assert len(project["floors"]) == 1


class TestHeatDemandMirrorDeviceAttachment:
    """The derived heat-demand binary sensor must attach to the source
    ramses_cc device directly, not redeclare its identifiers.

    Device-registry lookup by identifiers is scoped to the config entry,
    so copying the ramses_cc identifiers into ``DeviceInfo`` created a
    nameless duplicate device under ramses_extras that shadowed the real
    zone device (device-name lookups and remove_device registry checks
    then hit the stub).
    """

    def test_attaches_via_device_entry_not_device_info(self):
        source_device = MagicMock()
        source_device.id = "ha_device_1"
        source_device.identifiers = {("ramses_cc", "01:150000_03")}

        entity = fp_binary_sensor.FloorplanHeatDemandBinarySensor(
            MagicMock(), "sensor.01_150000_03_heat_demand", source_device
        )

        assert entity.device_entry is source_device
        assert entity.device_info is None
