"""Recipe R158: zone display glitches on reset + TRV local OFF (issue 1381).

Reproduces https://github.com/ramses-rf/ramses_cc/issues/1381:

- ``reset_zone_mode`` sends ``W 2349`` with setpoint 0x7FFF (None); the
  command echo used to be projected onto the zone, blanking its setpoint —
  the climate entity then showed ``unknown`` until the next coordinator
  heartbeat because zone entities never received per-packet signals.
- A TRV reporting a local OFF sends ``2309`` with 0x7EFF, which decodes to
  setpoint ``False``; it overwrote the controller-authoritative setpoint,
  rendering the zone as ``off`` with a 0 °C target.

Fix layers being verified end-to-end:

1. ``ramses_rf``: command echoes (RQ/W) are not routed to zones, and bool
   setpoint sentinels never overwrite a zone's setpoint read-models.
2. ``ramses_cc``: packets carrying a ``zone_index`` now also dispatch
   ``SIGNAL_UPDATE_<tcs.id>_<zone_index>`` so zone entities refresh in
   real time instead of waiting up to one scan interval (60 s).
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    call_service,
    get_entities,
    load_profile_yaml,
    wait_for_transport_ready,
)
from ..profile import _build_yaml

_ZONE = "03"
_ZONE_ID = f"{CTL}_{_ZONE}"  # virtual zone id -> "01:150000_03"

# 2349 payloads: idx(1) + setpoint(2) + mode(1) + until(3)
_PKT_2349_16C = "03064000FFFFFF"  # zone 03, 16.0 C, follow_schedule
_PKT_2349_RESET_ECHO = "037FFF00FFFFFF"  # reset_zone_mode echo (setpoint None)
_PKT_2309_16C = "030640"  # zone 03, 16.0 C (CTL sync element)
_PKT_2309_TRV_OFF = "037EFF"  # zone 03, TRV local OFF sentinel


def _profile_yaml() -> str:
    """Profile: CTL + zone 03 whose actuator is the TRV."""
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        TRV: {"class": "TRV"},
    }
    schema = {CTL: {"zones": {_ZONE: {"actuators": [TRV]}}}}
    return _build_yaml(kl, schema)


def _zone_state(token: str) -> tuple[str | None, float | None]:
    """Return (hvac state, target temperature) of the zone climate entity."""
    needle = _ZONE_ID.replace(":", "_")
    for s in get_entities(token):
        if s["entity_id"].startswith("climate.") and needle in s["entity_id"]:
            return s.get("state"), (s.get("attributes") or {}).get("temperature")
    return None, None


class R158ZoneDisplayGlitchIssue1381(Recipe):
    id = "R158"
    seq = 1580
    title = "Zone display glitches on reset + TRV local OFF (issue 1381)"

    def _inject(
        self,
        ctx: RecipeContext,
        source_id: str,
        dst: str,
        code: str,
        payload: str,
        verb: str = "I",
    ) -> None:
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

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 158: zone display glitches (issue 1381)")

        # 1. Minimal profile: CTL + zone 03 with a TRV actuator.
        print("  Loading profile (CTL + zone 03 + TRV actuator)...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            ctx.check("profile loaded", False, detail=str(e)[:200])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        # 2. Hydrate zone 03 via the controller's own broadcasts.
        print("  Hydrating zone 03 via CTL 2349/2309 broadcasts...")
        self._inject(ctx, CTL, "--:------", "2349", _PKT_2349_16C)
        self._inject(ctx, CTL, "--:------", "2309", _PKT_2309_16C)

        hydrated = ctx.wait_for(
            lambda: _zone_state(ctx.token)[0] in ("heat", "auto"),
            timeout=20,
            interval=0.5,
            msg="for zone 03 climate entity to show heat",
        )
        state, target = _zone_state(ctx.token)
        ctx.check(
            "zone entity appears and hydrates on packets (not heartbeat)",
            hydrated,
            f"state={state} target={target}",
        )
        if not hydrated:
            return
        ctx.check(
            "zone target temperature is 16.0",
            target == 16.0,
            f"target={target}",
        )

        # 3. Symptom 1a: the W 2349 reset echo must not blank the zone.
        #    Pre-fix, routing the echo wrote setpoint None into the zone —
        #    with per-packet signalling the entity would now render that
        #    as `unknown` immediately, so a stable state here proves the
        #    echo is no longer projected.
        print("  Injecting W 2349 reset echo (setpoint 7FFF)...")
        self._inject(ctx, HGI, CTL, "2349", _PKT_2349_RESET_ECHO, verb="W")
        ctx.wait(3, "for the echo to be processed")
        state, target = _zone_state(ctx.token)
        ctx.check(
            "reset echo does not blank the zone (no 'unknown')",
            state not in (None, "unknown", "unavailable"),
            f"state={state} target={target}",
        )

        # 3b. The controller's I 2349 reply must refresh the zone quickly.
        print("  Injecting CTL I 2349 reply (16.0 C)...")
        self._inject(ctx, CTL, HGI, "2349", _PKT_2349_16C)
        restored = ctx.wait_for(
            lambda: _zone_state(ctx.token)[0] == "heat",
            timeout=15,
            interval=0.5,
            msg="for zone to show heat after CTL reply",
        )
        state, target = _zone_state(ctx.token)
        ctx.check(
            "zone refresh after CTL reply is packet-paced, not heartbeat",
            restored,
            f"state={state} target={target}",
        )

        # 4. Symptom 2: a TRV local OFF (0x7EFF) must not flip the zone to
        #    off / 0 C — the sentinel is not a °C setpoint.
        print("  Injecting TRV I 2309 local OFF (7EFF)...")
        self._inject(ctx, TRV, CTL, "2309", _PKT_2309_TRV_OFF)
        ctx.wait(3, "for the TRV report to be processed")
        state, target = _zone_state(ctx.token)
        ctx.check(
            "TRV local OFF does not flip zone to 'off'",
            state not in (None, "off", "unknown", "unavailable"),
            f"state={state} target={target}",
        )
        ctx.check(
            "TRV local OFF does not set a 0 C target",
            target == 16.0,
            f"target={target}",
        )

        # 5. The controller's authoritative sync keeps the zone at heat.
        print("  Injecting CTL I 2309 sync (16.0 C)...")
        self._inject(ctx, CTL, "--:------", "2309", _PKT_2309_16C)
        settled = ctx.wait_for(
            lambda: _zone_state(ctx.token) == ("heat", 16.0),
            timeout=15,
            interval=0.5,
            msg="for zone to settle at heat/16.0",
        )
        state, target = _zone_state(ctx.token)
        ctx.check(
            "zone settles at heat/16.0 after CTL sync",
            settled,
            f"state={state} target={target}",
        )
