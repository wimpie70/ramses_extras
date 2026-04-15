from __future__ import annotations

import asyncio
from typing import Any

from ..const import (
    SCENARIO_AUTO_ANSWER,
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PROFILE_EMISSIONS,
)
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def _run_sequence(
    context: ScenarioContext,
    targets: list[str],
    silence_after: float,
    resume_after: float,
) -> None:
    try:
        context.logger.info(
            "device_unavailability: silencing %s in %.0fs", targets, silence_after
        )
        await asyncio.sleep(silence_after)
        for device_id in targets:
            await context.silence_device(device_id)
            context.logger.info("device_unavailability: silenced %s", device_id)

        context.logger.info(
            "device_unavailability: resuming %s in %.0fs", targets, resume_after
        )
        await asyncio.sleep(resume_after)
        for device_id in targets:
            await context.resume_device(device_id)
            context.logger.info("device_unavailability: resumed %s", device_id)
    except asyncio.CancelledError:
        context.logger.info("device_unavailability: cancelled")
        raise
    finally:
        context.clear_running(SCENARIO_DEVICE_UNAVAILABILITY)


def _format_message(
    targets: list[str], silence_after: float, resume_after: float
) -> str:
    return (
        f"Silencing {targets} in {silence_after:.0f}s,"
        f" resuming after {resume_after:.0f}s"
    )


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    device_id = params.get("device_id")
    silence_after = float(params.get("silence_after", 30.0))
    resume_after = float(params.get("resume_after", 60.0))

    targets = [device_id] if device_id else context.active_device_ids()
    if not targets:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_UNAVAILABILITY,
            success=False,
            errors=["No active devices to test"],
        )

    await context.cancel_existing(SCENARIO_DEVICE_UNAVAILABILITY)

    task = context.schedule_background_task(
        _run_sequence(context, targets, silence_after, resume_after),
        name="device_simulator_unavailability",
    )
    context.register_task(SCENARIO_DEVICE_UNAVAILABILITY, task)
    context.set_running_metadata(
        SCENARIO_DEVICE_UNAVAILABILITY,
        {
            "targets": targets,
            "silence_after": silence_after,
            "resume_after": resume_after,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_DEVICE_UNAVAILABILITY,
        success=True,
        details={
            "message": _format_message(targets, silence_after, resume_after),
            "targets": targets,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DEVICE_UNAVAILABILITY,
    label="Device Unavailability",
    toggleable=True,
    can_run_with=[
        SCENARIO_MANUAL_DEVICE_INJECTION,
        SCENARIO_PROFILE_EMISSIONS,
        SCENARIO_AUTO_ANSWER,
    ],
    description="Silence devices after a delay, then resume to simulate timeouts",
    run=run,
)
