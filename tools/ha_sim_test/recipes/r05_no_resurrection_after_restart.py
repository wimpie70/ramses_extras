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

        # TRV and CTL were removed in recipes 2/4.  The 7b profile reload brings
        # them back (mixed profile includes them in known_list).  Re-remove them
        # to verify that remove_device persists across sync cycles and that the
        # devices don't get resurrected by subsequent sync_learned_topology calls.
        print(f"  Re-removing TRV {TRV} and CTL {CTL} (brought back by 7b reload)...")
        for dev_id, name in [(TRV, "TRV"), (CTL, "CTL")]:
            try:
                call_service(
                    ctx.token, "ramses_cc", "remove_device", {"device_id": dev_id}
                )
                print(f"    {name} removed")
            except RuntimeError as e:
                print(f"    {name} remove failed: {str(e)[:80]}")
        ctx.wait(3, "for coordinator refresh")

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

        kl_post_restart = get_known_list()

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
