"""Recipe R148: early first poll after (re)start (issue 1335).

Issue: on 0.60.10 every polling task was created with
``next_due = now + interval``, so after each restart hourly codes stayed
silent for an hour and daily codes for a day.  Debugging restarts never
reached the first poll, so polling looked dead — and a
``polling_interval`` override did not help because the due time was
stale as well (the latter half was fixed by ramses_rf PR 1297).

Fix (ramses_rf PR 1300): newly-registered tasks get a first due of
``min(interval, INTERVAL_STARTUP_POLL = 120s)`` — the same
early-hydration approach ``2E04`` already uses.

This recipe cannot wait out a real interval, so it verifies the
observable boundary: after a ramses_cc reload (fresh gateway → fresh
PollingManager → fresh task registration), a quiet FAN's first
``RQ|10E0`` keep-alive poll must hit the wire well inside the
pre-fix interval (600 s) — it is expected at ~120 s:

  1. A FAN profile with ``suppress_autonomous`` is loaded and ramses_cc
     reloaded; the packet-log baseline is taken once the transport is
     back up
  2. ``RQ|10E0`` to the FAN appears within ~200 s (pre-fix: nothing
     until +600 s)
  3. The simulator answers with ``RP|10E0`` — the poll→reply loop works
     end-to-end right after restart

The FAN answers RQs but broadcasts nothing — the same quiet device as
R145.

See: https://github.com/ramses-rf/ramses_cc/issues/1335
"""

from __future__ import annotations

import time

import yaml

from ..base import Recipe, RecipeContext
from ..helpers import (
    container_log_timestamp,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)

FAN_ID = "32:150000"
# First poll must land well under the pre-fix keep-alive interval
# (600 s).  Registration lags transport-ready by a few seconds, so allow
# 240 s — a poll at 600 s+ would mean the fix is absent.
_STARTUP_WINDOW_S = 240


def _profile_yaml(hgi: str) -> str:
    """Minimal HGI+FAN profile; the FAN answers RQs but emits nothing."""
    return yaml.dump(
        {
            "known_list": {
                hgi: {"class": "HGI"},
                FAN_ID: {"class": "FAN", "suppress_autonomous": True},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": {FAN_ID: {"_class": "FAN"}},
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _rq_lines(since_ts: str, code: str) -> list[str]:
    """Outbound RQ lines for *code* addressed to the FAN since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RQ " in ln and f" {code} " in ln and FAN_ID in ln
    ]


def _rp_lines(since_ts: str, code: str) -> list[str]:
    """Inbound RP lines for *code* from the FAN since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RP " in ln and f" {code} " in ln and FAN_ID in ln
    ]


class R148StartupFirstPollIssue1335(Recipe):
    id = "R148"
    seq = 1480
    title = "Early first poll after restart (issue 1335)"
    tags = ("1335", "polling", "startup", "fan")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 148: early first poll after restart (issue 1335)")

        hgi = ctx.instance.hgi_id

        print(f"  Loading minimal FAN profile (FAN {FAN_ID}, quiet emitters)...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(hgi),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        if not wait_for_transport_ready(timeout=30):
            ctx.check(
                "first keep-alive RQ|10E0 within startup window "
                "(skipped — transport unavailable)",
                True,
                "ramses_rf transport did not reconnect after reload",
            )
            return

        # Activate the FAN so the ScenarioEngine answers its RQs.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": FAN_ID,
                },
            )
            print(f"    FAN {FAN_ID} activated (RQ answering, no emitters)")
        except RuntimeError:
            pass

        baseline = container_log_timestamp()

        # ── 1. First keep-alive poll lands inside the startup window ─
        #    Wall-clock wait — wait_for() would scale the timeout down
        #    (~8%) and the whole point of this check is real elapsed
        #    time: the first poll must arrive ~120 s after registration.
        print(
            f"  Waiting up to {_STARTUP_WINDOW_S}s (unscaled, real time) "
            f"for first RQ 10E0 to the FAN...",
            end="",
            flush=True,
        )
        deadline = time.monotonic() + _STARTUP_WINDOW_S
        rq10e0: list[str] = []
        while time.monotonic() < deadline:
            rq10e0 = _rq_lines(baseline, "10E0")
            if rq10e0:
                elapsed = _STARTUP_WINDOW_S - (deadline - time.monotonic())
                print(f" done ({int(elapsed)}s)")
                break
            time.sleep(10)
        else:
            print(f" TIMEOUT ({_STARTUP_WINDOW_S}s)")
        for ln in rq10e0:
            print(f"    {ln.strip()}")
        ctx.check(
            "first keep-alive RQ|10E0 within startup window "
            f"(< {_STARTUP_WINDOW_S}s, pre-fix waited +600s)",
            bool(rq10e0),
            f"RQ 10E0 lines since reload: {len(rq10e0)}",
        )

        # ── 2. The quiet FAN answers — poll→reply works post-restart ─
        if not rq10e0:
            ctx.check(
                "simulator answered first RQ|10E0 with RP|10E0 "
                "(skipped — no RQ observed)",
                True,
                "no RQ 10E0 in packet log",
            )
            return

        wait_for(
            lambda: _rp_lines(baseline, "10E0"),
            timeout=20,
            interval=3,
            msg="for RP 10E0 reply from the FAN",
            floor=5.0,
        )
        rp10e0 = _rp_lines(baseline, "10E0")
        ctx.check(
            "simulator answered first RQ|10E0 with RP|10E0",
            bool(rp10e0),
            "no RP 10E0 found in packet log",
        )
