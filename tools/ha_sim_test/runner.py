"""Test runner — setup, recipe execution, teardown/summary.

This is the orchestration layer that replaces the old monolithic
``async def main()``.  It:

1. Authenticates to ha-sim and starts the :class:`LogMonitor`.
2. Loads the mixed profile (100x speed) and activates devices.
3. Discovers and runs each registered recipe in ``seq`` order.
4. Collects the log report and prints the summary.

Usage::

    python3 -m ha_sim_test              # run all recipes
    python3 -m ha_sim_test R06 R29      # run specific recipes only
"""

from __future__ import annotations

import re
import sys
import time

from .base import RecipeContext
from .const import CO2, CTL, FAN, REM, TRV
from .helpers import (
    get_known_list,
    get_schema_retry,
    get_token,
    is_ha_ready,
    is_ramses_cc_loaded,
    log_section,
    wait,
    ws_send,
)
from .log_monitor import LogMonitor
from .registry import REGISTRY, discover_recipes

#: Path for the log report written at the end of each run.
REPORT_PATH = "/tmp/ha_sim_test_log_report.txt"


async def setup(ctx: RecipeContext) -> None:
    """Authenticate, load the mixed profile, and activate devices."""
    ctx.log_section("Setup: Load mixed profile (100x speed, heat + HVAC)")
    print("  Loading mixed profile via websocket...")
    try:
        result = await ws_send(
            ctx.token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,  # 100x faster heartbeats
                "preload_schema": True,
                "reload_ramses_cc": True,  # Reload to pick up new known_list
                "enable_auto_answer": True,
            },
        )
        print(f"  Profile loaded: {result.get('actions', [])[:3]}")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
        # Fall back: the profile may already be loaded

    wait(15, "for ramses_cc reload + init + config entry write")
    ctx.refresh_token()
    # Event-driven: wait for ramses_cc to be loaded instead of fixed 5s
    from .helpers import wait_for as _wait_for

    _wait_for(
        is_ramses_cc_loaded,
        timeout=15,
        interval=2,
        msg="for ramses_cc to initialize",
    )

    # Activate devices via websocket (faster — uses profile config)
    for dev_id, name in [
        (CTL, "CTL"),
        (TRV, "TRV"),
        (FAN, "FAN"),
        (REM, "REM"),
        (CO2, "CO2"),
    ]:
        print(f"  Activating {name} {dev_id}...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": dev_id,
                },
            )
            print(f"    {name} activated")
        except RuntimeError as e:
            # already_active is fine
            if "already_active" in str(e):
                print(f"    {name} already active")
            else:
                print(f"    {name} activate failed: {str(e)[:80]}")

    # Event-driven: wait for schema to be populated instead of fixed 10s
    _wait_for(
        lambda: len(get_schema_retry(max_tries=1)) > 5,
        timeout=15,
        interval=2,
        msg="for fast heartbeats + schema population (100x speed)",
    )

    # Check schema is populated (retry — profile reload may still be writing)
    schema = get_schema_retry()
    kl = get_known_list()
    print(f"  Schema keys: {list(schema.keys())}")
    print(f"  Known_list: {list(kl.keys())[:15]}")


async def teardown(
    ctx: RecipeContext,
    *,
    start_time: float,
    start_time_wall: float = 0,
) -> None:
    """Collect log report and print summary."""
    end_time = time.monotonic()
    elapsed = end_time - start_time

    # =====================================================================
    # LOG REPORT: Collect and analyse ha-sim logs from the entire test run
    # =====================================================================
    log_section("Log Report: ERROR/WARNING analysis")
    print("  Collecting logs since baseline...")
    assert ctx.log_monitor is not None
    log_data = ctx.log_monitor.collect()

    ctx.log_monitor.write_report(REPORT_PATH, log_data)
    print(f"  Report written to: {REPORT_PATH}")

    n_errors = len(log_data["errors"])
    n_warnings = len(log_data["warnings"])
    print(f"  Total log lines: {log_data['total_lines']}")
    print(f"  Unexpected errors: {n_errors}")
    print(f"  Unexpected warnings (ramses_cc/ramses_rf): {n_warnings}")

    if n_errors > 0:
        print("\n  --- Unexpected ERRORS (first 10) ---")
        for line in log_data["errors"][:10]:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            print(f"    {clean[:200]}")

    if n_warnings > 0:
        print("\n  --- Unexpected WARNINGS (first 10) ---")
        for line in log_data["warnings"][:10]:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            print(f"    {clean[:200]}")

    ctx.check(
        "No unexpected ERROR logs in full test run",
        n_errors == 0,
        f"{n_errors} unexpected errors (see {REPORT_PATH})",
    )
    ctx.check(
        "No unexpected ramses_cc/ramses_rf WARNING logs",
        n_warnings == 0,
        f"{n_warnings} unexpected warnings (see {REPORT_PATH})",
    )

    # =====================================================================
    # SUMMARY
    # =====================================================================
    log_section("SUMMARY")
    started_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(start_time_wall or start_time)
    )
    print(f"\n  Started:  {started_str}")
    print(f"  Elapsed:  {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    print(f"  Passed:   {ctx.passed}")
    print(f"  Failed:   {ctx.failed}")
    print(f"  Total:    {ctx.passed + ctx.failed}")
    print()

    # Per-recipe timing table
    if ctx.recipe_stats:
        print("  Per-recipe timing:")
        print(f"    {'Recipe':<8} {'Pass':>5} {'Fail':>5} {'Time':>8}  Title")
        print(f"    {'-' * 7} {'-' * 5} {'-' * 5} {'-' * 8}  {'-' * 30}")
        for rid, stats in ctx.recipe_stats.items():
            dur = stats.get("duration", 0.0)
            p = stats.get("passed", 0)
            f = stats.get("failed", 0)
            title = stats.get("title", "")[:40]
            print(f"    {rid:<8} {p:>5} {f:>5} {dur:>7.1f}s  {title}")
        print()

    for r in ctx.results:
        print(r)

    print(f"\n  Log report: {REPORT_PATH}")

    if ctx.failed > 0:
        print("\n  *** SOME TESTS FAILED ***")
        sys.exit(1)
    else:
        print("\n  *** ALL TESTS PASSED ***")
        sys.exit(0)


async def run(recipe_ids: list[str] | None = None) -> None:
    """Run the full test suite.

    :param recipe_ids: If given, run only these recipe ids (in seq order).
                       If None, run all registered recipes.
    """
    suite_start_mono = time.monotonic()
    suite_start_wall = time.time()

    # Discover all recipe modules so they self-register
    discover_recipes()
    print(f"  Discovered {len(REGISTRY)} recipes")

    # Select recipes to run
    if recipe_ids:
        recipes = []
        for rid in recipe_ids:
            r = REGISTRY.get(rid)
            if r is None:
                print(f"  WARNING: recipe {rid!r} not found, skipping")
                continue
            recipes.append(r)
    else:
        recipes = REGISTRY.sorted()

    # Authenticate
    print("Authenticating to ha-sim...")
    token = get_token()
    print(f"Token acquired: {token[:30]}...")

    # Build context
    log_monitor = LogMonitor()
    ctx = RecipeContext(token=token, log_monitor=log_monitor)

    # Start log monitor — captures baseline for error/warning detection
    log_monitor.start()

    # Setup phase
    await setup(ctx)

    # Run recipes with per-recipe timing + log attribution
    for recipe_cls in recipes:
        recipe = recipe_cls()
        print(f"\n  >>> Running {recipe.id} (seq={recipe.seq}): {recipe.title}")

        # Snapshot log baseline before recipe
        log_snapshot = log_monitor.snapshot()

        # Track check counts before/after for per-recipe accounting
        passed_before = ctx.passed
        failed_before = ctx.failed

        recipe_start = time.monotonic()
        try:
            await recipe.run(ctx)
        except Exception as e:
            ctx.check(
                f"Recipe {recipe.id} did not raise an unhandled exception",
                False,
                f"{type(e).__name__}: {e}",
            )
            print(f"  !!! Recipe {recipe.id} raised: {e}")
        recipe_elapsed = time.monotonic() - recipe_start

        # Record per-recipe stats
        ctx.recipe_stats[recipe.id] = {
            "passed": ctx.passed - passed_before,
            "failed": ctx.failed - failed_before,
            "duration": recipe_elapsed,
            "title": recipe.title,
        }

        # Per-recipe log check: collect logs since snapshot
        recipe_logs = log_monitor.record_recipe(recipe.id, log_snapshot)
        n_recipe_errors = len(recipe_logs["errors"])
        n_recipe_warnings = len(recipe_logs["warnings"])
        if n_recipe_errors or n_recipe_warnings:
            print(
                f"  [log] {recipe.id}: {n_recipe_errors} unexpected errors, "
                f"{n_recipe_warnings} unexpected warnings"
            )
            for line in recipe_logs["errors"][:3]:
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                print(f"    ERROR: {clean[:150]}")
            for line in recipe_logs["warnings"][:3]:
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                print(f"    WARN:  {clean[:150]}")

    # Teardown / summary
    await teardown(ctx, start_time=suite_start_mono, start_time_wall=suite_start_wall)
