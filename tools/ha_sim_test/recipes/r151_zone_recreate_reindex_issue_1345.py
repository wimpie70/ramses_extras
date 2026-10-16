"""Recipe R151: zone deleted + recreated under a new index (issue 1345).

Reproduces https://github.com/ramses-rf/ramses_cc/issues/1345:

- The stored schema has zone ``02`` = "Slaapkamer" (TRV ``04:150003``
  actuator) plus a stale scan comment ``zone 02`` on the TRV — matching
  the reporter's pre-incident state.
- The controller then deletes zone 02 and recreates the zone under index
  ``00``.  On the wire it announces this perfectly: an ``I 0005``
  zone-mask broadcast (``00003B00`` = zones 00,01,03,04,05) and an
  ``I 0004`` naming zone 00 "Slaapkamer".

Two defects are expected pre-fix:

1.  The learned zone ``00`` (named, but with no sensor/actuators — the
    TRV only binds via ``000C``/eavesdrop paths) is pruned by
    ``sync_learned_topology`` step 1b-post2 as an "empty phantom", so
    the authoritative ``0004`` name is lost and the zone never lands in
    the stored schema.
2.  ``remove_device`` on ``01:150000_02`` drops the zone entry, but the
    TRV's ``device_comments`` entry (``... zone 02.``) survives — it is
    keyed on the device id, not the child id — and the in-memory
    ``_removed`` tombstone is lost on reload.  Step 1g then recreates
    zone ``02`` with the TRV as actuator on the next sync after a
    reload.
"""

from __future__ import annotations

import time

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_ZONE_STALE = "02"  # deleted controller-side, still in stored schema
_ZONE_NEW = "00"  # recreated zone index announced via 0005/0004
_ZONE_NAME = "Slaapkamer"
_ZONE_CHILD_STALE = f"{CTL}_{_ZONE_STALE}"

# Controller broadcasts after the delete/recreate (verbatim from the
# reporter's packet log):
#   I --- 01:147133 --:------ 01:147133 0005 004 00003B00
#       zone_type=00, mask=0x003B -> zones 00,01,03,04,05 (no 02)
_PKT_ZONE_MASK = "00003B00"
#   I --- 01:147133 --:------ 01:147133 0004 022 0000<name>
#       zone_idx=00, flag=00, name="Slaapkamer" (20B, NUL-padded)
_PKT_ZONE_NAME = (
    "0000" + _ZONE_NAME.encode("ascii").hex().upper() + "00" * (20 - len(_ZONE_NAME))
)

# Stale scan comment the way refresh_device_comments writes it — the
# "(auto-generated ...)" suffix keeps refresh_device_comments from
# rebuilding it while the scan engine has no zone_index for the TRV.
_STALE_COMMENT = (
    f"Likely TRV. bound to {CTL} zone {_ZONE_STALE}. (auto-generated — do not edit)"
)


def _profile_yaml() -> str:
    """Pre-incident profile: stored schema still has zone 02 = Slaapkamer.

    Zones 01/03/04/05 keep a sensor+actuator so only zone 02 is the
    stale remnant; the TRV carries the stale ``zone 02`` comment.
    """
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        TRV: {"class": "TRV"},  # stale zone-02 actuator
        "01:150003": {"class": "CTL"},  # zone sensors (mixed convention)
        "01:150004": {"class": "CTL"},
        "01:150005": {"class": "CTL"},
        "01:150006": {"class": "CTL"},
        "04:150004": {"class": "TRV"},  # other zones' actuators
        "04:150005": {"class": "TRV"},
        "04:150006": {"class": "TRV"},
        "04:150007": {"class": "TRV"},
    }
    schema = {
        CTL: {
            "zones": {
                "01": {"sensor": "01:150003", "actuators": ["04:150004"]},
                _ZONE_STALE: {
                    "_name": _ZONE_NAME,
                    "class": "radiator_valve",
                    "actuators": [TRV],
                },
                "03": {"sensor": "01:150004", "actuators": ["04:150005"]},
                "04": {"sensor": "01:150005", "actuators": ["04:150006"]},
                "05": {"sensor": "01:150006", "actuators": ["04:150007"]},
            }
        },
        "device_comments": {TRV: _STALE_COMMENT},
    }
    return _build_yaml(kl, schema)


def _zones() -> dict:
    ctl = get_schema().get(CTL, {})
    return ctl.get("zones", {}) if isinstance(ctl, dict) else {}


class R151ZoneRecreateReindexIssue1345(Recipe):
    id = "R151"
    seq = 1510
    title = "Zone delete+recreate under new index (issue 1345)"

    def _inject(
        self, ctx: RecipeContext, source_id: str, code: str, payload: str
    ) -> None:
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": source_id,
                "code": code,
                "payload": payload,
                "verb": "I",
            },
        )

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 151: zone recreate reindex (issue 1345)")

        # 1. Seed the pre-incident schema (zones 01-05, 02=Slaapkamer,
        #    stale zone-02 comment on the TRV).
        print("  Loading pre-incident profile (stale zone 02 + comment)...")
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

        zones = _zones()
        ctx.check(
            f"precondition: stale zone {_ZONE_STALE} seeded",
            zones.get(_ZONE_STALE, {}).get("_name") == _ZONE_NAME
            and TRV in zones.get(_ZONE_STALE, {}).get("actuators", []),
            f"zone_{_ZONE_STALE}={zones.get(_ZONE_STALE)}",
        )
        ctx.check(
            f"precondition: zone {_ZONE_NEW} not yet known",
            _ZONE_NEW not in zones,
            f"zones={sorted(zones)}",
        )

        # Activate the CTL in the simulator so its packets are accepted
        # (the TRV stays inactive — we need its comment to remain stale).
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass

        # 2. Replay the controller's on-air announcement: 0005 zone mask
        #    (00,01,03,04,05) + 0004 naming zone 00 "Slaapkamer".
        print("  Injecting CTL 0005 zone mask + 0004 zone-00 name...")
        self._inject(ctx, CTL, "0005", _PKT_ZONE_MASK)
        time.sleep(0.5)
        self._inject(ctx, CTL, "0004", _PKT_ZONE_NAME)
        ctx.wait(3, "for injected packets to reach ramses_rf")

        # 3. Sync learned topology into the stored schema.
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait_for_schema_stable(timeout=10, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save")

        zones = get_schema_retry().get(CTL, {}).get("zones", {})
        zone_new = zones.get(_ZONE_NEW, {})
        # EXPECTED (post-fix): the 0004-broadcast name is controller-authored
        # evidence; a named learned zone must survive phantom pruning.
        ctx.check(
            f"learned zone {_ZONE_NEW} persisted in schema",
            _ZONE_NEW in zones,
            f"zones={sorted(zones)}",
        )
        ctx.check(
            f"zone {_ZONE_NEW} keeps controller name '{_ZONE_NAME}'",
            zone_new.get("_name") == _ZONE_NAME,
            f"zone_{_ZONE_NEW}={zone_new}",
        )

        # 4. User removes the stale zone child, then reloads — the
        #    in-memory tombstone is lost and the stale TRV comment must
        #    not resurrect zone 02.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _ZONE_CHILD_STALE},
            )
        except RuntimeError as e:
            ctx.check("remove_device stale zone call", False, str(e)[:120])
            return
        wait_for(
            lambda: _ZONE_STALE not in _zones(),
            timeout=30,
            interval=2,
            msg=f"for zone {_ZONE_STALE} removal to persist",
            floor=10.0,
        )

        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            ctx.check("ramses_cc config entry found", False, "no entry_id")
            return
        print("  Reloading ramses_cc (clears in-memory removed set)...")
        call_service(
            ctx.token,
            "homeassistant",
            "reload_config_entry",
            {"entry_id": entry_id},
        )
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for post-reload save")

        zones = get_schema_retry().get(CTL, {}).get("zones", {})
        ctx.check(
            f"zone {_ZONE_STALE} not resurrected after reload",
            _ZONE_STALE not in zones,
            f"zones={sorted(zones)} stale zone={zones.get(_ZONE_STALE)}",
        )
        ctx.check(
            f"zone {_ZONE_NEW} still present after reload",
            _ZONE_NEW in zones,
            f"zones={sorted(zones)}",
        )
