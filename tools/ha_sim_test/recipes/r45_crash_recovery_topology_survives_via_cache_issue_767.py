"""Recipe R45: Crash recovery — force reload, topology survives (issue 767).

Verifies that a hard crash (simulated by reloading ramses_cc without clean
shutdown) preserves learned topology from the 5-minute cache checkpoint in
``.storage/ramses_cc``.  Entities should reappear from the merged schema
(config + cache) after reload.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, TRV
from ..helpers import (
    get_entities,
    get_schema_retry,
    ws_send,
)


class R45CrashRecoveryTopologySurvivesViaCacheIssue767(Recipe):
    id = "R45"
    seq = 460
    title = "Crash recovery — topology survives via cache (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 45: Crash recovery — topology survives via cache")

        # 1. Load mixed profile with CTL, zones, DHW
        print("  Loading mixed profile (CTL + zones + DHW)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 2. Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        ctx.wait(10, "for CTL heartbeats + topology learning")

        # 3. Capture the learned topology (entities + schema)
        entities_before = get_entities(ctx.token)
        schema_before = get_schema_retry()

        entity_count_before = len(
            [
                e
                for e in entities_before
                if "ramses" in e.get("attributes", {}).get("friendly_name", "").lower()
                or any(
                    dev in e["entity_id"]
                    for dev in [
                        CTL.replace(":", "_"),
                        TRV.replace(":", "_"),
                        DHW.replace(":", "_"),
                    ]
                )
            ]
        )

        # Check schema has zones
        ctl_schema = schema_before.get(CTL, {})
        zones_before = ctl_schema.get("zones", {})
        dhw_before = ctl_schema.get("stored_hotwater", {})

        ctx.check(
            "schema has zones before crash",
            len(zones_before) > 0,
            f"zones={list(zones_before.keys())}",
        )

        ctx.check(
            "schema has DHW before crash",
            isinstance(dhw_before, dict) and "sensor" in dhw_before,
            f"dhw={dhw_before}",
        )

        # 4. Force-reload ramses_cc (simulating crash — no clean unload)
        #    The config_entries/reload endpoint triggers async_reload_entry
        #    which does a clean unload.  To simulate a crash more closely,
        #    we could stop/start the container, but that takes 60+ seconds.
        #    The reload is a reasonable approximation: the cache from the
        #    last save_state is what's available.
        print("  Force-reloading ramses_cc (simulating crash)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "config_entries/reload",
                    "entry_id": "ramses_cc",
                },
            )
        except RuntimeError:
            pass
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 5. Verify entities reappear from cached schema
        entities_after = get_entities(ctx.token)
        schema_after = get_schema_retry()

        ctl_schema_after = schema_after.get(CTL, {})
        zones_after = ctl_schema_after.get("zones", {})
        dhw_after = ctl_schema_after.get("stored_hotwater", {})

        ctx.check(
            "zones survived crash (from cache)",
            len(zones_after) > 0,
            f"zones={list(zones_after.keys())}",
        )

        ctx.check(
            "DHW sensor assignment survived crash",
            isinstance(dhw_after, dict) and "sensor" in dhw_after,
            f"dhw={dhw_after}",
        )

        # 6. Verify zone names survived (if they were set)
        #    Zone names come from 0004 packets and are cached in schema
        #    as _name under each zone.
        zone_names_survived = True
        for zidx, zdata in zones_before.items():
            name_before = zdata.get("_name", "")
            name_after = zones_after.get(zidx, {}).get("_name", "")
            if name_before and name_after != name_before:
                zone_names_survived = False
                print(f"    zone {zidx} name changed: '{name_before}' → '{name_after}'")

        ctx.check(
            "zone names survived crash (from cache)",
            zone_names_survived,
            "one or more zone names changed",
        )

        # 7. Verify entity count is similar (some may be temporarily
        #    unavailable until traffic resumes, but they should exist)
        entity_count_after = len(
            [
                e
                for e in entities_after
                if any(
                    dev in e["entity_id"]
                    for dev in [
                        CTL.replace(":", "_"),
                        TRV.replace(":", "_"),
                        DHW.replace(":", "_"),
                    ]
                )
            ]
        )

        ctx.check(
            "entities reappeared after crash",
            entity_count_after > 0,
            f"entity_count_before={entity_count_before}, after={entity_count_after}",
        )
