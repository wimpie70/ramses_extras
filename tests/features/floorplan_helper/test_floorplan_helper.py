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
from custom_components.ramses_extras.features.floorplan_helper.config_flow import (
    _format_icon_overrides,
    _parse_icon_overrides,
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
        # extra rules precede the toolbar rules (emitted last)
        idx = next(i for i, r in enumerate(rules) if r.get("entity") == "light.kitchen")
        assert idx < next(
            i
            for i, r in enumerate(rules)
            if str(r.get("element", "")).startswith("floorplan.")
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
    def test_toolbar_rules_emitted(self):
        rules = generator._build_rules(_model(), _options())
        by_element = {r.get("element"): r for r in rules if "element" in r}
        assert by_element[TOOLBAR_ELEMENT_EXPORT]["tap_action"]["service"] == (
            "ramses_extras.floorplan_export"
        )
        assert by_element[TOOLBAR_ELEMENT_IMPORT]["tap_action"][
            "navigation_path"
        ].endswith("floorplan_import")
        assert by_element[TOOLBAR_ELEMENT_UPLOAD]["tap_action"][
            "navigation_path"
        ].endswith("floorplan_upload_svg")
        assert by_element[TOOLBAR_ELEMENT_EDITOR]["tap_action"]["action"] == "url"
        assert by_element[TOOLBAR_ELEMENT_PLANNER]["tap_action"]["action"] == "url"

    def test_toolbar_disabled(self):
        rules = generator._build_rules(_model(), _options(toolbar_enabled=False))
        assert not any(
            str(r.get("element", "")).startswith("floorplan.") for r in rules
        )

    def test_internal_tool_url_uses_navigate(self):
        rules = generator._build_rules(
            _model(), _options(editor_url="/floorplan-editor/")
        )
        editor = next(r for r in rules if r.get("element") == TOOLBAR_ELEMENT_EDITOR)
        assert editor["tap_action"]["action"] == "navigate"
        assert editor["tap_action"]["navigation_path"] == "/floorplan-editor/"

    def test_toolbar_svg_snippet(self):
        snippet = generator.build_toolbar_svg()
        for element_id in (
            TOOLBAR_ELEMENT_EXPORT,
            TOOLBAR_ELEMENT_IMPORT,
            TOOLBAR_ELEMENT_UPLOAD,
            TOOLBAR_ELEMENT_EDITOR,
            TOOLBAR_ELEMENT_PLANNER,
        ):
            assert f'id="{element_id}"' in snippet

    def test_generated_svg_includes_toolbar(self):
        svg = generator.build_elements_svg(_model(devices=[_device()]), _options())
        assert 'id="floorplan.toolbar"' in svg
        svg_no = generator.build_elements_svg(
            _model(devices=[_device()]), _options(toolbar_enabled=False)
        )
        assert 'id="floorplan.toolbar"' not in svg_no


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

    def test_parse_and_format_icon_overrides(self):
        text = "FAN=gauge\n# comment\nbogusline\nTRV=notanicon\nCTL=thermostat"
        parsed = _parse_icon_overrides(text)
        assert parsed == {"FAN": "gauge", "CTL": "thermostat"}
        assert _format_icon_overrides(parsed) == "CTL=thermostat\nFAN=gauge"
