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

_LOGGER = logging.getLogger(__name__)

RAMSES_PLATFORMS = ("ramses_cc", "ramses_extras")

# Domains considered for a device's "primary" element, in preference order.
_PRIMARY_DOMAIN_ORDER = ("climate", "water_heater", "fan", "switch")


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
            else "unknown"
        )
        if device_id.startswith("18:") or device_class == "HGI":
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
                "display_name": _display_name(device_id, entities, ha_device),
                "primary_entity": primary,
                "entities": entities,
            }
        )

    return {
        "devices": devices,
        "areas": areas,
        "floors": floors,
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
) -> str:
    """Human label for a device on the floorplan."""
    if ha_device is not None:
        name = ha_device.name_by_user or ha_device.name
        if name:
            return str(name)
    for e in entities:
        if e["domain"] in _PRIMARY_DOMAIN_ORDER:
            return str(e["entity_id"]).split(".", 1)[-1]
    return device_id


__all__ = ["build_floorplan_model"]
