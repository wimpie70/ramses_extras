"""Floorplan topology model builder.

Combines the RAMSES device topology (heat / hvac / hgi / orphan,
parent links) with the HA entity/device/area registries to produce a
per-device model:

- which entities belong to the device
- which HA area (and floor) the device lives in
- which entity is the "primary" element candidate (the one that gets
  the icon on the floorplan)

The model is consumed by generator.py to emit the ha-floorplan bundle.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    floor_registry as fr,
)

from ...framework.helpers.ramses_topology import (
    build_topology,
    get_ramses_cc_coordinator,
    get_runtime_schema,
)
from .const import ENTITY_ROLE_PATTERNS
from .domains import device_class_from_id

_LOGGER = logging.getLogger(__name__)

RAMSES_PLATFORMS = ("ramses_cc", "ramses_extras")

# Domains considered for a device's "primary" element, in preference
# order. remote.* before the bare-entity fallback: remotes carry the
# "REM 37:…" / "DIS 37:…" friendly names — falling through to the first
# entity (usually *_battery_low) made every marker say "battery".
_PRIMARY_DOMAIN_ORDER = ("climate", "water_heater", "remote", "fan", "switch")


def _classify_entity(entity_id: str) -> str:
    """Classify an entity into a semantic role used by rule generation.

    :param entity_id: e.g. ``sensor.32_153289_fan_rate``
    :return: role string such as ``fan_rate`` or ``other``
    """
    name = entity_id.split(".", 1)[-1].lower()
    for role, patterns in ENTITY_ROLE_PATTERNS.items():
        if any(pattern in name for pattern in patterns):
            return role
    return "other"


def _ha_device_for_ramses_id(
    device_registry: dr.DeviceRegistry, ramses_device_id: str
) -> dr.DeviceEntry | None:
    """Find the HA device entry whose identifiers contain a ramses id."""
    for platform in RAMSES_PLATFORMS:
        entry = device_registry.async_get_device(
            identifiers={(platform, ramses_device_id)}
        )
        if entry is not None:
            return entry
    return None


def _entity_area(
    entity_entry: er.RegistryEntry,
    device_entry: dr.DeviceEntry | None,
) -> str | None:
    """Resolve the HA area for an entity (entity override wins)."""
    if entity_entry.area_id:
        return str(entity_entry.area_id)
    if device_entry is not None and device_entry.area_id:
        return str(device_entry.area_id)
    return None


async def build_floorplan_model(hass: HomeAssistant) -> dict[str, Any]:
    """Build the floorplan model.

    :param hass: Home Assistant instance
    :return: Model dict with devices, areas, floors and unassigned lists
    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)
    floor_registry = fr.async_get(hass)

    coordinator = get_ramses_cc_coordinator(hass)
    runtime_schema = await get_runtime_schema(coordinator)
    topo = build_topology(runtime_schema)

    registry = getattr(getattr(coordinator, "client", None), "device_registry", None)
    ramses_devices = getattr(registry, "device_by_id", {}) or {}

    stored_schema: dict[str, Any] = {}
    coordinator_options = getattr(coordinator, "options", None)
    if isinstance(coordinator_options, Mapping):
        stored = coordinator_options.get("schema")
        if isinstance(stored, dict):
            stored_schema = stored

    # ramses_cc registers HA sub-devices for controller zones
    # (<ctl_id>_<zone_idx>) and hot-water (<ctl_id>_HW). Map their
    # entities onto the corresponding physical sensor/actuator device
    # (or the controller when no dedicated sensor exists) so zones do
    # not spawn orphan "unknown" markers on the floorplan.
    subdevice_owner: dict[str, str | None] = {}
    for schema_src in (stored_schema, runtime_schema):
        for tcs_id, tcs in schema_src.items():
            if not isinstance(tcs, dict):
                continue
            dhw = tcs.get("stored_hotwater")
            if isinstance(dhw, dict):
                dhw_sensor = dhw.get("sensor")
                subdevice_owner[f"{tcs_id}_HW"] = (
                    str(dhw_sensor) if dhw_sensor else str(tcs_id)
                )
            for zid, zcfg in (tcs.get("zones") or {}).items():
                if not isinstance(zcfg, dict):
                    continue
                zsensor = zcfg.get("sensor")
                zacts = [str(a) for a in (zcfg.get("actuators") or []) if a]
                target = (
                    str(zsensor) if zsensor else (zacts[0] if len(zacts) == 1 else None)
                )
                subdevice_owner[f"{tcs_id}_{zid}"] = target

    # Index HA entities per ramses device id.
    entities_by_device: dict[str, list[dict[str, Any]]] = {}
    for entry in entity_registry.entities.values():
        if entry.platform not in RAMSES_PLATFORMS:
            continue
        raw_device = (
            device_registry.async_get(entry.device_id) if entry.device_id else None
        )
        device_entry = raw_device if isinstance(raw_device, dr.DeviceEntry) else None
        ramses_id = _ramses_id_from_device(device_entry)
        if ramses_id is None:
            # Entities with no device or no ramses identifier are skipped;
            # the floorplan binds devices, not loose entities.
            continue
        if "_" in ramses_id:
            mapped = subdevice_owner.get(ramses_id)
            if not mapped:
                continue
            ramses_id = mapped
        entities_by_device.setdefault(ramses_id, []).append(
            {
                "entity_id": entry.entity_id,
                "domain": entry.entity_id.split(".", 1)[0],
                "role": _classify_entity(entry.entity_id),
                "area_id": _entity_area(entry, device_entry),
                "name": entry.name or entry.original_name or "",
            }
        )

    # Areas and floors for grouping + labels.
    areas = {
        area_id: {
            "name": area.name,
            "floor_id": area.floor_id,
        }
        for area_id, area in area_registry.areas.items()
    }
    floors = {
        floor_id: {"name": floor.name, "level": floor.level}
        for floor_id, floor in floor_registry.floors.items()
    }

    devices: list[dict[str, Any]] = []
    for device_id in sorted(set(ramses_devices) | set(entities_by_device)):
        device = ramses_devices.get(device_id)
        device_class = (
            getattr(device, "_SLUG", None) or type(device).__name__
            if device is not None
            # no rf object — infer from the id prefix (ramses_rf's
            # DEVICE_ID_REGEX: 18:* → HGI, 07:* → DHW…)
            else device_class_from_id(device_id) or "unknown"
        )
        if device_class_from_id(device_id) == "HGI" or device_class == "HGI":
            device_class = "HGI"

        entities = entities_by_device.get(device_id, [])
        topo_info = topo.get(device_id, {})
        group = "hgi" if device_class == "HGI" else topo_info.get("group", "orphan")

        ha_device = _ha_device_for_ramses_id(device_registry, device_id)
        area_id = next(
            (e["area_id"] for e in entities if e["area_id"]),
            ha_device.area_id if ha_device is not None else None,
        )

        primary = _select_primary_entity(entities)
        devices.append(
            {
                "device_id": device_id,
                "device_class": device_class,
                "group": group,
                "parent": topo_info.get("parent"),
                "area_id": area_id,
                "area_name": areas.get(area_id, {}).get("name") if area_id else None,
                "display_name": _display_name(
                    device_id, entities, ha_device, device_class
                ),
                "primary_entity": primary,
                "entities": entities,
            }
        )

    # Non-ramses entities wired into _extras features (paired-valve
    # zones, zone sensors/actuators) — the floorplan treats them as
    # standalone members so everything _extras uses is visible and
    # draggable in studio.
    from ...framework.helpers.zones import get_zone_registry

    model_ids = {str(e["entity_id"]) for d in devices for e in d.get("entities") or []}
    extras_entities: set[str] = set()
    for zones in get_zone_registry(hass).list_all_zones().values():
        for zone in zones:
            for key in ("inlet_valve_entity", "outlet_valve_entity"):
                if zone.get(key):
                    extras_entities.add(str(zone[key]))
            extras_entities.update(
                str(ent) for ent in (zone.get("sensors") or {}).values() if ent
            )
            actuator = zone.get("actuator") or {}
            if actuator.get("entity_id"):
                extras_entities.add(str(actuator["entity_id"]))
    extras_entities.difference_update(model_ids)

    # Evohome zone topology, for zone auto-seeding: each TCS zone
    # carries its room name, zone sensor and actuator devices. ``_name``
    # is only reliable in the stored schema (the runtime schema may not
    # have hydrated names yet), so merge that in.
    heat_zones: list[dict[str, Any]] = []
    if isinstance(runtime_schema, dict):
        for tcs_id, tcs in runtime_schema.items():
            if not isinstance(tcs, dict):
                continue
            stored_zones = (stored_schema.get(str(tcs_id)) or {}).get("zones") or {}
            for zone_id, zone in (tcs.get("zones") or {}).items():
                if not isinstance(zone, dict):
                    continue
                stored_zone = stored_zones.get(str(zone_id)) or {}
                # Stored (user-declared) name wins over the packet-learned
                # runtime name — renames in the config flow take effect.
                heat_zones.append(
                    {
                        "ctl_id": str(tcs_id),
                        "zone_id": str(zone_id),
                        "name": str(
                            stored_zone.get("_name")
                            or zone.get("_name")
                            or f"zone {zone_id}"
                        ),
                        "sensor": str(zone["sensor"]) if zone.get("sensor") else None,
                        "actuators": [str(a) for a in zone.get("actuators") or []],
                        "class": str(zone.get("class") or ""),
                    }
                )

    return {
        "devices": devices,
        "areas": areas,
        "floors": floors,
        "extras_entities": sorted(extras_entities),
        "heat_zones": heat_zones,
    }


def _ramses_id_from_device(device_entry: dr.DeviceEntry | None) -> str | None:
    """Extract the ramses device id from a HA device entry's identifiers."""
    if device_entry is None:
        return None
    for platform, ident in device_entry.identifiers:
        if platform in RAMSES_PLATFORMS:
            return str(ident)
    return None


def _select_primary_entity(entities: list[dict[str, Any]]) -> str | None:
    """Pick the entity that represents the device on the floorplan."""
    by_domain: dict[str, str] = {}
    for e in entities:
        by_domain.setdefault(e["domain"], e["entity_id"])
    for domain in _PRIMARY_DOMAIN_ORDER:
        if domain in by_domain:
            return by_domain[domain]
    return entities[0]["entity_id"] if entities else None


def _display_name(
    device_id: str,
    entities: list[dict[str, Any]],
    ha_device: dr.DeviceEntry | None,
    device_class: str = "",
) -> str:
    """Human label for a device on the floorplan.

    Prefers the HA device name (alias when the user set one), then the
    friendly name of a representative entity (``remote.37_…`` → "REM
    37:…"), then ``<slug> <id>`` — e.g. "REM 37:169161" — rather than a
    bare entity slug like ``37_169161_battery_low``.
    """
    if ha_device is not None:
        name = ha_device.name_by_user or ha_device.name
        if name:
            return str(name)
    if device_class and device_class != "unknown":
        return f"{device_class} {device_id}"
    for e in entities:
        if e["domain"] in _PRIMARY_DOMAIN_ORDER:
            return str(e["entity_id"]).split(".", 1)[-1]
    return device_id


__all__ = ["build_floorplan_model"]
