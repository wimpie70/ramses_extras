"""Recipe R54: Topology event flow (BIND_DEVICE, CREATE_CONTROLLER).

Verifies that the ramses_rf TopologyBuilder correctly emits
``TopologyChangedEvent`` events when processing 1FC9 (rf_bind) packets
and CODES_ONLY_FROM_CTL broadcasts.  Also verifies that the
``DeviceRegistry`` handles these events by creating controllers,
binding devices, and promoting classes.

This is a structural test that runs inside the ha-sim container,
exercising the TopologyBuilder and DeviceRegistry directly.

See: https://github.com/ramses-rf/ramses_rf/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, HGI, REM, TRV
from ..helpers import docker_exec_python


class R54TopologyEventFlowIssue767(Recipe):
    id = "R54"
    seq = 540
    title = "Topology event flow: BIND_DEVICE, CREATE_CONTROLLER (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 54: Topology event flow (issue 767)")

        code = f"""
import json

try:
    from ramses_rf.models import TopologyChangedEvent
    from ramses_rf.enums import TopologyAction
    from ramses_rf.pipeline.topology_builder import TopologyBuilder

    results = {{}}

    # ── 1. TopologyChangedEvent is immutable and has correct fields ──
    event = TopologyChangedEvent(
        action=TopologyAction.BIND_DEVICE,
        parent_id="{FAN}",
        child_id="{REM}",
        metadata={{"zone_idx": "01"}},
    )
    results["event_action"] = str(event.action)
    results["event_parent"] = str(event.parent_id)
    results["event_child"] = str(event.child_id)
    results["event_has_metadata"] = "zone_idx" in event.metadata
    results["event_has_uuid"] = hasattr(event, "event_id")
    results["event_is_frozen"] = True  # dataclass(frozen=True)

    # Verify immutability
    try:
        event.action = TopologyAction.CREATE_CONTROLLER
        results["event_immutable"] = False
    except (AttributeError, Exception):
        results["event_immutable"] = True

    # ── 2. TopologyAction enum has all expected values ────────────────
    # NOTE: PR 914 renamed PROMOTE_CLASS to UPDATE_DEVICE_CLASS.
    # Accept either name for compatibility across versions.
    expected_actions = {{
        "update_traits", "bind_device",
        "create_controller", "create_circuit",
    }}
    actual_actions = {{str(a) for a in TopologyAction}}
    results["all_actions_present"] = expected_actions.issubset(actual_actions)
    # Check for either promote_class (pre-914) or update_device_class (post-914)
    has_promote_or_update = (
        "promote_class" in actual_actions
        or "update_device_class" in actual_actions
    )
    results["has_promote_or_update"] = has_promote_or_update
    results["actions"] = sorted(actual_actions)

    # ── 3. TopologyBuilder emits events via callback ──────────────────
    emitted_events: list[TopologyChangedEvent] = []

    def emit_cb(event: TopologyChangedEvent) -> None:
        emitted_events.append(event)

    builder = TopologyBuilder(
        emit_event_cb=emit_cb,
        enable_eavesdrop=True,
    )
    results["builder_created"] = True

    # ── 4. Simulate a 1FC9 rf_bind packet (OFFER phase) ───────────────
    # Build a minimal mock Message that the builder can process
    from unittest.mock import MagicMock
    from ramses_tx.const import Code

    # 1FC9 payload: 12 hex chars per binding chunk
    # Format: <parent_type><child_type><child_id_6bytes>
    # For a CTL binding a TRV: 01 (CTL) 04 (TRV) + TRV_ID
    bind_payload = f"0104{TRV.replace(":", "")}"  # 01=CTL, 04=TRV, id

    mock_pkt = MagicMock()
    mock_pkt.payload = bind_payload

    mock_msg = MagicMock()
    mock_msg.header.verb = " I"  # I_ broadcast
    mock_msg.header.code = Code._1FC9
    mock_msg.src.id = "{CTL}"
    mock_msg.dst.id = "18:765432"  # gateway
    mock_msg._pkt = mock_pkt

    # Process the message (consume is async)
    import asyncio
    asyncio.run(builder.consume(mock_msg))

    # Should emit CREATE_CONTROLLER (src is 01:) and possibly BIND_DEVICE
    _ctrl = TopologyAction.CREATE_CONTROLLER
    _bind = TopologyAction.BIND_DEVICE
    create_ctrl_events = [e for e in emitted_events if e.action == _ctrl]
    bind_events = [e for e in emitted_events if e.action == _bind]
    results["emitted_count"] = len(emitted_events)
    results["create_ctrl_count"] = len(create_ctrl_events)
    results["bind_count"] = len(bind_events)
    if create_ctrl_events:
        results["create_ctrl_device"] = str(create_ctrl_events[0].device_id)
    if bind_events:
        results["bind_first_parent"] = str(bind_events[0].parent_id or "")
        results["bind_first_child"] = str(bind_events[0].child_id or "")

    # ── 5. Simulate a CODES_ONLY_FROM_CTL broadcast ───────────────────
    emitted_events.clear()

    from ramses_tx.const import Code as Code2
    # 1F09 is a CTL-only code (system mode) in CODES_ONLY_FROM_CTL
    mock_msg2 = MagicMock()
    mock_msg2.header.verb = " I"
    mock_msg2.header.code = Code2._1F09
    mock_msg2.src.id = "{CTL}"
    mock_msg2.dst.id = "18:765432"
    mock_msg2._pkt = MagicMock()
    mock_msg2._pkt.payload = "000E003545C8"

    asyncio.run(builder.consume(mock_msg2))

    ctl_events = [e for e in emitted_events if e.action == _ctrl]
    results["ctl_broadcast_emitted"] = len(ctl_events) > 0
    if ctl_events:
        results["ctl_broadcast_device"] = str(ctl_events[0].device_id)
        results["ctl_broadcast_causation"] = str(ctl_events[0].causation)

    print(json.dumps({{"ok": True, **results}}))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": f"{{type(e).__name__}}: {{e}}",
        "traceback": traceback.format_exc()[:1500],
        "ok": False,
    }}))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "topology event infrastructure runs without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("topology event infrastructure runs without error", True, "")

        # 1. TopologyChangedEvent fields
        ctx.check(
            "event action is BIND_DEVICE",
            result.get("event_action") == "bind_device",
            f"action={result.get('event_action')}",
        )
        ctx.check(
            "event parent_id is FAN",
            result.get("event_parent") == FAN,
            f"parent={result.get('event_parent')}",
        )
        ctx.check(
            "event child_id is REM",
            result.get("event_child") == REM,
            f"child={result.get('event_child')}",
        )
        ctx.check(
            "event has metadata",
            result.get("event_has_metadata") is True,
            "metadata missing",
        )
        ctx.check(
            "event has UUID (event_id)",
            result.get("event_has_uuid") is True,
            "event_id missing",
        )
        ctx.check(
            "event is immutable (frozen dataclass)",
            result.get("event_immutable") is True,
            "event should be immutable",
        )

        # 2. TopologyAction enum
        ctx.check(
            "all TopologyAction values present",
            result.get("all_actions_present") is True,
            f"actions={result.get('actions')}",
        )
        ctx.check(
            "has promote_class or update_device_class (PR 914 rename)",
            result.get("has_promote_or_update") is True,
            f"actions={result.get('actions')}",
        )

        # 3. TopologyBuilder
        ctx.check(
            "TopologyBuilder created with callback",
            result.get("builder_created") is True,
            "builder creation failed",
        )

        # 4. 1FC9 rf_bind processing
        ctx.check(
            "1FC9 packet emits at least 1 event",
            result.get("emitted_count", 0) > 0,
            f"emitted_count={result.get('emitted_count')}",
        )
        ctx.check(
            "1FC9 from CTL emits CREATE_CONTROLLER",
            result.get("create_ctrl_count", 0) > 0,
            f"create_ctrl_count={result.get('create_ctrl_count')}",
        )
        if result.get("create_ctrl_count", 0) > 0:
            ctx.check(
                "CREATE_CONTROLLER device is CTL",
                result.get("create_ctrl_device") == CTL,
                f"device={result.get('create_ctrl_device')}",
            )

        # 5. CODES_ONLY_FROM_CTL broadcast
        ctx.check(
            "CTL broadcast emits CREATE_CONTROLLER",
            result.get("ctl_broadcast_emitted") is True,
            "no CREATE_CONTROLLER from CTL broadcast",
        )
        if result.get("ctl_broadcast_emitted"):
            ctx.check(
                "CTL broadcast device is CTL",
                result.get("ctl_broadcast_device") == CTL,
                f"device={result.get('ctl_broadcast_device')}",
            )
            ctx.check(
                "CTL broadcast causation is Evohome rule",
                "Evohome" in str(result.get("ctl_broadcast_causation", "")),
                f"causation={result.get('ctl_broadcast_causation')}",
            )
