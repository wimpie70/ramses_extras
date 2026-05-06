"""Unit tests for ramses_debugger log backend + websocket commands."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.ramses_debugger import websocket_commands
from custom_components.ramses_extras.features.ramses_debugger.messages_provider import (
    NormalizedMessage,
)

ws_log_list_files = websocket_commands.ws_log_list_files.__wrapped__
ws_log_get_tail = websocket_commands.ws_log_get_tail.__wrapped__
ws_log_search = websocket_commands.ws_log_search.__wrapped__
ws_packet_log_list_files = websocket_commands.ws_packet_log_list_files.__wrapped__
ws_packet_log_get_messages = websocket_commands.ws_packet_log_get_messages.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))


def _setup_config_entry(
    hass, *, log_path: Path | None = None, packet_log_path: Path | None = None
) -> None:
    options: dict[str, Any] = {}
    if log_path is not None:
        options["ramses_debugger_log_path"] = str(log_path)
    if packet_log_path is not None:
        options["ramses_debugger_packet_log_path"] = str(packet_log_path)

    hass.data.setdefault(DOMAIN, {})["config_entry"] = MagicMock(options=options)


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
async def test_ws_packet_log_list_and_get_messages(hass, tmp_path: Path) -> None:
    base = tmp_path / "packet_log.log"
    base.write_text(
        "2026-01-20T09:58:48.263427 I 32:153289 37:123456 --:------ 31DA 003 010203\n"
        "2026-01-20T09:58:48.275061 I 32:153289 37:123456 --:------ 31DA 003 010204\n"
        "2026-01-20T09:58:48.285690 I 32:153289 37:123456 --:------ 31DA 003 010205\n",
        encoding="utf-8",
    )

    rotated = tmp_path / "packet_log.log.1"
    rotated.write_text(
        "2026-01-20T09:50:00.000000 I 01:111111 02:222222 --:------ 10E0 000\n",
        encoding="utf-8",
    )

    _setup_config_entry(hass, packet_log_path=base)
    conn = _FakeConnection()

    await ws_packet_log_list_files(
        hass,
        conn,
        {"id": 1, "type": "ramses_extras/ramses_debugger/packet_log/list_files"},
    )

    assert not conn.errors
    assert conn.results and conn.results[-1][0] == 1
    files = conn.results[-1][1]["files"]
    file_ids = {f["file_id"] for f in files}
    assert base.name in file_ids
    assert rotated.name in file_ids

    await ws_packet_log_get_messages(
        hass,
        conn,
        {
            "id": 2,
            "type": "ramses_extras/ramses_debugger/packet_log/get_messages",
            "file_id": base.name,
            "limit": 50,
            "src": "32:153289",
        },
    )

    assert not conn.errors
    assert conn.results[-1][0] == 2
    payload = conn.results[-1][1]
    assert payload["file_id"] == base.name
    assert payload["messages"]
    assert payload["messages"][0]["source"] == "packet_log"


@pytest.mark.asyncio
async def test_ws_packet_log_not_configured(hass) -> None:
    conn = _FakeConnection()

    await ws_packet_log_get_messages(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/packet_log/get_messages",
            "file_id": "ramses_log",
        },
    )

    assert conn.errors
    assert conn.errors[-1][0] == 1
    assert conn.errors[-1][1] == "packet_log_not_configured"


@pytest.mark.asyncio
async def test_ws_packet_log_list_files_not_configured(hass) -> None:
    conn = _FakeConnection()

    await ws_packet_log_list_files(
        hass,
        conn,
        {"id": 1, "type": "ramses_extras/ramses_debugger/packet_log/list_files"},
    )

    assert not conn.errors
    expected = (1, {"base": None, "files": [], "_backend_version": "0.0.0"})
    assert conn.results[-1] == expected


@pytest.mark.asyncio
async def test_ws_packet_log_get_messages_rejects_unknown_file_id(
    hass,
    tmp_path: Path,
) -> None:
    base = tmp_path / "packet_log.log"
    base.write_text("test\n", encoding="utf-8")
    _setup_config_entry(hass, packet_log_path=base)

    conn = _FakeConnection()

    await ws_packet_log_get_messages(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/packet_log/get_messages",
            "file_id": "not-allowed.log",
        },
    )

    assert conn.errors
    assert conn.errors[-1][0] == 1
    assert conn.errors[-1][1] == "file_not_allowed"


@pytest.mark.asyncio
async def test_ws_packet_log_get_messages_decode(hass, tmp_path: Path) -> None:
    base = tmp_path / "packet_log.log"
    base.write_text("test\n", encoding="utf-8")
    _setup_config_entry(hass, packet_log_path=base)

    conn = _FakeConnection()

    messages = [
        NormalizedMessage(
            dtm="2026-01-20T10:00:00.000000",
            src="01:111111",
            dst="02:222222",
            verb="RQ",
            code="31DA",
            payload="003 010203",
            packet="RQ 01:111111 02:222222 --:------ 31DA 003 010203",
            source="packet_log",
        )
    ]

    with (
        patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.PacketLogParser.get_messages",
            new=AsyncMock(return_value=messages),
        ),
        patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.decode_message_with_ramses_rf",
            return_value={"decoded": True},
        ),
    ):
        await ws_packet_log_get_messages(
            hass,
            conn,
            {
                "id": 1,
                "type": "ramses_extras/ramses_debugger/packet_log/get_messages",
                "file_id": base.name,
                "decode": True,
                "limit": 50,
            },
        )

    assert not conn.errors
    payload = conn.results[-1][1]
    assert payload["file_id"] == base.name
    assert payload["messages"][0]["decoded"] == {"decoded": True}


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


@pytest.mark.asyncio
async def test_ws_log_search_truncated_by_max_matches(hass, tmp_path: Path) -> None:
    base = tmp_path / "home-assistant.log"
    base.write_text(
        "\n".join(["ERROR one", "ERROR two", "ERROR three"]) + "\n",
        encoding="utf-8",
    )

    _setup_config_entry(hass, log_path=base)
    conn = _FakeConnection()

    await ws_log_search(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/log/search",
            "file_id": base.name,
            "query": "ERROR",
            "before": 0,
            "after": 0,
            "max_matches": 1,
        },
    )

    payload = conn.results[-1][1]
    assert payload["matches"] == 1
    assert payload["truncated"] is True
    assert payload.get("truncated_by_max_matches") is True


@pytest.mark.asyncio
async def test_ws_log_search_truncated_by_max_chars(hass, tmp_path: Path) -> None:
    base = tmp_path / "home-assistant.log"
    base.write_text(
        "INFO start\n" + "ERROR " + ("x" * 200) + "\n" + "INFO end\n",
        encoding="utf-8",
    )

    _setup_config_entry(hass, log_path=base)
    conn = _FakeConnection()

    await ws_log_search(
        hass,
        conn,
        {
            "id": 1,
            "type": "ramses_extras/ramses_debugger/log/search",
            "file_id": base.name,
            "query": "ERROR",
            "before": 1,
            "after": 1,
            "max_chars": 50,
        },
    )

    payload = conn.results[-1][1]
    assert payload["matches"] == 1
    assert payload["truncated"] is True
    assert payload.get("truncated_by_max_chars") is True
    assert len(payload["plain"]) <= 50


@pytest.mark.asyncio
async def test_get_configured_packet_log_path_v1_fallback(hass, tmp_path: Path) -> None:
    """Test that v1 ramses_rf.file_name is used as fallback when packet_log
     is not configured.

    This covers the migration scenario where ramses_cc v2 migration removes file_name
    from packet_log but doesn't migrate it from ramses_rf.
    """
    from custom_components.ramses_extras.features.ramses_debugger.log_backend import (
        get_configured_packet_log_path,
    )

    log_base = tmp_path / "ramses_rf_logs"
    log_base.mkdir()
    # v1 file_name can be a directory path - function constructs packet_log.log
    expected_path = log_base / "packet_log.log"
    expected_path.write_text("test log\n", encoding="utf-8")

    # Mock ramses_cc config entry with v1 structure (file_name is directory)
    fake_cc_entry = MagicMock()
    fake_cc_entry.options = {
        "ramses_rf": {"file_name": str(log_base)},
        # No "packet_log" key - simulating incomplete migration
    }

    with patch.object(
        hass.config_entries, "async_entries", return_value=[fake_cc_entry]
    ):
        result = get_configured_packet_log_path(hass)

    assert result is not None
    assert result == expected_path


@pytest.mark.asyncio
async def test_get_configured_packet_log_path_v2_preferred_over_v1(
    hass, tmp_path: Path
) -> None:
    """Test that v2 packet_log.packet_log_path takes precedence
    over v1 ramses_rf.file_name."""
    from custom_components.ramses_extras.features.ramses_debugger.log_backend import (
        get_configured_packet_log_path,
    )

    v1_path = tmp_path / "v1_logs"
    v1_path.mkdir()
    v2_path = tmp_path / "v2_logs"
    v2_path.mkdir()
    # v2 constructs packet_log.log from directory path
    expected_v2_path = v2_path / "packet_log.log"
    expected_v2_path.write_text("v2 log\n", encoding="utf-8")

    # Mock ramses_cc config entry with both v1 and v2 structures
    fake_cc_entry = MagicMock()
    fake_cc_entry.options = {
        "ramses_rf": {"file_name": str(v1_path / "old.log")},
        "packet_log": {"packet_log_path": str(v2_path)},
    }

    with patch.object(
        hass.config_entries, "async_entries", return_value=[fake_cc_entry]
    ):
        result = get_configured_packet_log_path(hass)

    assert result is not None
    assert result == expected_v2_path


@pytest.mark.asyncio
async def test_get_configured_packet_log_path_defaults_when_path_empty(
    hass, tmp_path: Path
) -> None:
    """If packet_log_path is empty, fall back to default packet_log.log locations."""
    from custom_components.ramses_extras.features.ramses_debugger.log_backend import (
        get_configured_packet_log_path,
    )

    expected = tmp_path / "packet_log.log"
    expected.write_text("default location\n", encoding="utf-8")

    fake_cc_entry = MagicMock()
    fake_cc_entry.options = {
        "packet_log": {
            "packet_log_path": "",
            "packet_log_prefix": "packet_log",
        }
    }
    fake_cc_entry.data = {}

    hass.config.path = MagicMock(
        side_effect=lambda *parts: str(tmp_path / Path(*parts))
    )

    with patch.object(
        hass.config_entries, "async_entries", return_value=[fake_cc_entry]
    ):
        result = get_configured_packet_log_path(hass)

    assert result is not None
    assert result == expected


@pytest.mark.asyncio
async def test_get_configured_packet_log_path_reads_entry_data(
    hass, tmp_path: Path
) -> None:
    """Use ramses_cc entry.data packet_log when options are empty."""
    from custom_components.ramses_extras.features.ramses_debugger.log_backend import (
        get_configured_packet_log_path,
    )

    packet_dir = tmp_path / "rf_logs"
    packet_dir.mkdir()
    expected = packet_dir / "custom_prefix.log"
    expected.write_text("from data\n", encoding="utf-8")

    fake_cc_entry = MagicMock()
    fake_cc_entry.options = {}
    fake_cc_entry.data = {
        "packet_log": {
            "path": str(packet_dir),
            "prefix": "custom_prefix",
        }
    }

    with patch.object(
        hass.config_entries, "async_entries", return_value=[fake_cc_entry]
    ):
        result = get_configured_packet_log_path(hass)

    assert result is not None
    assert result == expected
