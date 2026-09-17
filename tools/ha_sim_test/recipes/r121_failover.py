"""Recipe R121: Live failover (primary disconnects, TX fails over to secondary).

Verifies that when the primary HGI goes offline (MQTT LWT), the pool
adapts and TX fails over to the secondary HGI.
"""

from __future__ import annotations

import subprocess

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_current_instance,
)
from ..multi_hgi_helpers import (
    ensure_multi_hgi_config,
    publish_mqtt_lwt,
    wait_for_hgi_states,
)


class R121Failover(Recipe):
    id = "R121"
    seq = 1210
    title = "Live failover: primary disconnects, TX fails over (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "failover",
        "mqtt",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify live failover when primary disconnects."""
        ctx.log_section("Recipe 121: Live failover")
        failed_at_start = ctx.failed
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        if not await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=get_current_instance().ha_url,
        ):
            ctx.check(
                "multi-HGI config applied",
                False,
                "ensure_multi_hgi_config failed — cannot proceed",
            )
            return
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        inst = get_current_instance()
        hgi_primary = inst.hgi_id
        hgi_secondary = inst.hgi_id_2

        def grep_log(pattern: str, tail: int = 5) -> str:
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    inst.name,
                    "bash",
                    "-c",
                    f"tail -n 2000 /config/home-assistant.log"
                    f" | grep -iE '{pattern}' | tail -{tail}",
                ],
                capture_output=True,
                text=True,
            )
            return r.stdout

        # Both configured HGIs connected — check per-HGI online sensors
        # rather than "N/M connected" log lines: foreign HGIs discovered
        # via the shared MQTT broker add receive-only pool children, so
        # the M count is nondeterministic under parallel runs.
        states = wait_for_hgi_states(ctx.token, [hgi_primary, hgi_secondary])
        ctx.check(
            "Initial: both configured MQTT children online",
            all(states.values()),
            detail=f"states: {states}",
        )

        # TX works before failover
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": "01:150000",
                    "verb": "RQ",
                    "code": "3150",
                    "payload": "00",
                },
            )
        except Exception:
            pass
        ctx.wait(3, "for TX before failover", floor=2)
        ctx.check(
            "TX works before failover",
            bool(grep_log("TX.*3150|3150.*TX", tail=3)),
            detail="No 3150 TX before failover",
        )

        # Disconnect primary via LWT offline (HA mqtt.publish, no paho)
        lwt_ok = publish_mqtt_lwt(
            inst.name,
            f"RAMSES/GATEWAY_SIM/{hgi_primary}",
            "offline",
            token=ctx.token,
            ha_url=inst.ha_url,
        )
        ctx.check(
            "Primary HGI LWT offline published",
            lwt_ok,
            detail="Failed to publish LWT offline",
        )
        ctx.wait(5, "for pool to detect primary offline", floor=3)

        # Pool detects primary offline — the bridge logs the LWT
        # transition.  (A sustained OFF sensor state can't be asserted:
        # the sim endpoint keeps publishing RX frames for this HGI, so
        # "inferred from RX" legitimately re-marks it online — issue
        # 1185.)
        offline_logs = grep_log(
            f"HGI.*{hgi_primary}.*offline|child.*{hgi_primary}.*offline|LWT.*{hgi_primary}",
            tail=5,
        )
        ctx.check(
            "Pool detects primary offline",
            bool(offline_logs),
            detail=f"No offline log for {hgi_primary}",
        )

        # TX must route through the secondary after failover.  The
        # simulator publishes loopback echoes on the primary endpoint,
        # which is deliberately offline here, so don't wait through the
        # normal three 30s HTTP attempts for an echo that cannot arrive.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": "01:150000",
                    "verb": "RQ",
                    "code": "3150",
                    "payload": "00",
                },
                timeout=5,
                retries=1,
            )
        except RuntimeError as err:
            if "timed out" not in str(err).lower():
                raise
        ctx.wait(3, "for TX after failover", floor=2)
        failover_logs = grep_log(
            rf"{hgi_secondary}/tx|selected child.*hgi={hgi_secondary}",
            tail=5,
        )
        ctx.check(
            "TX routes through secondary after primary fails",
            bool(failover_logs),
            detail=f"TX logs: {failover_logs[:200]}",
        )

        # Reconnect primary
        lwt_ok = publish_mqtt_lwt(
            inst.name,
            f"RAMSES/GATEWAY_SIM/{hgi_primary}",
            "online",
            token=ctx.token,
            ha_url=inst.ha_url,
        )
        ctx.check(
            "Primary HGI LWT online re-published",
            lwt_ok,
            detail="Failed to publish LWT online",
        )
        ctx.wait(8, "for pool to detect primary online", floor=5)

        # Pool recovers — the primary's per-HGI sensor is back on
        states = wait_for_hgi_states(ctx.token, [hgi_primary])
        ctx.check(
            "Pool recovers after primary reconnects",
            states[hgi_primary],
            detail=f"states: {states}",
        )

        # TX works after reconnect
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": "01:150000",
                    "verb": "RQ",
                    "code": "3150",
                    "payload": "00",
                },
            )
        except Exception:
            pass
        ctx.wait(3, "for TX after reconnect", floor=2)
        ctx.check(
            "TX works after primary reconnects",
            bool(grep_log("TX.*3150|3150.*TX", tail=3)),
            detail="No 3150 TX after reconnect",
        )

        # No errors
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=5)
        ctx.check(
            "No errors during failover",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        ctx.check("All failover checks passed", ctx.failed == failed_at_start)
