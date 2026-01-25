from __future__ import annotations

import asyncio
import inspect
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, cast


def freeze_for_key(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(freeze_for_key(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, freeze_for_key(v)) for k, v in value.items()))
    return repr(value)


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    expires_at: float


class DebuggerCache:
    """Small async TTL cache with in-flight de-duplication.

    This cache is used by ramses_debugger WebSocket handlers to:
    - deduplicate expensive log scans across multiple cards
    - avoid rescanning unchanged files (keyed by file state)

    Cache keys must already include request parameters and any relevant file state
    (e.g. size + mtime).
    """

    def __init__(self, *, max_entries: int = 256) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[Any, CacheEntry] = OrderedDict()
        self._inflight: dict[Any, asyncio.Task[Any]] = {}

    def clear(self) -> None:
        self._entries.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "max_entries": int(self._max_entries),
            "entries": int(len(self._entries)),
            "inflight": int(len(self._inflight)),
        }

    def _normalize_key(self, key: Any) -> Any:
        """Normalize a key to ensure it's hashable."""
        return freeze_for_key(key)

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _get_fresh(self, key: Any) -> Any | None:
        normalized_key = self._normalize_key(key)
        entry = self._entries.get(normalized_key)
        if entry is None:
            return None

        now = monotonic()
        if entry.expires_at <= now:
            self._entries.pop(normalized_key, None)
            return None

        self._entries.move_to_end(normalized_key)
        return entry.value

    def set(self, key: Any, value: Any, *, ttl_s: float) -> None:
        ttl_s = max(0.0, float(ttl_s))
        expires_at = monotonic() + ttl_s
        normalized_key = self._normalize_key(key)
        self._entries[normalized_key] = CacheEntry(value=value, expires_at=expires_at)
        self._entries.move_to_end(normalized_key)
        self._evict_if_needed()

    async def get_or_create(
        self,
        key: Any,
        *,
        ttl_s: float,
        create_fn: Callable[[], Awaitable[Any] | Any],
    ) -> Any:
        """Get a cached value or compute it once and share the result.

        `create_fn` may be a coroutine function or a regular function.
        """

        cached = self._get_fresh(key)
        if cached is not None:
            return cached

        normalized_key = self._normalize_key(key)
        inflight = self._inflight.get(normalized_key)
        if inflight is not None:
            return await inflight

        async def _runner() -> Any:
            try:
                created = create_fn()
                if inspect.isawaitable(created):
                    created = await cast(Awaitable[Any], created)

                value = created
                self.set(key, value, ttl_s=ttl_s)
                return value
            finally:
                self._inflight.pop(normalized_key, None)

        task = asyncio.create_task(_runner())
        self._inflight[normalized_key] = task
        return await task
