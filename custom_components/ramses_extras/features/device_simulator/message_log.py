# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Structured message log for device simulator traffic."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import time
from typing import Literal

PacketDirection = Literal["inbound", "outbound"]

_PACKET_RE = re.compile(
    r"^[0-9A-F]{3}\s+([A-Z ]{1,2})\s+\S+\s+([0-9A-F:]{8})\s+([0-9A-F:]{8})\s+"
    r"[0-9A-F:]{8}\s+([0-9A-F]{4})\s+[0-9]{3}\s+([0-9A-F]*)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class LoggedMessage:
    """Structured representation of a parsed simulator frame."""

    ts: float
    direction: PacketDirection
    verb: str
    code: str
    src: str
    dst: str
    payload: str
    raw: str
    device_id: str | None


def _parse_frame(
    frame: str,
) -> tuple[str, str, str, str, str] | None:
    """Return (verb, src, dst, code, payload) or None if parse fails."""
    match = _PACKET_RE.match(frame.strip())
    if not match:
        return None
    verb, src, dst, code, payload = match.groups()
    return verb.strip(), src, dst, code, payload


class DeviceMessageLog:
    """Thread-safe ring buffer tracking recent simulator frames."""

    def __init__(
        self,
        *,
        max_entries: int = 500,
        per_device_entries: int = 100,
    ) -> None:
        self._global: deque[LoggedMessage] = deque(maxlen=max_entries)
        self._per_device: dict[str, deque[LoggedMessage]] = defaultdict(
            lambda: deque(maxlen=per_device_entries)
        )
        self._lock = Lock()

    def log(self, direction: PacketDirection, frame: str) -> None:
        """Parse *frame* and append it to the global and per-device buffers."""
        parsed = _parse_frame(frame)
        if not parsed:
            return
        verb, src, dst, code, payload = parsed
        device_id = src if direction == "outbound" else dst
        entry = LoggedMessage(
            ts=time(),
            direction=direction,
            verb=verb,
            code=code,
            src=src,
            dst=dst,
            payload=payload,
            raw=frame,
            device_id=device_id if device_id and device_id != "--:------" else None,
        )
        with self._lock:
            self._global.append(entry)
            if entry.device_id:
                self._per_device[entry.device_id].append(entry)

    def get_recent(
        self,
        *,
        limit: int = 50,
        device_id: str | None = None,
    ) -> list[LoggedMessage]:
        """Return the most recent *limit* messages (optionally filtered by device)."""
        with self._lock:
            source = (
                self._per_device[device_id]
                if device_id and device_id in self._per_device
                else self._global
            )
            return list(source)[-limit:]

    def get_preview(
        self,
        device_ids: list[str],
        *,
        per_device: int = 5,
    ) -> dict[str, list[LoggedMessage]]:
        """Return the last *per_device* messages for each of *device_ids*."""
        preview: dict[str, list[LoggedMessage]] = {}
        with self._lock:
            for dev in device_ids:
                if dev in self._per_device:
                    preview[dev] = list(self._per_device[dev])[-per_device:]
        return preview

    def to_dict(self, msg: LoggedMessage) -> dict:
        """Serialise a LoggedMessage to a JSON-safe dict."""
        return {
            "ts": msg.ts,
            "direction": msg.direction,
            "verb": msg.verb,
            "code": msg.code,
            "src": msg.src,
            "dst": msg.dst,
            "payload": msg.payload,
            "device_id": msg.device_id,
        }
