"""Recipe R19b: Invalid zone indices are rejected [A]."""

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


class R19bInvalidZoneIndicesAreRejectedA(Recipe):
    id = "R19b"
    seq = 200
    title = "Invalid zone indices are rejected [A]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 19b: Invalid zone indices (>0B) are rejected")

        # Inject a 30C9 packet with zone_idx 0C (invalid — max is 0B)
        invalid_trv = "04:200006"
        print(f"  Injecting 30C9 with invalid zone 0C from {invalid_trv}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": invalid_trv,
                    "code": "30C9",
                    "payload": "0C0708",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"  Inject failed: {e}")

        ctx.wait(5, "for scan engine to process")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_r19b = get_schema_retry()
        ctl_r19b = schema_r19b.get(CTL, {})
        zones_r19b = ctl_r19b.get("zones", {}) if isinstance(ctl_r19b, dict) else {}
        ctx.check(
            "Invalid zone 0C not created in schema",
            "0C" not in zones_r19b,
            f"zones={list(zones_r19b.keys())}",
        )
