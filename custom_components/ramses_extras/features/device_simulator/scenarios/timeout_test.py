from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_TIMEOUT_TEST
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    device_id = params.get("device_id")
    if not device_id:
        return ScenarioResult(
            scenario_id=SCENARIO_TIMEOUT_TEST,
            success=False,
            errors=["Provide 'device_id'"],
        )

    device = context.get_active_device(device_id)
    if not device:
        return ScenarioResult(
            scenario_id=SCENARIO_TIMEOUT_TEST,
            success=False,
            errors=[f"Device '{device_id}' is not active"],
        )

    drop_codes = [code.upper() for code in params.get("drop_codes", [])]
    if not drop_codes:
        drop_codes = ["31DA"]

    delay = float(params.get("delay", 10.0))
    hold_for = float(params.get("duration", 30.0))
    suppress_all = bool(params.get("suppress_all_responses", False))

    await context.cancel_existing(SCENARIO_TIMEOUT_TEST)

    original_codes = list(device.excluded_codes)
    original_suppress_flag = device.suppress_responses

    task = context.schedule_background_task(
        _timeout_sequence(
            context,
            device_id=device_id,
            drop_codes=drop_codes,
            delay=delay,
            hold_for=hold_for,
            suppress_all=suppress_all,
            original_codes=original_codes,
            original_suppress_flag=original_suppress_flag,
        ),
        name="device_simulator_timeout_test",
    )
    context.register_task(SCENARIO_TIMEOUT_TEST, task)
    context.set_running_metadata(
        SCENARIO_TIMEOUT_TEST,
        {
            "device_id": device_id,
            "drop_codes": drop_codes,
            "delay": delay,
            "duration": hold_for,
            "suppress_all": suppress_all,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_TIMEOUT_TEST,
        success=True,
        details={
            "message": (f"Will drop {drop_codes} on {device_id} after {delay:.0f}s"),
            "device_id": device_id,
            "drop_codes": drop_codes,
            "delay": delay,
            "duration": hold_for,
        },
    )


async def _timeout_sequence(
    context: ScenarioContext,
    *,
    device_id: str,
    drop_codes: list[str],
    delay: float,
    hold_for: float,
    suppress_all: bool,
    original_codes: list[str],
    original_suppress_flag: bool,
) -> None:
    try:
        if delay > 0:
            await asyncio.sleep(delay)

        device = context.get_active_device(device_id)
        if not device:
            return

        if suppress_all:
            device.suppress_responses = True
        else:
            for code in drop_codes:
                if code not in device.excluded_codes:
                    device.excluded_codes.append(code)

        if hold_for > 0:
            await asyncio.sleep(hold_for)
    except asyncio.CancelledError:
        raise
    finally:
        device = context.get_active_device(device_id)
        if device:
            device.excluded_codes = original_codes
            device.suppress_responses = original_suppress_flag
        context.clear_running(SCENARIO_TIMEOUT_TEST)


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_TIMEOUT_TEST,
    label="Timeout Test",
    toggleable=False,
    can_run_with=[],
    description="Delay or drop responses from an active device to reproduce timeouts",
    run=run,
)
