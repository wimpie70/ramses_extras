"""Recipe R133: TX keeps working after a caller-cancelled in-flight send (issue 1241).

https://github.com/ramses-rf/ramses_cc/issues/1241 — a ``get_zone_schedule``
timeout cancelled a task while it was inside ``send_cmd()``, which cancelled
the queued command's future and silently killed ``PortProtocol._tx_worker``.
Afterwards every service call queued commands forever (RX kept working, no TX).

The simulator echoes every TX frame back immediately, so a send is normally
in-flight for only ~50 ms — far too short for a 15 s ``wait_for`` to land the
cancellation inside it.  This recipe first disables the simulator's gateway
loopback echo (``device_simulator/set_echo``); every ``send_cmd`` then holds
for the full QoS echo timeout (~20 s), so the schedule fetch's 15 s timeout
is guaranteed to cancel the task while its send is mid-flight — the exact
issue-1241 trigger.

On the buggy code the TX worker dies here and the verification send never
reaches MQTT.  On fixed code the worker drops the cancelled item and keeps
draining the queue.
"""

from __future__ import annotations

import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_current_instance,
    get_entities,
    load_profile_yaml,
    ws_send,
)
from ..profile import mixed_yaml

_ZONE_IDX = "03"


class R133TxSurvivesCancelledSend(Recipe):
    id = "R133"
    seq = 1330
    title = "TX survives caller-cancelled in-flight send (issue 1241)"
    tags = (
        "tx",
        "mqtt",
        "issue-1241",
        "schedule",
        "regression",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify TX still works after a cancelled in-flight send."""
        ctx.log_section("Recipe 133: TX survives cancelled send (issue 1241)")
        failed_at_start = ctx.failed
        ctx.wait_for_ramses_cc_loaded(timeout=20)
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
                    f"tail -n 500 /config/home-assistant.log"
                    f" | grep -iE '{pattern}' | tail -{tail}",
                ],
                capture_output=True,
                text=True,
            )
            return r.stdout

        def grep_since_marker(marker: str, pattern: str, tail: int = 4000) -> str:
            """Grep for pattern only in log lines after the LAST marker."""
            cmd = (
                f"tail -n {tail} /config/home-assistant.log | "
                f"awk '/{marker}/{{n=NR}} {{b[NR]=$0}} "
                f"END{{for(i=n||0;i<=NR;i++) if(b[i]) print b[i]}}' | "
                f"grep -iE '{pattern}'"
            )
            r = subprocess.run(
                ["docker", "exec", inst.name, "bash", "-c", cmd],
                capture_output=True,
                text=True,
            )
            return r.stdout

        # Mixed profile: zones 03-08 each with sensor + actuator give real
        # zone climate entities for get_zone_schedule.
        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as err:
            ctx.check("mixed profile loaded", False, detail=str(err)[:200])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()

        # Find the zone climate entity.  Skip "restored" orphans left by
        # earlier profiles (they keep the climate.*_03 name with a _2
        # suffix on the live entity) and match by entity_id, the ``id``
        # attribute ("01:150000_03"), or friendly_name.
        ctl_suffix = CTL.replace(":", "_")
        needle = f"{ctl_suffix}_{_ZONE_IDX}"

        def find_zone_eid() -> str:
            for e in get_entities(ctx.token):
                eid = e["entity_id"]
                attrs = e.get("attributes", {})
                if not eid.startswith("climate.") or attrs.get("restored"):
                    continue
                if attrs.get("id") == f"{CTL}_{_ZONE_IDX}":
                    return eid
                if attrs.get("friendly_name") == f"{CTL}_{_ZONE_IDX}":
                    return eid
                if needle in eid:
                    return eid
            return ""

        ctx.wait_for(
            find_zone_eid,
            timeout=30,
            msg="for zone climate entity",
        )
        zone_eid = find_zone_eid()
        ctx.check(
            "zone climate entity found",
            bool(zone_eid),
            detail="no live climate entity for zone 03",
        )
        if not zone_eid:
            return

        # Disable the gateway loopback echo so send_cmd blocks for the full
        # QoS echo timeout (DEFAULT_SEND_TIMEOUT ~20 s).  The schedule
        # fetch's own wait_for(15) then cancels its task while it is inside
        # send_cmd — deterministic issue-1241 trigger.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/set_echo",
                    "enabled": False,
                },
            )
        except RuntimeError as err:
            ctx.check("simulator echo disabled", False, detail=str(err)[:200])
            return

        try:
            # Trigger: get_zone_schedule wraps the fetch in wait_for(15).
            # With no echo, its first RQ is still in-flight at the timeout,
            # so the cancellation lands inside send_cmd's await fut.
            print("  Calling get_zone_schedule (expect ~15s timeout)...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "get_zone_schedule",
                    {"entity_id": zone_eid},
                    timeout=40,
                    retries=1,
                )
            except RuntimeError:
                pass  # expected — schedule fetch times out

            sched_logs = grep_log("Failed to obtain schedule|ScheduleFlowError", tail=5)
            ctx.check(
                "get_zone_schedule timed out (cancel trigger fired)",
                bool(sched_logs),
                detail="no schedule timeout logged — trigger did not run",
            )
        finally:
            # Always restore the echo — leaving it off breaks every later
            # recipe (send_cmd would block ~20 s on every send).
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/set_echo",
                        "enabled": True,
                    },
                )
            except RuntimeError:
                pass

        # Verify TX still works: a fresh send_packet must reach MQTT, which
        # only happens if the tx worker survived the cancelled send.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": CTL,
                    "verb": "RQ",
                    "code": "3150",
                    "payload": "00",
                },
                timeout=30,
                retries=1,
            )
        except RuntimeError:
            pass  # buggy code: dead worker -> send times out after ~20 s
        ctx.wait(3, "for TX after cancelled send", floor=2)

        # "TX ->" is the bridge's publish log — it only appears when the tx
        # worker actually publishes.  Scope to lines after the schedule
        # timeout marker so pre-kill publishes (e.g. zone polling) can't
        # false-pass.  (A bare "TX.*3150" also false-matches
        # "ramses_tx.protocol.base] Patching command ... RQ|3150" — patching
        # happens in send_cmd even when the worker is dead.)
        tx_logs = grep_since_marker("Failed to obtain schedule", "TX ->.*3150")
        ctx.check(
            "TX works after cancelled in-flight send",
            bool(tx_logs),
            detail="No 3150 TX after cancelled send — tx worker is dead",
        )

        ctx.check("All cancelled-send checks passed", ctx.failed == failed_at_start)
