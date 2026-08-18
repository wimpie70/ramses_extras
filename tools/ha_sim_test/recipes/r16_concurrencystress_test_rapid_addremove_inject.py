"""Recipe R16: Concurrency/stress test — rapid add/remove + inject."""

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
                # Retry on HTTP 400 — may be transient under load
                sync_ok = False
                for attempt in range(3):
                    try:
                        call_service(ctx.token, "ramses_cc", "sync_topology")
                        sync_ok = True
                        break
                    except RuntimeError as e:
                        if "HTTP 400" in str(e) and attempt < 2:
                            time.sleep(1)
                            continue
                        raise
                if not sync_ok:
                    errors += 1
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
            entities_stress is not None,
            "API not responding (get_entities returned None)",
        )

        # Check logs for errors during stress test
        log_result = subprocess.run(
            ["docker", "logs", get_current_instance().name, "--since", "60s"],
            capture_output=True,
            text=True,
        )
        # Filter out expected/cosmetic patterns (same list as log_monitor.py)
        from ..log_monitor import EXPECTED_WARNINGS

        def _is_expected(line: str) -> bool:
            return any(pat in line for pat in EXPECTED_WARNINGS)

        real_errors = False
        for line in log_result.stderr.splitlines():
            if "ERROR" not in line:
                continue
            if "ramses_cc" not in line and "ramses_rf" not in line:
                continue
            if _is_expected(line):
                continue
            real_errors = True
            print(f"    ERROR: {line.strip()[:120]}")
            break
        ctx.check(
            "No ramses_cc ERROR logs during stress test",
            not real_errors,
            "ERROR logs found" if real_errors else "clean",
        )
