"""Unit tests for ramses_debugger log backend + websocket commands."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.ramses_debugger import websocket_commands

ws_log_list_files = websocket_commands.ws_log_list_files.__wrapped__
ws_log_get_tail = websocket_commands.ws_log_get_tail.__wrapped__
ws_log_search = websocket_commands.ws_log_search.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))


def _setup_config_entry(hass, *, log_path: Path) -> None:
    hass.data.setdefault(DOMAIN, {})["config_entry"] = MagicMock(
        options={"ramses_debugger_log_path": str(log_path)}
    )


@pytest.mark.asyncio
async def test_ws_log_list_tail_and_search(hass, tmp_path: Path) -> None:
    base = tmp_path / "home-assistant.log"
    base.write_text(
        "INFO boot\nERROR first\nINFO mid\nERROR second\n",
        encoding="utf-8",
    )

    rotated = tmp_path / "home-assistant.log.1.gz"
    with gzip.open(rotated, "wt", encoding="utf-8") as f:
        f.write("INFO rotated\nERROR rotated\n")

    _setup_config_entry(hass, log_path=base)

    conn = _FakeConnection()

    await ws_log_list_files(
        hass,
        conn,
        {"id": 1, "type": "ramses_extras/ramses_debugger/log/list_files"},
    )

    assert not conn.errors
    assert conn.results and conn.results[0][0] == 1
    files = conn.results[0][1]["files"]
    file_ids = {f["file_id"] for f in files}
    assert base.name in file_ids
    assert rotated.name in file_ids

    await ws_log_get_tail(
        hass,
        conn,
        {
            "id": 2,
            "type": "ramses_extras/ramses_debugger/log/get_tail",
            "file_id": base.name,
            "max_lines": 2,
        },
    )
    assert conn.results[-1][0] == 2
    assert "ERROR second" in conn.results[-1][1]["text"]

    await ws_log_get_tail(
        hass,
        conn,
        {
            "id": 3,
            "type": "ramses_extras/ramses_debugger/log/get_tail",
            "file_id": rotated.name,
            "max_lines": 50,
        },
    )
    assert conn.results[-1][0] == 3
    assert "ERROR rotated" in conn.results[-1][1]["text"]

    await ws_log_search(
        hass,
        conn,
        {
            "id": 4,
            "type": "ramses_extras/ramses_debugger/log/search",
            "file_id": base.name,
            "query": "ERROR",
            "before": 1,
            "after": 0,
        },
    )

    assert conn.results[-1][0] == 4
    payload = conn.results[-1][1]
    assert payload["matches"] == 2
    assert payload["blocks"]
    assert "ERROR first" in payload["plain"]


@pytest.mark.asyncio
async def test_ws_log_rejects_unknown_file_id(hass, tmp_path: Path) -> None:
    base = tmp_path / "home-assistant.log"
    base.write_text("INFO boot\n", encoding="utf-8")

    _setup_config_entry(hass, log_path=base)

    conn = _FakeConnection()

    await ws_log_get_tail(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/log/get_tail",
            "file_id": "not-allowed.log",
        },
    )

    assert conn.errors
    assert conn.errors[-1][0] == 1
    assert conn.errors[-1][1] == "file_not_allowed"
