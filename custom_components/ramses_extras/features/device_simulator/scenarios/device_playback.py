from __future__ import annotations

from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DEVICE_PLAYBACK
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    log_file = params.get("log_file")
    if not log_file:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=["Missing log_file param"],
        )

    speed = float(params.get("speed", 1.0))
    context.logger.info("Device playback from %s (stub, speed=%.2f)", log_file, speed)

    return ScenarioResult(
        scenario_id=SCENARIO_DEVICE_PLAYBACK,
        success=True,
        details={
            "message": f"Playback started for {log_file} (speed={speed:.2f}x)",
            "log_file": log_file,
            "speed": speed,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DEVICE_PLAYBACK,
    label="Device Playback",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Replay packets from a captured device log (stub implementation)",
    run=run,
)
