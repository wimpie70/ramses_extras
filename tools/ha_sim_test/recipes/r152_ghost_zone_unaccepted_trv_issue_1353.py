"""Recipe R152: no ghost zones or auto-accept from unaccepted RF devices (issue 1353).

Reproduces https://github.com/ramses-rf/ramses_cc/issues/1353:

A user with a 5-zone Evohome system (``01:208973``, ``_owner: "me"``) kept
getting a ghost Zone 07 (and a pending Zone 06 + Zone 00 sensor hijack)
from weak-signal (-95 dBm) neighbour devices they never accepted:

- ``04:034047`` sending ``I --- 04:034047 --:------ 01:256581 2309 003 070320``
- ``04:034039`` sending ``I --- 04:034039 --:------ 01:256581 12B0 003 060000``
- ``34:170140`` sending ``I --- 34:170140 --:------ 34:170140 2309 003 000578``

Two defects combined pre-fix:

1. ``ramses_rf`` ``DiscoveryScan._process_packet`` only inspected ``addr2``
   as destination, ignoring ``addr3`` on directed ``I`` frames
   (``addr2 == "--:------"``).  ``bound_to`` stayed ``None`` instead of
   recording the neighbour controller ``01:256581``.
2. ``ramses_cc`` ``refresh_device_comments`` wrote ``zone NN`` comments for
   all scan devices (including unaccepted ``NEW`` devices), and
   ``sync_learned_topology`` step 0b/1g placed those unaccepted devices
   into ``main_tcs.zones``, causing ``sync_with_schema`` to flip their
   discovery status from ``NEW`` to ``ACCEPTED`` (``accepted_at=None``)
   and step 0a-post-quart to backfill ``{"_owner": "me"}`` on the next
   save cycle.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    call_service,
    get_current_instance,
    get_ramses_storage,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
)
from ..profile import _build_yaml

_NEIGHBOUR_CTL = "01:256581"
_NEIGHBOUR_TRV_Z07 = "04:034047"
_NEIGHBOUR_TRV_Z06 = "04:034039"
_NEIGHBOUR_RND_Z00 = "34:170140"
_OWN_TRV_Z01 = "04:150004"


def _profile_yaml() -> str:
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        TRV: {"class": "TRV"},
        _OWN_TRV_Z01: {"class": "TRV"},
    }
    schema = {
        "_owner": "me",
        "main_tcs": CTL,
        CTL: {
            "_class": "CTL",
            "_owner": "me",
            "zones": {
                "00": {
                    "_name": "Woonkamer",
                    "class": "radiator_valve",
                    "actuators": [TRV],
                },
                "01": {
                    "_name": "Gang",
                    "class": "radiator_valve",
                    "sensor": _OWN_TRV_Z01,
                    "actuators": [_OWN_TRV_Z01],
                },
            },
        },
        TRV: {"_class": "TRV", "_owner": "me"},
        _OWN_TRV_Z01: {"_class": "TRV", "_owner": "me"},
    }
    return _build_yaml(kl, schema)


class R152GhostZoneUnacceptedTrvIssue1353(Recipe):
    id = "R152"
    seq = 1520
    title = "No ghost zones or auto-accept from unaccepted RF devices (issue 1353)"

    def _publish_raw_rx(self, ctx: RecipeContext, frame: str) -> None:
        hgi_id = get_current_instance().hgi_id
        topic = f"RAMSES/GATEWAY_SIM/{hgi_id}/rx"
        payload = json.dumps({"msg": frame, "ts": datetime.now().isoformat()})
        call_service(
            ctx.token,
            "mqtt",
            "publish",
            {"topic": topic, "payload": payload},
        )

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 152: no ghost zones from unaccepted RF devices (issue 1353)"
        )

        print("  Loading 2-zone owner-tracked profile...")
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

        initial_zones = get_schema_retry().get(CTL, {}).get("zones", {})
        ctx.check(
            "precondition: only zones 00 and 01 configured",
            set(initial_zones.keys()) == {"00", "01"},
            f"zones={sorted(initial_zones)}",
        )

        # Inject wire-format frames from unaccepted neighbour devices:
        # 1) 04:034047 -> 01:256581 (in addr3) 2309 zone 07
        # 2) 04:034039 -> 01:256581 (in addr3) 12B0 zone 06
        # 3) 34:170140 broadcast (addr3 == src) 2309 zone 00
        frames = [
            f"-95  I --- {_NEIGHBOUR_TRV_Z07} --:------ "
            f"{_NEIGHBOUR_CTL} 2309 003 070320",
            f"-95  I --- {_NEIGHBOUR_TRV_Z06} --:------ "
            f"{_NEIGHBOUR_CTL} 12B0 003 060000",
            f"-95  I --- {_NEIGHBOUR_RND_Z00} --:------ "
            f"{_NEIGHBOUR_RND_Z00} 2309 003 000578",
        ]
        print("  Publishing raw RX frames from unaccepted neighbour devices...")
        for frame in frames:
            self._publish_raw_rx(ctx, frame)
            time.sleep(0.5)

        # Wait for the real-time new-device debounce checkpoint (5s) +
        # run two explicit save/sync cycles to exercise both the initial
        # comment placement path and the second-pass _owner backfill path.
        ctx.wait(7, "for real-time discovery checkpoint", floor=6.0)
        for cycle in (1, 2):
            try:
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                pass
            ctx.wait_for_schema_stable(timeout=10, msg=f"sync cycle {cycle}")
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            ctx.wait_for_schema_stable(timeout=10, msg=f"save cycle {cycle}")

        wait_for(
            lambda: _NEIGHBOUR_TRV_Z07 in get_schema_retry().get("device_comments", {}),
            timeout=20,
            interval=1,
            msg="for neighbour device_comments to be written",
            floor=5.0,
        )

        schema = get_schema_retry()
        comments = schema.get("device_comments", {})
        zones = schema.get(CTL, {}).get("zones", {})

        # 1. Verify ramses_rf DiscoveryScan captured bound_to from addr3
        c_z07 = comments.get(_NEIGHBOUR_TRV_Z07, "")
        c_z06 = comments.get(_NEIGHBOUR_TRV_Z06, "")
        ctx.check(
            f"DiscoveryScan records bound to {_NEIGHBOUR_CTL} "
            f"from addr3 on {_NEIGHBOUR_TRV_Z07}",
            f"bound to {_NEIGHBOUR_CTL}" in c_z07 and "zone 07" in c_z07,
            f"comment={c_z07!r}",
        )
        ctx.check(
            f"DiscoveryScan records bound to {_NEIGHBOUR_CTL} "
            f"from addr3 on {_NEIGHBOUR_TRV_Z06}",
            f"bound to {_NEIGHBOUR_CTL}" in c_z06 and "zone 06" in c_z06,
            f"comment={c_z06!r}",
        )

        # 2. Verify no ghost zones 06 or 07 were created on our CTL
        ctx.check(
            "no ghost Zone 07 created from unaccepted neighbour TRV",
            "07" not in zones,
            f"zones={sorted(zones)}",
        )
        ctx.check(
            "no ghost Zone 06 created from unaccepted neighbour TRV",
            "06" not in zones,
            f"zones={sorted(zones)}",
        )

        # 3. Verify Zone 00 sensor was not hijacked by unaccepted broadcast RND
        z00_sensor = zones.get("00", {}).get("sensor")
        ctx.check(
            f"Zone 00 sensor not hijacked by unaccepted {_NEIGHBOUR_RND_Z00}",
            z00_sensor != _NEIGHBOUR_RND_Z00,
            f"zone_00={zones.get('00')}",
        )

        # 4. Verify none of the unaccepted neighbour devices got root schema entries
        for dev_id in (_NEIGHBOUR_TRV_Z07, _NEIGHBOUR_TRV_Z06, _NEIGHBOUR_RND_Z00):
            ctx.check(
                f"unaccepted {dev_id} not added as root schema entry",
                dev_id not in schema,
                f"entry={schema.get(dev_id)}",
            )

        # 5. Verify discovery metadata kept them as NEW (not auto-accepted)
        disc_devices = get_ramses_storage().get("discovery", {}).get("devices", {})
        for dev_id in (_NEIGHBOUR_TRV_Z07, _NEIGHBOUR_TRV_Z06, _NEIGHBOUR_RND_Z00):
            status = disc_devices.get(dev_id, {}).get("status")
            ctx.check(
                f"discovery status for {dev_id} remains 'new' (not auto-accepted)",
                status == "new",
                f"meta={disc_devices.get(dev_id)}",
            )
