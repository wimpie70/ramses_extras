"""Log-once helper: emit log messages with dedup strategies.

Some log messages (especially startup warnings about missing
configuration) should only be emitted once — not repeated on every
restart or every reload.  This helper provides a reusable, generic
mechanism for that.

Strategies (``LogWhen``):

- ``RESTART``      — log once per HA process (in-memory set, not
  persisted).  Resets when HA restarts.
- ``INSTALL``      — log once ever (persisted in HA ``.storage``).
  Never repeats unless ``clear()`` is called.
- ``VERSION_BUMP`` — log once per integration version (persisted with
  the version string).  Re-logs when the integration is upgraded.
- ``INTERVAL``     — log once, then suppress for *N* days (persisted
  with an expiry timestamp).  Re-logs after the interval elapses.
- ``ALWAYS``       — no dedup; equivalent to a regular ``logger.log()``
  call.  Useful for a unified call site where only some messages need
  dedup.

All persisted state lives in a single HA ``Store`` (one ``.storage``
file), keyed by the caller-provided ``key``.  This keeps disk I/O
low and makes it easy to inspect or reset all flags at once.

Example::

    warner = LogOnce(hass)
    await warner.log(
        key="bound_rem_missing",
        msg="No bound REM configured — ...",
        level=logging.WARNING,
        when=LogWhen.INSTALL,
    )

    # When the situation resolves, clear the flag so a future
    # regression re-warns once:
    await warner.clear("bound_rem_missing")
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_DOMAIN = "ramses_extras"
_STORE_VERSION = 1
_STORE_KEY = "ramses_extras.log_once"
_RESTART_SET_KEY = "_log_once_restart_set"

_SECONDS_PER_DAY = 86_400.0


class LogWhen(StrEnum):
    """When a log-once message should be (re-)emitted."""

    RESTART = "restart"
    INSTALL = "install"
    VERSION_BUMP = "version_bump"
    INTERVAL = "interval"
    ALWAYS = "always"


class LogOnce:
    """Helper to log messages with once-only dedup strategies.

    A single instance can be reused for multiple keys.  State is
    persisted in a shared HA ``Store`` (one ``.storage`` file for all
    keys) so that ``INSTALL`` / ``VERSION_BUMP`` / ``INTERVAL``
    strategies survive HA restarts.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._hass = hass
        self._logger = logger or _LOGGER

    async def log(
        self,
        *,
        key: str,
        msg: str,
        level: int = logging.WARNING,
        when: LogWhen = LogWhen.INSTALL,
        interval_days: float | None = None,
        args: tuple[Any, ...] | None = None,
        logger: logging.Logger | None = None,
    ) -> bool:
        """Log *msg* at *level* if the dedup strategy allows it.

        :param key: Unique persistence key (scoped to this helper's
            store).  The same key must be used for the same message
            across calls/restarts.
        :param msg: Log message (may include ``%s``-style placeholders
            if *args* is provided).
        :param level: Standard ``logging`` level constant, e.g.
            ``logging.WARNING`` or ``logging.INFO``.
        :param when: Dedup strategy.  See :class:`LogWhen`.
        :param interval_days: Required for ``LogWhen.INTERVAL``;
            ignored otherwise.  Number of days to suppress after
            logging.
        :param args: Optional format args for lazy ``%``-interpolation
            (passed through to ``logger.log``).
        :param logger: Override the logger for this call only.  Defaults
            to the logger set at construction (or the module logger).
        :return: ``True`` if the message was logged this call,
            ``False`` if it was suppressed by the dedup strategy.
        """
        log = logger or self._logger
        log_args = args or ()

        # --- strategies that don't need persistence ------------------

        if when == LogWhen.ALWAYS:
            log.log(level, msg, *log_args)
            return True

        if when == LogWhen.RESTART:
            data = self._hass.data.setdefault(_DOMAIN, {})
            restart_set: set[str] = data.setdefault(_RESTART_SET_KEY, set())
            if key in restart_set:
                return False
            restart_set.add(key)
            log.log(level, msg, *log_args)
            return True

        # --- persisted strategies ------------------------------------

        state = await self._load_state()
        entry = state.get(key, {})
        now = time.time()

        should_log = False
        new_entry: dict[str, Any] = {"logged_at": now}

        if when == LogWhen.INSTALL:
            if not entry:
                should_log = True

        elif when == LogWhen.VERSION_BUMP:
            version = await self._get_integration_version()
            new_entry["version"] = version
            if not entry or entry.get("version") != version:
                should_log = True

        elif when == LogWhen.INTERVAL:
            days = interval_days if interval_days is not None else 1.0
            new_entry["expires_at"] = now + (days * _SECONDS_PER_DAY)
            expires_at = entry.get("expires_at")
            if not isinstance(expires_at, (int, float)) or now >= expires_at:
                should_log = True

        if should_log:
            state[key] = new_entry
            await self._save_state(state)
            log.log(level, msg, *log_args)
            return True

        return False

    async def clear(self, key: str) -> None:
        """Clear the dedup state for *key* so it can fire again.

        Works for all strategies (``RESTART`` in-memory set and the
        persisted store).  Use this when a previously-warned condition
        has been resolved, so that a future regression re-warns once.
        """
        # Clear from in-memory restart set
        data = self._hass.data.get(_DOMAIN, {})
        restart_set = data.get(_RESTART_SET_KEY)
        if isinstance(restart_set, set):
            restart_set.discard(key)

        # Clear from persisted store
        state = await self._load_state()
        if key in state:
            state.pop(key)
            await self._save_state(state)

    async def is_logged(self, key: str) -> bool:
        """Check whether *key* has been logged (without logging).

        For ``RESTART``: checks the in-memory set.
        For persisted strategies: checks whether the key exists in the
        store (does **not** check interval expiry or version match —
        the caller should know which strategy was used).
        """
        data = self._hass.data.get(_DOMAIN, {})
        restart_set = data.get(_RESTART_SET_KEY)
        if isinstance(restart_set, set) and key in restart_set:
            return True

        state = await self._load_state()
        return key in state

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    async def _get_integration_version(self) -> str:
        """Return the current integration version, cached if available."""
        data = self._hass.data.setdefault(_DOMAIN, {})
        cached = data.get("_integration_version")
        if isinstance(cached, str) and cached:
            return cached
        try:
            from ..setup.cards import async_get_integration_version

            version = await async_get_integration_version(self._hass)
            return str(version)
        except Exception:
            return "0.0.0"

    async def _load_state(self) -> dict[str, Any]:
        """Load the persisted log-once state dict."""
        try:
            from homeassistant.helpers.storage import Store

            store = Store(self._hass, _STORE_VERSION, _STORE_KEY)
            data = await store.async_load()
            if isinstance(data, dict):
                return data
        except Exception:
            _LOGGER.debug("Failed to load log-once state", exc_info=True)
        return {}

    async def _save_state(self, state: dict[str, Any]) -> None:
        """Persist the log-once state dict."""
        try:
            from homeassistant.helpers.storage import Store

            store = Store(self._hass, _STORE_VERSION, _STORE_KEY)
            await store.async_save(state)
        except Exception:
            _LOGGER.debug("Failed to save log-once state", exc_info=True)
