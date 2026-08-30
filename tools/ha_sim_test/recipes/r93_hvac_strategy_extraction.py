"""Recipe R93: HVAC strategy extraction."""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R93HvacStrategyExtraction(Recipe):
    id = "R93"
    seq = 930
    title = "HVAC strategy extraction"
    tags = ("12A0", "climarad", "orcon", "strategy")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify ClimaRad quirks and Orcon aliases in the installed library."""
        ctx.log_section("Recipe 93: HVAC strategy extraction")

        result = docker_exec_python(
            """
import json
from ramses_rf.const import SZ_REL_HUMIDITY
from ramses_rf.strategies import ClimaRadStrategy, OrconStrategy
from ramses_tx.const import Code

climarad = ClimaRadStrategy()
quirked = climarad.apply_quirk(
    {
        "hvac_index": "01",
        SZ_REL_HUMIDITY: 0.45,
        "temperature": 18.5,
    },
    None,
    Code._12A0,
)
print(json.dumps({
    "climarad_scheme": climarad.scheme,
    "supply_temp": quirked.get("supply_temp"),
    "rel_humidity_removed": SZ_REL_HUMIDITY not in quirked,
    "dutch_low": OrconStrategy().fan_mode_to_hex("laag"),
}))
"""
        )
        ctx.check(
            "ClimaRad strategy is available",
            result.get("climarad_scheme") == "climarad",
            f"result={result}",
        )
        ctx.check(
            "ClimaRad Ventura 12A0 maps supply temperature",
            result.get("supply_temp") == 18.5
            and result.get("rel_humidity_removed") is True,
            f"result={result}",
        )
        ctx.check(
            "Orcon Dutch alias 'laag' maps to 01",
            result.get("dutch_low") == "01",
            f"result={result}",
        )
