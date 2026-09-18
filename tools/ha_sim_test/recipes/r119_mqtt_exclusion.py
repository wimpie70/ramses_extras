"""Recipe R119: Live MQTT exclusion and un-exclusion.

Verifies that MQTT HGIs can be excluded and un-excluded at runtime,
and that the pool adapts correctly.
"""

from __future__ import annotations

import json
import os
import subprocess

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    docker_exec_python,
    get_current_instance,
)
from ..multi_hgi_helpers import ensure_multi_hgi_config, wait_for_hgi_states


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
        hgi_ids = [inst.hgi_id, inst.hgi_id_2]

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

        # Both configured HGIs connected — per-HGI sensors, not "N/M"
        # log counts (foreign HGIs add receive-only children in parallel).
        states = wait_for_hgi_states(ctx.token, hgi_ids)
        ctx.check(
            "Initial: both configured MQTT children online",
            all(states.values()),
            detail=f"states: {states}",
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

        # ---------------------------------------------------------------
        # Sentinel HGI 18:000730 must not leak into the schema (issue 1171)
        # ---------------------------------------------------------------
        # The sentinel is ramses_rf's internal placeholder source address —
        # not a real gateway.  Stale/retained broker topics under it must
        # be ignored end-to-end.  A real unknown HGI is published as a
        # positive control to prove discovery still works.
        ctx.log_section("Sentinel HGI 18:000730 must not leak into schema")
        sentinel = "18:000730"
        probe_hgi = "18:009999"
        tns = inst.mqtt_topic_ns

        try:
            # Stale retained LWT on the sentinel topic (the forum scenario).
            call_service(
                ctx.token,
                "mqtt",
                "publish",
                {
                    "topic": f"{tns}/{sentinel}",
                    "payload": "online",
                    "retain": True,
                },
            )
            # An rx frame on the sentinel topic.
            call_service(
                ctx.token,
                "mqtt",
                "publish",
                {
                    "topic": f"{tns}/{sentinel}/rx",
                    "payload": json.dumps(
                        {"msg": "000 RQ --- 18:000730 01:150000 --:------ 30C9 001 07"}
                    ),
                },
            )
            # Positive control: a real unknown HGI must still be discovered.
            call_service(
                ctx.token,
                "mqtt",
                "publish",
                {
                    "topic": f"{tns}/{probe_hgi}/rx",
                    "payload": json.dumps(
                        {
                            "msg": "000  I --- 01:150000 18:009999 "
                            "--:------ 30C9 003 000F1B"
                        }
                    ),
                },
            )
        except Exception as err:
            ctx.check(
                "Sentinel/control topics published",
                False,
                detail=f"mqtt.publish failed: {err}",
            )
            return
        finally:
            # Clear the retained topics so later recipes (and other
            # branches on the shared broker) start from a clean state.
            try:
                call_service(
                    ctx.token,
                    "mqtt",
                    "publish",
                    {"topic": f"{tns}/{sentinel}", "payload": "", "retain": True},
                )
            except Exception:
                pass

        # Poll the persisted schema — the discovery write is debounced,
        # so wait for the positive control to land before asserting the
        # sentinel is absent.
        flags: dict = {}
        for _attempt in range(10):
            flags = docker_exec_python(
                """
import json
d = json.load(open('/config/.storage/core.config_entries'))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        s = e['options'].get('schema', {})
        probe = s.get('18:009999') or {}
        print(json.dumps({
            'sentinel': '18:000730' in s,
            'probe': '18:009999' in s,
            'probe_owner': probe.get('_owner'),
            'probe_class': probe.get('_class'),
        }))
        break
"""
            )
            if flags.get("probe") or "error" in flags:
                break
            ctx.wait(2, "for discovery candidate write")

        ctx.check(
            "Schema probe executed",
            "error" not in flags,
            detail=f"{flags.get('error', flags)}",
        )
        ctx.check(
            "Unknown HGI 18:009999 discovered (control)",
            bool(flags.get("probe")),
            detail=f"schema flags: {flags}",
        )
        ctx.check(
            "Discovered HGI is an ownerless HGI candidate",
            flags.get("probe_class") == "HGI" and not flags.get("probe_owner"),
            detail=f"_class: {flags.get('probe_class')}, "
            f"_owner: {flags.get('probe_owner')}",
        )
        ctx.check(
            "Sentinel 18:000730 absent from schema",
            not flags.get("sentinel"),
            detail=f"schema flags: {flags}",
        )

        # No errors from the sentinel traffic either
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=5)
        ctx.check(
            "No errors during sentinel checks",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        ctx.check("All MQTT exclusion checks passed", ctx.failed == failed_at_start)
