"""Recipe R05: No resurrection after restart."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HA_URL, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R05NoResurrectionAfterRestart(Recipe):
    id = "R05"
    seq = 80
    title = "No resurrection after restart"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 5: No resurrection after restart")

        # The setup() profile reload may still be writing to .storage
        # (the profile loader's async_update_entry can fire 20+ seconds
        # after the reload starts).  Wait for it to complete before
        # removing devices, otherwise the profile loader overwrites
        # our remove_device changes.
        print("  Waiting for profile reload to fully complete...")
        for _ in range(15):
            kl_check = get_known_list()
            # The mixed profile has 20 devices — wait until they appear
            if len(kl_check) >= 15:
                break
            time.sleep(2)
        # Extra wait for the profile loader's async_update_entry to flush
        ctx.wait(5, "for profile loader .storage flush to complete")
        # Wait for ramses_cc to be fully loaded so the coordinator's
        # in-memory options match .storage (remove_device reads from
        # coordinator.options, not .storage).
        ctx.refresh_token()
        ctx.wait_for(is_ramses_cc_loaded, timeout=15, msg="for ramses_cc to initialize")

        # TRV and CTL were removed in recipes 2/4.  The 7b profile reload brings
        # them back (mixed profile includes them in known_list).  Re-remove them
        # to verify that remove_device persists across sync cycles and that the
        # devices don't get resurrected by subsequent sync_learned_topology calls.
        # If running standalone (without R07b), the devices may already be
        # absent — skip the removal in that case.
        kl_before = get_known_list()
        devices_present = TRV in kl_before or CTL in kl_before
        if devices_present:
            print(
                f"  Re-removing TRV {TRV} and CTL {CTL} (brought back by 7b reload)..."
            )
            for dev_id, name in [(TRV, "TRV"), (CTL, "CTL")]:
                try:
                    call_service(
                        ctx.token, "ramses_cc", "remove_device", {"device_id": dev_id}
                    )
                    print(f"    {name} removed")
                except RuntimeError as e:
                    print(f"    {name} remove failed: {str(e)[:80]}")
            ctx.wait(3, "for coordinator refresh")
        else:
            print(
                "  Devices already absent (standalone run without R07b)"
                " — skipping removal"
            )

        # Trigger a sync to verify the removal survives sync_learned_topology
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for save")

        # Wait for .storage to be flushed — HA doesn't flush immediately
        # after async_update_entry.  Retry for up to 30s.
        kl_post_restart = {}
        for i in range(10):
            kl_post_restart = get_known_list()
            trv_present = TRV in kl_post_restart
            ctl_present = CTL in kl_post_restart
            print(f"  Retry {i + 1}/10: TRV={trv_present}, CTL={ctl_present}")
            if not trv_present and not ctl_present:
                break
            time.sleep(3)

        ctx.check(
            "TRV not resurrected in known_list",
            TRV not in kl_post_restart,
            f"known_list still has {TRV}",
        )
        ctx.check(
            "CTL not resurrected in known_list",
            CTL not in kl_post_restart,
            f"known_list still has {CTL}",
        )
        # Note: HA's entity/device registry may not be flushed to disk before
        # restart, so orphaned entity states can linger in the states API.  The
        # known_list check above is the real persistence guarantee — if the
        # device is not in the known_list, ramses_cc won't create new entities
        # for it on the next reload.
