from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.loader import async_get_integration

from ...const import DOMAIN
from .ramses_commands import RamsesCommands

_LOGGER = logging.getLogger(__name__)

# ramses_cc 0.55.6 removed ramses_cc_message HA bus events and replaced
# them with HA Event Entities.  Before this version, ramses_cc itself
# fired ramses_cc_message events on the HA bus (when MESSAGE_EVENTS was
# enabled in advanced config).  After this version, the only way to
# receive messages is via coordinator.client.add_msg_handler().
_RAMSES_CC_MESSAGE_EVENTS_REMOVED = "0.55.6"


def _version_tuple(version: str) -> tuple[int, ...]:
    """Convert a dotted version string to a comparable tuple."""
    parts: list[int] = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            # Strip non-numeric suffixes (e.g. "0.55.6-beta" → 0.55.6)
            numeric = ""
            for ch in part:
                if ch.isdigit():
                    numeric += ch
                else:
                    break
            parts.append(int(numeric) if numeric else 0)
    return tuple(parts)


class RamsesMessageStream:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._event_unsub: CALLBACK_TYPE | None = None
        self._msg_handler_unsub: CALLBACK_TYPE | None = None
        self._subscribers: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._next_subscription_id = 0
        self._attach_task = None
        # None = not yet checked, True/False = ramses_cc fires its own
        # ramses_cc_message HA bus events
        self._ramses_cc_fires_events: bool | None = None

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

    async def _async_ramses_cc_fires_events(self) -> bool:
        """Check whether ramses_cc fires ramses_cc_message HA bus events.

        ramses_cc < 0.55.6 fired these events when MESSAGE_EVENTS was
        enabled.  ramses_cc >= 0.55.6 removed them entirely.  We detect
        the version at runtime via the integration manifest.
        """
        if self._ramses_cc_fires_events is not None:
            return self._ramses_cc_fires_events

        try:
            integration = await async_get_integration(self._hass, "ramses_cc")
            version = integration.manifest.get("version", "0.0.0")
            if isinstance(version, str) and version:
                fires = _version_tuple(version) < _version_tuple(
                    _RAMSES_CC_MESSAGE_EVENTS_REMOVED
                )
                self._ramses_cc_fires_events = fires
                _LOGGER.debug(
                    "ramses_cc version %s fires_message_events=%s",
                    version,
                    fires,
                )
                return fires
        except Exception as e:
            _LOGGER.debug(
                "Could not determine ramses_cc version, assuming no bus events: %s",
                e,
            )

        self._ramses_cc_fires_events = False
        return False

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
        max_attempts = 15

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

        # Detect ramses_cc version to decide whether we need to fire
        # ramses_cc_message HA bus events ourselves (newer versions) or
        # rely on ramses_cc firing them (older versions).
        await self._async_ramses_cc_fires_events()

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

    def _extract_msg_addr(self, msg: Any, attr: str, dto_attr: str) -> str | None:
        value = getattr(getattr(msg, attr, None), "id", None)
        if isinstance(value, str) and value:
            return value
        dto_value = getattr(msg, dto_attr, None)
        if isinstance(dto_value, str) and dto_value:
            return dto_value
        return None

    def _handle_ramses_cc_message(self, event: Event[dict[str, Any]]) -> None:
        data = dict(event.data or {})
        data["time_fired"] = event.time_fired.isoformat(timespec="microseconds")
        # Skip events that were fired by _handle_msg (via add_msg_handler)
        # to avoid duplicate subscriber notifications.  Events from other
        # sources (e.g. outbound RQ from ramses_cc) are still processed.
        if data.get("_from_msg_handler"):
            return
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
        if payload is None:
            payload = getattr(msg, "payload", None)
        data: dict[str, Any] = parsed or {
            "src": self._extract_msg_addr(msg, "src", "addr1"),
            "dst": self._extract_msg_addr(msg, "dst", "addr2"),
            "verb": str(getattr(msg, "verb", "")) or None,
            "code": str(getattr(msg, "code", "")) or None,
        }
        data["payload"] = str(payload) if payload is not None else None

        if "frame" not in data:
            frame = self._frame_from_dict(data)
            if frame:
                data["frame"] = frame

        if isinstance(packet, str) and packet:
            data["packet"] = packet
            data.setdefault("frame", packet)

        dtm = getattr(msg, "dtm", None)
        if dtm is None:
            dtm = getattr(msg, "timestamp", None)
        if isinstance(dtm, datetime):
            data["dtm"] = dtm.isoformat(timespec="microseconds")
        elif isinstance(dtm, str):
            data["dtm"] = dtm

        self._notify_subscribers(data)

        # Fire on HA event bus so frontend components (e.g. the HVAC Fan
        # Card's message broker) can receive real-time message data via
        # WebSocket subscription.
        #
        # Version-aware logic:
        # - ramses_cc >= 0.55.6 (_ramses_cc_fires_events=False): ramses_cc
        #   no longer fires ramses_cc_message events, so we must fire them
        #   here for the frontend.  The _from_msg_handler marker lets
        #   _handle_ramses_cc_message skip this event to avoid duplicates.
        # - ramses_cc < 0.55.6 (_ramses_cc_fires_events=True): ramses_cc
        #   fires these events itself (when MESSAGE_EVENTS is enabled), so
        #   we skip firing to avoid duplicates.  If MESSAGE_EVENTS is not
        #   enabled, the frontend falls back to entity states.
        # - Unknown (None): fire for safety until version is determined.
        if self._ramses_cc_fires_events is not True:
            try:
                data["_from_msg_handler"] = True
                self._hass.bus.async_fire("ramses_cc_message", data)
                _LOGGER.debug(
                    "Fired ramses_cc_message event: code=%s src=%s verb=%s",
                    data.get("code"),
                    data.get("src"),
                    data.get("verb"),
                )
            except Exception as e:
                _LOGGER.debug("Failed to fire ramses_cc_message event: %s", e)


def get_ramses_message_stream(hass: HomeAssistant) -> RamsesMessageStream:
    registry = hass.data.setdefault(DOMAIN, {})
    stream = registry.get("ramses_message_stream")
    if isinstance(stream, RamsesMessageStream):
        return stream
    stream = RamsesMessageStream(hass)
    registry["ramses_message_stream"] = stream
    return stream
