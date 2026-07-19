"""ha_sim_test recipe framework — automated test runner for ha-sim.

This package is the home of the recipes previously inlined as a ~3200-line
``async def main()`` in a single script.  Each recipe now lives in its own
module under :mod:`ha_sim_test.recipes` and is run by :mod:`ha_sim_test.runner`.

Usage::

    python3 -m ha_sim_test              # run all recipes in seq order
    python3 -m ha_sim_test R06 R29      # run specific recipes by id

Public API:
    Recipe, RecipeContext, RecipeError,
    RecipeRegistry, REGISTRY, recipe, discover_recipes
"""

from __future__ import annotations

from .base import Recipe, RecipeContext, RecipeError
from .registry import (
    REGISTRY,
    RecipeRegistry,
    discover_recipes,
    recipe,
)

__all__ = [
    "REGISTRY",
    "Recipe",
    "RecipeContext",
    "RecipeError",
    "RecipeRegistry",
    "discover_recipes",
    "recipe",
]
