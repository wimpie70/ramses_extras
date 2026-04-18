from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DEVICE_SUITE
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    device_specs, errors = _normalize_device_specs(params)
    if errors:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_SUITE,
            success=False,
            errors=errors,
        )

    if not device_specs:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_SUITE,
            success=False,
            errors=["No device definitions provided"],
        )

    await context.cancel_existing(SCENARIO_DEVICE_SUITE)

    started_devices: list[str] = []
    for spec in device_specs:
        device_id = spec["device_id"]
        existing = context.get_active_device(device_id)
        if existing:
            existing.slug = spec["slug"]
            existing.variant_id = spec["variant_id"]
            existing.excluded_codes = list(spec["excluded_codes"])
            existing.suppress_autonomous = spec["suppress_autonomous"]
            existing.suppress_responses = spec["suppress_responses"]
            existing.enabled = spec["enabled"]
            await context.engine.async_activate_device(existing)
            continue

        device = context.new_active_device(
            device_id=device_id,
            slug=spec["slug"],
            variant_id=spec["variant_id"],
            excluded_codes=list(spec["excluded_codes"]),
            suppress_autonomous=spec["suppress_autonomous"],
            suppress_responses=spec["suppress_responses"],
            enabled=spec["enabled"],
        )
        await context.engine.async_activate_device(device)
        started_devices.append(device_id)

    duration = float(params.get("duration", 300))
    auto_stop = bool(params.get("auto_stop", True))

    if duration > 0 or auto_stop:
        task = context.schedule_background_task(
            _suite_lifecycle(context, started_devices, duration, auto_stop),
            name="device_simulator_suite",
        )
        context.register_task(SCENARIO_DEVICE_SUITE, task)
        context.set_running_metadata(
            SCENARIO_DEVICE_SUITE,
            {
                "devices": [spec["device_id"] for spec in device_specs],
                "managed_devices": started_devices,
                "duration": duration,
                "auto_stop": auto_stop,
            },
        )

    return ScenarioResult(
        scenario_id=SCENARIO_DEVICE_SUITE,
        success=True,
        details={
            "message": f"Activated {len(device_specs)} devices",
            "devices": device_specs,
            "auto_stop": auto_stop,
            "duration": duration,
        },
    )


async def _suite_lifecycle(
    context: ScenarioContext,
    managed_devices: list[str],
    duration: float,
    auto_stop: bool,
) -> None:
    try:
        if duration > 0:
            await asyncio.sleep(duration)
    except asyncio.CancelledError:
        raise
    finally:
        if auto_stop and managed_devices:
            for device_id in managed_devices:
                await context.silence_device(device_id)
        context.clear_running(SCENARIO_DEVICE_SUITE)


def _normalize_device_specs(
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    devices_param = params.get("devices")
    if not devices_param:
        slugs = params.get("slugs", ["FAN", "CO2", "REM"])
        devices_param = [{"slug": slug} for slug in slugs]

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []

    for raw in devices_param:
        slug = str(raw.get("slug", "")).upper()
        if not slug:
            errors.append("Device definition missing 'slug'")
            continue
        device_id = raw.get("device_id") or SIM_DEVICE_ID.get(slug)
        if not device_id:
            errors.append(f"No device_id available for slug '{slug}'")
            continue
        normalized.append(
            {
                "slug": slug,
                "device_id": device_id,
                "variant_id": raw.get("variant_id", "default"),
                "excluded_codes": list(raw.get("excluded_codes", [])),
                "suppress_autonomous": bool(raw.get("suppress_autonomous", False)),
                "suppress_responses": bool(raw.get("suppress_responses", False)),
                "enabled": bool(raw.get("enabled", True)),
            }
        )

    return normalized, errors


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DEVICE_SUITE,
    label="Device Suite",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description="Activate a curated set of simulated devices for mixed testing",
    run=run,
)
