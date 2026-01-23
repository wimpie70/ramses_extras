from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant

from .messages_provider import TrafficBufferProvider

_LOGGER = logging.getLogger(__name__)


@dataclass
class TrafficFlowStats:
    src: str
    dst: str
    count_total: int = 0
    last_seen: str | None = None
    verbs_counter: Counter[str] = field(default_factory=Counter)
    codes_counter: Counter[str] = field(default_factory=Counter)

    def add_message(
        self, *, verb: str | None, code: str | None, dtm: str | None
    ) -> None:
        self.count_total += 1
        if verb:
            self.verbs_counter[verb] += 1
        if code:
            self.codes_counter[code] += 1
        if dtm:
            self.last_seen = dtm


class TrafficCollector:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsub: CALLBACK_TYPE | None = None

        self._flows: dict[tuple[str, str], TrafficFlowStats] = {}
        self._max_flows: int = 2000
        self._total_count = 0
        self._by_code: Counter[str] = Counter()
        self._by_verb: Counter[str] = Counter()
        self._started_at: str = datetime.now().isoformat(timespec="seconds")

        self._buffer_provider = TrafficBufferProvider()

    def configure(
        self,
        *,
        max_flows: int | None = None,
        buffer_max_global: int | None = None,
        buffer_max_per_flow: int | None = None,
        buffer_max_flows: int | None = None,
    ) -> None:
        if max_flows is not None:
            self._max_flows = max(1, int(max_flows))

        self._buffer_provider.configure(
            max_global=buffer_max_global,
            max_per_flow=buffer_max_per_flow,
            max_flows=buffer_max_flows,
        )

        self._evict_flows_if_needed()

    def _evict_flows_if_needed(self) -> None:
        while len(self._flows) > self._max_flows:
            oldest_key: tuple[str, str] | None = None
            oldest_dtm: str | None = None
            for k, flow in self._flows.items():
                if oldest_key is None:
                    oldest_key = k
                    oldest_dtm = flow.last_seen
                    continue

                dtm = flow.last_seen
                if oldest_dtm is None:
                    if dtm is not None:
                        oldest_key = k
                        oldest_dtm = dtm
                    continue

                if dtm is None or dtm < oldest_dtm:
                    oldest_key = k
                    oldest_dtm = dtm

            if oldest_key is None:
                break

            self._flows.pop(oldest_key, None)
            self._buffer_provider.evict_flow(oldest_key)

    def start(self) -> None:
        if self._unsub is not None:
            return
        self._unsub = self._hass.bus.async_listen(
            "ramses_cc_message",
            self._handle_ramses_cc_message,
        )
        _LOGGER.debug("TrafficCollector started (listening for ramses_cc_message)")

    def stop(self) -> None:
        if self._unsub is None:
            return
        self._unsub()
        self._unsub = None
        _LOGGER.debug("TrafficCollector stopped")

    def reset(self) -> None:
        self._flows.clear()
        self._total_count = 0
        self._by_code.clear()
        self._by_verb.clear()
        self._started_at = datetime.now().isoformat(timespec="seconds")

    def get_stats(
        self,
        *,
        device_id: str | None = None,
        src: str | None = None,
        dst: str | None = None,
        code: str | None = None,
        verb: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        flows: list[TrafficFlowStats] = []
        for flow in self._flows.values():
            if device_id and device_id not in (flow.src, flow.dst):
                continue
            if src and flow.src != src:
                continue
            if dst and flow.dst != dst:
                continue
            if code and flow.codes_counter.get(code, 0) == 0:
                continue
            if verb and flow.verbs_counter.get(verb, 0) == 0:
                continue
            flows.append(flow)

        flows.sort(key=lambda f: f.count_total, reverse=True)

        return {
            "started_at": self._started_at,
            "total_count": self._total_count,
            "by_code": dict(self._by_code),
            "by_verb": dict(self._by_verb),
            "flows": [
                {
                    "src": f.src,
                    "dst": f.dst,
                    "count_total": f.count_total,
                    "last_seen": f.last_seen,
                    "verbs": dict(f.verbs_counter),
                    "codes": dict(f.codes_counter),
                }
                for f in flows[: max(0, limit)]
            ],
        }

    def get_buffer_provider(self) -> TrafficBufferProvider:
        """Return the TrafficBufferProvider for message queries."""
        return self._buffer_provider

    def _handle_ramses_cc_message(self, event: Event[dict[str, Any]]) -> None:
        raw = event.data or {}
        data = dict(raw)
        data["time_fired"] = event.time_fired.isoformat(timespec="microseconds")

        src = data.get("src")
        dst = data.get("dst")
        if not isinstance(src, str) or not isinstance(dst, str):
            return

        verb = data.get("verb")
        if not isinstance(verb, str):
            verb = None

        code = data.get("code")
        if not isinstance(code, str):
            code = None

        dtm = data.get("time_fired")
        if not isinstance(dtm, str):
            dtm = data.get("dtm")
            if not isinstance(dtm, str):
                dtm = None

        # Ingest into buffer provider for message queries
        self._buffer_provider.ingest_event(data)

        self._total_count += 1
        if code:
            self._by_code[code] += 1
        if verb:
            self._by_verb[verb] += 1

        key = (src, dst)
        flow = self._flows.get(key)
        if flow is None:
            flow = TrafficFlowStats(src=src, dst=dst)
            self._flows[key] = flow

        flow.add_message(verb=verb, code=code, dtm=dtm)

        self._evict_flows_if_needed()
