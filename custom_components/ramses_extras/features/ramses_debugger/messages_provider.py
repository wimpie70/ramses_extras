from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .log_backend import get_configured_log_path
from .traffic_collector import TrafficCollector

_LOGGER = logging.getLogger(__name__)


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
        messages: list[NormalizedMessage] = []
        base = get_configured_log_path(hass)
        if not base:
            return messages

        log_path = base.parent / "ramses_log"
        if not log_path.is_file():
            return messages

        try:
            content = await hass.async_add_executor_job(
                log_path.read_text, encoding="utf-8"
            )
            for line in content.splitlines():
                # Very naive parsing for now; refine later
                if "RAMSES RF" not in line:
                    continue
                # TODO: extract dtm, src, dst, verb, code, payload/packet
                # For now, return a placeholder to indicate the line matched
                msg = NormalizedMessage(
                    dtm="",
                    src="",
                    dst="",
                    verb=None,
                    code=None,
                    payload=None,
                    packet=None,
                    source="packet_log",
                    raw_line=line,
                    parse_warnings=["packet log parser not yet implemented"],
                )
                messages.append(msg)
                if len(messages) >= limit:
                    break
        except Exception as exc:
            _LOGGER.debug("Failed to read packet log %s: %s", log_path, exc)
        return messages


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
        messages: list[NormalizedMessage] = []
        base = get_configured_log_path(hass)
        if not base:
            return messages
        if not base.is_file():
            return messages

        try:
            content = await hass.async_add_executor_job(
                base.read_text, encoding="utf-8"
            )
            for line in content.splitlines():
                # Look for lines that look like ramses_cc messages
                if "ramses_cc" not in line:
                    continue
                # TODO: extract dtm, src, dst, verb, code, payload/packet
                # For now, return a placeholder to indicate the line matched
                msg = NormalizedMessage(
                    dtm="",
                    src="",
                    dst="",
                    verb=None,
                    code=None,
                    payload=None,
                    packet=None,
                    source="ha_log",
                    raw_line=line,
                    parse_warnings=["ha log parser not yet implemented"],
                )
                messages.append(msg)
                if len(messages) >= limit:
                    break
        except Exception as exc:
            _LOGGER.debug("Failed to read HA log %s: %s", base, exc)
        return messages


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
        # For now, we don't have a shared buffer instance; placeholder
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
