"""Recipe R143: quiet CO2 sensor at 32: reclassified from FAN (issue 1287).

A ``32:`` device is classified FAN by prefix (unambiguous — a real FAN
sends 22F1 which VC-maps to REM, so the prefix wins).  But standalone
CO2 sensors live at ``32:`` addresses too, and for them the prefix pin
was absolute: ``_classify`` never contradicted itself, the topology
handler's FAN→CO2 path needs non-FAN evidence a pure sensor never
sends, and ``confidence`` still upgraded on unrelated topology
evidence — so ``schema=CO2, discovery=FAN`` mismatch notifications
could never resolve.

The fix distinguishes on both directions of traffic — a FAN sends
different packets than a CO2 sensor, and *receives* different ones.
In this recipe the 32: devices are declared FAN (so their device
objects are FAN-typed — a declaration of CO2 needs no reclassification)
and the schema is silently wrong, as in the issue reporter's setup.

- sent: a pure sensor broadcasts I 1298 and shows no FAN signatures
  (I 31D9, I/RP 31DA, RP 2411)
- received: a real FAN is the target of directed fan-domain requests
  (RQ 31DA, RQ 2411, I 22F1) from bound remotes and displays — a
  standalone CO2 sensor receives none.  Gateway-originated probes
  (18: src) don't count.

This recipe verifies:

  - QUIET_CO2 (FAN-typed 32:, only broadcasts I 1298) is reclassified
    to CO2 — Rule_HVAC_Quiet_1298_FAN_to_CO2 fires
  - PROBE_CO2 likewise, even after an HGI RQ 2411 probe — gateway
    probing is not fan-request evidence
  - POLLED_FAN (receives RQ 2411 from a REM) stays FAN — receive
    direction evidence proves it services the fan domain
  - REAL_FAN (broadcasts I 31D9 + I 1298) stays FAN — FAN signature
    proves integrated-CO2-sensor behaviour, not a standalone sensor

See: ramses_rf issue 1287, ramses_rf PR 1292, ramses_cc PR 1333
"""

from __future__ import annotations

from copy import deepcopy

import yaml

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    container_log_timestamp,
    get_schema_retry,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl

# Issue 1287's exact devices: schema-declared CO2 sensors at 32: that
# only ever broadcast I 1298.
QUIET_CO2 = "32:090174"
PROBE_CO2 = "32:092927"
# A FAN-typed 32: device that a bound REM actually polls — receive
# direction proves it services the fan domain.
POLLED_FAN = "32:090175"
POLLING_REM = "37:190091"
# A foreign HGI that probes PROBE_CO2 — gateway-originated requests
# must not count as fan-request evidence.
HGI_PROBE = "18:099999"

QUIET_CO2_RULE = "Rule_HVAC_Quiet_1298_FAN_to_CO2"


def _profile_yaml() -> str:
    """Build a profile with FAN-typed 32: devices and a polling REM."""
    known_list = get_mixed_kl()
    # Quiet sensors must be fully silent in the simulator — a real
    # standalone CO2 sensor never replies to RQ 2411, and a simulated
    # RP or the FAN-activation prime (RQ 2411/3E from a REM) would
    # count as FAN evidence and rightly block reclassification.
    # suppress_responses silences both the ScenarioEngine reply and
    # (by deferral) the legacy ResponseEngine reply; suppress_autonomous
    # stops the periodic emitter and startup burst.
    for dev_id in (QUIET_CO2, PROBE_CO2):
        known_list[dev_id] = {
            "class": "FAN",
            "suppress_autonomous": True,
            "suppress_responses": True,
        }
    known_list[POLLED_FAN] = {"class": "FAN"}
    known_list[POLLING_REM] = {"class": "REM"}
    known_list[HGI_PROBE] = {"class": "HGI"}

    schema = deepcopy(MIXED_SCHEMA)
    schema[FAN] = {
        **schema[FAN],
        "remotes": [*schema[FAN]["remotes"], POLLING_REM],
    }
    # The devices are declared FAN everywhere — that is the case the
    # reclassification exists for: a 32: device typed FAN whose traffic
    # is pure CO2 sensor.  (Declaring _class=CO2 would create CO2-typed
    # device objects — no reclassification is needed then.)
    for dev_id in (QUIET_CO2, PROBE_CO2, POLLED_FAN):
        schema[dev_id] = {"_class": "FAN"}
    schema[POLLING_REM] = {"_class": "REM", "_bound": FAN}
    schema[HGI_PROBE] = {"_class": "HGI"}
    return yaml.dump(
        {
            "known_list": known_list,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _inject(
    ctx: RecipeContext,
    source_id: str,
    code: str,
    verb: str = "I",
    dst: str = "--:------",
) -> None:
    """Inject a packet from source_id."""
    payload = {"1298": "0001DB", "31D9": "000031"}.get(code, "000031")
    call_service(
        ctx.token,
        "ramses_extras",
        "device_simulator_inject_message",
        {
            "source_id": source_id,
            "dst": dst,
            "code": code,
            "payload": payload,
            "verb": verb,
        },
    )


def _has_event_since(since_ts: str, device_id: str, rule: str) -> bool:
    return any(
        device_id in line and rule in line
        for line in log_lines_since("home-assistant.log*", since_ts)
    )


class R143QuietCo2Sensor32FanToCo2(Recipe):
    id = "R143"
    seq = 1430
    title = "Quiet CO2 sensor at 32: reclassified from FAN (issue 1287)"
    tags = ("co2", "fan", "1298", "2411", "discovery", "issue1287")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify direction-aware FAN-vs-CO2 disambiguation at 32:."""
        ctx.log_section("Recipe 143: quiet CO2 sensor FAN->CO2 (issue 1287)")

        await load_profile_yaml(ctx.token, _profile_yaml(), speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for issue-1287 profile reload")
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass

        wait_for(
            lambda: (
                QUIET_CO2 in get_schema_retry()
                and PROBE_CO2 in get_schema_retry()
                and POLLED_FAN in get_schema_retry()
            ),
            timeout=30,
            interval=2,
            msg="for 32: CO2 candidates in schema",
            floor=10.0,
        )

        baseline = container_log_timestamp()

        # --- Seed receive-direction evidence -------------------------
        # An HGI probes PROBE_CO2 (gateway-originated — must NOT count)
        _inject(ctx, HGI_PROBE, "2411", verb="RQ", dst=PROBE_CO2)
        # A bound REM polls POLLED_FAN (real fan-domain request)
        _inject(ctx, POLLING_REM, "2411", verb="RQ", dst=POLLED_FAN)
        ctx.wait(3, "for probe/request packets to be evaluated", floor=2.0)

        # --- REAL_FAN shows a FAN signature, then broadcasts CO2 -----
        _inject(ctx, FAN, "31D9", verb="I")
        _inject(ctx, FAN, "31D9", verb="I")

        # --- Broadcasts: 4x I 1298 per device (threshold is 3) -------
        for _ in range(4):
            _inject(ctx, QUIET_CO2, "1298", verb="I")
            _inject(ctx, PROBE_CO2, "1298", verb="I")
            _inject(ctx, POLLED_FAN, "1298", verb="I")
            _inject(ctx, FAN, "1298", verb="I")
            ctx.wait(2, "for I 1298 broadcasts to be evaluated", floor=1.0)

        # --- Check 1: pure sensor reclassified FAN -> CO2 ------------
        quiet_ok = wait_for(
            lambda: _has_event_since(baseline, QUIET_CO2, QUIET_CO2_RULE),
            timeout=30,
            interval=2,
            msg=f"for {QUIET_CO2_RULE} event on {QUIET_CO2}",
            floor=10.0,
        )
        ctx.check(
            "FAN-typed 32: device broadcasting only I 1298 reclassified to CO2",
            quiet_ok,
            f"device_id={QUIET_CO2}",
        )

        # --- Check 2: HGI probe does not block reclassification ------
        probe_ok = wait_for(
            lambda: _has_event_since(baseline, PROBE_CO2, QUIET_CO2_RULE),
            timeout=30,
            interval=2,
            msg=f"for {QUIET_CO2_RULE} event on {PROBE_CO2}",
            floor=5.0,
        )
        ctx.check(
            "HGI RQ 2411 probe is not fan-request evidence (still CO2)",
            probe_ok,
            f"device_id={PROBE_CO2}",
        )

        # --- Check 3: polled device stays FAN (receive direction) ----
        ctx.check(
            "32: device receiving REM's RQ 2411 is NOT reclassified",
            not _has_event_since(baseline, POLLED_FAN, QUIET_CO2_RULE),
            f"device_id={POLLED_FAN}",
        )

        # --- Check 4: FAN with integrated CO2 stays FAN --------------
        ctx.check(
            "FAN broadcasting 31D9 + I 1298 is NOT reclassified",
            not _has_event_since(baseline, FAN, QUIET_CO2_RULE),
            f"device_id={FAN}",
        )
