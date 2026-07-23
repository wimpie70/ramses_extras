"""Base classes for ha_sim_test recipes.

Defines:
    * :class:`RecipeContext`  - Shared mutable state passed to every recipe's
      ``run()``: the current HA token, the :class:`LogMonitor` instance, and
      the check accounting (passed/failed/results).  Also provides
      ``check``, ``wait``, ``log_section`` and ``refresh_token`` convenience
      methods so recipes don't need to import those from :mod:`.helpers`.
    * :class:`Recipe`         - Base class for class-based recipes.
    * :class:`RecipeError`    - Raised by a recipe to signal a hard failure.

Recipes import HA/ramses_cc helper functions (``call_service``, ``get_schema``,
``get_entities``, etc.) directly from :mod:`.helpers` and pass ``ctx.token``
where a token is required.  Device-ID constants (``HGI``, ``CTL``, ...) are
imported from :mod:`.const`.  Profile constants (``MIXED_SCHEMA``,
``mixed_yaml``) from :mod:`.profile`.

Two registration styles are supported (see :mod:`.registry`):

    Class-based::

        class R06ZoneBinding(Recipe):
            id = "R06"
            seq = 10
            title = "Zone binding via inject_message"

            async def run(self, ctx: RecipeContext) -> None:
                ...

    Function + decorator::

        @recipe("R06", "Zone binding via inject_message", seq=10)
        async def r06_zone_binding(ctx: RecipeContext) -> None:
            ...
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .helpers import get_token
from .helpers import log_section as _log_section
from .helpers import wait_for as _wait_for


class RecipeError(Exception):
    """Raised by a recipe to signal a hard failure (not a failed check)."""


@dataclass
class RecipeContext:
    """Shared mutable state passed to every recipe's ``run()``.

    Owns the check accounting (``passed`` / ``failed`` / ``results``) so
    recipes are self-contained.  ``token`` is mutable and refreshed via
    :meth:`refresh_token` (e.g. after a ramses_cc reload).  ``log_monitor``
    is the :class:`~.log_monitor.LogMonitor` instance shared across recipes.
    """

    token: str = ""
    log_monitor: Any = None
    # Cross-recipe shared state (e.g. faked_rem_id set by R18, read by R20)
    shared: dict[str, Any] = field(default_factory=dict)
    # Check accounting
    passed: int = 0
    failed: int = 0
    results: list[str] = field(default_factory=list)
    # Per-recipe accounting: {recipe_id: {"passed": N, "failed": N, "duration": float}}
    recipe_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    # -- token -----------------------------------------------------------
    def refresh_token(self) -> str:
        """Re-acquire the HA token (call after a ramses_cc reload)."""
        self.token = get_token()
        return self.token

    # -- check / wait / log_section --------------------------------------
    def check(self, label: str, condition: bool, detail: str = "") -> None:
        """Record a check result and print it (mirrors helpers.check)."""
        if condition:
            self.passed += 1
            self.results.append(f"  PASS: {label}")
            print(f"  PASS: {label}")
        else:
            self.failed += 1
            self.results.append(f"  FAIL: {label} {detail}")
            print(f"  FAIL: {label} {detail}")

    def wait(self, seconds: int, msg: str = "") -> None:
        """Wait and print progress (mirrors helpers.wait)."""
        print(f"  Waiting {seconds}s {msg}...", end="", flush=True)
        time.sleep(seconds)
        print(" done")

    def wait_for(
        self,
        condition: Callable[[], bool],
        timeout: int = 30,
        interval: float = 1.0,
        msg: str = "",
    ) -> bool:
        """Poll a condition until it returns True or timeout is reached.

        Event-driven replacement for fixed ``ctx.wait(N, ...)`` calls.
        Checks ``condition`` every ``interval`` seconds.  Returns True
        if the condition was met within ``timeout`` seconds, False
        otherwise.  Prints progress like :meth:`wait`.

        Example::

            if ctx.wait_for(
                lambda: "04:200001" in get_schema(),
                timeout=15,
                msg="for 04:200001 to appear in schema",
            ):
                ...
        """
        return _wait_for(condition, timeout, interval, msg)

    def log_section(self, title: str) -> None:
        """Emit a labelled section banner in the test output."""
        _log_section(title)


class Recipe:
    """Base class for class-based recipes.

    Subclasses set the class attributes ``id``, ``seq``, and ``title``
    (and optionally ``tags``) and implement :meth:`run`.  Subclasses are
    auto-registered via ``__init_subclass__`` (see :mod:`.registry`).

    ``seq`` determines the run order (ascending).  Use gaps of 10 to leave
    room for future insertions.
    """

    id: str = ""
    seq: int = 0
    title: str = ""
    tags: tuple[str, ...] = ()

    async def run(self, ctx: RecipeContext) -> None:
        raise NotImplementedError(
            f"Recipe {self.id!r} ({type(self).__name__}) did not implement run()"
        )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Auto-register concrete subclasses that declare an id.  The base
        # class itself (id == "") and intermediate abstract classes are
        # skipped.  Registry import is local to avoid a circular dependency.
        if cls.id:
            from .registry import REGISTRY

            REGISTRY.register(cls)

    def __repr__(self) -> str:
        return f"<Recipe {self.id} seq={self.seq} {self.title!r}>"
