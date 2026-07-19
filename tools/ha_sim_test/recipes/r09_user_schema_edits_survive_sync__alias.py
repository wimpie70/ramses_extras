"""Recipe R09: User schema edits survive sync — _alias."""

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


class R09UserSchemaEditsSurviveSyncAlias(Recipe):
    id = "R09"
    seq = 120
    title = "User schema edits survive sync — _alias"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 9: User schema edits survive sync — _alias")

        # This recipe tests that a user-added _alias on a zone survives
        # sync_learned_topology.  We use load_profile_yaml to load a custom
        # profile with _alias on zone 03 — this reloads ramses_cc in-process
        # (no docker restart needed, logs preserved).
        print("  Loading custom profile with _alias='Living Room' on zone 03...")
        alias_schema = dict(MIXED_SCHEMA)
        ctl_alias = dict(alias_schema[CTL])
        zones_alias = dict(ctl_alias["zones"])
        z03_alias = dict(zones_alias["03"])
        z03_alias["_alias"] = "Living Room"
        zones_alias["03"] = z03_alias
        ctl_alias["zones"] = zones_alias
        alias_schema[CTL] = ctl_alias
        try:
            await load_profile_yaml(ctx.token, mixed_yaml(alias_schema))
            print("  Profile loaded with _alias")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")

        ctx.wait(15, "for ramses_cc reload with _alias")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Verify _alias is present before sync
        schema_before_sync = get_schema()
        ctl_before = schema_before_sync.get(CTL, {})
        zones_before = (
            ctl_before.get("zones", {}) if isinstance(ctl_before, dict) else {}
        )
        z03_before = zones_before.get("03", {})
        print(f"  Zone 03 before sync: {json.dumps(z03_before)[:200]}")
        has_alias_before = z03_before.get("_alias") == "Living Room"
        ctx.check(
            "_alias present after reload (before sync)",
            has_alias_before,
            f"zone_03={json.dumps(z03_before)[:200]}",
        )

        # Trigger sync_topology to run sync_learned_topology
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
            print("  sync_topology called")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for sync_learned_topology to process")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save_client_state")

        # Verify _alias survived sync (check config entry schema)
        schema_r9 = get_schema()
        ctl_schema_r9 = schema_r9.get(CTL, {})
        zones_r9 = (
            ctl_schema_r9.get("zones", {}) if isinstance(ctl_schema_r9, dict) else {}
        )
        zone_03_r9 = zones_r9.get("03", {})
        print(f"  Zone 03 after sync: {json.dumps(zone_03_r9)[:200]}")
        ctx.check(
            "_alias survived sync_learned_topology",
            zone_03_r9.get("_alias") == "Living Room",
            f"zone_03={json.dumps(zone_03_r9)[:200]}",
        )
