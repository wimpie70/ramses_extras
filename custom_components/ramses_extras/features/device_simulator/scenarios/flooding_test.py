from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_FLOODING_TEST, VERB_I
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    slug = str(params.get("slug", "FAN")) or "FAN"
    slug = slug.upper()
    device_id = params.get("device_id") or SIM_DEVICE_ID.get(slug)
    if not device_id:
        return ScenarioResult(
            scenario_id=SCENARIO_FLOODING_TEST,
            success=False,
            errors=[f"No device_id available for slug '{slug}'"],
        )

    code = str(params.get("code", "22F7")).upper()
    payloads = _payload_cycle(context, slug, code)
    if not payloads:
        return ScenarioResult(
            scenario_id=SCENARIO_FLOODING_TEST,
            success=False,
            errors=[f"No payloads available for {slug}/{code}"],
        )

    count = max(1, int(params.get("count", 200)))
    interval = float(params.get("interval", 0.05))
    duration = float(params.get("duration", 0))

    await context.cancel_existing(SCENARIO_FLOODING_TEST)

    task = context.schedule_background_task(
        _emit_flood(
            context,
            device_id=device_id,
            code=code,
            payloads=payloads,
            count=count,
            interval=interval,
            duration=duration,
        ),
        name="device_simulator_flooding_test",
    )
    context.register_task(SCENARIO_FLOODING_TEST, task)
    context.set_running_metadata(
        SCENARIO_FLOODING_TEST,
        {
            "device_id": device_id,
            "code": code,
            "count": count,
            "interval": interval,
            "duration": duration,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_FLOODING_TEST,
        success=True,
        details={
            "message": (
                f"Flooding {device_id} with {count} {code} frames @ {interval}s"
            ),
            "device_id": device_id,
            "code": code,
            "count": count,
            "interval": interval,
        },
    )


async def _emit_flood(
    context: ScenarioContext,
    *,
    device_id: str,
    code: str,
    payloads: list[str],
    count: int,
    interval: float,
    duration: float,
) -> None:
    try:
        delay_between = max(0.0, interval)
        payload_idx = 0
        start = asyncio.get_event_loop().time()
        for sent in range(count):
            if sent and delay_between > 0:
                await asyncio.sleep(delay_between)
            payload = payloads[payload_idx % len(payloads)]
            payload_idx += 1
            packet = context.build_packet(device_id, "--:------", VERB_I, code, payload)
            await context.send_packet(packet)
            if duration > 0 and (asyncio.get_event_loop().time() - start) >= duration:
                break
    except asyncio.CancelledError:
        raise
    finally:
        context.clear_running(SCENARIO_FLOODING_TEST)


def _payload_cycle(context: ScenarioContext, slug: str, code: str) -> list[str]:
    entries = context.device_db.get_periodic(slug)
    for entry in entries:
        if entry.code == code and entry.payloads:
            return entry.payloads
    return []


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_FLOODING_TEST,
    label="Flooding Test",
    toggleable=False,
    can_run_with=[],
    description="Burst-send I frames at configurable rate to stress-test HA",
    run=run,
)
