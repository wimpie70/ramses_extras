"""Recipe R162: 1260 DHW-temp discovery reactor request loop (issue 1371).

The pre-0.60 DHW-sensor discovery reactor in ramses_rf sends ``RQ 1260``
to ``src_dev.ctl`` for every ``1260`` message whose source has a
controller — including ``RP`` replies and including the controller
itself.  When the controller is configured as a zone's sensor, its
``.ctl`` resolves to itself, so each ``RP 1260`` reply triggers
another ``RQ 1260``: a request/reply loop that saturates the RF
channel (~44 ms per iteration, thousands of packets per burst).

The fix restricts the reactor to ``I`` broadcasts and skips sources
whose ``ctl`` is itself.

This recipe loads a profile where the CTL is zone 03's sensor
(``ctl.ctl is ctl``), then counts ``RQ 1260`` frames in the packet
log:

* ``I 1260`` from the CS92A DHW sensor → exactly one ``RQ 1260``
  (discovery still works).
* ``RP 1260`` from the controller → zero ``RQ 1260`` (self-guard).
* ``RP 1260`` from the DHW sensor → zero ``RQ 1260`` (I-only guard).

See: https://github.com/ramses-rf/ramses_rf/issues/1371
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    call_service,
    docker_exec_python,
    get_current_instance,
    load_profile_yaml,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)


def _profile_yaml() -> str:
    """Build a profile with the CTL configured as zone 03's sensor."""
    from ..const import HGI
    from ..profile import _build_yaml

    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        DHW: {"class": "DHW"},
        "04:150003": {"class": "TRV"},
    }
    schema = {
        CTL: {
            "stored_hotwater": {"sensor": DHW},
            "zones": {
                "03": {"sensor": CTL, "actuators": ["04:150003"]},
            },
        }
    }
    return _build_yaml(kl, schema)


def _count_rq_1260() -> int:
    """Return the total RQ 1260 frame count across the packet logs.

    Callers compare counts before/after an injection (delta), which is
    immune to packet-log timestamp format differences.
    """
    result = docker_exec_python(
        """
import json
from pathlib import Path
count = 0
for root in ("/config", "/config/ramses_rf_logs"):
    for p in Path(root).glob("packet_log.log*"):
        try:
            count += sum(
                1
                for ln in p.read_text().splitlines()
                if " RQ " in ln and " 1260 " in ln
            )
        except OSError:
            pass
print(json.dumps({"count": count}))
"""
    )
    return int(result.get("count", 0))


class R162Dhw1260RqLoopIssue1371(Recipe):
    id = "R162"
    seq = 1620
    title = "1260 DHW discovery reactor request loop (issue 1371)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 162: 1260 discovery reactor request loop (issue 1371)")

        # 1. Load a profile where the CTL is zone 03's sensor — the
        #    configuration that makes ctl.ctl resolve to itself and turns
        #    each RP 1260 reply into a new RQ 1260.
        print("  Loading profile (CTL as zone-03 sensor + DHW sensor)...")
        await load_profile_yaml(
            ctx.token,
            _profile_yaml(),
            speed=0.01,
            preload_schema=True,
            reload_ramses=True,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        wait_for_schema_populated(min_keys=3, timeout=20)

        # Silence the DHW sensor's periodic emitter so its own 1260
        # broadcasts cannot pollute the RQ counts.
        print(f"  Silencing DHW {DHW} periodic emitter...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/silence_devices",
                    "device_ids": [DHW],
                    "set_suppress": False,
                },
            )
        except RuntimeError as e:
            print(f"    Silence failed (continuing): {str(e)[:80]}")
        ctx.wait(2, "for emitter cancellation to take effect")

        hgi = get_current_instance().hgi_id

        def _inject(src: str, verb: str, dst: str | None = None) -> None:
            data: dict = {
                "source_id": src,
                "code": "1260",
                "payload": "0015A0",  # 55.04 C
                "verb": verb,
            }
            if dst:
                data["dst"] = dst
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                data,
            )

        # 2. Baseline behaviour: I 1260 from the DHW sensor must still
        #    trigger the RQ 1260 to the controller (each send logs a
        #    TX line plus an MQTT-echo line, so assert on a delta).
        print(f"  Injecting I 1260 from DHW sensor {DHW}...")
        n0 = _count_rq_1260()
        _inject(DHW, "I")
        ctx.wait(6, "for 1260 reactor + RQ to land", floor=5.0)
        rq_after_i = _count_rq_1260() - n0
        ctx.check(
            "DHW sensor I 1260 triggers RQ 1260",
            rq_after_i >= 1,
            f"counted {rq_after_i} RQ 1260 frames after I broadcast",
        )

        # 3. The bug: RP 1260 from the controller (whose .ctl is itself)
        #    must NOT trigger another RQ 1260.
        print(f"  Injecting RP 1260 from CTL {CTL} (self-controller)...")
        n0 = _count_rq_1260()
        _inject(CTL, "RP", dst=hgi)
        ctx.wait(6, "for any reactor RQ after CTL RP", floor=5.0)
        rq_after_ctl_rp = _count_rq_1260() - n0
        ctx.check(
            "controller RP 1260 does not re-trigger RQ 1260",
            rq_after_ctl_rp == 0,
            f"counted {rq_after_ctl_rp} RQ 1260 frames after CTL RP",
        )

        # 4. An RP from the DHW sensor itself (e.g. answering a poll)
        #    must not trigger the reactor either — only I broadcasts.
        print(f"  Injecting RP 1260 from DHW sensor {DHW}...")
        n0 = _count_rq_1260()
        _inject(DHW, "RP", dst=hgi)
        ctx.wait(6, "for any reactor RQ after DHW RP", floor=5.0)
        rq_after_dhw_rp = _count_rq_1260() - n0
        ctx.check(
            "DHW sensor RP 1260 does not trigger RQ 1260",
            rq_after_dhw_rp == 0,
            f"counted {rq_after_dhw_rp} RQ 1260 frames after sensor RP",
        )

        # 5. Sanity: a second sensor broadcast still yields the query.
        print(f"  Injecting second I 1260 from DHW sensor {DHW}...")
        n0 = _count_rq_1260()
        _inject(DHW, "I")
        ctx.wait(6, "for second reactor RQ", floor=5.0)
        rq_after_i2 = _count_rq_1260() - n0
        ctx.check(
            "reactor still fires per sensor broadcast",
            rq_after_i2 >= 1,
            f"counted {rq_after_i2} RQ 1260 frames after second I",
        )
