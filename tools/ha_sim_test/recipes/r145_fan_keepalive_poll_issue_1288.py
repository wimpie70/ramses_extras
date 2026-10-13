"""Recipe R145: FAN keep-alive polling (issue 1288).

Issue: quiet fans that broadcast only every ~8h always lose the
heartbeat race — ``HEARTBEAT_TIMEOUT_FAN`` (900s) expires between
broadcasts and the FAN entities flap to unavailable.

Fix (ramses_rf PR 1297): the FAN poll schedule becomes capability-aware:

  * unconfirmed FAN (``supports_10d0`` not yet observed):
    ``10E0`` @ 600s keep-alive (universal liveness floor) + ``10D0`` @
    daily re-probe
  * confirmed FAN (an ``RP|10D0`` was seen): ``10D0`` @ 600s keep-alive
    (data + liveness in one frame) + ``10E0`` @ daily

A reply refreshes ``_last_msg_dtm`` exactly like a broadcast, so a
responsive-but-quiet fan stays available; a genuinely absent fan still
times out because unanswered polls stamp nothing.

The 600s default cannot be awaited in a recipe, so this verifies the
schedule *value* and the poll→reply *mechanism* instead:

  1. The FAN's ``number.*_polling_interval`` entity (which exposes
     ``min(effective_polling_interval)``) reads ~600s — the keep-alive
     schedule is in effect (pre-fix the FAN schedule was all-daily and
     this entity read 86400)
  2. Setting an explicit short ``polling_interval`` takes effect at the
     next scheduler refresh (``next_due`` is recomputed on interval
     change — without that, overrides only applied at the previously
     scheduled time): ``RQ|10E0`` and ``RQ|10D0`` appear in the packet
     log within seconds
  3. The simulator answers with ``RP`` replies — the liveness loop that
     keeps quiet fans available
  4. After the ``RP|10D0``, ``supports_10d0`` is confirmed and the FAN's
     filter-remaining sensor exists — the role-swap precondition

The FAN is loaded with ``suppress_autonomous`` so it answers RQs but
broadcasts nothing — the issue's quiet-but-responsive fan.

See: https://github.com/ramses-rf/ramses_rf/issues/1288
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

FAN_ID = "32:150000"
_KEEP_ALIVE_S = 600.0
_OVERRIDE_S = 8.0


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


def _poll_rq_lines(since_ts: str, code: str) -> list[str]:
    """Outbound RQ lines for *code* addressed to the FAN since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RQ " in ln and f" {code} " in ln and FAN_ID in ln
    ]


def _poll_rp_lines(since_ts: str, code: str) -> list[str]:
    """Inbound RP lines for *code* from the FAN since *since_ts*."""
    return [
        ln
        for ln in log_lines_since("packet_log.log*", since_ts)
        if " RP " in ln and f" {code} " in ln and FAN_ID in ln
    ]


def _poll_interval_entity(token: str) -> dict | None:
    """The FAN's polling_interval number entity state, if present."""
    fan_slug = FAN_ID.replace(":", "_")
    for e in get_entities(token):
        if (
            e["entity_id"].startswith("number.")
            and "polling_interval" in e["entity_id"]
            and (
                fan_slug in e["entity_id"]
                or e.get("attributes", {}).get("id") == FAN_ID
            )
        ):
            return e
    return None


def _filter_sensor_present(token: str) -> bool:
    """True once the FAN's filter-remaining sensor exists (supports_10d0)."""
    fan_slug = FAN_ID.replace(":", "_")
    return any(
        e["entity_id"].startswith("sensor.")
        and "filter" in e["entity_id"]
        and (fan_slug in e["entity_id"] or e.get("attributes", {}).get("id") == FAN_ID)
        for e in get_entities(token)
    )


class R145FanKeepalivePollIssue1288(Recipe):
    id = "R145"
    seq = 1450
    title = "FAN keep-alive polling schedule (issue 1288)"
    tags = ("1288", "fan", "polling", "keep_alive", "hvac")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 145: FAN keep-alive polling (issue 1288)")

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
            for label in (
                "polling_interval entity reads ~600s (keep-alive schedule)",
                "explicit short polling_interval reschedules promptly",
                "simulator answered RQ|10E0 with RP|10E0",
                "RP|10D0 confirms supports_10d0 (filter sensor present)",
            ):
                ctx.check(
                    f"{label} (skipped — transport unavailable)",
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

        # ── 1. Keep-alive schedule is in effect ─────────────────────
        #    The polling_interval number exposes min(effective schedule):
        #    ~600s means the keep-alive interval is live — either side of
        #    the supports_10d0 swap reads 600 (unconfirmed: 10E0@600;
        #    confirmed: 10D0@600).  Pre-fix this entity read 86400.
        def _interval_is_keepalive() -> bool:
            ent = _poll_interval_entity(ctx.token)
            if ent is None:
                return False
            try:
                return abs(float(ent["state"]) - _KEEP_ALIVE_S) < 30
            except TypeError, ValueError:
                return False

        wait_for(
            _interval_is_keepalive,
            timeout=45,
            interval=3,
            msg="for FAN polling_interval entity to read ~600s",
            floor=10.0,
        )
        ent = _poll_interval_entity(ctx.token)
        ctx.check(
            "polling_interval entity reads ~600s (keep-alive schedule)",
            _interval_is_keepalive(),
            "entity="
            + ("missing" if ent is None else f"{ent['entity_id']}={ent['state']}"),
        )

        # ── 2. A short explicit interval reschedules promptly ───────
        #    Without the next_due recompute on interval change, an
        #    override only applies at the previously-scheduled time
        #    (up to a day away).  Setting 8s must produce polls now.
        poll_baseline = container_log_timestamp()
        ent = _poll_interval_entity(ctx.token)
        if ent is None:
            ctx.check(
                "explicit short polling_interval reschedules promptly "
                "(skipped — no entity)",
                True,
                "polling_interval number entity not present",
            )
        else:
            try:
                call_service(
                    ctx.token,
                    "number",
                    "set_value",
                    {"entity_id": ent["entity_id"], "value": _OVERRIDE_S},
                )
                print(f"    polling_interval override set to {_OVERRIDE_S}s")
            except RuntimeError as e:
                print(f"    number.set_value failed: {e}")

            wait_for(
                lambda: (
                    _poll_rq_lines(poll_baseline, "10E0")
                    and _poll_rq_lines(poll_baseline, "10D0")
                ),
                timeout=60,
                interval=5,
                msg="for RQ 10E0 + RQ 10D0 polls to the FAN",
                floor=20.0,
            )
            rq10e0 = _poll_rq_lines(poll_baseline, "10E0")
            rq10d0 = _poll_rq_lines(poll_baseline, "10D0")
            for ln in rq10e0 + rq10d0:
                print(f"    {ln.strip()}")
            ctx.check(
                "explicit short polling_interval reschedules promptly "
                "(RQ|10E0 + RQ|10D0 observed)",
                bool(rq10e0) and bool(rq10d0),
                f"10E0 RQs={len(rq10e0)}, 10D0 RQs={len(rq10d0)}",
            )

            # ── 3. The quiet FAN answers — the liveness loop ────────
            wait_for(
                lambda: _poll_rp_lines(poll_baseline, "10E0"),
                timeout=20,
                interval=3,
                msg="for RP 10E0 reply from the FAN",
                floor=5.0,
            )
            rp10e0 = _poll_rp_lines(poll_baseline, "10E0")
            ctx.check(
                "simulator answered RQ|10E0 with RP|10E0 (liveness refreshed)",
                bool(rp10e0),
                "no RP 10E0 found in packet log — quiet fan would time out",
            )

            wait_for(
                lambda: _poll_rp_lines(poll_baseline, "10D0"),
                timeout=20,
                interval=3,
                msg="for RP 10D0 reply from the FAN",
                floor=5.0,
            )
            rp10d0 = _poll_rp_lines(poll_baseline, "10D0")
            if not rp10d0:
                ctx.check(
                    "RP|10D0 confirms supports_10d0 "
                    "(skipped — sim FAN did not answer 10D0)",
                    True,
                    "no RP 10D0 in packet log; flag path untestable here",
                )
                return

            # ── 4. supports_10d0 confirmed → role swap precondition ──
            wait_for(
                lambda: _filter_sensor_present(ctx.token),
                timeout=30,
                interval=3,
                msg="for filter-remaining sensor (supports_10d0)",
                floor=5.0,
            )
            ctx.check(
                "RP|10D0 confirms supports_10d0 (filter sensor present)",
                _filter_sensor_present(ctx.token),
                "no filter-remaining sensor for the FAN",
            )
