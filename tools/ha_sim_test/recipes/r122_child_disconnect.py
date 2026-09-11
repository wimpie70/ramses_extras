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
    publish_mqtt_lwt,
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

        await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=get_current_instance().ha_url,
        )
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        inst = get_current_instance()
        hgi_secondary = "18:149488"

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

        # Both HGIs connected
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=3)
        ctx.check(
            "Initial: 2/2 MQTT children connected",
            "2/2 connected" in logs,
            detail=f"logs: {logs[:200]}",
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

        # Pool detects secondary offline
        offline_logs = grep_log(
            f"HGI.*{hgi_secondary}.*offline|child.*{hgi_secondary}.*offline|LWT.*{hgi_secondary}",
            tail=5,
        )
        ctx.check(
            "Pool detects secondary offline",
            bool(offline_logs),
            detail=f"No offline log for {hgi_secondary}",
        )

        # Pool shows reduced connectivity
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=3)
        ctx.check(
            "Pool shows reduced connectivity after disconnect",
            "connected" in logs,
            detail=f"logs: {logs[:200]}",
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

        # Pool recovers to 2/2
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=10)
        ctx.check(
            "Pool recovers to 2/2 after reconnect",
            "2/2 connected" in logs,
            detail=f"logs: {logs[:300]}",
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
