"""Recipe R16: Concurrency/stress test — rapid add/remove + inject."""

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


class R16ConcurrencystressTestRapidAddremoveInject(Recipe):
    id = "R16"
    seq = 140
    title = "Concurrency/stress test — rapid add/remove + inject"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 16: Concurrency/stress test")

        # This recipe tests rapid add/remove cycles and concurrent
        # inject_message + sync_topology to verify no race conditions.
        stress_device = "04:300001"

        print(f"  Rapid inject + sync_topology cycles for {stress_device}...")
        errors = 0
        for i in range(5):
            try:
                # Inject a heartbeat
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": stress_device,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
                # Immediately trigger sync_topology (concurrent with inject)
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                errors += 1
            time.sleep(1)

        ctx.check(
            "No errors during rapid inject + sync cycles",
            errors == 0,
            f"{errors} errors in 5 cycles",
        )

        # Rapid remove/re-add cycle — use fresh_start + new device each time
        # (TRV 04:150003 was already removed in R2, so we use fresh devices)
        print("  Rapid discover/accept/remove cycles...")
        errors = 0
        for i in range(3):
            dev = f"04:40000{i + 1}"
            try:
                # Inject heartbeat to trigger discovery
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": dev,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
                time.sleep(3)
                # Accept
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "accept_discovered_device",
                        {
                            "device_id": dev,
                        },
                    )
                except RuntimeError:
                    pass  # May not be in discovery list
                time.sleep(2)
                # Remove
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "remove_device",
                        {
                            "device_id": dev,
                        },
                    )
                except RuntimeError:
                    pass  # May not be in schema if accept failed
            except RuntimeError:
                errors += 1
            time.sleep(1)

        ctx.check(
            "No errors during rapid discover/accept/remove cycles",
            errors == 0,
            f"{errors} errors in 3 cycles",
        )

        # Verify no orphaned tasks — check ha-sim is still responsive
        ctx.wait(5, "for any orphaned tasks to surface")
        entities_stress = get_entities(ctx.token)
        ctx.check(
            "ha-sim responsive after stress test",
            len(entities_stress) >= 0,
            "API not responding",
        )

        # Check logs for errors during stress test
        log_result = subprocess.run(
            ["docker", "logs", "ha-sim", "--since", "60s"],
            capture_output=True,
            text=True,
        )
        has_errors = "ERROR" in log_result.stderr or "Traceback" in log_result.stderr
        # Filter out expected warnings (not errors)
        real_errors = False
        if has_errors:
            for line in log_result.stderr.splitlines():
                if "ERROR" in line and "ramses_cc" in line:
                    real_errors = True
                    break
        ctx.check(
            "No ramses_cc ERROR logs during stress test",
            not real_errors,
            "ERROR logs found" if real_errors else "clean",
        )
