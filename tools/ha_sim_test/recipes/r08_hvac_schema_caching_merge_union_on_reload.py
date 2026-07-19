"""Recipe R08: HVAC schema caching — merge union on reload."""

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


class R08HvacSchemaCachingMergeUnionOnReload(Recipe):
    id = "R08"
    seq = 110
    title = "HVAC schema caching — merge union on reload"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 8: HVAC schema caching — merge union on reload")

        # This recipe tests that cached HVAC entries merge with config schema
        # (union, no duplicates) after reload.  We load a custom YAML profile
        # with FAN + 2 REMs (37:170000 from cache + 37:180000 from config),
        # and verify the coordinator merges both on reload.
        print("  Loading custom profile with FAN + 2 REMs (37:170000 + 37:180000)...")
        r8_schema = dict(MIXED_SCHEMA)
        r8_schema[FAN] = {"remotes": [REM, "37:180000"], "sensors": [CO2]}
        try:
            await load_profile_yaml(ctx.token, mixed_yaml(r8_schema))
            print("  Profile loaded with 2 REMs")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")

        ctx.wait(15, "for ramses_cc reload with 2 REMs")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Verify both REMs are in the FAN's schema after reload
        schema_r8 = get_schema_retry()
        fan_entry_r8 = schema_r8.get(FAN, {})
        remotes_r8 = fan_entry_r8.get("remotes", [])
        print(f"  FAN remotes after reload: {remotes_r8}")
        ctx.check(
            "37:170000 in FAN remotes (from cache/config)",
            "37:170000" in remotes_r8,
            f"remotes={remotes_r8}",
        )
        ctx.check(
            "37:180000 in FAN remotes (from config)",
            "37:180000" in remotes_r8,
            f"remotes={remotes_r8}",
        )
        ctx.check(
            "No duplicate remotes",
            len(remotes_r8) == len(set(remotes_r8)),
            f"remotes={remotes_r8}",
        )
