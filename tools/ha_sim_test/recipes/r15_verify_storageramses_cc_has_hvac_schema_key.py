"""Recipe R15: Verify .storage/ramses_cc schema has HVAC structure (Step 8).

After Step 8, the separate hvac_schema cache key is removed.  The HVAC
structure (FAN with remotes/sensors) now lives in the schema itself,
which is the SSOT.  This recipe verifies that:
1. The hvac_schema cache key is NO LONGER present in .storage
2. The FAN entry with remotes IS present in the schema (client_state.schema)
"""

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


class R15VerifyStorageramsesCcHasHvacSchemaKey(Recipe):
    id = "R15"
    seq = 50
    title = "Verify .storage/ramses_cc schema has HVAC structure (Step 8)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 15: Verify HVAC in schema (Step 8)")

        # Ensure the mixed profile is loaded — earlier recipes on the
        # same container (R04 remove CTL, R02 remove TRV) may have
        # stripped the schema down, leaving no FAN entry.
        schema = get_schema_retry()
        if FAN not in schema:
            print("  FAN not in schema — reloading mixed profile...")
            try:
                await load_profile_yaml(
                    ctx.token,
                    mixed_yaml(),
                    speed=0.01,
                    preload_schema=True,
                    reload_ramses=True,
                )
            except RuntimeError as e:
                print(f"  Profile reload failed: {e}")
            ctx.wait_for_ramses_cc_reload(timeout=30)
            ctx.refresh_token()
            from ..helpers import wait_for, wait_for_schema_populated

            wait_for_schema_populated(min_keys=5, timeout=20)

            # Wait for FAN to appear in client_state schema before
            # calling force_update (parallel mode timing — ramses_rf
            # may not have processed the FAN device yet).
            # Under parallel load, ramses_rf may take 30-40s to process
            # the FAN device from the simulator, so use a generous timeout.
            def _fan_in_storage() -> bool:
                s = get_ramses_storage()
                cs = s.get("client_state", {})
                sch = cs.get("schema", {})
                return FAN in sch

            if not _fan_in_storage():
                print("  Waiting for FAN to appear in client_state schema...")
                wait_for(
                    _fan_in_storage,
                    timeout=45,
                    interval=3,
                    msg="for FAN in client_state schema",
                    floor=10.0,
                )

            # Trigger a save so client_state.schema is persisted
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            ctx.wait_for_schema_stable(timeout=15, msg="for save_client_state")

        storage = get_ramses_storage()

        # Step 8: hvac_schema cache key should be gone
        ctx.check(
            "hvac_schema cache key NOT in storage (Step 8 removed it)",
            "hvac_schema" not in storage,
            f"keys={list(storage.keys())}",
        )

        # The FAN entry with remotes should be in the schema
        client_state = storage.get("client_state", {})
        schema = client_state.get("schema", {})
        fan_entry = schema.get(FAN, {})
        ctx.check(
            "FAN entry exists in schema (client_state.schema)",
            bool(fan_entry),
            f"schema keys={list(schema.keys())[:10]}",
        )
        ctx.check(
            "FAN entry has remotes in schema",
            "remotes" in fan_entry if fan_entry else False,
            f"fan_entry={json.dumps(fan_entry)[:200]}",
        )
        print(f"  FAN schema entry: {json.dumps(fan_entry)[:200]}")
