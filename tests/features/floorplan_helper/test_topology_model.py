"""Tests for ``topology.build_floorplan_model`` sub-device mapping.

ramses_cc registers HA sub-devices for controller zones
(``<ctl_id>_<zone_idx>``) and hot water (``<ctl_id>_HW``). Their
entities must map onto the physical sensor/actuator (or the
controller when no dedicated sensor exists) so zones don't spawn
orphan "unknown" markers on the floorplan.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.ramses_extras.features.floorplan_helper import topology
from custom_components.ramses_extras.features.floorplan_helper.domains import (
    STAT_DOMAIN,
    device_class_from_id,
)


def _ent(entity_id, device_id="dev-1", platform="ramses_cc"):
    e = MagicMock(spec=er.RegistryEntry)
    e.entity_id = entity_id
    e.device_id = device_id
    e.platform = platform
    e.name = None
    e.original_name = None
    e.area_id = None
    return e


def _device_entry(ident, ha_id="dev-1", area_id=None):
    d = MagicMock(spec=dr.DeviceEntry)
    d.id = ha_id
    d.identifiers = {("ramses_cc", ident)}
    d.area_id = area_id
    return d


def _hass_with(monkeypatch, reg, dev_reg, stored_schema=None, runtime_schema=None):
    # monkeypatch (not patch().start) so the registry/coordinator
    # stand-ins unwind after the test — a leaked er.async_get mock
    # breaks every later test that touches the HA registries
    hass = MagicMock()
    area_reg = MagicMock()
    area_reg.areas = {}
    floor_reg = MagicMock()
    floor_reg.floors = {}
    coordinator = MagicMock()
    coordinator.options = {"schema": stored_schema or {}}
    coordinator.client.device_registry.device_by_id = {}
    zone_reg = MagicMock()
    zone_reg.list_all_zones.return_value = {}
    monkeypatch.setattr(topology.er, "async_get", lambda hass: reg)
    monkeypatch.setattr(topology.dr, "async_get", lambda hass: dev_reg)
    monkeypatch.setattr(topology.ar, "async_get", lambda hass: area_reg)
    monkeypatch.setattr(topology.fr, "async_get", lambda hass: floor_reg)
    monkeypatch.setattr(topology, "get_ramses_cc_coordinator", lambda hass: coordinator)
    monkeypatch.setattr(
        topology,
        "get_runtime_schema",
        AsyncMock(return_value=runtime_schema or {}),
    )
    monkeypatch.setattr(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        lambda hass: zone_reg,
    )
    return hass


class TestSubdeviceMapping:
    """Entities on ``<ctl>_<zone>`` / ``<ctl>_HW`` sub-devices resolve
    onto the zone's physical sensor/actuator device."""

    RUNTIME = {
        "01:000001": {
            "zones": {
                "01": {"sensor": "34:000001", "actuators": ["04:150001"]},
                "02": {"actuators": ["04:150002"]},
            },
            "stored_hotwater": {"sensor": "07:150000"},
        }
    }

    def _registry(self, device_entries):
        dev_reg = MagicMock(spec=dr.DeviceRegistry)
        dev_reg.async_get.side_effect = lambda did: next(
            (d for d in device_entries if d.id == did), None
        )
        dev_reg.async_get_device.side_effect = lambda identifiers: next(
            (d for d in device_entries if set(identifiers) <= set(d.identifiers)),
            None,
        )
        return dev_reg

    @pytest.mark.asyncio
    async def test_zone_subdevice_maps_to_zone_sensor(self, monkeypatch):
        dev_zone = _device_entry("01:000001_01", ha_id="d1")
        dev_hw = _device_entry("01:000001_HW", ha_id="d2")
        dev_unknown = _device_entry("01:000001_99", ha_id="d3")
        reg = MagicMock(spec=er.EntityRegistry)
        reg.entities = {
            "sensor.z1_temp": _ent("sensor.z1_temp", "d1"),
            "sensor.hw_temp": _ent("sensor.hw_temp", "d2"),
            "sensor.orphan": _ent("sensor.orphan", "d3"),
        }
        hass = _hass_with(
            monkeypatch,
            reg,
            self._registry([dev_zone, dev_hw, dev_unknown]),
            runtime_schema=self.RUNTIME,
        )
        model = await topology.build_floorplan_model(hass)
        ids = {d["device_id"] for d in model["devices"]}
        # zone sub-device entities land on the physical zone sensor,
        # the HW sub-device on the DHW sensor — no *_01 / *_HW / *_99
        # orphan markers appear
        assert "01:000001_01" not in ids
        assert "01:000001_HW" not in ids
        assert "01:000001_99" not in ids
        assert "34:000001" in ids
        assert "07:150000" in ids
        ents = {e["entity_id"] for d in model["devices"] for e in d["entities"]}
        assert "sensor.z1_temp" in ents
        assert "sensor.hw_temp" in ents
        # an unresolvable sub-device is dropped, not parked as unknown
        assert "sensor.orphan" not in ents

    @pytest.mark.asyncio
    async def test_zone_without_sensor_maps_to_single_actuator(self, monkeypatch):
        dev_zone = _device_entry("01:000001_02", ha_id="d4")
        reg = MagicMock(spec=er.EntityRegistry)
        reg.entities = {"sensor.z2": _ent("sensor.z2", "d4")}
        hass = _hass_with(
            monkeypatch,
            reg,
            self._registry([dev_zone]),
            runtime_schema=self.RUNTIME,
        )
        model = await topology.build_floorplan_model(hass)
        ids = {d["device_id"] for d in model["devices"]}
        # zone 02 has no sensor — its one actuator owns the entities
        assert "04:150002" in ids
        assert "01:000001_02" not in ids

    @pytest.mark.asyncio
    async def test_stored_schema_fills_subdevice_map(self, monkeypatch):
        # when the runtime schema lacks the zone config, the stored
        # options schema supplies the mapping
        dev_zone = _device_entry("01:000001_01", ha_id="d1")
        reg = MagicMock(spec=er.EntityRegistry)
        reg.entities = {"sensor.z1_temp": _ent("sensor.z1_temp", "d1")}
        hass = _hass_with(
            monkeypatch,
            reg,
            self._registry([dev_zone]),
            stored_schema=self.RUNTIME,
            runtime_schema={},
        )
        model = await topology.build_floorplan_model(hass)
        ids = {d["device_id"] for d in model["devices"]}
        assert "34:000001" in ids
        assert "01:000001_01" not in ids


class TestDomainCoverage:
    def test_thermostat_classes_land_in_heat_domain(self):
        # THM/RND/SEN/ZON (the sim's thermostat variants) join DTS/DT2
        # in the heat domain so they don't fall to "other"
        for cls in ("DTS", "DT2", "THM", "RND", "SEN", "ZON"):
            assert cls in STAT_DOMAIN.device_classes

    def test_thm_id_prefix_resolves(self):
        assert device_class_from_id("34:000001") in STAT_DOMAIN.device_classes
