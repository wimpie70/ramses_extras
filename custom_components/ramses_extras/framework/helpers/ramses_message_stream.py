from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant

from ...const import DOMAIN
from .ramses_commands import RamsesCommands


class RamsesMessageStream:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._event_unsub: CALLBACK_TYPE | None = None
        self._msg_handler_unsub: CALLBACK_TYPE | None = None
        self._subscribers: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._next_subscription_id = 0
        self._attach_task = None

    def start(self) -> None:
        if self._event_unsub is not None or self._msg_handler_unsub is not None:
            return
        self._event_unsub = self._hass.bus.async_listen(
            "ramses_cc_message",
            self._handle_ramses_cc_message,
        )
        if self._attach_task is None or self._attach_task.done():  # type: ignore[unreachable]
            self._attach_task = self._hass.async_create_task(
                self._async_attach_client_listener()
            )

    def stop(self) -> None:
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        if self._msg_handler_unsub is not None:
            self._msg_handler_unsub()
            self._msg_handler_unsub = None
        attach_task = self._attach_task
        if attach_task is not None and not attach_task.done():  # type: ignore[unreachable]
            attach_task.cancel()  # type: ignore[unreachable]
        self._attach_task = None

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> CALLBACK_TYPE:
        subscription_id = self._next_subscription_id
        self._next_subscription_id += 1
        self._subscribers[subscription_id] = callback

        def _unsub() -> None:
            self._subscribers.pop(subscription_id, None)

        return _unsub

    async def _async_attach_client_listener(self) -> None:
        commands = RamsesCommands(self._hass)
        coordinator = await commands._get_ramses_cc_coordinator()
        client = (
            getattr(coordinator, "client", None) if coordinator is not None else None
        )
        add_msg_handler = getattr(client, "add_msg_handler", None)
        if not callable(add_msg_handler) or self._msg_handler_unsub is not None:
            return

        msg_handler_unsub = add_msg_handler(self._handle_msg)
        if callable(msg_handler_unsub):
            self._msg_handler_unsub = msg_handler_unsub

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

        if parts[0] in {"...", "---"} or parts[0].isdigit():
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

    def _handle_ramses_cc_message(self, event: Event[dict[str, Any]]) -> None:
        data = dict(event.data or {})
        data["time_fired"] = event.time_fired.isoformat(timespec="microseconds")
        verb = data.get("verb")
        verb_upper = verb.upper().strip() if isinstance(verb, str) else None
        if self._msg_handler_unsub is not None and verb_upper in {"RP", "I"}:
            return
        frame = self._frame_from_dict(data)
        if frame:
            data["frame"] = frame
        self._notify_subscribers(data)

    def _handle_msg(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        pkt = getattr(msg, "_pkt", None)
        packet = str(pkt).strip() if pkt is not None else None
        parsed = (
            self._packet_fields_from_frame(packet)
            if isinstance(packet, str) and packet
            else None
        )
        payload = getattr(pkt, "payload", None)
        data = parsed or {
            "src": getattr(getattr(msg, "src", None), "id", None),  # type: ignore[dict-item]
            "dst": getattr(getattr(msg, "dst", None), "id", None),  # type: ignore[dict-item]
            "verb": str(getattr(msg, "verb", "")) or None,  # type: ignore[dict-item]
            "code": str(getattr(msg, "code", "")) or None,  # type: ignore[dict-item]
        }
        data["payload"] = str(payload) if payload is not None else None  # type: ignore[assignment]
        if isinstance(packet, str) and packet:
            data["packet"] = packet
            data.setdefault("frame", packet)

        dtm = getattr(msg, "dtm", None)
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
