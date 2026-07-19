"""Recipe R12: HVAC device loss scenario."""

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


class R12HvacDeviceLossScenario(Recipe):
    id = "R12"
    seq = 130
    title = "HVAC device loss scenario"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 12: HVAC device loss scenario")

        # This recipe tests the hvac_device_loss scenario — a REM silences
        # then restores, and we verify the FAN stays available throughout.
        print("  Starting hvac_device_loss scenario for REM 37:170000...")
        try:
            result = call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_run_scenario",
                {
                    "scenario_type": "hvac_device_loss",
                    "params": {
                        "device_id": REM,
                        "loss_after": 10,
                        "restore_after": 20,
                    },
                },
            )
            print(f"  Scenario started: {result}")
        except RuntimeError as e:
            print(f"  Scenario start failed: {str(e)[:80]}")

        # Check FAN entity before loss
        entities_before_loss = get_entities(ctx.token)
        fan_entity_before = None
        for s in entities_before_loss:
            if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
                fan_entity_before = s
                break
        fan_eid = fan_entity_before["entity_id"] if fan_entity_before else "None"
        print(f"  FAN entity before loss: {fan_eid}")

        # Wait for loss phase (10s) + some margin
        ctx.wait(15, "for REM loss phase")

        # Check FAN entity during loss
        entities_during_loss = get_entities(ctx.token)
        fan_entity_during = None
        for s in entities_during_loss:
            if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
                fan_entity_during = s
                break
        ctx.check(
            "FAN entity available during REM loss",
            fan_entity_during is not None,
            "FAN entity not found during loss",
        )

        # Check HVAC schema preserved during loss (use hvac_schema from .storage)
        storage_r12 = get_ramses_storage()
        hvac_schema_r12 = storage_r12.get("hvac_schema", {})
        fan_hvac_r12 = hvac_schema_r12.get(FAN, {})
        remotes_during = fan_hvac_r12.get("remotes", [])
        ctx.check(
            "HVAC schema preserved during REM loss",
            REM in remotes_during,
            f"remotes={remotes_during}",
        )

        # Wait for restore phase (20s) + some margin
        ctx.wait(15, "for REM restore phase")

        # Check FAN entity after restore
        entities_after_restore = get_entities(ctx.token)
        fan_entity_after = None
        for s in entities_after_restore:
            if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
                fan_entity_after = s
                break
        ctx.check(
            "FAN entity available after REM restore",
            fan_entity_after is not None,
            "FAN entity not found after restore",
        )

        # Stop the scenario
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_stop_scenario",
                {
                    "device_id": REM,
                },
            )
            print("  Scenario stopped")
        except RuntimeError:
            pass
