"""Helpers for mapping RAMSES devices to Home Assistant entities."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


def normalize_ramses_id(device_id: str | None) -> str | None:
    """Normalize a RAMSES device identifier to its base form.

    ramses_cc uses identifiers like ``01:123456`` for devices and may append
    suffixes (e.g. ``_03`` for zone members). The simulator only tracks the
    base ID, so strip any suffix after the first underscore when the prefix
    still looks like a RAMSES ID (contains a colon).
    """

    if not device_id or not isinstance(device_id, str):
        return None

    candidate = device_id.strip().upper()
    if ":" not in candidate:
        return candidate

    if "_" not in candidate:
        return candidate

    base, _suffix = candidate.split("_", 1)
    if ":" in base:
        return base
    return candidate


def get_device_entities(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """Return entity metadata for a RAMSES device ID.

    Looks up the HA device registry entry for the provided RAMSES device ID and
    returns a lightweight list of entities (ID, domain, name, availability, state).
    """

    try:
        entity_reg = er.async_get(hass)
        device_reg = dr.async_get(hass)
    except Exception:  # pragma: no cover - registry unavailable
        return []

    normalized_target = normalize_ramses_id(device_id)
    if not normalized_target:
        return []

    matching_device_entry_ids: set[str] = set()
    for dev in device_reg.devices.values():
        for domain, identifier in dev.identifiers:
            if domain != "ramses_cc":
                continue
            if normalize_ramses_id(identifier) == normalized_target:
                matching_device_entry_ids.add(dev.id)
                break

    if not matching_device_entry_ids:
        return []

    entities: list[dict[str, Any]] = []
    for entity_entry in entity_reg.entities.values():
        if entity_entry.device_id not in matching_device_entry_ids:
            continue
        state = hass.states.get(entity_entry.entity_id)
        entities.append(
            {
                "entity_id": entity_entry.entity_id,
                "domain": entity_entry.domain,
                "name": entity_entry.name or entity_entry.entity_id.split(".")[-1],
                "available": state is not None and state.state != "unavailable",
                "state": state.state if state else "unavailable",
            }
        )

    return entities
