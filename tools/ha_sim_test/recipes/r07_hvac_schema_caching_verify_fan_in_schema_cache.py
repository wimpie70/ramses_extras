"""Recipe R07: HVAC schema caching — verify FAN in schema + cache."""

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
    title = "HVAC schema caching — verify FAN in schema + cache"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 7: HVAC schema caching — FAN + REM")

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

        # Trigger a save by calling force_update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
            print("  force_update called")
        except RuntimeError as e:
            print(f"  force_update failed: {e}")

        ctx.wait(5, "for save_client_state")

        storage = get_ramses_storage()
        hvac_schema = storage.get("hvac_schema", {})
        print(f"  hvac_schema after save: {json.dumps(hvac_schema)[:300]}")

        ctx.check(
            "hvac_schema populated",
            bool(hvac_schema),
            f"hvac_schema={json.dumps(hvac_schema)[:200]}",
        )
