from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .log_backend import get_configured_log_path

_LOGGER = logging.getLogger(__name__)


class PacketLogParser:
    """Provider for parsing traffic records from ramses packet/message log."""

    @staticmethod
    async def get_messages(
        hass: HomeAssistant,
        src: str | None = None,
        dst: str | None = None,
        verb: str | None = None,
        code: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 1000,
    ) -> list[NormalizedMessage]:
        """Parse traffic records from ramses_log."""
        log_path = get_configured_log_path(hass)
        if not log_path:
            return []

        try:
            # Simple file reading approach
            content = await hass.async_add_executor_job(
                log_path.read_text, encoding="utf-8"
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
    # Expected format: timestamp verb src dst filler code payload_len payload_hex
    # Example: 2026-01-20T09:58:48.263427 I 32:153289 32:153289 --:------
    # 31DA 030 00EF007F...
    parts = line.strip().split()
    if len(parts) < 7:
        return None

    try:
        dtm = parts[0]
        verb = parts[1]
        src = parts[2]
        dst = parts[3]
        # parts[4] is filler (e.g., --:------)
        code = parts[5]
        payload_len = parts[6]
        payload_hex = " ".join(parts[7:]) if len(parts) > 7 else ""

        packet = " ".join(parts[1:])  # Full packet string
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
            # Simple file reading approach
            content = await hass.async_add_executor_job(
                log_path.read_text, encoding="utf-8"
            )
            lines = content.splitlines()

            messages: list[NormalizedMessage] = []
            for line in lines:
                # Look for lines that contain ramses_cc
                if "ramses_cc" not in line:
                    continue
                msg = _parse_ha_log_line(line)
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
            _LOGGER.warning("HALogProvider error: %s", exc)
            return []


def _parse_ha_log_line(line: str) -> NormalizedMessage | None:
    """Parse a HA log line containing a ramses_cc message."""
    # Expected HA log format with JSON payload:
    # 2026-01-20 09:58:48 DEBUG (MainThread) [custom_components.ramses_cc] ...
    # {"src": "...", "dst": "...", "verb": "...", ...}
    # We'll try to extract JSON from the line and parse it.
    import json
    import re

    # Look for JSON-like structure in the line
    json_match = re.search(r"\{.*\}", line)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        src = data.get("src")
        dst = data.get("dst")
        verb = data.get("verb")
        code = data.get("code")
        payload = data.get("payload")
        packet = data.get("packet")

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
        return None


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
            from .traffic_collector import TrafficCollector

            domain_data = hass.data.setdefault("ramses_extras", {})
            feature_data = domain_data.setdefault("ramses_debugger", {})
            collector = feature_data.get("traffic_collector")
            if isinstance(collector, TrafficCollector):
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
