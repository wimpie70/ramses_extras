"""Tests for device_status_card websocket commands."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.device_status_card import (
    websocket_commands,
)

ws_get_device_status = websocket_commands.ws_get_device_status.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))


def _make_hass(states: dict[str, Any] | None = None) -> MagicMock:
    """Build a mock hass with the given entity states."""
    mock_hass = MagicMock(spec=HomeAssistant)
    mock_hass.data = {}

    def _get_state(entity_id: str) -> Any:
        return (states or {}).get(entity_id)

    mock_hass.states = MagicMock()
    mock_hass.states.get = MagicMock(side_effect=_get_state)
    return mock_hass


def _make_coordinator(devices: dict[str, Any]) -> MagicMock:
    """Build a mock ramses_cc coordinator exposing the given devices."""
    registry = SimpleNamespace(device_by_id=devices)
    coordinator = MagicMock()
    coordinator.client.device_registry = registry
    return coordinator


def _make_monitor(
    status_entities: dict[str, str] | None = None,
    pool_entity: str | None = None,
    hgi_entities: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock transport monitor with the given discovery maps."""
    monitor = MagicMock()
    monitor.device_status_entity_ids = status_entities or {}
    monitor.pool_status_entity_id = pool_entity
    monitor.hgi_online_entity_ids = hgi_entities or {}
    return monitor


def _state(state: str, **attrs: Any) -> SimpleNamespace:
    return SimpleNamespace(state=state, attributes=dict(attrs))


@pytest.fixture
def _patch_coordinator():
    """Patch the ramses_cc coordinator lookup."""
    with patch.object(websocket_commands, "_get_ramses_cc_coordinator") as mock_get:
        yield mock_get


@pytest.fixture
def _patch_monitor():
    """Patch the global transport monitor lookup."""
    with patch.object(websocket_commands, "get_transport_monitor") as mock_get:
        yield mock_get


@pytest.mark.asyncio
async def test_snapshot_uses_status_entity_attributes(
    _patch_coordinator, _patch_monitor
):
    """Rows are built from the ramses_cc status entity when present."""
    device = SimpleNamespace(_SLUG="FAN", is_available=True)
    coordinator = _make_coordinator({"32:153289": device})
    _patch_coordinator.return_value = coordinator

    monitor = _make_monitor(
        status_entities={"32:153289": "binary_sensor.fan_32_153289_status"},
        pool_entity="binary_sensor.pool_status",
        hgi_entities={"18:130236": "binary_sensor.hgi_18_130236_online"},
    )
    _patch_monitor.return_value = monitor

    hass = _make_hass(
        {
            "binary_sensor.fan_32_153289_status": _state(
                "on",
                last_seen="2026-09-19T10:59:02",
                staleness_seconds=154.8,
                heartbeat_timeout=900.0,
                consecutive_missed_polls=0,
                best_rssi=-36,
                rssi_quality="strong",
                is_stale=False,
                rssi_per_hgi={"18:130236": -36},
            ),
            "binary_sensor.pool_status": _state(
                "on", children_online=2, children_total=3
            ),
            "binary_sensor.hgi_18_130236_online": _state(
                "on",
                connected=True,
                availability="ONLINE",
                pkts_received=1234,
            ),
        }
    )

    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 1})

    assert not conn.errors
    assert len(conn.results) == 1
    payload = conn.results[0][1]

    # 1 device + 1 HGI row for the pool child absent from device_by_id
    assert len(payload["devices"]) == 2
    row = next(d for d in payload["devices"] if d["id"] == "32:153289")
    assert row["class"] == "FAN"
    assert row["status"] == "on"
    assert row["source"] == "entity"
    assert row["status_entity_id"] == "binary_sensor.fan_32_153289_status"
    assert row["best_rssi"] == -36
    assert row["rssi_quality"] == "strong"
    assert row["rssi_per_hgi"] == {"18:130236": -36}
    assert row["heartbeat_timeout"] == 900.0

    pool = payload["pool"]
    assert pool["status"] == "on"
    assert pool["children_online"] == 2
    assert pool["children_total"] == 3
    assert pool["hgis"][0]["hgi_id"] == "18:130236"
    assert pool["hgis"][0]["online"] is True
    assert pool["hgis"][0]["pkts_received"] == 1234


@pytest.mark.asyncio
async def test_snapshot_falls_back_to_device_signals(
    _patch_coordinator, _patch_monitor
):
    """Without a status entity, device signals from ramses_rf are used."""
    quality = SimpleNamespace(
        best_rssi=-52,
        rssi_quality="ok",
        is_stale=False,
        last_seen="2026-09-19T11:00:00",
        staleness_seconds=42.0,
    )
    device = SimpleNamespace(
        _SLUG="REM",
        is_available=True,
        communication_quality=quality,
        heartbeat_timeout=None,
        consecutive_missed_polls=0,
        rssi_per_hgi={"18:149488": -52},
    )
    coordinator = _make_coordinator({"37:169161": device})
    _patch_coordinator.return_value = coordinator

    _patch_monitor.return_value = _make_monitor()

    hass = _make_hass()
    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 2})

    assert not conn.errors
    row = conn.results[0][1]["devices"][0]
    assert row["id"] == "37:169161"
    assert row["status"] == "on"
    assert row["source"] == "device"
    assert row["best_rssi"] == -52
    assert row["rssi_quality"] == "ok"
    assert row["rssi_per_hgi"] == {"18:149488": -52}


@pytest.mark.asyncio
async def test_snapshot_offline_device_from_entity(_patch_coordinator, _patch_monitor):
    """An 'off' status entity produces an offline row."""
    device = SimpleNamespace(_SLUG="FAN", is_available=False)
    coordinator = _make_coordinator({"32:153289": device})
    _patch_coordinator.return_value = coordinator

    _patch_monitor.return_value = _make_monitor(
        status_entities={"32:153289": "binary_sensor.fan_32_153289_status"},
    )

    hass = _make_hass(
        {
            "binary_sensor.fan_32_153289_status": _state(
                "off",
                staleness_seconds=1200.0,
                consecutive_missed_polls=3,
                best_rssi=None,
                rssi_per_hgi={},
            ),
        }
    )

    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 3})

    row = conn.results[0][1]["devices"][0]
    assert row["status"] == "off"
    assert row["source"] == "entity"
    assert row["consecutive_missed_polls"] == 3


@pytest.mark.asyncio
async def test_snapshot_includes_pool_hgi_without_device_object(
    _patch_coordinator, _patch_monitor
):
    """Pool HGIs absent from the rf registry still appear as HGI rows.

    Covers e.g. a zigbee-only HGI whose transport was never created:
    it has a pool *_online entity but no device_by_id entry.
    """
    device = SimpleNamespace(_SLUG="FAN", is_available=True)
    coordinator = _make_coordinator({"32:153289": device})
    _patch_coordinator.return_value = coordinator

    _patch_monitor.return_value = _make_monitor(
        status_entities={"32:153289": "binary_sensor.fan_32_153289_status"},
        pool_entity="binary_sensor.pool_status",
        hgi_entities={
            "18:130236": "binary_sensor.hgi_18_130236_online",
            "18:254172": "binary_sensor.hgi_18_254172_online",
        },
    )

    hass = _make_hass(
        {
            "binary_sensor.fan_32_153289_status": _state("on"),
            "binary_sensor.pool_status": _state("on"),
            "binary_sensor.hgi_18_130236_online": _state(
                "on", connected=True, availability="ONLINE"
            ),
            "binary_sensor.hgi_18_254172_online": _state(
                "off", connected=False, availability="OFFLINE"
            ),
        }
    )

    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 6})

    devices = conn.results[0][1]["devices"]
    by_id = {d["id"]: d for d in devices}

    assert by_id["18:254172"]["class"] == "HGI"
    assert by_id["18:254172"]["status"] == "off"
    assert by_id["18:254172"]["source"] == "hgi"
    assert by_id["18:254172"]["availability"] == "OFFLINE"

    assert by_id["18:130236"]["class"] == "HGI"
    assert by_id["18:130236"]["status"] == "on"


@pytest.mark.asyncio
async def test_snapshot_hgi_device_row_overlaid_by_pool_entity(
    _patch_coordinator, _patch_monitor
):
    """An HGI with a device object still follows its pool online entity.

    An HGI's rf device object reports is_available=True regardless of
    the pool child state, so the *_online entity must win.
    """
    hgi_device = SimpleNamespace(_SLUG="HGI", is_available=True)
    coordinator = _make_coordinator({"18:254172": hgi_device})
    _patch_coordinator.return_value = coordinator

    _patch_monitor.return_value = _make_monitor(
        hgi_entities={"18:254172": "binary_sensor.hgi_18_254172_online"},
    )

    hass = _make_hass(
        {
            "binary_sensor.hgi_18_254172_online": _state(
                "off", connected=False, availability="OFFLINE", pkts_received=0
            ),
        }
    )

    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 7})

    devices = conn.results[0][1]["devices"]
    assert len(devices) == 1
    row = devices[0]
    assert row["class"] == "HGI"
    assert row["status"] == "off"
    assert row["availability"] == "OFFLINE"
    assert row["status_entity_id"] == "binary_sensor.hgi_18_254172_online"


@pytest.mark.asyncio
async def test_snapshot_pool_none_without_pool_entities(
    _patch_coordinator, _patch_monitor
):
    """The pool section is None when no pool entities were discovered."""
    _patch_coordinator.return_value = _make_coordinator({})
    _patch_monitor.return_value = _make_monitor()

    hass = _make_hass()
    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 4})

    assert conn.results[0][1]["pool"] is None


@pytest.mark.asyncio
async def test_snapshot_sends_error_on_failure(_patch_coordinator, _patch_monitor):
    """An unexpected failure returns a websocket error."""
    _patch_monitor.return_value = _make_monitor()
    _patch_coordinator.side_effect = RuntimeError("boom")

    hass = _make_hass()
    conn = _FakeConnection()
    await ws_get_device_status(hass, conn, {"id": 5})

    assert not conn.results
    assert conn.errors == [(5, "snapshot_failed", "Failed to build device status")]
