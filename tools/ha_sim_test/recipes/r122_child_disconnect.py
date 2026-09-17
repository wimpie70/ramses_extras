"""Recipe R122: Live MQTT child disconnect and reconnect.

Verifies that the pool handles MQTT child disconnect and reconnect
gracefully.
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
    hgi_online_states,
    publish_mqtt_lwt,
    wait_for_hgi_states,
)


class R122ChildDisconnect(Recipe):
    id = "R122"
    seq = 1220
    title = "Live MQTT child disconnect and reconnect (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "disconnect",
        "reconnect",
        "mqtt",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify live MQTT child disconnect and reconnect."""
        ctx.log_section("Recipe 122: Live MQTT child disconnect and reconnect")
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

        # Disconnect secondary via LWT offline (HA mqtt.publish, no paho)
        lwt_ok = publish_mqtt_lwt(
            inst.name,
            f"RAMSES/GATEWAY_SIM/{hgi_secondary}",
            "offline",
            token=ctx.token,
            ha_url=inst.ha_url,
        )
        ctx.check(
            "Secondary HGI LWT offline published",
            lwt_ok,
            detail="Failed to publish LWT offline",
        )
        ctx.wait(5, "for pool to detect secondary offline", floor=3)

        # Pool detects secondary offline — the bridge logs the LWT
        # transition.  (A sustained OFF state can't be asserted here:
        # the sim endpoint keeps publishing RX frames for this HGI, so
        # the bridge's "inferred from RX" path legitimately marks it
        # back online within seconds — issue 1185.)
        offline_logs = grep_log(
            f"HGI.*{hgi_secondary}.*offline|child.*{hgi_secondary}.*offline|LWT.*{hgi_secondary}",
            tail=5,
        )
        ctx.check(
            "Pool detects secondary offline",
            bool(offline_logs),
            detail=f"No offline log for {hgi_secondary}",
        )

        # Primary stays connected — reduced connectivity, not total loss
        states = hgi_online_states(ctx.token, [hgi_primary])
        ctx.check(
            "Pool shows reduced connectivity after disconnect",
            states[hgi_primary],
            detail=f"states: {states}",
        )

        # TX still works with primary
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
        ctx.wait(3, "for TX with primary only", floor=2)
        ctx.check(
            "TX works with primary only (after secondary disconnect)",
            bool(grep_log("TX.*3150|3150.*TX", tail=3)),
            detail="No 3150 TX with primary only",
        )

        # Reconnect secondary
        lwt_ok = publish_mqtt_lwt(
            inst.name,
            f"RAMSES/GATEWAY_SIM/{hgi_secondary}",
            "online",
            token=ctx.token,
            ha_url=inst.ha_url,
        )
        ctx.check(
            "Secondary HGI LWT online re-published",
            lwt_ok,
            detail="Failed to publish LWT online",
        )
        ctx.wait(8, "for pool to detect secondary online", floor=5)

        # Secondary child comes back online
        states = wait_for_hgi_states(ctx.token, [hgi_primary, hgi_secondary])
        ctx.check(
            "Pool recovers after secondary reconnect",
            all(states.values()),
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
            "TX works after secondary reconnect",
            bool(grep_log("TX.*3150|3150.*TX", tail=3)),
            detail="No 3150 TX after reconnect",
        )

        # No errors
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=5)
        ctx.check(
            "No errors during disconnect/reconnect",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        ctx.check(
            "All child disconnect/reconnect checks passed",
            ctx.failed == failed_at_start,
        )
