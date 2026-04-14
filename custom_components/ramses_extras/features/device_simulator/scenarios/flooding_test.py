from __future__ import annotations

from typing import Any

from ..const import SCENARIO_FLOODING_TEST
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    count = int(params.get("count", 100))
    interval = float(params.get("interval", 0.1))
    context.logger.info(
        "Flooding test: %d messages at %.3fs intervals (stub)", count, interval
    )

    return ScenarioResult(
        scenario_id=SCENARIO_FLOODING_TEST,
        success=True,
        details={
            "message": f"Flooding test started ({count} msgs @ {interval}s)",
            "count": count,
            "interval": interval,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_FLOODING_TEST,
    label="Flooding Test",
    toggleable=False,
    can_run_with=[],
    description="Emit I-frames at high frequency (stub)",
    run=run,
)
