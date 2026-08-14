"""Live per-container status dashboard for parallel ha_sim_test runs.

Renders a fixed-height pane per container (current recipe, running
pass/fail tally, elapsed time, last few output lines) that refreshes in
place using ANSI cursor movement, instead of a wall of interleaved raw
prints from all containers.

Attribution works by intercepting ``sys.stdout.write()`` and looking up
the *currently active* :class:`~.const.InstanceConfig` via the same
``contextvars``-based mechanism the parallel runner already uses
(:func:`.helpers.get_current_instance`) — not by parsing ``[name]``
prefixes out of the text.  Since ``asyncio`` runs one task's code at a
time, whichever task is executing when a line is printed is the
correct owner, regardless of whether that line happens to also contain
its own ``[name]`` tag (which is stripped for display since it would be
redundant with the pane's own header).

Falls back to a complete no-op (no interception, no reserved screen
space) when stdout is not a TTY — e.g. piped to a file for later
``grep``, or running in CI — so existing log-capture workflows are
unaffected.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TextIO

from .helpers import get_current_instance

_RUNNING_RE = re.compile(r">>> Running (\S+) \(seq=\d+\): (.*)")
# Strip leading [N/64 M:SS] progress tag and [container-name] tag
_TAG_RE = re.compile(r"^\s*(?:\[[\d/:]+\s+\d+:\d+\]\s*)?\[[\w-]+\]\s*")
# Strip ANSI escape codes (e.g. \033[32mPASS\033[0m → PASS) so that
# PASS/FAIL detection works even when colour_status() wraps the word
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _terminal_width(default: int = 100) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


@dataclass
class _Pane:
    """Mutable render state for a single container's status pane."""

    name: str
    recipe: str = "-"
    title: str = ""
    passed: int = 0
    failed: int = 0
    start: float = field(default_factory=time.monotonic)
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=6))
    done: bool = False

    def feed(self, text: str) -> None:
        """Absorb a chunk of stdout text attributed to this pane."""
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line:
                continue
            m = _RUNNING_RE.search(line)
            if m:
                self.recipe, self.title = m.group(1), m.group(2)
            stripped = _TAG_RE.sub("", line).strip()
            if not stripped:
                continue
            # Strip ANSI colour codes for PASS/FAIL detection —
            # color_status() wraps the word in \033[32m...\033[0m when
            # stdout is a TTY, which would break startswith("PASS:").
            plain = _ANSI_RE.sub("", stripped)
            if plain.startswith("PASS:"):
                self.passed += 1
            elif plain.startswith("FAIL:"):
                self.failed += 1
            self.lines.append(stripped)


class LiveDashboard:
    """Fixed per-container status panes that refresh in place.

    Usage::

        dash = LiveDashboard([inst.name for inst in instances])
        dash.start()
        try:
            results = await asyncio.gather(*tasks)
        finally:
            await dash.stop()

    Each pane is ``LINES_PER_PANE`` terminal lines tall: one header line
    (container name, current recipe, pass/fail tally, elapsed time) and
    up to ``LINES_PER_PANE - 1`` of the most recent output lines.
    """

    LINES_PER_PANE = 7

    def __init__(self, names: list[str], *, interval: float = 0.5) -> None:
        self._panes: dict[str, _Pane] = {n: _Pane(name=n) for n in names}
        self._interval = interval
        self._real_stdout: TextIO = sys.stdout
        self._task: asyncio.Task[None] | None = None
        self._lines_drawn = 0
        # Only take over the terminal when there's an actual terminal to
        # take over — piping to a file/CI keeps the plain interleaved
        # print() behaviour so `grep`-based log analysis still works.
        self._enabled = sys.stdout.isatty()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- stdout interception ------------------------------------------------
    def write(self, text: str) -> int:
        if not text:
            return 0
        try:
            name = get_current_instance().name
        except Exception:
            name = None
        pane = self._panes.get(name) if name else None
        if pane is None:
            # Not attributable to a container pane (e.g. printed before any
            # per-container task set the contextvar) — pass through as-is.
            return self._real_stdout.write(text)
        pane.feed(text)
        return len(text)

    def flush(self) -> None:
        self._real_stdout.flush()

    def isatty(self) -> bool:
        return self._real_stdout.isatty()

    # -- rendering ------------------------------------------------------
    def _render(self) -> None:
        cols = _terminal_width()
        out: list[str] = []
        if self._lines_drawn:
            out.append(f"\x1b[{self._lines_drawn}A")
        n_lines = 0

        # Progress counter from parallel module (lazy import to avoid cycle)
        progress = ""
        try:
            from .parallel import _progress_str

            progress = _progress_str() + " "
        except Exception:
            pass

        for pane in self._panes.values():
            elapsed = time.monotonic() - pane.start
            status = "done " if pane.done else "..."
            header = (
                f"  {progress}{pane.name:<10} [{pane.recipe:<5}]"
                f" {pane.title[:34]:<34} "
                f"P:{pane.passed:>3} F:{pane.failed:>3} {elapsed:>5.0f}s {status}"
            )
            out.append(_fit(header, cols))
            n_lines += 1
            tail = list(pane.lines)
            for line in tail:
                out.append(_fit(f"    {line}", cols))
                n_lines += 1
            for _ in range(max(self.LINES_PER_PANE - 1 - len(tail), 0)):
                out.append("\x1b[K")
                n_lines += 1
        self._lines_drawn = n_lines
        self._real_stdout.write("\n".join(out) + "\n")
        self._real_stdout.flush()

    async def _refresh_loop(self) -> None:
        try:
            while True:
                self._render()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    def mark_done(self, name: str) -> None:
        pane = self._panes.get(name)
        if pane:
            pane.done = True

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if not self._enabled:
            return
        # Reserve blank screen space matching what _render() will draw.
        n = len(self._panes) * self.LINES_PER_PANE
        self._real_stdout.write("\n" * n)
        self._lines_drawn = n
        sys.stdout = self
        self._task = asyncio.get_event_loop().create_task(self._refresh_loop())

    async def stop(self) -> None:
        if not self._enabled:
            return
        sys.stdout = self._real_stdout
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._render()


def _fit(s: str, width: int) -> str:
    if len(s) > width:
        s = s[: max(width - 1, 0)]
    return s + "\x1b[K"
