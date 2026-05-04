from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DISCOVERY_TEST, VERB_I
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult

DEFAULT_PAYLOAD = "0000000000000000"


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    slug = str(params.get("slug", "FAN")) or "FAN"
    slug = slug.upper()

    device_id = _resolve_device_id(context, slug, params.get("device_id"))
    if not device_id:
        return ScenarioResult(
            scenario_id=SCENARIO_DISCOVERY_TEST,
            success=False,
            errors=[f"No device_id available for slug '{slug}'"],
        )

    payload = _resolve_payload(context, slug, device_id, params)
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
            "slug": slug,
            "count": count,
            "interval": interval,
            "payload": payload,
            "include_startup_burst": include_burst,
        },
    )

    return ScenarioResult(
        scenario_id=SCENARIO_DISCOVERY_TEST,
        success=True,
        details={
            "message": f"Emitting {count} discovery frames from {device_id}",
            "device_id": device_id,
            "slug": slug,
            "payload": payload,
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


def _resolve_device_id(
    context: ScenarioContext, slug: str, explicit_id: str | None
) -> str | None:
    if explicit_id:
        return str(explicit_id).upper()

    active = context.active_devices_by_slug(slug)
    if active:
        return active[0].device_id

    return SIM_DEVICE_ID.get(slug)


def _resolve_payload(
    context: ScenarioContext,
    slug: str,
    device_id: str,
    params: dict[str, Any],
) -> str:
    payload = params.get("payload")
    if payload:
        return str(payload).replace(" ", "").upper()

    fingerprint = params.get("fingerprint")
    if fingerprint:
        resolved = context.device_db.get_fingerprint_payload(str(fingerprint).upper())
        if resolved:
            return resolved.upper()
        return str(fingerprint).upper()

    active_device = context.get_active_device(device_id)
    if active_device:
        response = context.device_db.find_response(
            active_device.slug, "10E0", active_device.variant_id
        )
        if response and response.payloads:
            return response.payloads[0].upper()

    entry = context.device_db.find_response(slug, "10E0", None)
    if entry and entry.payloads:
        return entry.payloads[0].upper()

    return DEFAULT_PAYLOAD


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DISCOVERY_TEST,
    label="Discovery Test",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Emit 10E0 announcements for discovery regression testing",
    run=run,
)
