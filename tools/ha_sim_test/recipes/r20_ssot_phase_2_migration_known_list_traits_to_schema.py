"""Recipe R20: SSOT Phase 2 migration — known_list traits to schema."""

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


class R20SsotPhase2MigrationKnownListTraitsToSchema(Recipe):
    id = "R20"
    seq = 250
    title = "SSOT Phase 2 migration — known_list traits to schema"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 20: SSOT Phase 2 migration (known_list → schema)")

        # This recipe verifies that traits from the known_list (class, faked,
        # bound, scheme, alias) are copied into the schema's _ traits by
        # _sync_known_list_traits_to_schema after sync_learned_topology runs.
        #
        # NOTE: Recipes 19 and 22 load fresh_start/mixed profiles which wipe
        # the faked REM from recipe 18.  We re-add it here to test trait migration.

        fan_id_r20 = FAN  # 32:150000
        rem_id_r20 = ctx.shared.get("faked_rem_id", "37:999999")  # set by R18

        # Re-add the faked REM (wiped by profile reloads in recipes 19/22)
        print(f"  Re-adding faked REM {rem_id_r20} (wiped by profile reloads)...")
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "add_faked_rem",
                {
                    "device_id": rem_id_r20,
                    "bound_to": fan_id_r20,
                },
            )
            print(f"  add_faked_rem succeeded for {rem_id_r20}")
        except RuntimeError as e:
            print(f"  add_faked_rem failed: {e}")
        ctx.wait(3, "for schema merge")

        # Force a sync cycle to trigger backfill + trait migration
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology + trait migration")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_r20 = get_schema_retry()

        # Check 1: REM should have a root entry (from add_faked_rem in recipe 18,
        # which creates a root entry with _class, _bound, _faked, _owner traits)
        ctx.check(
            "REM has root entry in schema",
            rem_id_r20 in schema_r20,
            f"keys={list(schema_r20.keys())}",
        )

        # Check 2: REM root entry should have _faked trait (from add_faked_rem)
        rem_entry_r20 = schema_r20.get(rem_id_r20, {})
        if isinstance(rem_entry_r20, dict):
            ctx.check(
                "REM root entry has _faked",
                rem_entry_r20.get("_faked") is True,
                f"keys={list(rem_entry_r20.keys())}",
            )
            ctx.check(
                "REM root entry has _bound",
                rem_entry_r20.get("_bound") == fan_id_r20,
                f"_bound={rem_entry_r20.get('_bound')}",
            )
            ctx.check(
                "REM root entry has _class",
                rem_entry_r20.get("_class") == "REM",
                f"_class={rem_entry_r20.get('_class')}",
            )

        # Check 3: If FAN has class in known_list, it should be in schema as _class
        # (This is the core Phase 2 migration — known_list traits → schema _ traits)
        known_list_r20 = get_known_list()
        fan_kl = known_list_r20.get(fan_id_r20, {})
        if isinstance(fan_kl, dict) and "class" in fan_kl:
            fan_entry_r20 = schema_r20.get(fan_id_r20, {})
            if isinstance(fan_entry_r20, dict):
                ctx.check(
                    "FAN _class migrated from known_list",
                    fan_entry_r20.get("_class") == fan_kl["class"],
                    f"schema _class={fan_entry_r20.get('_class')}, "
                    f"known_list class={fan_kl['class']}",
                )

        # Check 5: Schema should be ordered (root traits first, orphans at top)
        schema_keys_r20 = list(schema_r20.keys())
        if "_owner" in schema_keys_r20:
            ctx.check(
                "_owner is first key in schema",
                schema_keys_r20[0] == "_owner",
                f"first key={schema_keys_r20[0]}",
            )
