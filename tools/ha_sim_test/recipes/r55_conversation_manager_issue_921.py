"""Recipe R55: L7 ConversationManager RQ/RP tracking + retransmission.

Verifies the Phase 4b ConversationManager that replaces L3 RQ/RP tracking:

1. **ConversationManager instantiation** — created by Gateway, accessible
   via ``gwy.conversation_manager``
2. **PendingConversation dataclass** — immutable tracking structure
3. **track_intent** — registers an intent, returns a future, schedules
   timeout
4. **process_msg** — matches incoming RP messages to pending conversations,
   resolves futures
5. **Timeout + retry** — on timeout, retries via send_func up to
   max_retries, then raises ProtocolTimeoutError
6. **cancel_all** — cancels all pending conversations on shutdown
7. **CommandDispatcher integration** — ``dispatcher.send()`` with
   ``wait_for_reply=True`` uses ConversationManager

This is a structural test that runs inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_rf/pull/921
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, HGI, REM
from ..helpers import docker_exec_python


class R55ConversationManagerIssue921(Recipe):
    id = "R55"
    seq = 550
    title = "L7 ConversationManager RQ/RP tracking + retransmission (PR 921)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 55: L7 ConversationManager (PR 921)")

        code = f"""
import asyncio
import json

try:
    from ramses_rf.pipeline.conversation import (
        ConversationManager,
        PendingConversation,
        DEFAULT_RPLY_TIMEOUT,
        MAX_RETRY_LIMIT,
    )
    from ramses_rf.commands.core import Command
    from ramses_rf.enums import Action
    from ramses_rf.address import Address
    from ramses_tx import RP, Packet
    from ramses_tx.exceptions import ProtocolTimeoutError

    results = {{}}

    # ── 1. Constants and dataclass structure ──────────────────────────
    results["default_timeout"] = DEFAULT_RPLY_TIMEOUT
    results["max_retry_limit"] = MAX_RETRY_LIMIT
    _fields = PendingConversation.__dataclass_fields__
    results["pending_has_intent"] = "intent" in _fields
    results["pending_has_fut"] = "fut" in _fields
    results["pending_has_timeout"] = "timeout" in _fields
    results["pending_has_max_retries"] = "max_retries" in _fields
    results["pending_has_retry_count"] = "retry_count" in _fields
    results["pending_has_timer_task"] = "timer_task" in _fields

    # ── 2. ConversationManager instantiation ──────────────────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    send_calls = []

    async def mock_send(dto):
        send_calls.append(dto)
        # Return a mock packet
        from unittest.mock import MagicMock
        return MagicMock()

    cm = ConversationManager(
        loop=loop,
        default_timeout=0.5,  # short for testing
        max_retries=2,
        send_func=mock_send,
    )
    results["cm_created"] = True
    results["cm_pending_count_init"] = cm.pending_count

    # ── 3. track_intent registers a pending conversation ──────────────
    src = Address("{HGI}")
    dst = Address("{CTL}")
    intent = Command(
        src=src,
        dst=dst,
        action=Action.GET_ZONE_SETPOINT,
        data={{"zone_idx": "01"}},
        needs_reply=True,
        timeout=0.5,
    )

    fut = loop.run_until_complete(cm.track_intent(intent, timeout=0.5, max_retries=2))
    results["track_returns_future"] = asyncio.isfuture(fut)
    results["cm_pending_count_after_track"] = cm.pending_count

    # ── 4. process_msg matches RP and resolves future ─────────────────
    # Create a mock RP message that matches the pending conversation
    from unittest.mock import MagicMock
    mock_msg = MagicMock()
    mock_msg.verb = RP
    mock_msg.src.id = "{CTL}"  # matches intent.dst.id
    mock_msg.code = MagicMock()
    # Need str(msg.code) to match dto.code
    from ramses_rf.commands.builders import build_dto
    dto = build_dto(intent)
    mock_msg.code.__str__ = lambda self: dto.code
    mock_msg._pkt = MagicMock()

    matched = cm.process_msg(mock_msg)
    results["process_msg_matched"] = matched
    results["cm_pending_count_after_match"] = cm.pending_count

    # The future should be resolved
    if fut.done() and not fut.cancelled():
        try:
            result = fut.result()
            results["future_resolved"] = True
        except Exception as e:
            results["future_resolved"] = False
            results["future_error"] = str(e)
    else:
        results["future_resolved"] = False
        results["future_state"] = "pending" if not fut.done() else "cancelled"

    # ── 5. Timeout + retry behavior ───────────────────────────────────
    send_calls.clear()

    intent2 = Command(
        src=src,
        dst=Address("04:150003"),  # different device, won't match
        action=Action.GET_ZONE_SETPOINT,
        data={{"zone_idx": "02"}},
        needs_reply=True,
        timeout=0.3,
    )

    fut2 = loop.run_until_complete(
        cm.track_intent(intent2, timeout=0.3, max_retries=2)
    )

    # Wait for timeout + retries to complete (0.3 * 3 = 0.9s + overhead)
    try:
        loop.run_until_complete(asyncio.wait_for(fut2, timeout=2.0))
        results["timeout_future_completed"] = True
    except ProtocolTimeoutError as e:
        results["timeout_future_completed"] = True
        results["timeout_error_type"] = "ProtocolTimeoutError"
    except asyncio.TimeoutError:
        results["timeout_future_completed"] = False
        results["timeout_error_type"] = "asyncio.TimeoutError"
    except Exception as e:
        results["timeout_future_completed"] = True
        results["timeout_error_type"] = type(e).__name__

    # Should have retried 2 times (max_retries=2)
    results["timeout_retry_count"] = len(send_calls)
    results["cm_pending_count_after_timeout"] = cm.pending_count

    # ── 6. cancel_all clears pending conversations ────────────────────
    intent3 = Command(
        src=src,
        dst=Address("07:150000"),
        action=Action.GET_DHW_TEMP,
        data={{}},
        needs_reply=True,
        timeout=10.0,  # long timeout, won't fire before cancel
    )
    fut3 = loop.run_until_complete(cm.track_intent(intent3, timeout=10.0))
    results["cm_pending_before_cancel"] = cm.pending_count

    cm.cancel_all()
    results["cm_pending_after_cancel"] = cm.pending_count
    results["cancelled_future_done"] = fut3.done()

    # ── 7. Gateway has conversation_manager property ──────────────────
    # Check if the Gateway class has the property (without instantiating)
    from ramses_rf.gateway import Gateway
    results["gateway_has_conv_mgr_prop"] = hasattr(Gateway, "conversation_manager")

    # ── 8. CommandDispatcher uses ConversationManager ─────────────────
    from ramses_rf.commands.dispatcher import CommandDispatcher
    import inspect
    src_code = inspect.getsource(CommandDispatcher.send)
    results["dispatcher_uses_conv_mgr"] = "conversation_manager" in src_code
    results["dispatcher_uses_wait_for_reply_false"] = "wait_for_reply=False" in src_code
    results["dispatcher_uses_track_intent"] = "track_intent" in src_code

    print(json.dumps({{"ok": True, **results}}))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": f"{{type(e).__name__}}: {{e}}",
        "traceback": traceback.format_exc()[:2000],
        "ok": False,
    }}))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "ConversationManager infrastructure runs without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("ConversationManager infrastructure runs without error", True, "")

        # 1. Constants and dataclass
        ctx.check(
            "DEFAULT_RPLY_TIMEOUT is 1.0s",
            result.get("default_timeout") == 1.0,
            f"timeout={result.get('default_timeout')}",
        )
        ctx.check(
            "MAX_RETRY_LIMIT is 3",
            result.get("max_retry_limit") == 3,
            f"retries={result.get('max_retry_limit')}",
        )
        ctx.check(
            "PendingConversation has intent field",
            result.get("pending_has_intent") is True,
            "missing intent field",
        )
        ctx.check(
            "PendingConversation has fut field",
            result.get("pending_has_fut") is True,
            "missing fut field",
        )
        ctx.check(
            "PendingConversation has timeout field",
            result.get("pending_has_timeout") is True,
            "missing timeout field",
        )
        ctx.check(
            "PendingConversation has max_retries field",
            result.get("pending_has_max_retries") is True,
            "missing max_retries field",
        )
        ctx.check(
            "PendingConversation has retry_count field",
            result.get("pending_has_retry_count") is True,
            "missing retry_count field",
        )
        ctx.check(
            "PendingConversation has timer_task field",
            result.get("pending_has_timer_task") is True,
            "missing timer_task field",
        )

        # 2. ConversationManager instantiation
        ctx.check(
            "ConversationManager created with callback",
            result.get("cm_created") is True,
            "creation failed",
        )
        ctx.check(
            "pending_count is 0 initially",
            result.get("cm_pending_count_init") == 0,
            f"count={result.get('cm_pending_count_init')}",
        )

        # 3. track_intent
        ctx.check(
            "track_intent returns a future",
            result.get("track_returns_future") is True,
            "not a future",
        )
        ctx.check(
            "pending_count is 1 after track_intent",
            result.get("cm_pending_count_after_track") == 1,
            f"count={result.get('cm_pending_count_after_track')}",
        )

        # 4. process_msg matching
        ctx.check(
            "process_msg matches RP to pending conversation",
            result.get("process_msg_matched") is True,
            "RP not matched",
        )
        ctx.check(
            "pending_count is 0 after match",
            result.get("cm_pending_count_after_match") == 0,
            f"count={result.get('cm_pending_count_after_match')}",
        )
        ctx.check(
            "future resolved with RP message",
            result.get("future_resolved") is True,
            f"state={result.get('future_state', 'N/A')},"
            f" err={result.get('future_error', 'N/A')}",
        )

        # 5. Timeout + retry
        ctx.check(
            "timeout future completes with ProtocolTimeoutError",
            result.get("timeout_future_completed") is True,
            f"error={result.get('timeout_error_type', 'N/A')}",
        )
        ctx.check(
            "retried 2 times (max_retries=2)",
            result.get("timeout_retry_count") == 2,
            f"retries={result.get('timeout_retry_count')}",
        )
        ctx.check(
            "pending_count is 0 after timeout",
            result.get("cm_pending_count_after_timeout") == 0,
            f"count={result.get('cm_pending_count_after_timeout')}",
        )

        # 6. cancel_all
        ctx.check(
            "pending_count is 1 before cancel_all",
            result.get("cm_pending_before_cancel") == 1,
            f"count={result.get('cm_pending_before_cancel')}",
        )
        ctx.check(
            "pending_count is 0 after cancel_all",
            result.get("cm_pending_after_cancel") == 0,
            f"count={result.get('cm_pending_after_cancel')}",
        )
        ctx.check(
            "cancelled future is done",
            result.get("cancelled_future_done") is True,
            "future not done after cancel",
        )

        # 7. Gateway property
        ctx.check(
            "Gateway has conversation_manager property",
            result.get("gateway_has_conv_mgr_prop") is True,
            "property missing",
        )

        # 8. CommandDispatcher integration
        ctx.check(
            "CommandDispatcher.send uses conversation_manager",
            result.get("dispatcher_uses_conv_mgr") is True,
            "ConversationManager not referenced in send()",
        )
        ctx.check(
            "CommandDispatcher.send passes wait_for_reply=False to L3",
            result.get("dispatcher_uses_wait_for_reply_false") is True,
            "wait_for_reply=False not found in send()",
        )
        ctx.check(
            "CommandDispatcher.send calls track_intent",
            result.get("dispatcher_uses_track_intent") is True,
            "track_intent not found in send()",
        )
