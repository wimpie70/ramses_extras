from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .log_backend import (
    get_configured_log_path,
    get_configured_packet_log_path,
    tail_text,
)

_LOGGER = logging.getLogger(__name__)


class PacketLogParser:
    """Provider for parsing traffic records from ramses packet/message log."""

    @staticmethod
    async def get_messages(
        hass: HomeAssistant,
        log_path: Path | None = None,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 1000,
    ) -> list[NormalizedMessage]:
        """Parse traffic records from ramses_log."""
        if log_path is None:
            log_path = get_configured_packet_log_path(hass)
        if log_path is None:
            return []

        try:
            # Simple file reading approach
            content = await hass.async_add_executor_job(
                partial(log_path.read_text, encoding="utf-8")
            )
            lines = content.splitlines()

            # Apply filters
            messages: list[NormalizedMessage] = []
            for line in lines:
                msg = _parse_packet_log_line(line)
                if msg:
                    # Apply filters
                    if src and msg.src != src:
                        continue
                    if dst and msg.dst != dst:
                        continue
                    if verb and msg.verb != verb:
                        continue
                    if code and msg.code != code:
                        continue
                    messages.append(msg)
                    if len(messages) >= limit:
                        break

            return messages
        except Exception as exc:
            _LOGGER.warning("PacketLogProvider error: %s", exc)
            return []


def _parse_packet_log_line(line: str) -> NormalizedMessage | None:
    """Parse a single ramses packet log line into a normalized message."""
    # Common ramses_log formats:
    # - With RSSI + extra fields:
    #   2026-01-20T13:31:43.693075 000 RQ --- 18:149488 01:000000 --:------ 0006 001 00
    #   2026-01-20T13:31:43.070025 036 I --- 32:153289 --:------ 32:153289 31DA
    #   030
    #   00EF...
    # - Older/shorter format (kept for compatibility):
    #   2026-01-20T09:58:48.263427 I 32:153289 37:123456 --:------ 31DA 003 010203
    line_no_comment = line.split("#", 1)[0]
    parts = line_no_comment.strip().split()
    if len(parts) < 7:
        return None

    def _is_addr(token: str) -> bool:
        return bool(re.match(r"^(--:------|\d{2}:\d{6})$", token))

    def _is_code(token: str) -> bool:
        return bool(re.match(r"^[0-9A-F]{4}$", token))

    def _is_len(token: str) -> bool:
        return bool(re.match(r"^\d{3}$", token))

    def _is_rssi(token: str) -> bool:
        return bool(re.match(r"^(\d{3}|---|\.\.\.)$", token))

    def _is_seqn(token: str) -> bool:
        return _is_rssi(token)

    try:
        dtm = parts[0]
        i = 1

        if i >= len(parts):
            return None

        # ramses_log uses: "..." (or "063" etc.) before verb
        if _is_rssi(parts[i]):
            i += 1

        if i >= len(parts):
            return None

        verb = parts[i]
        i += 1

        # ramses_log has a seqn token ("---" or digits like "245") after verb
        if i < len(parts) and _is_seqn(parts[i]):
            i += 1

        rest = parts[i:]

        addrs = [t for t in rest if _is_addr(t)]
        if len(addrs) < 2:
            return None

        src, dst = addrs[0], addrs[1]
        if dst == "--:------" and len(addrs) >= 3:
            dst = addrs[2]

        code_idx: int | None = None
        for idx, token in enumerate(rest):
            if _is_code(token):
                code_idx = idx
                break
        if code_idx is None:
            return None

        code = rest[code_idx]

        payload_len: str | None = None
        payload_hex = ""
        for idx in range(code_idx + 1, len(rest)):
            token = rest[idx]
            if _is_len(token):
                payload_len = token
                payload_hex = " ".join(rest[idx + 1 :])
                break

        if payload_len is None:
            return None

        packet = " ".join(parts[1:])
        payload = f"{payload_len} {payload_hex}" if payload_hex else payload_len

        return NormalizedMessage(
            dtm=dtm,
            src=src,
            dst=dst,
            verb=verb,
            code=code,
            payload=payload,
            packet=packet,
            source="packet_log",
            raw_line=line,
            parse_warnings=[],
        )
    except Exception:
        return None


@contextmanager
def _silence_loggers(logger_names: list[str]) -> Iterator[None]:
    old: list[tuple[logging.Logger, bool, int]] = []
    try:
        for name in logger_names:
            logger = logging.getLogger(name)
            old.append((logger, logger.disabled, logger.level))
            logger.disabled = True
            logger.setLevel(logging.CRITICAL + 1)
        yield
    finally:
        for logger, disabled, level in old:
            logger.disabled = disabled
            logger.setLevel(level)


def decode_message_with_ramses_rf(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Decode a message using ramses_rf (ramses_tx) without side effects.

    Returns None if ramses_tx is not installed or if decoding fails.
    """

    try:
        from ramses_tx.message import Message
        from ramses_tx.packet import Packet
    except ModuleNotFoundError:
        return None

    dtm_raw = msg.get("dtm")
    if not isinstance(dtm_raw, str):
        return None
    src_raw = msg.get("src")
    if not isinstance(src_raw, str):
        return None
    dst_raw = msg.get("dst")
    if not isinstance(dst_raw, str):
        return None
    verb_raw = msg.get("verb")
    if not isinstance(verb_raw, str):
        return None
    code_raw = msg.get("code")
    if not isinstance(code_raw, str):
        return None
    payload_raw = msg.get("payload")
    if not isinstance(payload_raw, str):
        return None

    dtm = dtm_raw
    src = src_raw
    dst = dst_raw
    verb = verb_raw
    code = code_raw
    payload = payload_raw

    payload_parts = payload.split()
    if not payload_parts:
        return None

    payload_len = payload_parts[0]
    if not re.match(r"^\d{3}$", payload_len):
        return None

    payload_hex = "".join(payload_parts[1:]).replace("-", "")

    verb2 = verb if len(verb) == 2 else f" {verb}"
    seqn = "---"
    addrs = [src, dst, src]

    frame = (
        f"--- {verb2} {seqn} {addrs[0]} {addrs[1]} {addrs[2]} "
        f"{code} {payload_len} {payload_hex}"
    )

    try:
        dt_obj = datetime.fromisoformat(dtm)
    except ValueError:
        return None

    with _silence_loggers(
        [
            "ramses_tx.packet_log",
            "ramses_tx.packet",
            "ramses_tx.message",
            "ramses_tx.parsers",
        ]
    ):
        try:
            pkt = Packet(dt_obj, frame)
            m = Message._from_pkt(pkt)
        except Exception:
            return None

    try:
        payload_decoded = m.payload
    except Exception:
        return None

    return {
        "dtm": m.dtm.isoformat(timespec="microseconds"),
        "src": m.src.id,
        "dst": m.dst.id,
        "verb": m.verb.strip(),
        "code": str(m.code),
        "payload": payload_decoded,
    }


@dataclass
class NormalizedMessage:
    dtm: str
    src: str
    dst: str
    verb: str | None
    code: str | None
    payload: str | None
    packet: str | None
    source: str  # "traffic_buffer" | "packet_log" | "ha_log"
    raw_line: str | None = None
    parse_warnings: list[str] = field(default_factory=list)


class MessagesProvider:
    """Base class for message providers."""

    async def get_messages(
        self,
        hass: HomeAssistant,
        *,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[NormalizedMessage]:
        raise NotImplementedError


class TrafficBufferProvider(MessagesProvider):
    """Provider for in-memory traffic buffer from TrafficCollector."""

    def __init__(self, max_global: int = 5000, max_per_flow: int = 500) -> None:
        self._max_global = max_global
        self._max_per_flow = max_per_flow
        self._global_buffer: deque[dict[str, Any]] = deque(maxlen=max_global)
        self._per_flow_buffers: dict[tuple[str, str], deque[dict[str, Any]]] = {}

    def ingest_event(self, event_data: dict[str, Any]) -> None:
        """Ingest a ramses_cc_message event into buffers."""
        self._global_buffer.append(event_data)
        src = event_data.get("src")
        dst = event_data.get("dst")
        if isinstance(src, str) and isinstance(dst, str):
            key = (src, dst)
            buf = self._per_flow_buffers.setdefault(
                key, deque(maxlen=self._max_per_flow)
            )
            buf.append(event_data)

    async def get_messages(
        self,
        hass: HomeAssistant,
        *,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[NormalizedMessage]:
        messages: list[NormalizedMessage] = []
        for raw in self._global_buffer:
            if src and raw.get("src") != src:
                continue
            if dst and raw.get("dst") != dst:
                continue
            if verb and raw.get("verb") != verb:
                continue
            if code and raw.get("code") != code:
                continue
            # TODO: since/until filtering by dtm if needed
            msg = NormalizedMessage(
                dtm=raw.get("dtm", ""),
                src=raw.get("src", ""),
                dst=raw.get("dst", ""),
                verb=raw.get("verb"),
                code=raw.get("code"),
                payload=raw.get("payload"),
                packet=raw.get("packet"),
                source="traffic_buffer",
            )
            messages.append(msg)
            if len(messages) >= limit:
                break
        return messages


class PacketLogProvider(MessagesProvider):
    """Provider for packet log (ramses_log) parsing."""

    async def get_messages(
        self,
        hass: HomeAssistant,
        *,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[NormalizedMessage]:
        # Delegate to the static implementation added earlier
        return await PacketLogParser.get_messages(
            hass,
            src=src,
            dst=dst,
            verb=verb,
            code=code,
            since=since,
            until=until,
            limit=limit,
        )


class HALogProvider(MessagesProvider):
    """Provider for HA log parsing."""

    async def get_messages(
        self,
        hass: HomeAssistant,
        *,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[NormalizedMessage]:
        """Parse HA log lines for ramses_cc messages."""
        log_path = get_configured_log_path(hass)
        if not log_path:
            return []

        try:
            text = await hass.async_add_executor_job(
                partial(tail_text, log_path, max_lines=200_000, max_chars=10_000_000)
            )
            lines = text.splitlines()

            messages: list[NormalizedMessage] = []
            for line in reversed(lines):
                if not line:
                    continue

                if "ramses" not in line.lower():
                    continue

                if "{" not in line and "--:------" not in line and ":" not in line:
                    continue

                msg = _parse_ha_log_line(line)
                if msg is None:
                    continue

                if src and msg.src != src:
                    continue
                if dst and msg.dst != dst:
                    continue
                if verb and msg.verb != verb:
                    continue
                if code and msg.code != code:
                    continue

                messages.append(msg)
                if len(messages) >= limit:
                    break

            return messages
        except Exception as exc:
            _LOGGER.warning("HALogProvider error: %s", exc)
            return []


def _parse_ha_log_line(line: str) -> NormalizedMessage | None:
    """Parse a HA log line containing a ramses_cc message."""
    # Expected HA log format with JSON payload:
    # 2026-01-20 09:58:48 DEBUG (MainThread) [custom_components.ramses_cc] ...
    # {"src": "...", "dst": "...", "verb": "...", ...}
    # We'll try to extract JSON from the line and parse it.
    try:
        import ast
        import json
        import re

        data: dict[str, Any] | None = None

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(line):
            if ch != "{":
                continue
            try:
                obj, _end = decoder.raw_decode(line[idx:])
            except Exception:
                continue
            if isinstance(obj, dict):
                data = obj
                break

        if data is None:
            start = line.find("{")
            end = line.rfind("}")
            if start >= 0 and end > start:
                try:
                    obj = ast.literal_eval(line[start : end + 1])
                    if isinstance(obj, dict):
                        data = obj
                except Exception:
                    data = None

        if data is None:
            raise ValueError("No JSON/dict payload found")

        # Sometimes the dict is nested, e.g. {"message": {...}} or {"msg": {...}}
        if not ("src" in data and "dst" in data):
            nested = None
            for key in ("msg", "message", "data"):
                v = data.get(key)
                if isinstance(v, dict) and "src" in v and "dst" in v:
                    nested = v
                    break
            if nested is None:
                for v in data.values():
                    if isinstance(v, dict) and "src" in v and "dst" in v:
                        nested = v
                        break
            if isinstance(nested, dict):
                data = nested

        src = data.get("src")
        dst = data.get("dst")
        verb = data.get("verb")
        code = data.get("code")
        payload = data.get("payload")
        packet = data.get("packet")

        # Keep dst as-is for broadcast; the UI can derive any effective target
        # from the packet/via fields if needed.

        # Extract timestamp from the beginning of the line
        dtm_match = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)", line)
        dtm = dtm_match.group(1) if dtm_match else ""

        return NormalizedMessage(
            dtm=dtm,
            src=src or "",
            dst=dst or "",
            verb=verb,
            code=code,
            payload=str(payload) if payload is not None else None,
            packet=str(packet) if packet is not None else None,
            source="ha_log",
            raw_line=line,
            parse_warnings=[],
        )
    except Exception:
        pass

    msg = _parse_ha_log_line_as_packet(line)
    if msg is not None:
        return msg

    return None


def _parse_ha_log_line_as_packet(line: str) -> NormalizedMessage | None:
    raw_tokens = line.split()
    tokens = [t.strip('[](),;"') for t in raw_tokens]
    if not tokens:
        return None

    # Try to derive a timestamp from the start of the line
    dtm = ""
    if len(tokens) >= 2 and re.match(r"^\d{4}-\d{2}-\d{2}$", tokens[0]):
        if re.match(r"^\d{2}:\d{2}:\d{2}(?:\.\d+)?$", tokens[1]):
            dtm = f"{tokens[0]} {tokens[1]}"
    if not dtm and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", tokens[0]):
        dtm = tokens[0]

    verbs = {"RQ", "RP", "I", "W"}
    addr_re = re.compile(r"^(--:------|\d{2}:\d{6})$")
    code_re = re.compile(r"^[0-9A-F]{4}$")
    len_re = re.compile(r"^\d{3}$")

    verb_idx: int | None = None
    verb: str | None = None
    for i, tok in enumerate(tokens):
        if tok in verbs:
            verb_idx = i
            verb = tok
            break
    if verb_idx is None or verb is None:
        return None

    rest = tokens[verb_idx + 1 :]

    addrs = [t for t in rest if addr_re.match(t)]
    if len(addrs) < 2:
        return None
    src = addrs[0]
    dst_raw = addrs[1]
    dst = dst_raw

    code: str | None = None
    code_idx: int | None = None
    for idx, tok in enumerate(rest):
        if code_re.match(tok):
            code = tok
            code_idx = idx
            break
    if code is None or code_idx is None:
        return None

    length: str | None = None
    payload_hex = ""
    for idx in range(code_idx + 1, len(rest)):
        tok = rest[idx]
        if len_re.match(tok):
            length = tok
            payload_hex = " ".join(rest[idx + 1 :])
            break
    if length is None:
        return None

    payload = f"{length} {payload_hex}".strip()
    packet = " ".join(tokens[verb_idx:])

    return NormalizedMessage(
        dtm=dtm,
        src=src,
        dst=dst,
        verb=verb,
        code=code,
        payload=payload,
        packet=packet,
        source="ha_log",
        raw_line=line,
        parse_warnings=[],
    )


async def get_messages_from_sources(
    hass: HomeAssistant,
    sources: list[str],
    *,
    src: str | None = None,
    dst: str | None = None,
    verb: str | None = None,
    code: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
    dedupe: bool = True,
) -> list[dict[str, Any]]:
    """Fetch normalized messages from multiple sources with optional deduplication."""
    providers: dict[str, MessagesProvider] = {}
    # Initialize providers (TODO: cache/reuse instances)
    if "traffic_buffer" in sources:
        # Use the shared buffer provider from TrafficCollector if available
        try:
            domain_data = hass.data.setdefault("ramses_extras", {})
            feature_data = domain_data.setdefault("ramses_debugger", {})
            collector = feature_data.get("traffic_collector")
            if collector is not None and hasattr(collector, "get_buffer_provider"):
                providers["traffic_buffer"] = collector.get_buffer_provider()
            else:
                providers["traffic_buffer"] = TrafficBufferProvider()
        except Exception:
            providers["traffic_buffer"] = TrafficBufferProvider()
    if "packet_log" in sources:
        providers["packet_log"] = PacketLogProvider()
    if "ha_log" in sources:
        providers["ha_log"] = HALogProvider()

    all_messages: list[NormalizedMessage] = []
    for source in sources:
        provider = providers.get(source)
        if not provider:
            continue
        try:
            msgs = await provider.get_messages(
                hass,
                src=src,
                dst=dst,
                verb=verb,
                code=code,
                since=since,
                until=until,
                limit=limit,
            )
            all_messages.extend(msgs)
        except Exception as exc:
            _LOGGER.warning("Error fetching messages from %s: %s", source, exc)

    if dedupe:
        seen = set()
        deduped: list[NormalizedMessage] = []
        for msg in all_messages:
            # Dedupe key: dtm+src+dst+verb+code+packet/payload
            key = (
                msg.dtm,
                msg.src,
                msg.dst,
                msg.verb or "",
                msg.code or "",
                msg.packet or msg.payload or "",
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(msg)
        all_messages = deduped

    # Sort by dtm descending (if present) or insertion order
    all_messages.sort(key=lambda m: m.dtm or "", reverse=True)

    # Convert to dict for JSON serialization
    return [
        {
            "dtm": msg.dtm,
            "src": msg.src,
            "dst": msg.dst,
            "verb": msg.verb,
            "code": msg.code,
            "payload": msg.payload,
            "packet": msg.packet,
            "source": msg.source,
            "raw_line": msg.raw_line,
            "parse_warnings": msg.parse_warnings,
        }
        for msg in all_messages[:limit]
    ]
