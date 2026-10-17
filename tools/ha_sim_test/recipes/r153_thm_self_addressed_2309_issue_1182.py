"""Recipe R153: standalone THM self-addressed 2309 corrupts zones (issue 1182).

Reproduces https://github.com/ramses-rf/ramses_cc/issues/1182:

- UFH thermostats (22:) are standalone: they broadcast setpoint/demand
  packets to themselves (``I --- 22:xxxxxx --:------ 22:xxxxxx``) and
  never address the CTL.  Their ``2309`` payload index is the stat's own
  internal index (``00``), not a CTL zone.
- Pre-fix, the scan engine extracted ``zone_index = "00"`` from such a
  2309, wrote ``Likely THM. zone 00.`` into ``device_comments``, and
  ``sync_learned_topology`` step 1g placed the THM into zone 00 — as
  ``actuators`` once the zone already had a sensor (rejected by
  ramses_rf: "must be ('BdrSwitch', 'TrvActuator', 'UfhCircuit')"), while
  evicting the THM from the UFH zone where it was the real sensor.
  Manual schema repairs were reverted on every reload.

Checks cover both layers of the fix:

1.  ``ramses_rf``: a self-addressed ``2309`` from a THM no longer stamps
    ``zone_index`` — an unplaced THM (``22:150003``) must not appear in
    zone 00 and must not gain a ``zone NN`` comment.
2.  ``ramses_cc``: a *stale* ``zone 00`` comment on ``22:150002`` (which
    is legitimately zone 03's sensor) must not add it to zone 00's
    actuators nor evict it from zone 03 — before or after a reload.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_THM_Z00 = "22:150001"  # legit sensor of zone 00
_THM_Z03 = "22:150002"  # legit sensor of UFH zone 03, stale "zone 00" comment
_THM_ORPHAN = "22:150003"  # unplaced THM — must stay unplaced

_ZONE_RAD = "00"
_ZONE_UFH = "03"

# Verbatim payload shape from the reporter's packet log:
#   I --- 22:072769 --:------ 22:072769 2309 003 0001F4
_PKT_SETPOINT = "0001F4"

# Stale scan comment the way refresh_device_comments writes it — the
# "(auto-generated ...)" suffix keeps it stable while the scan engine
# holds no (bogus) zone_index for the THM.
_STALE_COMMENT = (
    "Likely THM. zone 00. codes: 0008, 2309. (auto-generated — do not edit)"
)


def _profile_yaml() -> str:
    """Profile: THM sensors in zones 00 + 03, stale comment on the UFH THM."""
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        _THM_Z00: {"class": "THM"},
        _THM_Z03: {"class": "THM"},
        _THM_ORPHAN: {"class": "THM"},
        TRV: {"class": "TRV"},
    }
    schema = {
        CTL: {
            "zones": {
                _ZONE_RAD: {
                    "_name": "Kitchen",
                    "class": "radiator_valve",
                    "sensor": _THM_Z00,
                    "actuators": [TRV],
                },
                _ZONE_UFH: {
                    "_name": "Sitting room",
                    "class": "underfloor_heating",
                    "sensor": _THM_Z03,
                },
            }
        },
        "device_comments": {_THM_Z03: _STALE_COMMENT},
    }
    return _build_yaml(kl, schema)


def _zones() -> dict:
    ctl = get_schema().get(CTL, {})
    return ctl.get("zones", {}) if isinstance(ctl, dict) else {}


def _comments() -> dict:
    comments = get_schema().get("device_comments", {})
    return comments if isinstance(comments, dict) else {}


class R153ThmSelfAddressed2309Issue1182(Recipe):
    id = "R153"
    seq = 1530
    title = "Standalone THM self-addressed 2309 corrupts zones (issue 1182)"

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
        ctx.log_section("Recipe 153: THM self-addressed 2309 (issue 1182)")

        # 1. Seed the schema: Kitchen (sensor THM + TRV actuator) and a
        #    UFH zone whose THM sensor carries a stale "zone 00" comment.
        print("  Loading profile (zones 00+03, stale THM comment)...")
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
            "precondition: zone 00 sensor + TRV actuator",
            zones.get(_ZONE_RAD, {}).get("sensor") == _THM_Z00
            and TRV in zones.get(_ZONE_RAD, {}).get("actuators", []),
            f"zone_{_ZONE_RAD}={zones.get(_ZONE_RAD)}",
        )
        ctx.check(
            f"precondition: UFH zone {_ZONE_UFH} sensor seeded",
            zones.get(_ZONE_UFH, {}).get("sensor") == _THM_Z03,
            f"zone_{_ZONE_UFH}={zones.get(_ZONE_UFH)}",
        )

        # Activate the THMs so their injected packets are accepted.
        for thm in (_THM_Z03, _THM_ORPHAN):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": (
                            "ramses_extras/device_simulator/activate_profile_device"
                        ),
                        "device_id": thm,
                    },
                )
            except RuntimeError:
                pass

        # 2. Replay the standalone-thermostat broadcast: self-addressed
        #    I 2309 (addr3 == src, payload index is internal, not a zone).
        print("  Injecting self-addressed 2309 from UFH + orphan THMs...")
        self._inject(ctx, _THM_Z03, "2309", _PKT_SETPOINT)
        self._inject(ctx, _THM_ORPHAN, "2309", _PKT_SETPOINT)
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
        comments = _comments()
        # EXPECTED (post-fix): the stale "zone 00" comment cannot move a
        # sensor-type device into actuators or evict it from its real zone.
        ctx.check(
            "UFH THM not added to zone 00 actuators",
            _THM_Z03 not in zones.get(_ZONE_RAD, {}).get("actuators", []),
            f"zone_{_ZONE_RAD}={zones.get(_ZONE_RAD)}",
        )
        ctx.check(
            "UFH THM not evicted from zone 03 sensor",
            zones.get(_ZONE_UFH, {}).get("sensor") == _THM_Z03,
            f"zone_{_ZONE_UFH}={zones.get(_ZONE_UFH)}",
        )
        ctx.check(
            "zone 00 sensor/actuators unchanged",
            zones.get(_ZONE_RAD, {}).get("sensor") == _THM_Z00
            and zones.get(_ZONE_RAD, {}).get("actuators") == [TRV],
            f"zone_{_ZONE_RAD}={zones.get(_ZONE_RAD)}",
        )
        # EXPECTED (post-fix ramses_rf): the orphan THM's self-addressed
        # 2309 stamps no zone_index — no "zone NN" comment, no placement.
        ctx.check(
            "orphan THM gains no zone from self-addressed 2309",
            _THM_ORPHAN not in zones.get(_ZONE_RAD, {}).get("actuators", [])
            and zones.get(_ZONE_RAD, {}).get("sensor") != _THM_ORPHAN,
            f"zone_{_ZONE_RAD}={zones.get(_ZONE_RAD)}",
        )
        orphan_comment = str(comments.get(_THM_ORPHAN, ""))
        ctx.check(
            "orphan THM comment has no zone index",
            "zone" not in orphan_comment,
            f"comment={orphan_comment or '<none>'}",
        )

        # 4. Reload — the reported symptom was a schema revert on reload.
        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            ctx.check("ramses_cc config entry found", False, "no entry_id")
            return
        print("  Reloading ramses_cc...")
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
            "post-reload: UFH THM still zone 03 sensor",
            zones.get(_ZONE_UFH, {}).get("sensor") == _THM_Z03,
            f"zone_{_ZONE_UFH}={zones.get(_ZONE_UFH)}",
        )
        ctx.check(
            "post-reload: zone 00 unchanged (no THM actuators)",
            zones.get(_ZONE_RAD, {}).get("sensor") == _THM_Z00
            and zones.get(_ZONE_RAD, {}).get("actuators") == [TRV],
            f"zone_{_ZONE_RAD}={zones.get(_ZONE_RAD)}",
        )
