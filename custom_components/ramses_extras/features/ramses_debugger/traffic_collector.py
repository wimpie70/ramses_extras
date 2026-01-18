from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

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
        self._total_count = 0
        self._by_code: Counter[str] = Counter()
        self._by_verb: Counter[str] = Counter()
        self._started_at: str = datetime.now().isoformat(timespec="seconds")

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
        src: str | None = None,
        dst: str | None = None,
        code: str | None = None,
        verb: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        flows: list[TrafficFlowStats] = []
        for flow in self._flows.values():
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

    # @callback # deprecated
    def _handle_ramses_cc_message(self, event: Event[dict[str, Any]]) -> None:
        data = event.data or {}

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

        dtm = data.get("dtm")
        if not isinstance(dtm, str):
            dtm = None

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
