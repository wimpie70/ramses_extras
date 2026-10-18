"""Unit tests for the floorplan_helper feature (pure-logic parts)."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import yaml
from homeassistant.config_entries import ConfigEntry

from custom_components.ramses_extras.features.floorplan_helper import (
    generator,
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
        entities = {r["entity"] for r in rules}
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
        assert rules[-1]["entity"] == "light.kitchen"

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
