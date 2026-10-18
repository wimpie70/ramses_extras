"""Shared RAMSES topology helpers.

Extracted from the device_status_card websocket commands so both the
status card and the floorplan_helper feature can derive the same
system topology (heat / hvac / hgi / orphan grouping with parent
links) from the ramses_cc coordinator and runtime schema.

:platform: Home Assistant
"""

import logging
import re
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DEVICE_ID_RE = re.compile(r"^\d{2}:\d{6}$")

# Schema keys that are metadata, not per-system device dicts.
SCHEMA_META_KEYS = frozenset(
    {"main_tcs", "orphans_heat", "orphans_hvac", "_owner", "transport_constructor"}
)


def get_ramses_cc_coordinator(hass: HomeAssistant) -> Any | None:
    """Return the first ramses_cc coordinator, or None.

    :param hass: Home Assistant instance
    :return: ramses_cc coordinator or None when ramses_cc is not loaded
    """
    for entry in hass.config_entries.async_entries("ramses_cc"):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None and getattr(coordinator, "client", None):
            return coordinator
    return None


def collect_device_ids(value: Any, out: set[str]) -> None:
    """Recursively collect device IDs from a schema subtree.

    :param value: Schema value to scan
    :param out: Set to accumulate device IDs into
    """
    if isinstance(value, str):
        if DEVICE_ID_RE.match(value):
            out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            collect_device_ids(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            collect_device_ids(v, out)


def build_topology(schema: Any) -> dict[str, dict[str, Any]]:
    """Map device IDs to topology groups from ``gateway.schema()``.

    Returns ``{device_id: {"group": ..., "parent": ...}}`` where group
    is ``"heat"`` (controller + zone/DHW/system children), ``"hvac"``
    (FAN + bound remotes/sensors), or ``"orphan"``.  HGI rows are
    assigned ``"hgi"`` separately by callers since HGIs never appear
    in the runtime schema.

    :param schema: Runtime schema dict from ``client.schema()``
    :return: Mapping of device id to group/parent info
    """
    topo: dict[str, dict[str, Any]] = {}
    if not isinstance(schema, dict):
        return topo

    main_tcs = schema.get("main_tcs")
    for key, value in schema.items():
        if key in SCHEMA_META_KEYS or not isinstance(value, dict):
            continue
        if (
            "zones" in value
            or "system" in value
            or "stored_hotwater" in value
            or key == main_tcs
        ):
            group = "heat"
        elif "remotes" in value or "sensors" in value:
            group = "hvac"
        else:
            continue
        topo.setdefault(str(key), {"group": group})
        children: set[str] = set()
        collect_device_ids(value, children)
        children.discard(str(key))
        for child in children:
            topo.setdefault(child, {"group": group, "parent": str(key)})

    for orphan_key in ("orphans_heat", "orphans_hvac"):
        for orphan in schema.get(orphan_key) or []:
            topo.setdefault(str(orphan), {"group": "orphan"})
    return topo


def build_owner_map(coordinator: Any) -> dict[str, str]:
    """Classify devices as ``owned`` / ``foreign`` / ``unowned``.

    Uses the config-entry schema: devices with an ``_owner`` different
    from the root ``_owner`` are foreign (a neighbour's devices adopted
    for monitoring); devices absent from the schema — or HGIs with no
    ``_owner`` yet (discovery candidates) — are unowned.

    :param coordinator: ramses_cc coordinator
    :return: Mapping of device id to ownership class
    """
    options = getattr(coordinator, "options", None)
    schema = options.get("schema", {}) if isinstance(options, Mapping) else {}
    if not isinstance(schema, dict) or not schema:
        return {}

    root_owner = schema.get("_owner")
    all_ids: set[str] = set()
    collect_device_ids(schema, all_ids)

    owners: dict[str, str] = {}
    for key, value in schema.items():
        if not DEVICE_ID_RE.match(str(key)):
            continue
        entry = value if isinstance(value, dict) else {}
        entry_owner = entry.get("_owner")
        if entry_owner and root_owner and entry_owner != root_owner:
            owners[str(key)] = "foreign"
        elif (
            str(key).startswith("18:")
            and entry.get("_class") == "HGI"
            and not entry_owner
            and root_owner
        ):
            # HGIs without an _owner are discovery candidates, not
            # accepted pool members.
            owners[str(key)] = "unowned"
        else:
            owners.setdefault(str(key), "owned")
    for dev_id in all_ids:
        owners.setdefault(dev_id, "owned")
    return owners


async def get_runtime_schema(coordinator: Any) -> dict[str, Any]:
    """Fetch the ramses_rf runtime schema from a coordinator's client.

    :param coordinator: ramses_cc coordinator (may be None)
    :return: Runtime schema dict, empty on failure
    """
    client = getattr(coordinator, "client", None)
    if client is None or not hasattr(client, "schema"):
        return {}
    try:
        schema = await client.schema()
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not build runtime schema for topology: %s", err)
        return {}
    return schema if isinstance(schema, dict) else {}


__all__ = [
    "DEVICE_ID_RE",
    "SCHEMA_META_KEYS",
    "build_owner_map",
    "build_topology",
    "collect_device_ids",
    "get_ramses_cc_coordinator",
    "get_runtime_schema",
]
