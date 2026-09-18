"""Recipe R128: HA reaches RUNNING state promptly after restart.

Regression coverage for the 2026-09-18 startup-wrap-up block: several
ramses_cc/ramses_extras fire-and-forget tasks were created with
``hass.async_create_task`` (tracked), so ``async_block_till_done``
waited on them during startup wrap-up.  With a degraded transport
(dead Zigbee child / slow MQTT) they ran for minutes, leaving
``hass.config.state`` below ``RUNNING`` — which latched every
ramses_extras frontend card into "Home Assistant is initializing"
even though the REST/websocket API already answered.  The suite's
existing readiness checks only probe the API, so the failure was
invisible to ha_sim_test.

This recipe restarts the container and polls ``GET /api/config``
until ``state == "RUNNING"``, with a deadline well under HA's own
5-minute bootstrap timeout.  It also greps the log for the
"blocking Home Assistant from wrapping up" signature.
"""

from __future__ import annotations

import subprocess
import time

from ..base import Recipe, RecipeContext
from ..helpers import (
    get_current_instance,
    grep_ha_log,
    is_ha_running,
)

RUNNING_DEADLINE_S = 150  # previously blocked >=300s (bootstrap timeout)


class R128StartupRunningState(Recipe):
    id = "R128"
    seq = 1280
    title = "HA reaches RUNNING state promptly after restart"
    tags = ("startup", "running-state", "regression")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 128: HA reaches RUNNING after restart")

        inst = get_current_instance()
        print(f"  Restarting {inst.name}...")
        ctx.log_monitor.capture_before_restart()
        subprocess.run(["docker", "restart", inst.name], check=True, timeout=60)
        ctx.log_monitor.reset_baseline()
        t0 = time.monotonic()

        # Poll /api/config until state == RUNNING.  The token survives
        # the restart (long-lived access token); get_ha_config returns
        # None while the API is still unreachable.
        running_at: float | None = None
        deadline = t0 + RUNNING_DEADLINE_S
        while time.monotonic() < deadline:
            try:
                ctx.refresh_token()
            except Exception:  # noqa: BLE001 — API still restarting
                pass
            if is_ha_running(ctx.token):
                running_at = time.monotonic() - t0
                break
            time.sleep(2)

        ctx.check(
            f"hass.config.state reached RUNNING within {RUNNING_DEADLINE_S}s",
            running_at is not None,
            f"still not RUNNING after {RUNNING_DEADLINE_S}s "
            "(tracked startup tasks blocking wrap-up?)",
        )
        if running_at is not None:
            print(f"  state=RUNNING after {running_at:.1f}s")

        blocking = grep_ha_log(
            r"blocking Home Assistant from wrapping up the start up phase",
            since_lines=1000,
        )
        ctx.check(
            "no startup wrap-up block warning in log",
            len(blocking) == 0,
            f"found {len(blocking)} warning(s): " + "; ".join(blocking[:3]),
        )

        # Leave the instance usable for subsequent recipes.
        ctx.wait_for_ramses_cc_loaded(timeout=60, msg="for ramses_cc after restart")
