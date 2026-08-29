"""Recipe R07: HVAC schema — verify FAN in schema (Step 8).

After Step 8, the separate hvac_schema cache is removed.  The FAN entry
with remotes/sensors lives in the schema itself (client_state.schema).
This recipe verifies that the FAN entry with remotes is persisted in
.storage/ramses_cc[client_state][schema] after a force_update.
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


class R07HvacSchemaCachingVerifyFanInSchemaCache(Recipe):
    id = "R07"
    seq = 60
    title = "HVAC schema — verify FAN in schema (Step 8)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 7: HVAC schema — FAN + REM (Step 8)")

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

        schema = get_schema_retry()
        fan_in_schema = FAN in schema
        print(f"  FAN in schema: {fan_in_schema}")
        if fan_in_schema:
            print(f"  FAN schema: {json.dumps(schema[FAN])[:150]}")

        ctx.check(
            "FAN in config entry schema",
            fan_in_schema,
            f"schema keys={list(schema.keys())}",
        )

        # Trigger a save by calling force_update.
        # In parallel mode, the FAN entry may be in the config entry
        # schema but not yet in the client_state schema (ramses_rf
        # hasn't processed it).  Wait for the FAN to appear in storage
        # before calling force_update, otherwise the saved schema will
        # be missing the FAN entry.
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

        try:
            call_service(ctx.token, "ramses_cc", "force_update")
            print("  force_update called")
        except RuntimeError as e:
            print(f"  force_update failed: {e}")

        ctx.wait_for_schema_stable(timeout=15, msg="for save_client_state")

        storage = get_ramses_storage()

        # Step 8: hvac_schema cache key should be gone
        ctx.check(
            "hvac_schema cache key NOT in storage (Step 8)",
            "hvac_schema" not in storage,
            f"keys={list(storage.keys())}",
        )

        # FAN with remotes should be in the persisted schema
        client_state = storage.get("client_state", {})
        stored_schema = client_state.get("schema", {})
        fan_stored = stored_schema.get(FAN, {})
        ctx.check(
            "FAN entry persisted in schema (client_state.schema)",
            bool(fan_stored),
            f"schema keys={list(stored_schema.keys())[:10]}",
        )
        ctx.check(
            "FAN remotes persisted in schema",
            "remotes" in fan_stored if fan_stored else False,
            f"fan_entry={json.dumps(fan_stored)[:200]}",
        )
        print(f"  FAN stored schema: {json.dumps(fan_stored)[:200]}")
