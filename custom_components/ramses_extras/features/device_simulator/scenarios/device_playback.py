from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from ..const import SCENARIO_AUTO_ANSWER, SCENARIO_DEVICE_PLAYBACK
from ..system_config import SIM_DEVICE_ID
from .base import ScenarioContext, ScenarioDefinition, ScenarioResult

LOGGER = logging.getLogger(__name__)

_DEVICE_ID_RE = re.compile(r"^[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6}$")


async def run(context: ScenarioContext, params: dict[str, Any]) -> ScenarioResult:
    LOGGER.debug("device_playback called with params: %s", params)
    conversation = (
        params.get("conversation")
        or params.get("conversation_ref")
        or params.get("log_file")
    )
    LOGGER.debug("conversation: %s", conversation)
    log_content = params.get("log_content")

    # If log_content is provided, import it first
    if log_content:
        name = params.get("name") or "imported_log"
        save_yaml = bool(params.get("save_yaml", True))
        success = await context.device_db.import_user_log(
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
    LOGGER.debug("About to access context.device_db")
    LOGGER.debug("About to call get_conversation: %s (scheme=%s)", conversation, scheme)
    conv = context.device_db.get_conversation(conversation, scheme)
    LOGGER.debug("get_conversation returned: %s", conv)
    if not conv:
        LOGGER.error("Conversation '%s' not found", conversation)
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=[f"Conversation '{conversation}' not found"],
        )
    LOGGER.debug("Conversation found with peers: %s", conv.peers)

    raw_device_map = params.get("device_map")
    if isinstance(raw_device_map, dict) and raw_device_map:
        device_map = {slug.upper(): did for slug, did in raw_device_map.items()}
        missing: list[str] = []
    else:
        # Use conversation's device_map as fallback
        if conv.device_map:
            device_map = {slug.upper(): did for slug, did in conv.device_map.items()}
            missing = [p for p in conv.peers if p.upper() not in device_map]
        else:
            overrides = params.get("device_map_overrides")
            overrides = {k.upper(): v for k, v in (overrides or {}).items()}
            device_map, missing = _infer_device_map(context, conv.peers, overrides)

    if missing:
        LOGGER.error("Unable to map conversation peers: %s", missing)
        return ScenarioResult(
            scenario_id=SCENARIO_DEVICE_PLAYBACK,
            success=False,
            errors=[
                "Unable to map conversation peers: " + ", ".join(sorted(set(missing)))
            ],
        )
    LOGGER.debug("device_map: %s", device_map)

    # Auto-activate devices from device_map if not already active
    auto_activate = params.get("auto_activate_devices", True)
    auto_start_emitter = params.get("auto_start_emitter", False)
    if auto_activate:
        from ..scenario_engine import ActiveDevice

        engine = context.engine
        activated_ids: list[str] = []
        for peer_slug, device_id in device_map.items():
            if engine.is_device_active(device_id):
                continue
            # Infer device type from device ID prefix (e.g., 32: -> FAN, 37: -> FAN)
            device_type = context.device_db.infer_device_type_from_id(device_id)
            if not device_type:
                # Fallback to peer_slug if inference fails
                device_type = peer_slug
            device = ActiveDevice(
                device_id=device_id,
                slug=device_type,
                variant_id=None,
                origin="device_playback",
            )
            await engine.async_activate_device(
                device, start_emitter=auto_start_emitter, emit_startup_burst=False
            )
            activated_ids.append(device_id)
            LOGGER.info(
                "Auto-activated device %s as %s (emitter=%s)",
                device_id,
                device_type,
                auto_start_emitter,
            )
        if activated_ids:
            LOGGER.info(
                "Auto-activated %d devices for playback: %s",
                len(activated_ids),
                activated_ids,
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
    # skip_answers=True (or skip_verbs=[...]) silences chosen verbs so the
    # simulator's auto-answer scenario can respond to RQ frames instead of
    # playing the recorded RP. Timing of later frames is preserved.
    skip_verbs_param = params.get("skip_verbs")
    if isinstance(skip_verbs_param, (list, tuple)):
        skip_verbs: tuple[str, ...] | None = tuple(str(v) for v in skip_verbs_param)
    elif params.get("skip_answers"):
        skip_verbs = ("RP",)
    else:
        skip_verbs = None
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

    LOGGER.debug(
        "Starting playback: conversation=%s, loops=%s, speed=%s, imd=%s",
        conversation,
        loops,
        speed,
        inter_message_delay,
    )
    try:
        for _ in range(loops):
            playback = await engine.async_play_conversation(
                ref=conversation,
                device_map=device_map,
                scheme=scheme,
                speed=speed,
                pause_event=pause_event,
                inter_message_delay=inter_message_delay,
                skip_verbs=skip_verbs,
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
                f"Replayed {conversation} x{loops}"
                if loops > 1
                else f"Replayed {conversation}"
            )
            + (f" @ {speed:.2f}x" if speed is not None else " @ live speed"),
            "conversation": conversation,
            "device_map": device_map,
            "loops": loops,
            "speed": speed,
            "skip_verbs": list(skip_verbs) if skip_verbs else [],
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
        # Try slug lookup first (for conversations that use slugs like FAN, REM)
        active = context.active_devices_by_slug(slug)
        if active:
            mapping[slug] = active[0].device_id
            continue
        # Try direct device ID lookup (for conversations that use actual addresses)
        if context.engine.is_device_active(peer):
            mapping[slug] = peer
            continue
        # If the peer is already a valid device ID (XX:NNNNNN), use it directly.
        # The auto-activate logic will create an ActiveDevice for it.
        if _DEVICE_ID_RE.match(peer):
            mapping[slug] = peer
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
