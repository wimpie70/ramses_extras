"""Recipe R146: Concurrent identical RQ sends on an MQTT pool (issue 1336).

https://github.com/ramses-rf/ramses_cc/issues/1336 — nine concurrent
``get_zone_schedule`` calls each issued the TCS-level ``RQ 0006``
(schedule version), producing byte-identical frames.  The pool's
content-keyed dedup dropped every identical TX's echo after the first,
so each extra send stalled on the 20 s WantEcho timeout and the outer
15 s schedule timeout fired before eight of nine zones even reached
the ``0404`` fragment fetch.

Two fixes are verified here, each independently observable:

* Conversation single-flight (ramses_rf): identical in-flight RQ
  intents share one pending conversation, so the burst emits at most
  one ``RQ 0006`` and one reply resolves every waiter.
* Per-TX echo entitlements (ramses_tx): each recorded transmission
  gets one forwarded echo copy, so concurrent identical raw sends
  (``send_packet``, which bypasses the conversation manager) all
  resolve promptly instead of stalling 20 s.

Note: the simulator's recorded ``0404`` replies reference zone ``01``,
so ``get_zone_schedule`` itself still fails at the fragment stage —
the checks assert progression *to* that stage, not service success.
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_current_instance,
    get_entities,
    load_profile_yaml,
)
from ..multi_hgi_helpers import ensure_multi_hgi_config
from ..profile import mixed_yaml

_MAX_ZONE_CALLS = 5


class R146ConcurrentIdenticalRq(Recipe):
    id = "R146"
    seq = 1460
    title = "Concurrent identical RQ sends on a pool (issue 1336)"
    tags = (
        "pooled",
        "multi-hgi",
        "tx",
        "mqtt",
        "schedule",
        "issue-1336",
        "regression",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify identical RQ sends coalesce and each TX echo forwards."""
        ctx.log_section("Recipe 146: Concurrent identical RQ (issue 1336)")
        failed_at_start = ctx.failed
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        inst = get_current_instance()

        def grep_since_marker(marker: str, pattern: str) -> str:
            """Grep for pattern only in log lines after the LAST marker."""
            cmd = (
                f"tail -n 4000 /config/home-assistant.log | "
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

        def count_since_marker(marker: str, pattern: str) -> int:
            out = grep_since_marker(marker, pattern)
            return len([ln for ln in out.splitlines() if ln.strip()])

        def marker(name: str) -> None:
            """Write a unique marker into the HA log."""
            call_service(
                ctx.token,
                "system_log",
                "write",
                {"message": name, "level": "warning"},
            )

        # -----------------------------------------------------------------
        # Setup: mixed profile + real two-HGI MQTT pool (the dedup paths
        # under test only exist in PooledTransport).
        # -----------------------------------------------------------------
        try:
            await load_profile_yaml(ctx.token, mixed_yaml(), speed=0.01)
        except RuntimeError as err:
            ctx.check("mixed profile loaded", False, detail=str(err)[:200])
            return
        ctx.wait_for_ramses_cc_reload(timeout=20)
        if not await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=inst.ha_url,
        ):
            ctx.check(
                "multi-HGI config applied",
                False,
                "ensure_multi_hgi_config failed — cannot proceed",
            )
            return
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        # DEBUG on the loggers that prove forwarding decisions.
        call_service(
            ctx.token,
            "logger",
            "set_level",
            {
                "ramses_tx.transport.pooled": "debug",
                "ramses_rf.pipeline.conversation": "debug",
            },
        )

        # Find live zone climate entities (id attribute "CTL_NN").
        def zone_eids() -> list[str]:
            eids = []
            for e in get_entities(ctx.token):
                eid = e["entity_id"]
                attrs = e.get("attributes", {})
                dev_id = attrs.get("id") or ""
                if (
                    eid.startswith("climate.")
                    and dev_id.startswith(f"{CTL}_")
                    and not attrs.get("restored")
                ):
                    eids.append(eid)
            return eids[:_MAX_ZONE_CALLS]

        ctx.wait_for(
            lambda: len(zone_eids()) >= 2,
            timeout=30,
            msg="for >=2 zone climate entities",
        )
        eids = zone_eids()
        ctx.check(
            "at least 2 zone climate entities found",
            len(eids) >= 2,
            detail=f"entities={eids}",
        )
        if len(eids) < 2:
            return
        n_zones = len(eids)
        print(f"  Using {n_zones} zones: {eids}")

        # -----------------------------------------------------------------
        # Part A: concurrent get_zone_schedule → single-flight RQ 0006.
        # Every call must reach the 0404 stage promptly (the sim cannot
        # complete a schedule — asserts progression, not success).
        # -----------------------------------------------------------------
        marker("R146_PART_A_START")

        def call_schedule(eid: str) -> float:
            t0 = time.monotonic()
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "get_zone_schedule",
                    {"entity_id": eid},
                    timeout=40,
                    retries=1,
                )
            except RuntimeError:
                pass  # sim 0404 replies mismatch — expected
            return time.monotonic() - t0

        # Pool threads start with a fresh context — get_current_instance()
        # would fall back to ha-sim.  Copy the context so workers target
        # this recipe's own instance.
        t_start = time.monotonic()
        ctx_copy = contextvars.copy_context()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_zones) as pool:
            durations = list(
                pool.map(lambda eid: ctx_copy.run(call_schedule, eid), eids)
            )
        burst_wall = time.monotonic() - t_start
        print(
            f"  {n_zones} concurrent calls done in {burst_wall:.1f}s"
            f" (slowest {max(durations):.1f}s)"
        )

        # At most one RQ 0006 TX for the whole burst: the first call
        # transmits, concurrent callers share its pending conversation
        # (or the freshly-cached _msg_0006 afterwards).
        n_0006 = count_since_marker(
            "R146_PART_A_START", r"TX ->.*RQ --- .* 0006 001 00"
        )
        ctx.check(
            "at most one RQ 0006 TX for the concurrent burst",
            n_0006 <= 1,
            detail=f"RQ 0006 TX count={n_0006}",
        )

        n_coalesced = count_since_marker("R146_PART_A_START", "Coalescing identical")
        print(f"  coalesced conversations: {n_coalesced}")

        # Every call must reach the 0404 fragment stage quickly — on the
        # buggy code only the resolved conversation's zone got there,
        # the rest stalled ~20 s apiece on dropped echoes.
        def distinct_0404_zones() -> int:
            out = grep_since_marker(
                "R146_PART_A_START",
                r"TX ->.*0404 007 [0-9A-F]{2}200008000100",
            )
            zones = set()
            for ln in out.splitlines():
                idx = ln.split("0404 007 ")[-1][:2]
                zones.add(idx)
            return len(zones)

        ctx.wait_for(
            lambda: distinct_0404_zones() >= n_zones,
            timeout=25,
            msg=f"for all {n_zones} zones to reach the 0404 stage",
        )
        n_0404 = distinct_0404_zones()
        ctx.check(
            "all zones reached the 0404 stage promptly",
            n_0404 >= n_zones,
            detail=f"distinct 0404 zones={n_0404} of {n_zones}",
        )

        n_echo_timeout = count_since_marker(
            "R146_PART_A_START", r"Echo timeout for RQ.*0006"
        )
        ctx.check(
            "no echo timeouts for RQ 0006",
            n_echo_timeout == 0,
            detail=f"echo timeouts={n_echo_timeout}",
        )

        # -----------------------------------------------------------------
        # Part B: concurrent identical send_packet (bypasses the
        # conversation manager → real byte-identical TXs).  Each TX's
        # echo must reach the protocol — on the buggy code the second
        # send stalled ~20 s per retry.
        # -----------------------------------------------------------------
        marker("R146_PART_B_START")

        def call_send_packet(_idx: int) -> float:
            t0 = time.monotonic()
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
                    timeout=60,
                    retries=1,
                )
            except RuntimeError:
                pass  # buggy code stalls past the HTTP timeout
            return time.monotonic() - t0

        n_raw = 3
        t_start = time.monotonic()
        ctx_copy = contextvars.copy_context()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_raw) as pool:
            raw_durations = list(
                pool.map(lambda i: ctx_copy.run(call_send_packet, i), range(n_raw))
            )
        raw_wall = time.monotonic() - t_start
        slowest = max(raw_durations)
        print(
            f"  {n_raw} identical send_packet calls done in "
            f"{raw_wall:.1f}s (slowest {slowest:.1f}s)"
        )

        ctx.check(
            "identical raw sends resolve promptly (no echo stall)",
            slowest < 15.0,
            detail=f"slowest send={slowest:.1f}s (buggy: ~20s+)",
        )

        n_3150_tx = count_since_marker("R146_PART_B_START", r"TX ->.*RQ --- .* 3150")
        ctx.check(
            "all identical raw frames were transmitted",
            n_3150_tx == n_raw,
            detail=f"RQ 3150 TX count={n_3150_tx} of {n_raw}",
        )

        # Every TX's echo must reach the protocol (Recv'd is_echo).
        # Poll — echo copies land a few ms after the calls return.
        # NB: pattern uses "Recv.d" — a literal apostrophe would break
        # the single-quoted grep inside docker exec.
        def echo_fwd_count() -> int:
            return count_since_marker("R146_PART_B_START", r"Recv.d: .*RQ --- .* 3150")

        ctx.wait_for(
            lambda: echo_fwd_count() >= n_raw,
            timeout=15,
            msg=f"for {n_raw} forwarded echoes",
        )
        n_echo_fwd = echo_fwd_count()
        ctx.check(
            "each identical TX's echo was forwarded upstream",
            n_echo_fwd >= n_raw,
            detail=f"forwarded echoes={n_echo_fwd} of {n_raw} TXs",
        )

        n_3150_timeout = count_since_marker(
            "R146_PART_B_START", r"Echo timeout for RQ.*3150"
        )
        ctx.check(
            "no echo timeouts for identical raw sends",
            n_3150_timeout == 0,
            detail=f"echo timeouts={n_3150_timeout}",
        )

        ctx.check("All issue-1336 checks passed", ctx.failed == failed_at_start)
