from __future__ import annotations

from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DEVICE_SUITE
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    slugs = params.get("slugs", ["FAN", "REM", "CO2"])
    duration = int(params.get("duration", 300))

    if not isinstance(slugs, list) or not slugs:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_SUITE,
            success=False,
            errors=["Provide at least one device slug"],
        )

    context.logger.info(
        "Device suite scenario: %s for %ds (stub)", ", ".join(slugs), duration
    )

    return ScenarioResult(
        scenario_id=SCENARIO_DEVICE_SUITE,
        success=True,
        details={
            "message": f"Suite started for {len(slugs)} devices (duration={duration}s)",
            "slugs": slugs,
            "duration": duration,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DEVICE_SUITE,
    label="Device Suite",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Activate multiple device types simultaneously (stub)",
    run=run,
)
