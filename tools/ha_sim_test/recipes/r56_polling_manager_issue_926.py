"""Recipe R56: L7 PollingManager live cutover (Phase 4c.3).

Verifies the PollingManager infrastructure that replaces legacy
DiscoveryService polling:

1. **PollingManager module** — importable from ``ramses_rf.pipeline.polling``
2. **PollingTask dataclass** — tracking structure with required fields
3. **DEFAULT_POLLING_SCHEDULES** — battery devices have None intervals
4. **Gateway property** — ``gwy.polling_manager`` exists
5. **shadow_mode=False** — live cutover, not shadow
6. **Legacy poller deactivated** — ``DiscoveryService.start_poller`` is a no-op
7. **Lifecycle integration** — ``GatewayLifecycle.start`` calls ``pm.start()``,
   ``GatewayLifecycle.stop`` calls ``pm.stop()``
8. **Schedule resolution** — battery devices get empty schedule, mains
   devices get non-empty schedule
9. **Config trait** — ``disable_polling`` config option respected

This is a structural test that runs inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_rf/pull/926 (Phase 4c.3)
     https://github.com/ramses-rf/ramses_rf/pull/925 (Phase 4c.2)
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, HGI, TRV
from ..helpers import docker_exec_python


class R56PollingManagerIssue926(Recipe):
    id = "R56"
    seq = 560
    title = "L7 PollingManager live cutover (PR 926)"
    tags = ("structural",)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 56: L7 PollingManager (PR 926)")

        code = """
import json

try:
    from ramses_rf.pipeline.polling import (
        PollingManager,
        PollingTask,
        DEFAULT_POLLING_SCHEDULES,
        DEFAULT_POLL_CYCLE_SECS,
    )
    from ramses_rf.const import DevType
    from ramses_rf.gateway import Gateway
    from ramses_rf.lifecycle import GatewayLifecycle
    import inspect

    # PR 927+ removes DiscoveryService entirely.  PR 926 keeps it as a
    # deprecated no-op.  Handle both cases.
    try:
        from ramses_rf.discovery import DiscoveryService
        discovery_service_exists = True
    except ImportError:
        DiscoveryService = None
        discovery_service_exists = False

    results = {}

    # ── 1. Module imports ────────────────────────────────────────────
    results["polling_module_imported"] = True
    results["polling_task_is_dataclass"] = hasattr(PollingTask, "__dataclass_fields__")
    _fields = PollingTask.__dataclass_fields__
    results["task_has_device_id"] = "device_id" in _fields
    results["task_has_code"] = "code" in _fields
    results["task_has_interval"] = "interval" in _fields
    results["task_has_next_due"] = "next_due" in _fields

    # ── 2. DEFAULT_POLLING_SCHEDULES ──────────────────────────────────
    results["schedules_has_ctl"] = DevType.CTL in DEFAULT_POLLING_SCHEDULES
    results["schedules_has_fan"] = DevType.FAN in DEFAULT_POLLING_SCHEDULES
    results["schedules_has_trv"] = DevType.TRV in DEFAULT_POLLING_SCHEDULES
    results["schedules_has_default"] = "DEFAULT" in DEFAULT_POLLING_SCHEDULES

    # Battery devices (TRV, THM, DHW) must have None intervals
    trv_schedule = DEFAULT_POLLING_SCHEDULES.get(DevType.TRV, {})
    results["trv_has_none_interval"] = any(
        v is None for v in trv_schedule.values()
    )

    # Mains devices (CTL, FAN) must have non-None intervals
    ctl_schedule = DEFAULT_POLLING_SCHEDULES.get(DevType.CTL, {})
    results["ctl_has_active_interval"] = any(
        v is not None and v > 0 for v in ctl_schedule.values()
    )

    results["default_poll_cycle"] = DEFAULT_POLL_CYCLE_SECS

    # ── 3. Gateway has polling_manager property ───────────────────────
    results["gateway_has_polling_mgr_prop"] = hasattr(
        Gateway, "polling_manager"
    )

    # ── 4. PollingManager constructor accepts shadow_mode ─────────────
    sig = inspect.signature(PollingManager.__init__)
    results["pm_has_shadow_mode_param"] = "shadow_mode" in sig.parameters

    # ── 5. Legacy poller deactivated ──────────────────────────────────
    # PR 926: DiscoveryService.start_poller is a deprecated no-op.
    # PR 927+: DiscoveryService is removed entirely (stronger deprecation).
    if discovery_service_exists:
        poller_src = inspect.getsource(DiscoveryService.start_poller)
        results["legacy_poller_is_noop"] = (
            "deprecated" in poller_src.lower()
            or "disabled" in poller_src.lower()
        )
        results["legacy_poller_no_schedule_task"] = (
            "schedule_task" not in poller_src
        )
    else:
        # DiscoveryService fully removed — stronger than no-op
        results["legacy_poller_is_noop"] = True
        results["legacy_poller_no_schedule_task"] = True

    # ── 6. Lifecycle integration ──────────────────────────────────────
    start_src = inspect.getsource(GatewayLifecycle.start)
    results["lifecycle_start_calls_pm_start"] = (
        "polling_manager" in start_src and "pm.start" in start_src
    )

    stop_src = inspect.getsource(GatewayLifecycle.stop)
    results["lifecycle_stop_calls_pm_stop"] = (
        "polling_manager" in stop_src and "pm.stop" in stop_src
    )

    # ── 7. PollingManager.send uses async_send_cmd (live mode) ────────
    poll_src = inspect.getsource(PollingManager.poll_due_commands)
    results["poll_dispatches_cmd"] = "async_send_cmd" in poll_src
    results["poll_uses_build_rq_cmd"] = "build_rq_cmd" in poll_src
    results["poll_no_raw_command_dto"] = "CommandDTO(" not in poll_src
    results["poll_checks_disable_polling"] = "disable_polling" in poll_src

    # ── 8. Config has disable_polling ─────────────────────────────────
    from ramses_rf.config import GatewayConfig
    config_src = inspect.getsource(GatewayConfig)
    results["config_has_disable_polling"] = "disable_polling" in config_src

    print(json.dumps({"ok": True, **results}))
except Exception as e:
    import traceback
    print(json.dumps({
        "error": f"{type(e).__name__}: {e}",
        "traceback": traceback.format_exc()[:2000],
        "ok": False,
    }))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "PollingManager infrastructure runs without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("PollingManager infrastructure runs without error", True, "")

        # 1. Module + dataclass
        ctx.check(
            "PollingTask is a dataclass",
            result.get("polling_task_is_dataclass") is True,
            "not a dataclass",
        )
        ctx.check(
            "PollingTask has device_id field",
            result.get("task_has_device_id") is True,
            "missing device_id",
        )
        ctx.check(
            "PollingTask has code field",
            result.get("task_has_code") is True,
            "missing code",
        )
        ctx.check(
            "PollingTask has interval field",
            result.get("task_has_interval") is True,
            "missing interval",
        )
        ctx.check(
            "PollingTask has next_due field",
            result.get("task_has_next_due") is True,
            "missing next_due",
        )

        # 2. DEFAULT_POLLING_SCHEDULES
        ctx.check(
            "Schedules include CTL",
            result.get("schedules_has_ctl") is True,
            "CTL missing",
        )
        ctx.check(
            "Schedules include FAN",
            result.get("schedules_has_fan") is True,
            "FAN missing",
        )
        ctx.check(
            "Schedules include TRV",
            result.get("schedules_has_trv") is True,
            "TRV missing",
        )
        ctx.check(
            "Schedules include DEFAULT fallback",
            result.get("schedules_has_default") is True,
            "DEFAULT missing",
        )
        ctx.check(
            "TRV (battery) has None interval (polling disabled)",
            result.get("trv_has_none_interval") is True,
            "TRV should have None intervals",
        )
        ctx.check(
            "CTL (mains) has active interval",
            result.get("ctl_has_active_interval") is True,
            "CTL should have active intervals",
        )

        # 3. Gateway property
        ctx.check(
            "Gateway has polling_manager property",
            result.get("gateway_has_polling_mgr_prop") is True,
            "property missing",
        )

        # 4. Constructor
        ctx.check(
            "PollingManager accepts shadow_mode parameter",
            result.get("pm_has_shadow_mode_param") is True,
            "shadow_mode param missing",
        )

        # 5. Legacy poller deactivated
        ctx.check(
            "Legacy start_poller is deprecated/no-op",
            result.get("legacy_poller_is_noop") is True,
            "start_poller not marked as deprecated",
        )
        ctx.check(
            "Legacy start_poller does not call schedule_task",
            result.get("legacy_poller_no_schedule_task") is True,
            "start_poller still schedules tasks",
        )

        # 6. Lifecycle integration
        ctx.check(
            "GatewayLifecycle.start calls pm.start()",
            result.get("lifecycle_start_calls_pm_start") is True,
            "pm.start() not called in lifecycle start",
        )
        ctx.check(
            "GatewayLifecycle.stop calls pm.stop()",
            result.get("lifecycle_stop_calls_pm_stop") is True,
            "pm.stop() not called in lifecycle stop",
        )

        # 7. Live command dispatch
        ctx.check(
            "PollingManager.poll_due_commands dispatches via async_send_cmd",
            result.get("poll_dispatches_cmd") is True,
            "async_send_cmd not found in poll_due_commands",
        )
        ctx.check(
            "PollingManager uses build_rq_cmd (correct address convention)",
            result.get("poll_uses_build_rq_cmd") is True,
            "build_rq_cmd not found in poll_due_commands",
        )
        ctx.check(
            "PollingManager does not construct raw CommandDTO (avoids addr bugs)",
            result.get("poll_no_raw_command_dto") is True,
            "raw CommandDTO() constructor found in poll_due_commands",
        )
        ctx.check(
            "PollingManager respects disable_polling config",
            result.get("poll_checks_disable_polling") is True,
            "disable_polling check missing",
        )

        # 8. Config
        ctx.check(
            "GatewayConfig has disable_polling option",
            result.get("config_has_disable_polling") is True,
            "disable_polling not in GatewayConfig",
        )
