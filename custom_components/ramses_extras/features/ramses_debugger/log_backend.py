"""Log file helpers for the Ramses Debugger.

This module provides:

- Discovery of log files (base file + rotated variants).
- Allowlisted resolution of a user-provided ``file_id`` to an on-disk path.
- Efficient tail reading for plain text and gzip files.
- Best-effort search with context blocks.

All public helpers are designed for use by WebSocket handlers.
"""

from __future__ import annotations

import gzip
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN


@dataclass(frozen=True)
class LogFileInfo:
    """Metadata about a discovered log file."""

    file_id: str
    path: Path
    size: int
    modified_at: str


def _get_config_entry(hass: HomeAssistant) -> Any | None:
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return None
    return domain_data.get("config_entry")


def get_configured_log_path(hass: HomeAssistant) -> Path:
    """Return the configured Home Assistant log path.

    The configured path comes from the Ramses Debugger options if set,
    otherwise it falls back to ``hass.config.path('home-assistant.log')``.
    """

    entry = _get_config_entry(hass)
    options = getattr(entry, "options", {}) if entry else {}
    raw = options.get("ramses_debugger_log_path")
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip())

    return Path(hass.config.path("home-assistant.log"))


def get_configured_packet_log_path(hass: HomeAssistant) -> Path | None:
    """Return the configured ramses_cc packet log path.

    This is resolved from the Ramses Debugger options if set. Otherwise it is
    derived from the active ``ramses_cc`` config entry (``packet_log.file_name``)
    when available.
    """

    entry = _get_config_entry(hass)
    options = getattr(entry, "options", {}) if entry else {}

    raw_override = options.get("ramses_debugger_packet_log_path")
    if isinstance(raw_override, str) and raw_override.strip():
        return Path(raw_override.strip())

    try:
        entries = hass.config_entries.async_entries("ramses_cc")
        for cc_entry in entries:
            packet_log = getattr(cc_entry, "options", {}).get("packet_log")
            if not isinstance(packet_log, dict):
                continue
            raw = packet_log.get("file_name")
            if isinstance(raw, str) and raw.strip():
                return Path(raw.strip())
    except Exception:
        return None

    return None


def discover_log_files(base_path: Path) -> list[LogFileInfo]:
    """Discover the base log file and rotated variants.

    Rotated variants are discovered by matching ``<base>.X`` and
    ``<base>.X.gz`` siblings in the same directory.

    :param base_path: Path to the base log file.
    :return: Sorted list (newest first) of discovered files.
    """

    base_path = base_path.expanduser()

    candidates: list[Path] = []
    if base_path.exists():
        candidates.append(base_path)

    parent = base_path.parent
    stem = base_path.name

    if parent.exists() and parent.is_dir():
        for p in parent.iterdir():
            name = p.name
            if name == stem:
                continue
            if name.startswith(stem + "."):
                candidates.append(p)

    seen: set[Path] = set()
    files: list[LogFileInfo] = []

    for path in candidates:
        if path in seen:
            continue
        seen.add(path)

        try:
            stat = path.stat()
        except OSError:
            continue

        if not path.is_file():
            continue

        file_id = path.name
        files.append(
            LogFileInfo(
                file_id=file_id,
                path=path,
                size=int(stat.st_size),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            )
        )

    files.sort(key=lambda f: (f.modified_at, f.file_id), reverse=True)
    return files


def resolve_log_file_id(base_path: Path, file_id: str) -> Path | None:
    """Resolve a file_id to a Path if it is allowlisted by discovery.

    The allowlist is the set of files discovered from the configured base path
    and its rotated variants (same directory). The resolved path must remain
    inside the base directory.
    """

    allowed = {f.path.name: f.path for f in discover_log_files(base_path)}
    p = allowed.get(file_id)
    if p is None:
        return None

    try:
        resolved = p.resolve()
        base_dir = base_path.expanduser().resolve().parent
        if base_dir not in resolved.parents and resolved != base_dir:
            return None
    except OSError:
        return None

    return p


def _open_text(path: Path) -> Iterable[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        with path.open("rt", encoding="utf-8", errors="replace") as f:
            yield from f


def tail_text(path: Path, *, max_lines: int = 200, max_chars: int = 200_000) -> str:
    """Read the tail of a log file.

    For plain text files this seeks backwards from EOF to limit reads.
    For gzip files it falls back to streaming and retaining the last
    ``max_lines``.

    :param path: Log file path.
    :param max_lines: Maximum lines returned.
    :param max_chars: Maximum characters returned.
    :return: Tail content.
    """

    max_lines = max(0, min(int(max_lines), 10_000))
    max_chars = max(0, min(int(max_chars), 2_000_000))

    if max_lines == 0 or max_chars == 0:
        return ""

    if path.suffix == ".gz":
        buf: deque[str] = deque(maxlen=max_lines)
        for line in _open_text(path):
            buf.append(line)
        out = "".join(buf)
        if len(out) > max_chars:
            out = out[-max_chars:]
        return out

    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            block_size = 8192
            data = b""
            pos = end

            while (
                pos > 0 and data.count(b"\n") <= max_lines + 1 and len(data) < max_chars
            ):
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data

            text = data.decode("utf-8", errors="replace")
    except OSError:
        text = "".join(_open_text(path))

    lines = text.splitlines(keepends=True)
    out = "".join(lines[-max_lines:])
    if len(out) > max_chars:
        out = out[-max_chars:]
    return out


@dataclass(frozen=True)
class LogBlock:
    """A contiguous block of log lines returned from search."""

    file_id: str
    start_line: int
    end_line: int
    lines: list[str]


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    ranges.sort()
    merged: list[tuple[int, int]] = [ranges[0]]
    for start, end in ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def search_with_context(
    path: Path,
    *,
    query: str,
    before: int = 3,
    after: int = 3,
    max_matches: int = 200,
    max_chars: int = 400_000,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """Search for one or more terms and return surrounding context blocks.

    :param path: Log file path.
    :param query: Search query. Multiple lines are treated as OR terms.
    :param before: Context lines before each match.
    :param after: Context lines after each match.
    :param max_matches: Maximum matches considered.
    :param max_chars: Maximum returned output size.
    :param case_sensitive: Whether matching is case sensitive.
    :return: A dict containing plain/markdown content plus structured blocks.
    """

    before = max(0, min(int(before), 200))
    after = max(0, min(int(after), 200))
    max_matches = max(0, min(int(max_matches), 5000))
    max_chars = max(0, min(int(max_chars), 2_000_000))

    if not isinstance(query, str) or not query:
        return {
            "matches": 0,
            "blocks": [],
            "truncated": False,
            "truncated_by_max_chars": False,
            "truncated_by_max_matches": False,
        }

    terms = [t.strip() for t in query.splitlines() if t.strip()]
    if not terms:
        return {
            "matches": 0,
            "blocks": [],
            "truncated": False,
            "truncated_by_max_chars": False,
            "truncated_by_max_matches": False,
        }

    needles = terms if case_sensitive else [t.lower() for t in terms]

    match_lines: list[int] = []
    ranges: list[tuple[int, int]] = []
    truncated_by_max_matches = False

    for idx, line in enumerate(_open_text(path), start=1):
        hay = line if case_sensitive else line.lower()
        if any(needle in hay for needle in needles):
            match_lines.append(idx)
            ranges.append((max(1, idx - before), idx + after))
            if len(match_lines) >= max_matches:
                truncated_by_max_matches = True
                break

    merged = _merge_ranges(ranges)
    if not merged:
        return {
            "matches": 0,
            "blocks": [],
            "truncated": False,
            "truncated_by_max_chars": False,
            "truncated_by_max_matches": False,
        }

    blocks: list[LogBlock] = []
    current_idx = 0
    current_range = merged[current_idx]
    start, end = current_range
    current_lines: list[str] = []

    total_chars = 0
    truncated = False
    truncated_by_max_chars = False

    for idx, line in enumerate(_open_text(path), start=1):
        while idx > end:
            blocks.append(
                LogBlock(
                    file_id=path.name,
                    start_line=start,
                    end_line=end,
                    lines=current_lines,
                )
            )
            current_idx += 1
            if current_idx >= len(merged):
                break
            start, end = merged[current_idx]
            current_lines = []

        if current_idx >= len(merged):
            break

        if start <= idx <= end:
            s = line.rstrip("\n")
            total_chars += len(s) + 1
            if total_chars > max_chars:
                truncated = True
                truncated_by_max_chars = True
                break
            current_lines.append(s)

    if current_idx < len(merged) and current_lines and not truncated:
        blocks.append(
            LogBlock(
                file_id=path.name,
                start_line=start,
                end_line=end,
                lines=current_lines,
            )
        )

    plain = "\n\n".join(
        "\n".join(block.lines) for block in blocks if block.lines
    ).strip("\n")
    markdown = f"```text\n{plain}\n```" if plain else ""

    truncated = truncated or truncated_by_max_matches

    return {
        "matches": len(match_lines),
        "match_lines": match_lines,
        "blocks": [
            {
                "file_id": b.file_id,
                "start_line": b.start_line,
                "end_line": b.end_line,
                "lines": b.lines,
            }
            for b in blocks
        ],
        "plain": plain,
        "markdown": markdown,
        "truncated": truncated,
        "truncated_by_max_chars": truncated_by_max_chars,
        "truncated_by_max_matches": truncated_by_max_matches,
    }


def resolve_file_id(hass: HomeAssistant, file_id: str) -> Path | None:
    base = get_configured_log_path(hass)
    allowed = {f.path.name: f.path for f in discover_log_files(base)}
    p = allowed.get(file_id)
    if p is None:
        return None

    try:
        resolved = p.resolve()
        base_dir = base.expanduser().resolve().parent
        if base_dir not in resolved.parents and resolved != base_dir:
            return None
    except OSError:
        return None

    return p
