"""Recipe R07b: Restart, verify HVAC survives, and device-loss scenario.

Merges the former R12 (HVAC device loss) into R07b so that the device-loss
test runs immediately after the restart+profile-reload, which guarantees
the mixed profile (FAN/REM/CO2) is active.  R12 previously assumed the
setup profile was still loaded, which broke when profile-stripping recipes
(R01, fresh_start recipes) ran before it on the same container.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_current_instance,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_ha_ready,
    wait_for_schema_populated,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R07bRestartAndVerifyHvacSurvives(Recipe):
    id = "R07b"
    seq = 70
    title = "Restart, HVAC survives + device-loss scenario"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 7b: Restart ha-sim, verify HVAC survives")

        # Capture logs before restart — docker restart wipes the log buffer
        ctx.log_monitor.capture_before_restart("R7b pre-restart")

        print("  Restarting ha-sim...")
        subprocess.run(
            ["docker", "restart", get_current_instance().name], capture_output=True
        )
        wait_for_ha_ready(timeout=30)

        # Reset log baseline — logs are wiped by the restart
        ctx.log_monitor.reset_baseline()

        # Re-authenticate
        print("  Re-authenticating...")
        ctx.refresh_token()
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
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
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
        wait_for_schema_populated(timeout=15)

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

        # ── Part 2: HVAC device-loss scenario (merged from R12) ──────
        # The mixed profile is now loaded and FAN/REM/CO2 are active,
        # so this is the safe point to test the device_simulator's
        # hvac_device_loss scenario (REM silences then restores).
        ctx.log_section("Recipe 7b: HVAC device-loss scenario (REM 37:170000)")

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

        # Wait for loss phase (10s scenario time, ~0.1s real at 100x speed)
        ctx.wait(3, "for REM loss phase")

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
        storage_loss = get_ramses_storage()
        hvac_schema_loss = storage_loss.get("hvac_schema", {})
        fan_hvac_loss = hvac_schema_loss.get(FAN, {})
        remotes_during = fan_hvac_loss.get("remotes", [])
        ctx.check(
            "HVAC schema preserved during REM loss",
            REM in remotes_during,
            f"remotes={remotes_during}",
        )

        # Wait for restore phase (20s scenario time, ~0.2s real at 100x speed)
        ctx.wait(3, "for REM restore phase")

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

        # ── Part 3: No resurrection after restart (merged from R05) ──
        ctx.log_section("Recipe 7b: No resurrection after restart")
        kl_before_remove = get_known_list()
        if TRV in kl_before_remove or CTL in kl_before_remove:
            print(f"  Removing TRV {TRV} and CTL {CTL}...")
            for dev_id, name in [(TRV, "TRV"), (CTL, "CTL")]:
                try:
                    call_service(
                        ctx.token, "ramses_cc", "remove_device", {"device_id": dev_id}
                    )
                except RuntimeError:
                    pass

            def _devices_removed() -> bool:
                kl = get_known_list()
                return TRV not in kl and CTL not in kl

            wait_for(
                _devices_removed,
                timeout=10,
                interval=1,
                msg="for TRV+CTL removal to propagate",
            )

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=8, msg="for sync_learned_topology")

        kl_post_check = get_known_list()
        ctx.check(
            "TRV not resurrected in known_list",
            TRV not in kl_post_check,
            f"known_list still has {TRV}",
        )
        ctx.check(
            "CTL not resurrected in known_list",
            CTL not in kl_post_check,
            f"known_list still has {CTL}",
        )
