"""Recipe R26: Phase 3c — missing _class detection."""

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


class R26Phase3cMissingClassDetection(Recipe):
    id = "R26"
    seq = 260
    title = "Phase 3c — missing _class detection"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 26: Phase 3c — missing _class detection")

        # The missing_class check flags devices where the scan engine has a
        # likely_type but the schema entry has no _class.  From R19, TRVs
        # 04:200002-005 were accepted from discovery and added to the schema
        # without _class.  However, subsequent profile reloads (R22, R23)
        # wiped them from the scan engine, so we re-inject a 30C9 packet
        # to get 04:200002 back into the scan engine before checking.

        print("  Re-injecting 30C9 from 04:200002 to re-populate scan engine...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": "04:200002",
                    "code": "30C9",
                    "payload": "020708",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for scan engine to process 30C9")

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for missing_class detection")

        # Check: the log should contain the missing_class INFO message.
        # We check the log instead of the persistent notification because
        # the periodic discovery checkpoint may dismiss the notification
        # between sync_topology and our check (if the TRVs have left the
        # scan engine by then).
        log_url = HA_URL + "/api/error_log"
        req = urllib.request.Request(
            log_url,
            headers={"Authorization": f"Bearer {ctx.token}"},
        )
        log_text = urllib.request.urlopen(req).read().decode()
        ctx.check(
            "Log contains missing _class detection for 04:200002",
            "missing _class for 04:200002" in log_text,
            "no missing _class log entry for 04:200002",
        )
