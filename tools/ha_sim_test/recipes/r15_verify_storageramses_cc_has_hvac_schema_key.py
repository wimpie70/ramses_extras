"""Recipe R15: Verify .storage/ramses_cc has hvac_schema key."""

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
    title = "Verify .storage/ramses_cc has hvac_schema key"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 15: Verify hvac_schema key in .storage")

        storage = get_ramses_storage()
        ctx.check(
            "hvac_schema key exists in storage",
            "hvac_schema" in storage,
            f"keys={list(storage.keys())}",
        )

        hvac_schema = storage.get("hvac_schema", {})
        print(f"  hvac_schema: {json.dumps(hvac_schema)[:200]}")
