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
    python3 -m ha_sim_test --parallel 2 # run across 2 containers
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from .base import RecipeContext
from .colors import bold, color_status, green, red
from .const import MQTT_BROKER_URL, InstanceConfig, make_instances
from .helpers import (
    delete_test_profiles,
    get_known_list,
    get_schema_retry,
    get_token,
    is_ha_ready,
    is_ramses_cc_loaded,
    log_section,
    set_current_instance,
    wait,
    wait_for,
    ws_send,
)
from .log_monitor import LogMonitor
from .registry import REGISTRY, discover_recipes

#: Directory for persistent test reports (keeps the last N per container).
REPORTS_DIR = Path(__file__).parent / "reports"

#: How many report files to keep per container (older ones are pruned).
MAX_REPORTS_PER_CONTAINER = 5


def _report_path(container_name: str) -> Path:
    """Return a timestamped report path for *container_name*.

    Also prunes older reports for the same container, keeping only the
    last ``MAX_REPORTS_PER_CONTAINER`` files.

    :param container_name: Container name (e.g. ``"ha-sim"`` or
        ``"ha-sim-2"``).
    :return: Absolute path for the new report file.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"log_report_{container_name}_{ts}.txt"

    # Prune: keep only the newest MAX_REPORTS_PER_CONTAINER per container
    pattern = f"log_report_{container_name}_*.txt"
    existing = sorted(REPORTS_DIR.glob(pattern))
    if len(existing) >= MAX_REPORTS_PER_CONTAINER:
        for old in existing[: -MAX_REPORTS_PER_CONTAINER + 1]:
            old.unlink(missing_ok=True)

    return path


async def setup(ctx: RecipeContext) -> None:
    """Authenticate, load the mixed profile, and activate devices."""
    inst = ctx.instance
    ctx.log_section(
        f"Setup [{inst.name}]: Load mixed profile (100x speed, heat + HVAC)"
    )
    print(f"  Target: {inst.ha_url} (container: {inst.name}, hgi: {inst.hgi_id})")

    # Publish retained "online" message for this instance's HGI topic.
    # ramses_rf's MQTT transport requires this to set _topic_pub.
    try:
        from .mqtt_setup import publish_retained_online_messages

        publish_retained_online_messages([inst.hgi_id])
    except Exception as err:  # noqa: BLE001
        print(
            f"  ERROR: could not publish retained online message: {err}\n"
            "  The MQTT broker was reachable but the publish failed. Aborting."
        )
        sys.exit(1)

    # Reset stale state: delete .storage/ramses_cc so ramses_cc starts fresh.
    # The profile load updates config entry options, but .storage/ramses_cc
    # may have stale schema from previous recipes (e.g. R58/R59 strip it).
    # Without this, warm containers have dirty state (main_tcs=null, etc).
    try:
        subprocess.run(
            ["docker", "exec", inst.name, "rm", "-f", "/config/.storage/ramses_cc"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass  # Container might not exist yet on first run

    print("  Loading mixed profile via websocket...")
    # ramses_extras websocket commands may not be registered yet on a cold
    # start (takes ~60s after HA is ready).  Retry with backoff.
    profile_loaded = False
    for attempt in range(10):
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
            profile_loaded = True
            break
        except RuntimeError as e:
            err = str(e)
            if (
                "unknown_command" in err
                or "not_ready" in err
                or "Simulator not initialized" in err
            ):
                # ramses_extras not ready yet — wait and retry
                if attempt < 9:
                    import asyncio as _asyncio

                    delay = min(5 + attempt * 5, 15)  # 5,10,15,15,15,...
                    print(
                        f"  ramses_extras not ready (attempt {attempt + 1}), "
                        f"retrying in {delay}s..."
                    )
                    await _asyncio.sleep(delay)
                    ctx.refresh_token()
                    continue
            print(f"  Profile load attempt {attempt + 1} failed: {err}")
            if attempt < 9:
                import asyncio as _asyncio

                await _asyncio.sleep(2)
    if not profile_loaded:
        print("  Profile load failed after retries — using existing profile")

    wait_for(is_ramses_cc_loaded, timeout=20, msg="for ramses_cc reload + init")
    ctx.refresh_token()

    # Activate devices via websocket (faster — uses profile config)
    for dev_id, name in [
        (inst.ctl, "CTL"),
        (inst.trv, "TRV"),
        (inst.fan, "FAN"),
        (inst.rem, "REM"),
        (inst.co2, "CO2"),
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
    from .helpers import wait_for_schema_populated

    wait_for_schema_populated(min_keys=5, timeout=15)

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
    # FINAL CLEANUP: delete any remaining test profiles
    # =====================================================================
    try:
        ctx.refresh_token()
        n = await delete_test_profiles(ctx.token)
        if n:
            print(f"  Final cleanup: removed {n} test profile(s)")
    except Exception:
        pass

    # =====================================================================
    # LOG REPORT: Collect and analyse ha-sim logs from the entire test run
    # =====================================================================
    log_section("Log Report: ERROR/WARNING analysis")
    print("  Collecting logs since baseline...")
    assert ctx.log_monitor is not None
    log_data = ctx.log_monitor.collect()

    report_path = _report_path(ctx.instance.name)
    ctx.log_monitor.write_report(str(report_path), log_data)
    print(f"  Report written to: {report_path}")

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
        f"{n_errors} unexpected errors (see {report_path})",
    )
    ctx.check(
        "No unexpected ramses_cc/ramses_rf WARNING logs",
        n_warnings == 0,
        f"{n_warnings} unexpected warnings (see {report_path})",
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
    print(f"  Passed:   {green(str(ctx.passed))}")
    print(f"  Failed:   {red(str(ctx.failed)) if ctx.failed else str(ctx.failed)}")
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
            fail_str = red(str(f)) if f else str(f)
            print(f"    {rid:<8} {p:>5} {fail_str:>5} {dur:>7.1f}s  {title}")
        print()

    for r in ctx.results:
        print(r)

    print(f"\n  Log report: {report_path}")

    if ctx.failed > 0:
        print(f"\n  {bold(red('*** SOME TESTS FAILED ***'))}")
        sys.exit(1)
    else:
        print(f"\n  {bold(green('*** ALL TESTS PASSED ***'))}")
        sys.exit(0)


async def run(
    recipe_ids: list[str] | None = None,
    *,
    instance: InstanceConfig | None = None,
) -> None:
    """Run the full test suite on a single container.

    :param recipe_ids: If given, run only these recipe ids (in seq order).
                       If None, run all registered recipes.
    :param instance: Instance config (container name, port, URLs).  Defaults
                     to the standard ``ha-sim`` instance (backward compatible).
    """
    inst = instance or InstanceConfig.default()
    suite_start_mono = time.monotonic()
    suite_start_wall = time.time()

    # Discover all recipe modules so they self-register
    discover_recipes(__name__.rsplit(".", 1)[0] + ".recipes")
    print(f"  Discovered {len(REGISTRY)} recipes")

    # Verify the MQTT broker is reachable — ramses_cc's MQTT transport
    # cannot function without it, and all recipes will fail with
    # cascading errors if it's down.
    from .mqtt_setup import is_mqtt_broker_ready

    if not is_mqtt_broker_ready():
        print(
            f"\n  ERROR: MQTT broker at {MQTT_BROKER_URL} is not reachable.\n"
            "  Start it via docker compose:\n"
            "    cd ~/docker_files/ha-sim && \\\n"
            "    docker compose -f docker-compose.mqtt.yml up -d\n"
            "  Or run a standalone mosquitto container:\n"
            "    docker run -d --name ha-sim-mqtt -p 1884:1884 \\\n"
            "    eclipse-mosquitto:latest \\\n"
            "    sh -c \"printf 'listener 1884 0.0.0.0\\nallow_anonymous true\\n' \\\n"
            '    > /tmp/mosquitto.conf && mosquitto -c /tmp/mosquitto.conf"\n'
            "  Aborting."
        )
        sys.exit(1)
    print(f"  MQTT broker at {MQTT_BROKER_URL} is reachable")

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
    print(f"Authenticating to {inst.name} ({inst.ha_url})...")
    set_current_instance(inst)
    token = get_token()
    print(f"Token acquired: {token[:30]}...")

    # Build context (sets contextvar via __post_init__)
    log_monitor = LogMonitor()
    ctx = RecipeContext(token=token, log_monitor=log_monitor, instance=inst)

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

        # Clean up test profiles created by this recipe to prevent
        # user_profiles.json from growing unboundedly across runs.
        try:
            ctx.refresh_token()
            n = await delete_test_profiles(ctx.token)
            if n:
                print(f"  Cleaned up {n} test profile(s)")
        except Exception:
            pass

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

        # Running P:/F: tally after each recipe
        p_str = green(f"P:{ctx.passed:>3}")
        f_str = red(f"F:{ctx.failed:>3}") if ctx.failed else f"F:{ctx.failed:>3}"
        print(f"  [{p_str} {f_str}]  {recipe.id} done ({recipe_elapsed:.1f}s)")

    # Teardown / summary
    await teardown(ctx, start_time=suite_start_mono, start_time_wall=suite_start_wall)
