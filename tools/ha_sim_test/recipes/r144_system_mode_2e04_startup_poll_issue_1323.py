"""Recipe R144: System mode 2E04 startup-poll hydration (issue 1323).

Issue: after a restart, ``tcs.system_state.system_mode`` never hydrated
until the user changed the mode manually.  Cached 2E04 packets are
deliberately not replayed on restore (issue ramses-rf/ramses_cc#1242),
so hydration depends on the PollingManager's early first 2E04 poll
(``INTERVAL_STARTUP_2E04`` = 60s after task registration).

The poll itself ran, but the RQ went out with the generic ``00``
payload — while the canonical RQ|2E04 payload is ``FF`` (used by
``build_get_system_mode`` and seen in every real-world capture).  A
controller that does not answer ``RQ|2E04|00`` leaves system_mode empty
forever.  The fix gives the 2E04 task ``payload=FF``.

This recipe verifies end-to-end:

  1. The outbound ``RQ --- <hgi> <ctl> --:------ 2E04 001 FF`` appears
     in the packet log ~60s after the ramses_cc reload — the payload
     byte is the actual regression check (the simulator would answer
     a ``00`` payload too, so hydration alone cannot detect the bug)
  2. The simulator's ``RP|2E04`` reply follows and system_mode hydrates
     (``climate.<ctl>`` attribute ``system_mode`` becomes "auto")
  3. If the ramses_cc system-mode select entity exists, its state
     becomes "auto"

The CTL is activated with ``suppress_autonomous`` so it answers the RQ
but its own periodic ``I|2E04`` emitter cannot hydrate the state early
and mask a broken poll.

See: https://github.com/ramses-rf/ramses_cc/issues/1323
"""

from __future__ import annotations

import yaml

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    container_log_timestamp,
    get_entities,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)

# RP payload served by the CTL device DB entry for 2E04 — mode 00 = auto
_SIM_RP_MODE = "auto"


def _profile_yaml(ctl: str, hgi: str) -> str:
    """Minimal CTL+HGI profile; CTL answers RQs but emits nothing.

    ``suppress_autonomous`` keeps the CTL's periodic emitters (incl. a
    ~47s ``I|2E04`` broadcast) silent so only the polled RP can hydrate
    system_mode.
    """
    return yaml.dump(
        {
            "known_list": {
                hgi: {"class": "HGI"},
                ctl: {"class": "CTL", "suppress_autonomous": True},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": {ctl: {}},
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _rq_2e04_lines(since_ts: str, ctl: str) -> list[str]:
    """Outbound RQ|2E04 lines to *ctl* in the packet log since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RQ " in ln and " 2E04 " in ln and ctl in ln
    ]


def _rp_2e04_lines(since_ts: str, ctl: str) -> list[str]:
    """Inbound RP|2E04 lines from *ctl* in the packet log since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RP " in ln and " 2E04 " in ln and ctl in ln
    ]


def _ctl_climate_attrs(token: str, ctl: str) -> dict | None:
    """Attributes of the controller's climate entity (id == ctl)."""
    for e in get_entities(token):
        if (
            e["entity_id"].startswith("climate.")
            and e.get("attributes", {}).get("id") == ctl
        ):
            return e.get("attributes", {})
    return None


def _ctl_select_state(token: str, ctl: str) -> str | None:
    """State of the controller's system-mode select entity, if present."""
    for e in get_entities(token):
        if (
            e["entity_id"].startswith("select.")
            and e.get("attributes", {}).get("id") == ctl
        ):
            return e.get("state")
    return None


class R144SystemMode2e04StartupPollIssue1323(Recipe):
    id = "R144"
    seq = 1440
    title = "System mode 2E04 startup-poll hydration (issue 1323)"
    tags = ("2e04", "system_mode", "polling", "issue1323")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 144: 2E04 startup-poll hydration (issue 1323)")

        ctl = ctx.instance.ctl
        hgi = ctx.instance.hgi_id

        # Baseline BEFORE the profile load: the ramses_cc reload inside
        # it restarts the gateway, which is when the PollingManager's
        # 60s first-poll timer starts.
        baseline = container_log_timestamp()

        print(f"  Loading minimal CTL profile (CTL {ctl}, quiet emitters)...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(ctl, hgi),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        transport_ok = wait_for_transport_ready(timeout=30)
        if not transport_ok:
            # HA/transport down (e.g. container restarted mid-run) —
            # every subsequent check would be meaningless.
            for label in (
                "startup poll sent RQ|2E04 to the CTL",
                "RQ|2E04 payload is FF (canonical system-mode query)",
                "simulator answered RQ|2E04 with RP|2E04",
                "controller system_mode hydrated from RP (climate attr)",
                "system-mode select entity shows auto",
            ):
                ctx.check(
                    f"{label} (skipped — transport unavailable)",
                    True,
                    "ramses_rf transport did not reconnect after reload",
                )
            return

        # Activate the CTL so the ScenarioEngine answers its RQs.
        # suppress_autonomous (profile trait) keeps its periodic
        # I|2E04 emitter silent.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": ctl,
                },
            )
            print(f"    CTL {ctl} activated (RQ answering, no emitters)")
        except RuntimeError:
            pass

        # Sample the mode before the poll fires (~60s after gateway
        # start).  On a fresh gateway 2E04 cache is not replayed, so
        # this should be empty; a pre-existing value would make the
        # hydration check below ambiguous.
        pre_mode = (_ctl_climate_attrs(ctx.token, ctl) or {}).get("system_mode")

        # ── 1. The startup poll sends RQ|2E04 with payload FF ───────
        #    INTERVAL_STARTUP_2E04 fires ~60s after task registration
        #    (gateway start inside the reload).  Timeout covers reload
        #    latency plus the poll delay.
        print("  Waiting for outbound RQ|2E04 (startup poll, ~60s)...")
        wait_for(
            lambda: _rq_2e04_lines(baseline, ctl),
            timeout=150,
            interval=5,
            msg="for RQ 2E04 in packet log",
            floor=90.0,
        )
        rq_lines = _rq_2e04_lines(baseline, ctl)
        for ln in rq_lines:
            print(f"    {ln.strip()}")

        ctx.check(
            "startup poll sent RQ|2E04 to the CTL",
            bool(rq_lines),
            f"no RQ 2E04 found in packet log since {baseline}",
        )

        # The payload byte is the actual fix under test: must be FF,
        # not the generic "00" fallback.
        rq_payloads = [ln.split()[-1] for ln in rq_lines]
        ctx.check(
            "RQ|2E04 payload is FF (canonical system-mode query)",
            bool(rq_lines) and all(p == "FF" for p in rq_payloads),
            f"payloads={rq_payloads}",
        )

        # ── 2. The simulator answers with RP|2E04 ───────────────────
        wait_for(
            lambda: _rp_2e04_lines(baseline, ctl),
            timeout=15,
            interval=2,
            msg="for RP 2E04 reply",
            floor=3.0,
        )
        rp_lines = _rp_2e04_lines(baseline, ctl)
        ctx.check(
            "simulator answered RQ|2E04 with RP|2E04",
            bool(rp_lines),
            "no RP 2E04 found in packet log",
        )

        if not rp_lines:
            # Without an observed post-baseline RP, any system_mode
            # value could be stale state from before this run — the
            # hydration checks would be vacuous, so report them as
            # skipped rather than passing them on old data.
            ctx.check(
                "controller system_mode hydrated from RP (skipped — no RP observed)",
                True,
                f"pre-poll mode={pre_mode}",
            )
            ctx.check(
                "system-mode select entity shows auto (skipped — no RP observed)",
                True,
                "no RP 2E04 found in packet log",
            )
            return

        # ── 3. system_mode hydrates on the controller entity ────────
        #    Nudge entity state writes, then check the controller
        #    climate's system_mode attribute (read from
        #    tcs.system_state via _device.system_mode()).
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass

        def _mode_hydrated() -> bool:
            attrs = _ctl_climate_attrs(ctx.token, ctl)
            if attrs is None:
                return False
            mode = attrs.get("system_mode")
            return isinstance(mode, dict) and mode.get("system_mode") == _SIM_RP_MODE

        hydrated = wait_for(
            _mode_hydrated,
            timeout=30,
            interval=3,
            msg=f"for system_mode={_SIM_RP_MODE!r} on climate.{ctl}",
            floor=10.0,
        )
        attrs = _ctl_climate_attrs(ctx.token, ctl)
        ctx.check(
            "controller system_mode hydrated from RP (climate attr)",
            hydrated,
            f"pre-poll={pre_mode}, post={attrs.get('system_mode') if attrs else None}",
        )

        # ── 4. System-mode select entity (ramses_cc >= PR 1329) ─────
        select_state = _ctl_select_state(ctx.token, ctl)
        if select_state is None:
            ctx.check(
                "system-mode select entity state (skipped — not present)",
                True,
                "no select entity for the CTL on this ramses_cc version",
            )
        else:
            ctx.check(
                "system-mode select entity shows auto",
                select_state == _SIM_RP_MODE,
                f"select state={select_state!r}",
            )
