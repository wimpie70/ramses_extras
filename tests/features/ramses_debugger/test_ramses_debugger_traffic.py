"""Unit tests for ramses_debugger traffic collector + websocket commands."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.ramses_debugger import websocket_commands
from custom_components.ramses_extras.features.ramses_debugger.traffic_collector import (
    TrafficCollector,
)

ws_traffic_get_stats = websocket_commands.ws_traffic_get_stats.__wrapped__
ws_traffic_reset_stats = websocket_commands.ws_traffic_reset_stats.__wrapped__
ws_traffic_subscribe_stats = websocket_commands.ws_traffic_subscribe_stats.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []
        self.messages: list[dict[str, Any]] = []
        self.subscriptions: dict[int, Any] = {}

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))

    def send_message(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_collector_aggregates_events(hass) -> None:
    collector = TrafficCollector(hass)
    collector.start()

    hass.bus.async_fire(
        "ramses_cc_message",
        {
            "dtm": "2026-01-18T12:00:00",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "000A",
        },
    )

    hass.bus.async_fire(
        "ramses_cc_message",
        {
            "dtm": "2026-01-18T12:00:01",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "I",
            "code": "000A",
        },
    )
    await hass.async_block_till_done()

    stats = collector.get_stats()
    assert stats["total_count"] == 2
    assert stats["by_code"]["000A"] == 2
    assert stats["by_verb"]["RQ"] == 1
    assert stats["by_verb"]["I"] == 1
    assert len(stats["flows"]) == 1
    flow = stats["flows"][0]
    assert flow["src"] == "01:111111"
    assert flow["dst"] == "02:222222"
    assert flow["count_total"] == 2
    assert flow["codes"]["000A"] == 2


@pytest.mark.asyncio
async def test_ws_get_stats_and_reset(hass) -> None:
    collector = TrafficCollector(hass)
    collector.start()

    hass.data.setdefault(DOMAIN, {})["ramses_debugger"] = {
        "traffic_collector": collector,
    }

    hass.bus.async_fire(
        "ramses_cc_message",
        {
            "dtm": "2026-01-18T12:00:00",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "000A",
        },
    )
    await hass.async_block_till_done()

    conn = _FakeConnection()

    await ws_traffic_get_stats(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/traffic/get_stats",
            "limit": 200,
        },
    )

    assert not conn.errors
    assert conn.results
    assert conn.results[0][0] == 1
    assert conn.results[0][1]["total_count"] == 1

    # device_id filtering (matches src)
    await ws_traffic_get_stats(
        hass,
        conn,
        {
            "id": 10,
            "type": "ramses_extras/ramses_debugger/traffic/get_stats",
            "device_id": "01:111111",
            "limit": 200,
        },
    )
    assert conn.results[-1][0] == 10
    assert conn.results[-1][1]["total_count"] == 1

    # device_id filtering (non-matching)
    await ws_traffic_get_stats(
        hass,
        conn,
        {
            "id": 11,
            "type": "ramses_extras/ramses_debugger/traffic/get_stats",
            "device_id": "99:999999",
            "limit": 200,
        },
    )
    assert conn.results[-1][0] == 11
    assert conn.results[-1][1]["total_count"] == 1
    assert conn.results[-1][1]["flows"] == []

    await ws_traffic_reset_stats(
        hass,
        conn,
        {
            "id": 2,
            "type": "ramses_extras/ramses_debugger/traffic/reset_stats",
        },
    )

    assert conn.results[-1] == (2, {"success": True})

    await ws_traffic_get_stats(
        hass,
        conn,
        {
            "id": 3,
            "type": "ramses_extras/ramses_debugger/traffic/get_stats",
            "limit": 200,
        },
    )
    assert conn.results[-1][0] == 3
    assert conn.results[-1][1]["total_count"] == 0


@pytest.mark.asyncio
async def test_ws_subscribe_stats_sends_initial_and_updates(hass) -> None:
    collector = TrafficCollector(hass)
    collector.start()

    hass.data.setdefault(DOMAIN, {})["ramses_debugger"] = {
        "traffic_collector": collector,
    }

    conn = _FakeConnection()
    msg_id = 42

    await ws_traffic_subscribe_stats(
        hass,
        conn,
        {
            "id": msg_id,
            "type": "ramses_extras/ramses_debugger/traffic/subscribe_stats",
            "throttle_ms": 0,
            "limit": 200,
        },
    )

    assert not conn.errors
    assert conn.results and conn.results[0][0] == msg_id
    assert conn.results[0][1]["success"] is True
    assert conn.messages

    hass.bus.async_fire(
        "ramses_cc_message",
        {
            "dtm": "2026-01-18T12:00:00",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "000A",
        },
    )
    await hass.async_block_till_done()

    # With throttle_ms=0, each event triggers a push snapshot
    assert len(conn.messages) >= 2


@pytest.mark.asyncio
async def test_ws_returns_error_when_collector_missing(hass) -> None:
    hass.data[DOMAIN] = {}

    conn = _FakeConnection()

    await ws_traffic_get_stats(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/traffic/get_stats",
            "limit": 200,
        },
    )

    assert conn.errors
    assert conn.errors[0][0] == 1
    assert conn.errors[0][1] == "collector_not_ready"

    await ws_traffic_reset_stats(
        hass,
        conn,
        {
            "id": 2,
            "type": "ramses_extras/ramses_debugger/traffic/reset_stats",
        },
    )

    assert conn.errors[-1][0] == 2
    assert conn.errors[-1][1] == "collector_not_ready"


@pytest.mark.asyncio
async def test_collector_ignores_invalid_event(hass) -> None:
    collector = TrafficCollector(hass)
    collector.start()

    hass.bus.async_fire(
        "ramses_cc_message",
        {
            "dtm": "2026-01-18T12:00:00",
            "src": 123,  # invalid
            "dst": "02:222222",
            "verb": "RQ",
            "code": "000A",
        },
    )
    await hass.async_block_till_done()

    stats = collector.get_stats()
    assert stats["total_count"] == 0
    assert stats["flows"] == []


def test_collector_time_fired_used_when_missing_dtm(hass) -> None:
    collector = TrafficCollector(hass)

    event = MagicMock()
    event.data = {
        "src": "01:111111",
        "dst": "02:222222",
        "verb": "RQ",
        "code": "000A",
    }
    event.time_fired = datetime(2026, 1, 20, 12, 0, 0)

    collector._handle_ramses_cc_message(event)

    stats = collector.get_stats()
    assert stats["total_count"] == 1
    flow = stats["flows"][0]
    assert flow["last_seen"].startswith("2026-01-20T12:00:00")
