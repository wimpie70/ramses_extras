"""Recipe R07b: Restart and verify HVAC survives."""

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


class R07bRestartAndVerifyHvacSurvives(Recipe):
    id = "R07b"
    seq = 70
    title = "Restart and verify HVAC survives"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 7b: Restart ha-sim, verify HVAC survives")

        # Capture logs before restart — docker restart wipes the log buffer
        ctx.log_monitor.capture_before_restart("R7b pre-restart")

        print("  Restarting ha-sim...")
        subprocess.run(["docker", "restart", "ha-sim"], capture_output=True)
        ctx.wait(20, "for ha-sim to start up")

        # Reset log baseline — logs are wiped by the restart
        ctx.log_monitor.reset_baseline()

        # Re-authenticate
        print("  Re-authenticating...")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Reload mixed profile — docker restart may reload a stale profile
        # (e.g. fresh_start from a later recipe in a previous test run).
        # Reloading ensures FAN/REM/CO2 are in the known_list and schema.
        print("  Reloading mixed profile after restart...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Mixed profile reload failed: {e}")
        ctx.wait(15, "for ramses_cc reload with mixed profile")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Re-activate devices (profile reload stops all active devices)
        for dev_id, name in [(FAN, "FAN"), (REM, "REM"), (CO2, "CO2")]:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/"
                        "activate_profile_device",
                        "device_id": dev_id,
                    },
                )
                print(f"    {name} activated")
            except RuntimeError:
                pass
        ctx.wait(10, "for heartbeats + schema population")

        schema_after_restart = get_schema_retry()
        fan_after_restart = FAN in schema_after_restart
        ctx.check(
            "FAN in schema after restart",
            fan_after_restart,
            f"schema keys={list(schema_after_restart.keys())}",
        )

        storage_after = get_ramses_storage()
        hvac_after = storage_after.get("hvac_schema", {})
        ctx.check(
            "hvac_schema preserved in storage after restart",
            bool(hvac_after),
            f"hvac_schema={json.dumps(hvac_after)[:200]}",
        )
