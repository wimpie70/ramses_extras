"""Recipe registry, decorator and discovery.

Recipes register themselves in :data:`REGISTRY` either:

    * implicitly, by subclassing :class:`ha_sim_test.base.Recipe` with an
      ``id`` (``__init_subclass__`` calls :meth:`RecipeRegistry.register`),
      or
    * explicitly, by decorating an async function with :func:`recipe`, which
      wraps it in a ``Recipe`` subclass and registers it.

Discovery (:func:`discover_recipes`) imports every module in
:mod:`ha_sim_test.recipes` so registration side-effects run.  It is called
by the runner before iterating over recipes.

Run order is determined by the ``seq`` class attribute (ascending).  Use
gaps of 10 between recipes to leave room for future insertions.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any, Callable, Coroutine

from .base import Recipe, RecipeContext


class RecipeRegistry:
    """Holds all known recipes keyed by their string id."""

    def __init__(self) -> None:
        self._recipes: dict[str, type[Recipe]] = {}

    def register(self, recipe_cls: type[Recipe]) -> type[Recipe]:
        """Register a Recipe subclass.

        Raises ValueError if ``recipe_cls.id`` is empty or if the id is
        already registered by a *different* class (re-importing the same
        module is idempotent).
        """
        if not recipe_cls.id:
            raise ValueError(f"Cannot register {recipe_cls.__name__}: empty id")
        existing = self._recipes.get(recipe_cls.id)
        if existing is not None and existing is not recipe_cls:
            raise ValueError(
                f"Recipe id {recipe_cls.id!r} already registered by "
                f"{existing.__name__} (conflict with {recipe_cls.__name__})"
            )
        self._recipes[recipe_cls.id] = recipe_cls
        return recipe_cls

    def get(self, recipe_id: str) -> type[Recipe] | None:
        return self._recipes.get(recipe_id)

    def all(self) -> dict[str, type[Recipe]]:
        return dict(self._recipes)

    def sorted(self) -> list[type[Recipe]]:
        """Recipes sorted by ``seq`` (ascending), then by id as tiebreaker."""
        return [
            self._recipes[k]
            for k in sorted(self._recipes, key=lambda k: (self._recipes[k].seq, k))
        ]

    def __len__(self) -> int:
        return len(self._recipes)

    def __contains__(self, recipe_id: str) -> bool:
        return recipe_id in self._recipes


#: Singleton registry used by the recipe framework.
REGISTRY = RecipeRegistry()


def recipe(
    recipe_id: str,
    title: str,
    *tags: str,
    seq: int = 0,
) -> Callable[
    [Callable[[RecipeContext], Coroutine[Any, Any, None]]],
    type[Recipe],
]:
    """Decorator: turn an async function into a registered Recipe subclass.

    Usage::

        @recipe("R06", "Zone binding via inject_message", seq=10)
        async def r06_zone_binding(ctx: RecipeContext) -> None:
            ...

    The decorated function becomes the ``run`` method of a synthetically
    created ``Recipe`` subclass, which is then registered (and so can also
    be invoked as a class-based recipe).
    """

    def decorator(
        fn: Callable[[RecipeContext], Coroutine[Any, Any, None]],
    ) -> type[Recipe]:
        cls_name = (
            "".join(part.capitalize() for part in fn.__name__.split("_") if part)
            or f"Recipe_{recipe_id}"
        )
        attrs: dict[str, Any] = {
            "id": recipe_id,
            "seq": seq,
            "title": title,
            "tags": tuple(tags),
            "run": lambda self, ctx, _fn=fn: _fn(ctx),
            "__module__": getattr(fn, "__module__", __name__),
            "__qualname__": cls_name,
            "__doc__": fn.__doc__,
        }
        # type(...) triggers Recipe.__init_subclass__, which registers it.
        return type(cls_name, (Recipe,), attrs)

    return decorator


def discover_recipes(package: str | ModuleType = "ha_sim_test.recipes") -> None:
    """Import every module in the recipes package so recipes self-register.

    Safe to call multiple times (importlib caches modules).  Silently does
    nothing if the package is not importable.
    """
    try:
        pkg = importlib.import_module(package) if isinstance(package, str) else package
    except ModuleNotFoundError:
        return
    if not hasattr(pkg, "__path__"):
        return
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"{pkg.__name__}.{mod_info.name}")
