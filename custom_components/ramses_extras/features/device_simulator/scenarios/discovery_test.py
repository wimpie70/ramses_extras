from __future__ import annotations

from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DISCOVERY_TEST
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    context.logger.info("Discovery test scenario (stub)")

    return ScenarioResult(
        scenario_id=SCENARIO_DISCOVERY_TEST,
        success=True,
        details={"message": "Discovery test started"},
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DISCOVERY_TEST,
    label="Discovery Test",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Simulate 10E0 discovery exchanges (stub)",
    run=run,
)
