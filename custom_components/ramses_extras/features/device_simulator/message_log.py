# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Structured message log for device simulator traffic."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from time import time
from typing import Any, Literal

PacketDirection = Literal["inbound", "outbound"]

_ADDR = r"(?:[0-9]{2}:[0-9]{6}|--:------)"

_PACKET_RE = re.compile(
    r"^(?:(?:[0-9]{3}|---)\s+)?"  # optional RSSI / ---
    r"([ RQWIP]{1,2})\s+"  # verb (space-padded 1-char or 2-char)
    r"(?:[0-9]{3}|---)\s+"  # SEQ
    rf"({_ADDR})\s+"  # SRC
    rf"({_ADDR})\s+"  # DST
    rf"({_ADDR})\s+"  # BROADCAST
    r"([0-9A-F]{4})\s+[0-9]{3}\s*([0-9A-F]*)",  # CODE LEN PAYLOAD
    re.IGNORECASE,
)

PROFILE_PREVIEW_SAMPLES = 5


@dataclass(slots=True)
class LoggedMessage:
    """Structured representation of a parsed simulator frame."""

    ts: float
    direction: PacketDirection
    verb: str
    code: str
    src: str
    dst: str
    broadcast: str
    payload: str
    raw: str
    device_id: str | None


_SILENT_LOGGERS = (
    "ramses_tx.packet_log",
    "ramses_tx.packet",
    "ramses_tx.message",
    "ramses_tx.parsers",
)


def _decode_payload(
    verb: str,
    src: str,
    dst: str,
    broadcast: str,
    code: str,
    payload_hex: str,
    ts: float,
) -> Any:
    """Decode a RAMSES payload via ramses_tx; returns parsed value or None."""
    import logging

    try:
        from ramses_tx.message import Message
        from ramses_tx.packet import Packet
    except ModuleNotFoundError:
        return None

    via = (
        broadcast
        if broadcast and broadcast != "--:------"
        else (src if dst == "--:------" else "--:------")
    )
    verb2 = verb if len(verb) == 2 else f" {verb}"
    length = len(payload_hex) // 2
    frame = f"000 {verb2} --- {src} {dst} {via} {code} {length:03d} {payload_hex}"
    dt_obj = datetime.fromtimestamp(ts)

    for name in _SILENT_LOGGERS:
        logging.getLogger(name).disabled = True
    try:
        pkt = Packet(dt_obj, frame)
        m = Message._from_pkt(pkt)
        return m.payload
    except Exception:
        return None
    finally:
        for name in _SILENT_LOGGERS:
            logging.getLogger(name).disabled = False


def _parse_frame(
    frame: str,
) -> tuple[str, str, str, str, str, str] | None:
    """Return (verb, src, dst, broadcast, code, payload) or None if parse fails."""
    match = _PACKET_RE.match(frame.strip())
    if not match:
        return None
    verb, src, dst, broadcast, code, payload = match.groups()
    return verb.strip().upper(), src, dst, broadcast, code, payload


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

    def log(
        self, direction: PacketDirection, frame: str, timestamp: float | None = None
    ) -> LoggedMessage | None:
        """Parse *frame* and append it to the global and per-device buffers.

        Both src and dst are indexed so traffic between two active devices
        appears in the log for each of them.
        """
        parsed = _parse_frame(frame)
        if not parsed:
            return None
        verb, src, dst, broadcast, code, payload = parsed
        entry = LoggedMessage(
            ts=timestamp if timestamp is not None else time(),
            direction=direction,
            verb=verb,
            code=code,
            src=src,
            dst=dst,
            broadcast=broadcast,
            payload=payload,
            raw=frame,
            device_id=src
            if src and src != "--:------"
            else (dst if dst and dst != "--:------" else None),
        )
        with self._lock:
            self._global.append(entry)
            for dev in (src, dst):
                if dev and dev != "--:------":
                    self._per_device[dev].append(entry)
        return entry

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
            messages = list(source)
            messages.sort(key=lambda m: m.ts)
            return messages[-limit:]

    def get_for_devices(
        self,
        device_ids: list[str],
        *,
        per_device: int = 8,
    ) -> dict[str, list[dict]]:
        """Return the last *per_device* messages for each id, serialised."""
        result: dict[str, list[dict]] = {}
        with self._lock:
            for dev in device_ids:
                if dev in self._per_device:
                    messages = list(self._per_device[dev])
                    messages.sort(key=lambda m: m.ts)
                    result[dev] = [self.to_dict(m) for m in messages[-per_device:]]
        return result

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
                    messages = list(self._per_device[dev])
                    messages.sort(key=lambda m: m.ts)
                    preview[dev] = messages[-per_device:]
        return preview

    def clear(self, device_ids: list[str] | None = None) -> None:
        """Clear the entire log or specific device slices."""
        with self._lock:
            if not device_ids:
                self._global.clear()
                self._per_device.clear()
                return

            targets = {dev for dev in device_ids if dev in self._per_device}
            for dev in targets:
                self._per_device.pop(dev, None)

            if targets:
                filtered = deque(
                    (msg for msg in self._global if msg.device_id not in targets),
                    maxlen=self._global.maxlen,
                )
                self._global = filtered

    def to_dict(self, msg: LoggedMessage) -> dict:
        """Serialise a LoggedMessage to a JSON-safe dict."""
        decoded = _decode_payload(
            msg.verb,
            msg.src,
            msg.dst,
            msg.broadcast,
            msg.code,
            msg.payload,
            msg.ts,
        )
        device_ids = [dev for dev in {msg.src, msg.dst} if dev and dev != "--:------"]
        return {
            "ts": msg.ts,
            "direction": msg.direction,
            "verb": msg.verb,
            "code": msg.code,
            "src": msg.src,
            "dst": msg.dst,
            "broadcast": msg.broadcast,
            "payload": msg.payload,
            "decoded_payload": decoded,
            "device_id": msg.device_id,
            "device_ids": device_ids,
        }
