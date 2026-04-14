from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DISCOVERY_TEST, VERB_I
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    slug = str(params.get("slug", "FAN")) or "FAN"
    slug = slug.upper()
    device_id = params.get("device_id") or SIM_DEVICE_ID.get(slug)
    if not device_id:
        return ScenarioResult(
            scenario_id=SCENARIO_DISCOVERY_TEST,
            success=False,
            errors=[f"No device_id available for slug '{slug}'"],
        )

    fingerprint = params.get("fingerprint")
    payload = params.get("payload")
    if not payload:
        if fingerprint:
            payload = (
                context.device_db.get_fingerprint_payload(fingerprint) or fingerprint
            )
        else:
            payload = fingerprint or "0000000000000000"

    payload = str(payload).upper()
    count = max(1, int(params.get("count", 3)))
    interval = float(params.get("interval", 1.0))
    include_burst = bool(params.get("include_startup_burst", True))

    await context.cancel_existing(SCENARIO_DISCOVERY_TEST)

    task = context.schedule_background_task(
        _emit_discovery_frames(
            context,
            device_id=device_id,
            payload=payload,
            count=count,
            interval=interval,
            include_burst=include_burst,
        ),
        name="device_simulator_discovery_test",
    )
    context.register_task(SCENARIO_DISCOVERY_TEST, task)
    context.set_running_metadata(
        SCENARIO_DISCOVERY_TEST,
        {
            "device_id": device_id,
            "count": count,
            "interval": interval,
            "payload": payload,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_DISCOVERY_TEST,
        success=True,
        details={
            "message": f"Emitting {count} discovery frames from {device_id}",
            "device_id": device_id,
            "count": count,
            "interval": interval,
        },
    )


async def _emit_discovery_frames(
    context: ScenarioContext,
    *,
    device_id: str,
    payload: str,
    count: int,
    interval: float,
    include_burst: bool,
) -> None:
    try:
        if include_burst:
            await context.send_packet(
                context.build_packet(device_id, "--:------", VERB_I, "10E0", payload)
            )
        for idx in range(count):
            if idx or include_burst:
                await asyncio.sleep(max(0.0, interval))
            packet = context.build_packet(
                device_id, "--:------", VERB_I, "10E0", payload
            )
            await context.send_packet(packet)
    except asyncio.CancelledError:
        raise
    finally:
        context.clear_running(SCENARIO_DISCOVERY_TEST)


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DISCOVERY_TEST,
    label="Discovery Test",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Emit 10E0 announcements for discovery regression testing",
    run=run,
)
