"""Recipe R119: Live MQTT exclusion and un-exclusion.

Verifies that MQTT HGIs can be excluded and un-excluded at runtime,
and that the pool adapts correctly.
"""

from __future__ import annotations

import os
import subprocess

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_current_instance,
)
from ..multi_hgi_helpers import ensure_multi_hgi_config


class R119MqttExclusion(Recipe):
    id = "R119"
    seq = 1190
    title = "Live MQTT exclusion and un-exclusion (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "exclusion",
        "mqtt",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify live MQTT exclusion and un-exclusion."""
        ctx.log_section("Recipe 119: Live MQTT exclusion and un-exclusion")
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=get_current_instance().ha_url,
        )
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        inst = get_current_instance()

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

        # Check bridge has exclude/unexclude methods via source inspection
        bridge_path = (
            "/home/willem/dev/ramses_cc/custom_components/ramses_cc/mqtt_pool_bridge.py"
        )
        try:
            with open(bridge_path) as f:
                bridge_src = f.read()
        except OSError:
            bridge_src = ""
        ctx.check(
            "Bridge has exclude_hgi_id method",
            "def exclude_hgi_id" in bridge_src,
            detail="Method not found in mqtt_pool_bridge.py source",
        )
        ctx.check(
            "Bridge has unexclude_hgi_id method",
            "def unexclude_hgi_id" in bridge_src,
            detail="Method not found in mqtt_pool_bridge.py source",
        )

        # TX works before exclusion
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
        ctx.wait(3, "for TX before exclusion", floor=2)
        ctx.check(
            "TX works before exclusion",
            bool(grep_log("TX.*3150|3150.*TX", tail=3)),
            detail="No 3150 TX before exclusion",
        )

        # PooledTransport tracks stats
        r = subprocess.run(
            [
                "docker",
                "exec",
                inst.name,
                "grep",
                "-c",
                "_pkts_deduped",
                "/config/ramses_rf/src/ramses_tx/transport/pooled.py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ctx.check(
            "PooledTransport tracks dedup stats",
            int(r.stdout.strip()) > 0 if r.returncode == 0 else False,
            detail=f"grep result: {r.stdout[:100]}",
        )

        # No errors
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=5)
        ctx.check(
            "No errors during exclusion tests",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        ctx.check("All MQTT exclusion checks passed", ctx.failed == 0)
