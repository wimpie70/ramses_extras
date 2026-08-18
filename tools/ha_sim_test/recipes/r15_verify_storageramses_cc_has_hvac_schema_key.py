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
