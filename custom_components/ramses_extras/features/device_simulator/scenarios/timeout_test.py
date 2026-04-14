from __future__ import annotations

from typing import Any

from ..const import SCENARIO_TIMEOUT_TEST
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    delay = float(params.get("delay", 10.0))
    context.logger.info("Timeout test with delay %fs (stub)", delay)

    return ScenarioResult(
        scenario_id=SCENARIO_TIMEOUT_TEST,
        success=True,
        details={
            "message": f"Timeout test started (delay={delay:.1f}s)",
            "delay": delay,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_TIMEOUT_TEST,
    label="Timeout Test",
    toggleable=False,
    can_run_with=[],
    description="Drop or delay responses to simulate timeouts (stub)",
    run=run,
)
