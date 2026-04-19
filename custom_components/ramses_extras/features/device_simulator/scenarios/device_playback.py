from __future__ import annotations

import asyncio
from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DEVICE_PLAYBACK
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    conversation = (
        params.get("conversation")
        or params.get("conversation_ref")
        or params.get("log_file")
    )
    log_content = params.get("log_content")

    # If log_content is provided, import it first
    if log_content:
        name = params.get("name") or "imported_log"
        save_yaml = bool(params.get("save_yaml", False))
        success = context.device_db.import_user_log(
            None, name, log_content, save_yaml=save_yaml
        )
        if not success:
            return ScenarioResult(
                scenario_id=SCENARIO_DEVICE_PLAYBACK,
                success=False,
                errors=["Failed to import log content"],
            )
        conversation = name

    if not conversation:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=[
                "Provide 'conversation' (or legacy log_file) or 'log_content' parameter"
            ],
        )

    scheme = params.get("scheme")
    conv = context.device_db.get_conversation(conversation, scheme)
    if not conv:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=[f"Conversation '{conversation}' not found"],
        )

    raw_device_map = params.get("device_map")
    if isinstance(raw_device_map, dict) and raw_device_map:
        device_map = {slug.upper(): did for slug, did in raw_device_map.items()}
        missing: list[str] = []
    else:
        overrides = params.get("device_map_overrides")
        overrides = {k.upper(): v for k, v in (overrides or {}).items()}
        device_map, missing = _infer_device_map(context, conv.peers, overrides)

    if missing:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=[
                "Unable to map conversation peers: " + ", ".join(sorted(set(missing)))
            ],
        )

    # speed=None → engine uses global autonomous_speed (Devices-tab slider)
    raw_speed = params.get("speed")
    speed: float | None = float(raw_speed) if raw_speed is not None else None
    loops = max(1, int(params.get("loops", 1)))
    raw_imd = params.get("inter_message_delay")
    inter_message_delay: float | None = (
        float(raw_imd)
        if raw_imd not in (None, "") and isinstance(raw_imd, (int, float, str))
        else None
    )
    total_messages = 0
    total_duration = 0.0
    run_errors: list[str] = []

    # Register this run so the UI can pause/resume/stop it.
    engine = context.engine
    pause_event = engine.get_pause_event(SCENARIO_DEVICE_PLAYBACK)
    pause_event.set()
    engine.set_running_metadata(
        SCENARIO_DEVICE_PLAYBACK,
        {
            "conversation": conversation,
            "loops": loops,
            "speed": speed,
            "paused": False,
        },
    )
    current_task = asyncio.current_task()
    if current_task is not None:
        engine._scenario_tasks[SCENARIO_DEVICE_PLAYBACK] = current_task

    try:
        for _ in range(loops):
            playback = await engine.async_play_conversation(
                ref=conversation,
                device_map=device_map,
                scheme=scheme,
                speed=speed,
                pause_event=pause_event,
                inter_message_delay=inter_message_delay,
            )
            if not playback.success:
                run_errors.extend(playback.errors)
                break
            total_messages += playback.messages_sent
            total_duration += playback.duration_seconds
    finally:
        engine._scenario_tasks.pop(SCENARIO_DEVICE_PLAYBACK, None)
        engine._scenario_pause_events.pop(SCENARIO_DEVICE_PLAYBACK, None)
        engine.clear_running_metadata(SCENARIO_DEVICE_PLAYBACK)

    if run_errors:
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            messages_sent=total_messages,
            duration_seconds=total_duration,
            errors=run_errors,
        )

    return ScenarioResult(
        scenario_id=SCENARIO_DEVICE_PLAYBACK,
        success=True,
        messages_sent=total_messages,
        duration_seconds=total_duration,
        details={
            "message": (
                f"Replayed {conversation} x{loops} @ {speed:.2f}x"
                if loops > 1
                else f"Replayed {conversation} @ {speed:.2f}x"
            ),
            "conversation": conversation,
            "device_map": device_map,
            "loops": loops,
            "speed": speed,
        },
    )


def _infer_device_map(
    context: ScenarioContext, peers: list[str], overrides: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    missing: list[str] = []

    for peer in peers:
        slug = peer.upper()
        if slug == "ALL":
            continue
        if slug in overrides:
            mapping[slug] = overrides[slug]
            continue
        active = context.active_devices_by_slug(slug)
        if active:
            mapping[slug] = active[0].device_id
            continue
        default_id = SIM_DEVICE_ID.get(slug)
        if default_id:
            mapping[slug] = default_id
            continue
        missing.append(slug)

    return mapping, missing


SCENARIO_DEFINITION = ScenarioDefinition(
    scenario_id=SCENARIO_DEVICE_PLAYBACK,
    label="Device Playback",
    toggleable=False,
    can_run_with=[SCENARIO_AUTO_ANSWER],
    description=(
        "Replay captured conversation blocks with inferred device mapping. "
        "Can use existing conversations or paste ramses.log content directly."
    ),
    run=run,
)
