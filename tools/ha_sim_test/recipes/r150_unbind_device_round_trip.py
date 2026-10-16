"""Recipe R150: unbind_device service — local detach round-trip.

Covers ramses-rf/ramses_cc issue 1283: detaching a REM from a FAN must
be a non-destructive, schema-level operation.  This recipe runs a full
bind → unbind → re-bind round trip against a faked REM and asserts the
persisted schema at every phase:

  1. ``add_faked_rem`` binds a fresh REM to the FAN (``_bound`` traits
     both ways, REM in the FAN's ``remotes[]``).
  2. ``unbind_device`` without ``confirm: true`` is refused and leaves
     the schema untouched.
  3. ``unbind_device`` with ``confirm: true`` strips the REM from
     ``remotes[]``, clears ``_bound`` both ways, writes an ``_unbound``
     tombstone on the REM, keeps the REM's root entry, and lists it
     under ``orphans_hvac`` for review.
  4. ``add_faked_rem`` re-binds the same REM — the explicit ``_bound``
     re-declaration wins over the tombstone.
  5. ``sync_topology`` purges the ``_unbound`` tombstone.

The FAN carries ``_scheme: orcon`` so ``on_air: true`` exercises the
strategy-dispatched RF path too: the Orcon ``unbind_remote`` runs the
standard 1FC9 handshake with an *empty* Confirm (payload ``00`` — the
hardware-verified unbind discriminator, see issue comment).  A ``W``
Accept from the FAN is injected like R135; the emitted Confirm frame is
asserted in the docker log.

See: https://github.com/ramses-rf/ramses_cc/issues/1283
"""

from __future__ import annotations

import json
import time
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    get_current_instance,
    get_docker_logs,
    get_schema_retry,
    load_profile_yaml,
    spawn_thread,
    wait_for,
    wait_for_transport_ready,
)
from ..profile import minimal_hvac_yaml

# Fresh REM id (not in any profile) — r18 uses 37:999999, keep ours
# distinct so the two recipes cannot collide on a shared container.
FAKED_REM = "37:001283"

# FAN 32:150000 -> 0x8249F0 — the captured Orcon Accept offers 31D9+31DA
_FAN_ACCEPT_PAYLOAD = "0031D98249F00031DA8249F0"


class R150UnbindDeviceRoundTrip(Recipe):
    """unbind_device round trip: bind → refuse → unbind → rebind."""

    id = "R150"
    seq = 1500
    title = "unbind_device — local detach + rebind round-trip"
    tags = ("binding", "unbind_device", "schema", "issue1283")

    async def run(self, ctx: RecipeContext) -> None:
        """Run the bind/unbind/rebind schema round trip."""
        ctx.log_section("Recipe 150: unbind_device round-trip")

        # Load the minimal HVAC profile so FAN 32:150000 exists
        # regardless of what a previous recipe left behind.
        print("  Loading minimal_hvac profile (FAN + REM + CO2 + HGI)...")
        try:
            await load_profile_yaml(
                ctx.token,
                minimal_hvac_yaml({FAN: {"_class": "FAN", "_scheme": "orcon"}}),
            )
            print("  minimal_hvac profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        wait_for(
            lambda: FAN in get_schema_retry(),
            timeout=15,
            interval=1,
            msg=f"for {FAN} in schema",
            floor=2.0,
        )

        # Services can be unregistered by a preceding profile reload —
        # wait for both add_faked_rem and unbind_device (mirrors R18).
        def _services_ready() -> bool:
            ha_url = get_current_instance().ha_url
            req = urllib.request.Request(
                f"{ha_url}/api/services",
                headers={"Authorization": f"Bearer {ctx.token}"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                services = json.loads(resp.read())
                return any(
                    s.get("domain") == "ramses_cc"
                    and "add_faked_rem" in s.get("services", {})
                    and "unbind_device" in s.get("services", {})
                    for s in services
                )
            except Exception:
                return False

        wait_for(
            _services_ready,
            timeout=45,
            interval=3,
            msg="for ramses_cc add_faked_rem/unbind_device services",
            floor=15.0,
        )

        def _fan() -> dict:
            entry = get_schema_retry().get(FAN, {})
            return entry if isinstance(entry, dict) else {}

        def _rem() -> dict:
            entry = get_schema_retry().get(FAKED_REM, {})
            return entry if isinstance(entry, dict) else {}

        def _orphans() -> list:
            orphans = get_schema_retry().get("orphans_hvac", [])
            return orphans if isinstance(orphans, list) else []

        def _bind_faked_rem() -> bool:
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "add_faked_rem",
                    {
                        "device_id": FAKED_REM,
                        "bound_to": FAN,
                        "alias": "Unbind Round-Trip REM",
                    },
                )
            except RuntimeError as e:
                print(f"  add_faked_rem failed: {str(e)[:120]}")
                return False
            return True

        # --- Phase 1: bind -------------------------------------------------
        print(f"  Phase 1: bind {FAKED_REM} to {FAN} via add_faked_rem...")
        bound = _bind_faked_rem()
        ctx.check("add_faked_rem binds REM to FAN", bound, "")
        if bound:
            wait_for(
                lambda: FAKED_REM in _fan().get("remotes", []),
                timeout=15,
                interval=1,
                msg=f"for {FAKED_REM} in FAN remotes[]",
                floor=2.0,
            )
            ctx.wait(3, "for config entry persistence")
            ctx.check(
                "bound: REM in FAN remotes[]",
                FAKED_REM in _fan().get("remotes", []),
                f"remotes={_fan().get('remotes')}",
            )
            ctx.check(
                "bound: FAN _bound -> REM",
                _fan().get("_bound") == FAKED_REM,
                f"_bound={_fan().get('_bound')}",
            )
            ctx.check(
                "bound: REM _bound -> FAN",
                _rem().get("_bound") == FAN,
                f"entry={_rem()}",
            )

        # --- Phase 2: unbind refused without confirm -----------------------
        print("  Phase 2: unbind_device without confirm must refuse...")
        refused = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "unbind_device",
                {"device_id": FAKED_REM},
            )
        except RuntimeError:
            refused = True
        ctx.check(
            "unbind_device without confirm is refused",
            refused,
            "service call unexpectedly succeeded" if not refused else "",
        )
        ctx.check(
            "refused call leaves remotes[] intact",
            FAKED_REM in _fan().get("remotes", []),
            f"remotes={_fan().get('remotes')}",
        )

        # --- Phase 3: confirmed unbind, with the on-air handshake ----------
        # The FAN is _scheme: orcon, so unbind_remote runs the real FSM:
        # a 1FC9 Offer from the (faked) REM, a W Accept from the FAN
        # (injected — the sim has no auto-respondent), then the empty
        # Confirm `1FC9 001 00` that releases the FAN's slot.
        #
        # The faked REM is not part of the sim's device DB, so its
        # I-frames are not echoed by the scenario engine — and without
        # the echo the TX layer retries for 60s+.  Activate an
        # autonomous_emissions device for it so the echo path sees an
        # active device (mirrors a real REM on the bus).
        print(f"  Phase 3: unbind_device {FAKED_REM} (confirm: true, on_air: true)...")
        wait_for_transport_ready(timeout=30)
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_run_scenario",
                {
                    "scenario_type": "autonomous_emissions",
                    "params": {
                        "device_id": FAKED_REM,
                        "device_type": "REM",
                        "excluded_codes": ["1FC9"],
                    },
                },
            )
        except RuntimeError as e:
            print(f"  autonomous_emissions activation failed: {e}")

        def _inject_fan_accept() -> None:
            time.sleep(1.5)
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": FAN,
                        "dst": FAKED_REM,
                        "code": "1FC9",
                        "payload": _FAN_ACCEPT_PAYLOAD,
                        "verb": "W",
                    },
                )
            except RuntimeError as e:
                print(f"  Accept inject failed: {e}")

        spawn_thread(_inject_fan_accept)
        log_since = ctx.log_monitor.snapshot()

        unbound = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "unbind_device",
                {
                    "device_id": FAKED_REM,
                    "confirm": True,
                    "on_air": True,
                },
            )
            unbound = True
        except RuntimeError as e:
            print(f"  unbind_device failed: {str(e)[:120]}")
        ctx.check("unbind_device service call succeeds", unbound, "")

        # Verify the on-air frames: an Offer broadcast by the REM, then
        # the empty Confirm directed at the FAN (the unbind marker).
        raw_logs = get_docker_logs(since=log_since)
        tx_lines = [
            line
            for line in raw_logs.splitlines()
            if FAKED_REM in line and "1FC9" in line
        ]
        ctx.check(
            f"on-air: 1FC9 offer sent impersonating {FAKED_REM}",
            any(" I " in line for line in tx_lines),
            f"tx_lines={tx_lines[-3:]}",
        )
        ctx.check(
            "on-air: empty Confirm (1FC9 001 00) sent to FAN",
            any("1FC9 001 00" in line and FAN in line for line in tx_lines),
            f"tx_lines={tx_lines[-3:]}",
        )

        if unbound:
            wait_for(
                lambda: FAKED_REM in _orphans(),
                timeout=10,
                interval=1,
                msg=f"for {FAKED_REM} in orphans_hvac",
                floor=1.0,
            )
            ctx.wait(3, "for config entry persistence")
            ctx.check(
                "unbind: REM removed from FAN remotes[]",
                FAKED_REM not in _fan().get("remotes", []),
                f"remotes={_fan().get('remotes')}",
            )
            ctx.check(
                "unbind: FAN _bound cleared",
                "_bound" not in _fan(),
                f"fan_entry={_fan()}",
            )
            ctx.check(
                "unbind: REM _bound cleared",
                "_bound" not in _rem(),
                f"entry={_rem()}",
            )
            ctx.check(
                "unbind: REM tombstoned _unbound=[FAN]",
                _rem().get("_unbound") == [FAN],
                f"entry={_rem()}",
            )
            ctx.check(
                "unbind: REM keeps its root schema entry",
                FAKED_REM in get_schema_retry(),
                "device was fully removed instead of detached",
            )
            ctx.check(
                "unbind: REM listed under orphans_hvac",
                FAKED_REM in _orphans(),
                f"orphans_hvac={_orphans()}",
            )

        # --- Phase 4: re-bind the same REM ---------------------------------
        print(f"  Phase 4: re-bind {FAKED_REM} to {FAN}...")
        rebound = _bind_faked_rem()
        ctx.check("re-bind: add_faked_rem succeeds again", rebound, "")
        if rebound:
            ctx.wait(3, "for config entry persistence")
            ctx.check(
                "re-bind: REM back in FAN remotes[]",
                FAKED_REM in _fan().get("remotes", []),
                f"remotes={_fan().get('remotes')}",
            )
            ctx.check(
                "re-bind: REM _bound -> FAN restored",
                _rem().get("_bound") == FAN,
                f"entry={_rem()}",
            )

        # --- Phase 5: sync purges the _unbound tombstone -------------------
        print("  Phase 5: sync_topology purges the _unbound tombstone...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {str(e)[:120]}")
        wait_for(
            lambda: "_unbound" not in _rem(),
            timeout=15,
            interval=2,
            msg=f"for _unbound tombstone purge on {FAKED_REM}",
            floor=3.0,
        )
        ctx.check(
            "rebind clears _unbound tombstone after sync",
            "_unbound" not in _rem(),
            f"entry={_rem()}",
        )
        ctx.check(
            "re-bind: REM removed from orphans_hvac after sync",
            FAKED_REM not in _orphans(),
            f"orphans_hvac={_orphans()}",
        )

        # Any error mentioning the device or the service indicates a
        # broken call path.
        log_data = ctx.log_monitor.collect()
        unbind_errors = [
            line
            for line in log_data.get("errors", [])
            if FAKED_REM in line or "unbind_device" in line
        ]
        ctx.check(
            "no unbind errors in ha-sim log",
            len(unbind_errors) == 0,
            f"{unbind_errors[:3]}",
        )
