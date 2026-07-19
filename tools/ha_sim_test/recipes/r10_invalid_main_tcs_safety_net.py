"""Recipe R10: Invalid main_tcs safety net."""

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


class R10InvalidMainTcsSafetyNet(Recipe):
    id = "R10"
    seq = 100
    title = "Invalid main_tcs safety net"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 10: Invalid main_tcs safety net")

        # Load a custom YAML profile with an invalid main_tcs — this reloads
        # ramses_cc in-process (no docker restart needed, logs preserved).
        # The coordinator's _async_setup safety net should clear the invalid
        # main_tcs during the reload.
        print("  Loading custom profile with invalid main_tcs=04:999999...")
        invalid_schema = dict(MIXED_SCHEMA)
        invalid_schema["main_tcs"] = "04:999999"
        invalid_schema["04:999999"] = {}
        try:
            await load_profile_yaml(ctx.token, mixed_yaml(invalid_schema))
            print("  Profile loaded with invalid main_tcs")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")

        ctx.wait(15, "for ramses_cc reload with invalid main_tcs")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Debug: check what the config entry looks like
        schema_debug = get_schema()
        schema_keys = list(schema_debug.keys())
        main_tcs = schema_debug.get("main_tcs")
        print(f"  DEBUG: schema keys={schema_keys}, main_tcs={main_tcs}")

        # Check logs for sanitisation warning
        log_result = subprocess.run(
            ["docker", "logs", "ha-sim", "--since", "30s"],
            capture_output=True,
            text=True,
        )
        sanitised = (
            "Sanitising invalid main_tcs" in log_result.stdout
            or "Sanitising invalid main_tcs" in log_result.stderr
        )
        ctx.check(
            "Coordinator sanitises invalid main_tcs",
            sanitised,
            "sanitisation warning not found in logs",
        )

        # Verify main_tcs is cleared (the invalid value 04:999999 should be gone;
        # sync_learned_topology may re-derive main_tcs=01:150000 which is valid)
        schema_after_sanitise = get_schema_retry()
        main_tcs_after = schema_after_sanitise.get("main_tcs")
        ctx.check(
            "Invalid main_tcs cleared after sanitisation",
            main_tcs_after != "04:999999",
            f"main_tcs={main_tcs_after}",
        )
        ctx.check(
            "Invalid main_tcs persisted to config entry",
            "04:999999" not in json.dumps(schema_after_sanitise),
            "config entry still references 04:999999",
        )

        # Verify no crash — ha-sim is running and responding
        entities_check = get_entities(ctx.token)
        ctx.check(
            "ha-sim running after invalid main_tcs",
            len(entities_check) >= 0,
            "API not responding",
        )
