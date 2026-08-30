"""Recipe R94: HVAC strategy selection."""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R94HvacStrategySelection(Recipe):
    id = "R94"
    seq = 940
    title = "HVAC strategy selection"
    tags = ("climarad", "itho", "nuaire", "orcon", "strategy", "vasco")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify explicit, default, and fallback strategy selection."""
        ctx.log_section("Recipe 94: HVAC strategy selection")

        result = docker_exec_python(
            """
import json
from ramses_rf.strategies import best_hvac_strategy

schemes = ("climarad", "itho", "nuaire", "orcon", "vasco")
selected = {
    scheme: best_hvac_strategy("32:150000", scheme=scheme).scheme
    for scheme in schemes
}
print(json.dumps({
    "selected": selected,
    "default": best_hvac_strategy("32:150000").scheme,
    "unknown": best_hvac_strategy("32:150000", scheme="unknown").scheme,
}))
"""
        )
        expected = {
            "climarad": "climarad",
            "itho": "itho",
            "nuaire": "nuaire",
            "orcon": "orcon",
            "vasco": "vasco",
        }
        ctx.check(
            "Explicit HVAC schemes select matching strategies",
            result.get("selected") == expected,
            f"result={result}",
        )
        ctx.check(
            "Default and unknown schemes fall back to Orcon",
            result.get("default") == "orcon" and result.get("unknown") == "orcon",
            f"result={result}",
        )
