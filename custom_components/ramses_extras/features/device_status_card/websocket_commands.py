# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""WebSocket commands for the Device Status Card feature.

Provides a fleet snapshot: all known RAMSES devices with their
communication status and signal quality, plus pool health when a
multi-HGI pool is configured.

Data sources (ramses_cc issue 1210 / ramses_extras issue 227):

- Primary: ``binary_sensor.<device>_status`` entities and their
  attributes (last_seen, staleness, RSSI per HGI, missed polls).
- Fallback: the ramses_rf device's own ``is_available`` /
  ``communication_quality`` signals for older ramses_cc versions.

:platform: Home Assistant
:feature: Device Status Card WebSocket Commands
"""

import logging
from datetime import datetime as dt
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.ramses_topology import (
    build_owner_map,
    build_topology,
    get_ramses_cc_coordinator,
    get_runtime_schema,
)
from custom_components.ramses_extras.framework.helpers.transport_monitor import (
    get_transport_monitor,
)

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection

_LOGGER = logging.getLogger(__name__)


async def _device_rows(hass: HomeAssistant, coordinator: Any) -> list[dict[str, Any]]:
    """Build the per-device status rows.

    :param hass: Home Assistant instance
    :param coordinator: The ramses_cc coordinator (or None)
    :return: List of device status dictionaries
    """
    monitor = get_transport_monitor()
    status_entities = monitor.device_status_entity_ids

    registry = getattr(getattr(coordinator, "client", None), "device_registry", None)
    devices = getattr(registry, "device_by_id", {}) or {}

    runtime_schema = await get_runtime_schema(coordinator)
    topo = build_topology(runtime_schema)
    owners = build_owner_map(coordinator) if coordinator is not None else {}

    def _classify(device_id: str, row: dict[str, Any]) -> None:
        info = topo.get(device_id)
        if info:
            row["group"] = info["group"]
            if parent := info.get("parent"):
                row["parent"] = parent
        else:
            row["group"] = "orphan"
        # Only classify ownership when a config schema exists — without
        # one, every device would look "unowned".
        if owners:
            row["owner"] = owners.get(device_id, "unowned")

    rows: list[dict[str, Any]] = []
    for device_id, device in devices.items():
        row: dict[str, Any] = {
            "id": str(device_id),
            "class": getattr(device, "_SLUG", None) or type(device).__name__,
        }

        status_entity_id = status_entities.get(str(device_id))
        state = hass.states.get(status_entity_id) if status_entity_id else None
        if state is not None and state.state not in ("unknown", "unavailable"):
            # Primary: the ramses_cc status entity carries everything.
            row["status"] = state.state
            row["status_entity_id"] = status_entity_id
            for key in (
                "last_seen",
                "staleness_seconds",
                "heartbeat_timeout",
                "consecutive_missed_polls",
                "best_rssi",
                "rssi_quality",
                "is_stale",
                "rssi_per_hgi",
                "last_known_rssi",
                "last_known_rssi_per_hgi",
                "last_rssi_seen",
                "last_rssi_age_seconds",
            ):
                if key in state.attributes:
                    row[key] = state.attributes[key]
            row["source"] = "entity"
        else:
            # Fallback: the ramses_rf device object itself.
            row["status"] = "on" if getattr(device, "is_available", True) else "off"
            quality = getattr(device, "communication_quality", None)
            if quality is not None:
                row["best_rssi"] = getattr(quality, "best_rssi", None)
                row["rssi_quality"] = getattr(quality, "rssi_quality", None)
                row["is_stale"] = getattr(quality, "is_stale", None)
                last_seen = getattr(quality, "last_seen", None)
                row["last_seen"] = (
                    last_seen.isoformat() if isinstance(last_seen, dt) else last_seen
                )
                row["staleness_seconds"] = getattr(quality, "staleness_seconds", None)
            timeout = getattr(device, "heartbeat_timeout", None)
            row["heartbeat_timeout"] = (
                timeout.total_seconds() if timeout is not None else None
            )
            row["consecutive_missed_polls"] = getattr(
                device, "consecutive_missed_polls", 0
            )
            rssi_per_hgi = getattr(device, "rssi_per_hgi", None)
            row["rssi_per_hgi"] = (
                dict(rssi_per_hgi) if isinstance(rssi_per_hgi, dict) else {}
            )
            row["source"] = "device"

        _classify(str(device_id), row)
        if row.get("class") == "HGI" or str(device_id).startswith("18:"):
            row["group"] = "hgi"
        rows.append(row)

    # Pool HGIs: the per-HGI ``*_online`` entity is the transport-level
    # source of truth. An HGI's rf device object can report
    # ``is_available=True`` while its pool child is offline, so overlay
    # the entity state onto existing device rows — and add rows for
    # HGIs with no device object at all (e.g. a zigbee-only HGI whose
    # transport was never created).
    rows_by_id = {r["id"]: r for r in rows}
    for hgi_id, entity_id in monitor.hgi_online_entity_ids.items():
        hgi_state = hass.states.get(entity_id)
        hgi_row = rows_by_id.get(hgi_id)
        if hgi_row is None:
            hgi_row = {"id": hgi_id, "source": "hgi"}
            rows.append(hgi_row)
            rows_by_id[hgi_id] = hgi_row
            _classify(hgi_id, hgi_row)
        hgi_row["class"] = "HGI"
        hgi_row["group"] = "hgi"
        hgi_row["status"] = (
            "on" if hgi_state is not None and hgi_state.state == "on" else "off"
        )
        hgi_row["status_entity_id"] = entity_id
        if hgi_state is not None:
            for key in ("connected", "availability", "pkts_received", "last_pkt_time"):
                if key in hgi_state.attributes:
                    hgi_row[key] = hgi_state.attributes[key]

    return rows


def _pool_section(hass: HomeAssistant) -> dict[str, Any] | None:
    """Build the pool health section, or None when no pool exists.

    :param hass: Home Assistant instance
    :return: Pool status dictionary or None
    """
    monitor = get_transport_monitor()
    if not monitor.pool_status_entity_id and not monitor.hgi_online_entity_ids:
        return None

    pool: dict[str, Any] = {"hgis": []}
    state = hass.states.get(monitor.pool_status_entity_id or "")
    if state is not None:
        pool["status"] = state.state
        for key in ("children_online", "children_total"):
            if key in state.attributes:
                pool[key] = state.attributes[key]

    for hgi_id, entity_id in monitor.hgi_online_entity_ids.items():
        hgi_state = hass.states.get(entity_id)
        hgi: dict[str, Any] = {
            "hgi_id": hgi_id,
            "entity_id": entity_id,
            "online": (hgi_state.state == "on" if hgi_state is not None else None),
        }
        if hgi_state is not None:
            for key in (
                "connected",
                "availability",
                "pkts_received",
                "last_pkt_time",
                "callback_driven",
            ):
                if key in hgi_state.attributes:
                    hgi[key] = hgi_state.attributes[key]
        pool["hgis"].append(hgi)

    return pool


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/device_status_card/get_device_status",
    }
)
@websocket_api.async_response
async def ws_get_device_status(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a snapshot of all RAMSES devices' status and quality."""
    try:
        # Refresh entity discovery so newly created/renamed status
        # entities are picked up.
        get_transport_monitor().refresh_entity_discovery(hass)

        coordinator = get_ramses_cc_coordinator(hass)

        connection.send_result(
            msg["id"],
            {
                "devices": await _device_rows(hass, coordinator),
                "pool": _pool_section(hass),
            },
        )
    except Exception as err:
        _LOGGER.error("Failed to build device status snapshot: %s", err)
        connection.send_error(
            msg["id"], "snapshot_failed", "Failed to build device status"
        )
