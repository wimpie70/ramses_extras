from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from ...const import DOMAIN
from .ramses_commands import RamsesCommands

try:
    from ramses_rf.messages import Message
    from ramses_tx.dtos import PacketDTO
    from ramses_tx.exceptions import PacketInvalid
except ImportError:  # ramses_rf not available at import time
    Message = None
    PacketDTO = None
    PacketInvalid = Exception

_LOGGER = logging.getLogger(__name__)


class RamsesMessageStream:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._msg_handler_unsub: CALLBACK_TYPE | None = None
        self._subscribers: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._next_subscription_id = 0
        self._attach_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._msg_handler_unsub is not None:
            return
        if self._attach_task is None or self._attach_task.done():
            self._attach_task = self._hass.async_create_task(
                self._async_attach_client_listener()
            )

    def stop(self) -> None:
        if self._msg_handler_unsub is not None:
            self._msg_handler_unsub()
            self._msg_handler_unsub = None
        attach_task = self._attach_task
        if attach_task is not None and not attach_task.done():
            attach_task.cancel()
        self._attach_task = None

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> CALLBACK_TYPE:
        subscription_id = self._next_subscription_id
        self._next_subscription_id += 1
        self._subscribers[subscription_id] = callback

        def _unsub() -> None:
            self._subscribers.pop(subscription_id, None)

        return _unsub

    def _resolve_add_msg_handler(self, coordinator: Any) -> Callable[..., Any] | None:
        if coordinator is None:
            return None

        add_msg_handler = getattr(coordinator, "add_msg_handler", None)
        if callable(add_msg_handler):
            return add_msg_handler  # type: ignore[no-any-return]

        client = getattr(coordinator, "client", None)
        add_msg_handler = getattr(client, "add_msg_handler", None)
        if callable(add_msg_handler):
            return add_msg_handler  # type: ignore[no-any-return]

        return None

    async def _async_attach_client_listener(self) -> None:
        commands = RamsesCommands(self._hass)
        max_attempts = 30  # 30s total — coordinator.client may take ~20s

        for attempt in range(max_attempts):
            if self._msg_handler_unsub is not None:
                break

            coordinator = await commands._get_ramses_cc_coordinator()
            add_msg_handler = self._resolve_add_msg_handler(coordinator)
            if callable(add_msg_handler):
                msg_handler_unsub = add_msg_handler(self._handle_msg)
                if callable(msg_handler_unsub):
                    self._msg_handler_unsub = msg_handler_unsub
                    _LOGGER.info(
                        "RamsesMessageStream: attached add_msg_handler "
                        "after %d attempt(s)",
                        attempt + 1,
                    )
                    break

            await asyncio.sleep(1)

        if self._msg_handler_unsub is None:
            _LOGGER.warning(
                "RamsesMessageStream: could not attach add_msg_handler "
                "after %d attempts (ramses_cc coordinator not available)",
                max_attempts,
            )

    def inject(self, data: dict[str, Any]) -> None:
        """Inject a message directly to all subscribers.

        Used by the simulator to push inbound RQ/W frames into the shared
        stream so traffic-collector consumers (e.g. Packet Log Explorer)
        also see outbound commands that ramses_rf never echoes back.
        """
        self._notify_subscribers(data)

    def _notify_subscribers(self, data: dict[str, Any]) -> None:
        for callback in list(self._subscribers.values()):
            callback(data)

    def _frame_from_dict(self, data: dict[str, Any]) -> str | None:
        for key in ("frame", "raw", "msg", "packet"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        verb = data.get("verb")
        src = data.get("src")
        dst = data.get("dst")
        code = data.get("code")
        payload = data.get("payload")
        if not all(isinstance(v, str) and v for v in (verb, src, dst, code)):
            return None
        if not isinstance(payload, str):
            payload = ""
        if any(ch not in "0123456789ABCDEFabcdef" for ch in payload):
            return None

        via = src if dst == "--:------" else "--:------"
        verb_fmt = verb if isinstance(verb, str) and len(verb) == 2 else f" {verb}"
        return (
            f"000 {verb_fmt} --- {src} {dst} {via} {code} "
            f"{len(payload) // 2:03d} {payload}"
        )

    def _packet_fields_from_frame(self, frame: str) -> dict[str, str] | None:
        parts = frame.split("#", 1)[0].strip().split()
        if len(parts) < 8:
            return None

        if parts[0].startswith("20") and len(parts) >= 9:
            parts = parts[1:]

        if len(parts) < 8:
            return None

        # Strip RSSI prefix: signed dBm (-39), unsigned (039), or sentinels.
        # ramses_rf 6e0c5242 normalises RSSI to signed dBm in the log, so
        # we must accept negative values here too.
        if re.match(r"^(?:-?\d{1,3}|---|\.\.\.|///)$", parts[0]):
            parts = parts[1:]

        if len(parts) < 7:
            return None

        verb = parts[0].strip().upper()
        seqn = parts[1]
        if len(parts) < 7 or len(seqn) != 3 and seqn != "---":
            return None

        src, dst = parts[2], parts[3]
        code = parts[5]
        return {
            "verb": verb,
            "src": src,
            "dst": dst,
            "code": code,
            "frame": frame.strip(),
        }

    def _extract_msg_addr(self, msg: Any, attr: str, dto_attr: str) -> str | None:
        value = getattr(getattr(msg, attr, None), "id", None)
        if isinstance(value, str) and value:
            return value
        dto_value = getattr(msg, dto_attr, None)
        if isinstance(dto_value, str) and dto_value:
            return dto_value
        return None

    def _parse_payload(self, data: dict[str, Any]) -> None:
        """Enrich ``data["decoded_payload"]`` with a parsed dict if possible.

        If the payload is a raw hex string, try to parse it via
        ramses_rf's Message parser and store the result in
        ``data["decoded_payload"]``.  ``data["payload"]`` is left as the
        raw hex string so it remains hashable and decodable.
        """
        payload = data.get("payload")
        if payload is None or isinstance(payload, dict):
            return

        # payload is a raw hex string — try to parse it via ramses_rf
        if Message is not None and PacketDTO is not None:
            try:
                from datetime import UTC
                from datetime import datetime as dt

                dto = PacketDTO(
                    timestamp=dt.now(UTC),
                    rssi="",
                    verb=str(data.get("verb", "")).strip(),
                    seq="000",
                    addr1=str(data.get("src", "")),
                    addr2=str(data.get("dst", "")),
                    addr3="--:------",
                    code=str(data.get("code", "")),
                    length=f"{len(str(payload)) // 2:03d}",
                    payload=str(payload),
                )
                parsed_msg = Message(dto)
                data["decoded_payload"] = parsed_msg.payload
                return
            except (PacketInvalid, Exception):
                pass

        # Keep payload as string if we couldn't parse
        data["payload"] = str(payload) if payload is not None else None

    def _handle_msg(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        pkt = getattr(msg, "_pkt", None)
        packet = str(pkt).strip() if pkt is not None else None
        parsed = (
            self._packet_fields_from_frame(packet)
            if isinstance(packet, str) and packet
            else None
        )
        raw_payload = getattr(pkt, "payload", None)
        if raw_payload is None:
            raw_payload = getattr(msg, "payload", None)
        data: dict[str, Any] = parsed or {
            "src": self._extract_msg_addr(msg, "src", "addr1"),
            "dst": self._extract_msg_addr(msg, "dst", "addr2"),
            "verb": str(getattr(msg, "verb", "")) or None,
            "code": str(getattr(msg, "code", "")) or None,
        }
        data["payload"] = raw_payload

        # Capture RSSI for the traffic buffer / viewer.
        # ramses_rf's Message stores rssi directly on the message (msg.rssi),
        # not on a _pkt attribute.  Fall back to pkt.rssi for older versions
        # or other message types that do use _pkt.
        rssi = getattr(msg, "rssi", None)
        if not isinstance(rssi, str) or not rssi:
            rssi = getattr(pkt, "rssi", None)
        if isinstance(rssi, str) and rssi and rssi != "...":
            data["rssi"] = rssi

        if "frame" not in data:
            frame = self._frame_from_dict(data)
            if frame:
                data["frame"] = frame

        if isinstance(packet, str) and packet:
            data["packet"] = packet
            data.setdefault("frame", packet)

        # Parse raw hex payload into a dict via ramses_rf's Message parser.
        # Store the parsed result separately so data["payload"] stays as
        # the raw hex string (needed for dedupe keys and decode).
        if Message is not None and raw_payload is not None:
            try:
                parsed_msg = Message(msg)
                data["decoded_payload"] = parsed_msg.payload
            except (PacketInvalid, Exception):
                self._parse_payload(data)
        else:
            self._parse_payload(data)

        dtm = getattr(msg, "dtm", None)
        if dtm is None:
            dtm = getattr(msg, "timestamp", None)
        if isinstance(dtm, datetime):
            data["dtm"] = dtm.isoformat(timespec="microseconds")
        elif isinstance(dtm, str):
            data["dtm"] = dtm

        self._notify_subscribers(data)


def get_ramses_message_stream(hass: HomeAssistant) -> RamsesMessageStream:
    registry = hass.data.setdefault(DOMAIN, {})
    stream = registry.get("ramses_message_stream")
    if isinstance(stream, RamsesMessageStream):
        return stream
    stream = RamsesMessageStream(hass)
    registry["ramses_message_stream"] = stream
    return stream
