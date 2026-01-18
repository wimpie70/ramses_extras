"""Unit tests for ramses_debugger traffic collector + websocket commands."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.ramses_debugger import websocket_commands
from custom_components.ramses_extras.features.ramses_debugger.traffic_collector import (
    TrafficCollector,
)

ws_traffic_get_stats = websocket_commands.ws_traffic_get_stats.__wrapped__
ws_traffic_reset_stats = websocket_commands.ws_traffic_reset_stats.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))


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
