from __future__ import annotations

import asyncio
from typing import Any

from ..const import (
    SCENARIO_AUTO_ANSWER,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PROFILE_EMISSIONS,
)
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def _run_sequence(
    context: ScenarioContext,
    device_id: str,
    loss_after: float,
    restore_after: float | None,
) -> None:
    try:
        context.logger.info(
            "hvac_device_loss: silencing %s in %.0fs", device_id, loss_after
        )
        await asyncio.sleep(loss_after)
        await context.silence_device(device_id)
        context.logger.info("hvac_device_loss: %s is now silent", device_id)

        if restore_after is not None:
            await asyncio.sleep(restore_after)
            await context.resume_device(device_id)
            context.logger.info("hvac_device_loss: %s restored", device_id)
    except asyncio.CancelledError:
        context.logger.info("hvac_device_loss: cancelled")
        raise
    finally:
        context.clear_running(SCENARIO_HVAC_DEVICE_LOSS)


def _format_message(
    device_id: str, loss_after: float, restore_after: float | None
) -> str:
    base = f"Silencing {device_id} in {loss_after:.0f}s"
    if restore_after is not None:
        base += f", restoring after {restore_after:.0f}s"
    return base


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    device_id = params.get("device_id")
    if not device_id:
        return ScenarioResult(
            scenario_id=SCENARIO_HVAC_DEVICE_LOSS,
            success=False,
            errors=["Missing device_id param"],
        )

    if not context.get_active_device(device_id):
        return ScenarioResult(
            scenario_id=SCENARIO_HVAC_DEVICE_LOSS,
            success=False,
            errors=[f"Device '{device_id}' is not active"],
        )

    loss_after = float(params.get("loss_after", 30.0))
    restore_after_param = params.get("restore_after")
    restore_after = (
        float(restore_after_param) if restore_after_param is not None else None
    )

    await context.cancel_existing(SCENARIO_HVAC_DEVICE_LOSS)

    task = context.schedule_background_task(
        _run_sequence(context, device_id, loss_after, restore_after),
        name="device_simulator_hvac_device_loss",
    )
    context.register_task(SCENARIO_HVAC_DEVICE_LOSS, task)
    context.set_running_metadata(
        SCENARIO_HVAC_DEVICE_LOSS,
        {
            "device_id": device_id,
            "loss_after": loss_after,
            "restore_after": restore_after,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_HVAC_DEVICE_LOSS,
        success=True,
        details={
            "message": _format_message(device_id, loss_after, restore_after),
            "device_id": device_id,
        },
    )


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_HVAC_DEVICE_LOSS,
    label="HVAC Device Loss",
    toggleable=True,
    can_run_with=[
        SCENARIO_MANUAL_DEVICE_INJECTION,
        SCENARIO_PROFILE_EMISSIONS,
        SCENARIO_AUTO_ANSWER,
    ],
    description="Silence a single HVAC device mid-run, optionally restore later",
    run=run,
)
