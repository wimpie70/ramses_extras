"""Parallel test runner — distributes recipes across multiple ha-sim containers.

Each container gets its own:
- Port (8124, 8125, 8126, ...)
- Config directory (config, config-2, config-3, ...)
- MQTT topic namespace (via unique HGI ID: 18:001234, 18:002234, ...)
- InstanceConfig propagated via contextvar

The runner:
1. Clones the ha-sim config dir for each parallel instance
2. Patches the port and MQTT URL in each clone
3. Starts the containers via docker-compose
4. Distributes recipes across containers (respecting dependency chains)
5. Runs each container's recipe group in parallel via asyncio.gather
6. Merges results and prints a combined summary
"""

from __future__ import annotations

import asyncio
import functools
import os
import subprocess
import sys
import time
from contextvars import Token
from dataclasses import dataclass, field
from typing import Any

from .base import RecipeContext
from .colors import bold, color_status, green, red
from .const import MQTT_BROKER_URL, InstanceConfig, make_instances
from .dashboard import LiveDashboard
from .helpers import (
    _current_instance as _current_instance_var,
)
from .helpers import (
    delete_test_profiles,
    get_token,
    is_ha_ready,
    is_ramses_extras_ready,
    log_section,
    set_current_instance,
    wait_for,
)
from .log_monitor import LogMonitor
from .mqtt_setup import publish_retained_online_messages
from .registry import REGISTRY, discover_recipes
from .runner import setup, teardown
from .timing_store import TimingStore

#: Path to ramses_cc custom_components (bind-mounted into each container).
_RAMSES_CC_PATH = "/home/willem/dev/ramses_cc/custom_components/ramses_cc"

#: Path to ramses_extras custom_components (bind-mounted into each container).
_RAMSES_EXTRAS_PATH = "/home/willem/dev/ramses_extras/custom_components/ramses_extras"

#: docker-compose template for parallel instances (2+).
COMPOSE_TEMPLATE = """\
services:
{services}
"""

SERVICE_TEMPLATE = """\
  {name}:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: {name}
    ports:
      - "{port}:{port}"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - TZ=Europe/Amsterdam
      - HASSIO_PORT={port}
      - PYTHONPATH=/config/ramses_rf/src
      - RAMSES_SIM_HGI_ID={hgi_id}
    volumes:
      - {config_dir}:/config
      - /home/willem/dev/ramses_rf:/config/ramses_rf
      - {ramses_cc_path}:/config/custom_components/ramses_cc
      - {ramses_extras_path}:/config/custom_components/ramses_extras
"""


# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------
def clone_config_dir(inst: InstanceConfig, *, force: bool = False) -> None:
    """Clone the ha-sim config dir for a parallel instance.

    Copies the base config dir to ``config-{i}``, then patches:
    - Port in ``configuration.yaml``
    - MQTT URL in ``.storage/core.config_entries``

    Uses a helper docker container (alpine) for the copy because some
    files in ``.storage/`` are root-owned inside the HA container and
    not readable from the host.
    """
    if os.path.exists(inst.config_dir) and not force:
        print(f"  [{inst.name}] Config dir exists: {inst.config_dir} (reusing)")
        return

    base_dir = InstanceConfig.default().config_dir
    print(f"  [{inst.name}] Cloning {base_dir} -> {inst.config_dir}")

    # If force=True and dir exists, remove it first (use docker for root-owned files)
    if os.path.exists(inst.config_dir):
        parent = os.path.dirname(inst.config_dir)
        dirname = os.path.basename(inst.config_dir)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{parent}:/parent",
                "alpine",
                "sh",
                "-c",
                f"rm -rf /parent/{dirname}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    os.makedirs(inst.config_dir, exist_ok=True)

    # Use a docker container to copy as root (handles root-owned .storage files)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{base_dir}:/src:ro",
            "-v",
            f"{inst.config_dir}:/dst",
            "alpine",
            "sh",
            "-c",
            # Copy everything except logs, caches, and the recorder DB
            # (each container creates its own fresh DB on first start)
            "cp -a /src/. /dst/ && "
            "rm -rf /dst/home-assistant.log* /dst/ramses.db* "
            "/dst/home-assistant_v2.db* "
            "/dst/__pycache__ /dst/.cache 2>/dev/null; "
            "true",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to clone config dir: {result.stderr[:200]}")
    patch_port_in_config(inst)
    patch_mqtt_url_in_config(inst)


def patch_port_in_config(inst: InstanceConfig) -> None:
    """Patch the HA port in the cloned configuration.yaml and .storage/http.

    Since HA 2026.8, the HTTP server port is stored in .storage/http (migrated
    from YAML).  We patch both files to cover all HA versions.
    """
    config_yaml = f"{inst.config_dir}/configuration.yaml"
    storage_http = f"{inst.config_dir}/.storage/http"
    files_to_patch = []
    if os.path.exists(config_yaml):
        files_to_patch.append("/config/configuration.yaml")
    if os.path.exists(storage_http):
        files_to_patch.append("/config/.storage/http")
    if not files_to_patch:
        return
    # Use alpine sed for simple string replace (8124 -> new port)
    files_arg = " ".join(files_to_patch)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{inst.config_dir}:/config",
            "alpine",
            "sh",
            "-c",
            f"sed -i 's/8124/{inst.port}/g' {files_arg} && "
            f"echo 'Patched port to {inst.port} in {files_arg}'",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"  [{inst.name}] WARNING: patch_port failed: {result.stderr[:100]}")
    else:
        print(f"  [{inst.name}] Patched port -> {inst.port}")


def patch_mqtt_url_in_config(inst: InstanceConfig) -> None:
    """Patch the ramses_cc serial_port MQTT URL in the cloned config entries.

    Also patches the HA MQTT integration's broker address to use
    ``host.docker.internal`` instead of ``localhost`` so that parallel
    containers (which use bridge networking) can reach the host's MQTT
    broker.
    """
    ce_path = f"{inst.storage_path}/core.config_entries"
    if not os.path.exists(ce_path):
        return
    # Use python container to patch JSON (files are root-owned from the clone)
    mqtt_url = inst.mqtt_url.replace("'", "\\'")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{inst.config_dir}:/config",
            "python:3.12-slim",
            "python3",
            "-c",
            f"import json; "
            f"p='/config/.storage/core.config_entries'; "
            f"d=json.load(open(p)); "
            f"entries = d.get('data',{{}}).get('entries',[]); "
            f"[e.get('options',{{}}).get('serial_port',{{}}).update("
            f"{{'port_name': '{mqtt_url}'}}) "
            f"for e in entries if e.get('domain')=='ramses_cc']; "
            f"[e.get('data',{{}}).update({{'broker': 'host.docker.internal'}}) "
            f"or print('Patched HA MQTT broker -> host.docker.internal') "
            f"for e in entries if e.get('domain')=='mqtt' "
            f"and e.get('data',{{}}).get('broker')=='localhost']; "
            f"json.dump(d, open(p,'w'), indent=2); "
            f"print('Patched MQTT URL')",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"  [{inst.name}] WARNING: patch_mqtt_url failed: {result.stderr[:100]}")
    else:
        print(f"  [{inst.name}] Patched MQTT URL -> {inst.mqtt_url}")


def generate_compose_file(instances: list[InstanceConfig]) -> str:
    """Generate a docker-compose.yml for parallel instances (2+)."""
    services = []
    for inst in instances[1:]:  # skip instance 1 (already running as ha-sim)
        services.append(
            SERVICE_TEMPLATE.format(
                name=inst.name,
                port=inst.port,
                hgi_id=inst.hgi_id,
                config_dir=inst.config_dir,
                ramses_cc_path=_RAMSES_CC_PATH,
                ramses_extras_path=_RAMSES_EXTRAS_PATH,
            )
        )
    compose_path = "/home/willem/docker_files/ha-sim/docker-compose.parallel.yml"
    with open(compose_path, "w") as f:
        f.write(COMPOSE_TEMPLATE.format(services="\n".join(services)))
    return compose_path


# Path to the HA config switch script
_HA_CONFIG_SCRIPT = os.path.join(
    os.path.dirname(__file__), "ha_configs", "switch_ha_config.sh"
)


def _switch_ha_config(profile: str, container: str = "ha-sim") -> None:
    """Switch ha-sim to minimal/full config and restart it.

    No-op if the switch script doesn't exist or the container is already
    in the requested mode (avoids an unnecessary restart).
    """
    if not os.path.isfile(_HA_CONFIG_SCRIPT):
        return

    # Check if already in the requested mode by comparing configuration.yaml
    config_dir = os.path.dirname(_HA_CONFIG_SCRIPT)
    target_config = os.path.join(config_dir, f"configuration.{profile}.yaml")
    if os.path.isfile(target_config):
        result = subprocess.run(
            ["docker", "exec", container, "cat", "/config/configuration.yaml"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            with open(target_config) as f:
                target_content = f.read()
            # Normalize whitespace for comparison
            current_norm = "".join(result.stdout.split())
            target_norm = "".join(target_content.split())
            if current_norm == target_norm:
                print(f"  {container} already in '{profile}' mode, skipping switch")
                return

    print(f"  Switching {container} to '{profile}' config...")
    result = subprocess.run(
        [_HA_CONFIG_SCRIPT, profile, container],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"  WARNING: config switch to '{profile}' failed: {result.stderr[:200]}")
    else:
        for line in result.stdout.strip().splitlines():
            if line.startswith("  "):
                print(f"  {line.strip()}")
        print(f"  {container} is now in '{profile}' mode")


async def ensure_containers(instances: list[InstanceConfig]) -> None:
    """Start all parallel containers.

    Instance 1 (ha-sim) is assumed to be already running, but we verify
    it's reachable and wait up to 30s if not.  Instances 2+ are cloned
    from the base config and started via docker-compose.
    If a container is already running and healthy, it is reused as-is
    (warm start — skips clone and HA readiness wait).

    **Optimization**: Parallel containers are started via a single
    ``docker compose up -d`` call, then all readiness checks run in
    parallel via ``asyncio.gather``.  This saves ~30-60s vs sequential
    startup (4 containers × 15s startup → 1× 15s startup).
    """
    log_section("Parallel: Starting containers")

    # Publish retained "online" messages to the MQTT broker for each HGI
    # topic.  ramses_rf's MQTT transport requires this to set _topic_pub
    # (the publish topic).  Without it, the first publish fails.
    hgi_ids = [inst.hgi_id for inst in instances]
    try:
        publish_retained_online_messages(hgi_ids)
        print(f"  Published retained 'online' messages for {len(hgi_ids)} HGI(s)")
    except Exception as err:  # noqa: BLE001
        print(
            f"  ERROR: could not publish retained online messages: {err}\n"
            "  The MQTT broker was reachable but the publish failed. Aborting."
        )
        sys.exit(1)

    # Verify instance 1 (ha-sim) is reachable — it's not started by us
    inst1 = instances[0]
    print(f"  [{inst1.name}] Verifying HA is reachable on port {inst1.port}...")

    def _ready1(inst: InstanceConfig = inst1) -> bool:
        token = set_current_instance(inst)
        try:
            return is_ha_ready()
        finally:
            _current_instance_reset(token)

    ready1 = wait_for(
        _ready1, timeout=30, interval=2, msg=f"[{inst1.name}] HA ready", floor=10.0
    )
    if not ready1:
        raise RuntimeError(
            f"[{inst1.name}] is not reachable on port {inst1.port}. "
            f"Start it first: cd ~/docker_files/ha-sim && docker compose up -d"
        )
    print(f"  [{inst1.name}] HA is ready")

    parallel_instances = instances[1:]
    if not parallel_instances:
        return

    # Check which containers are already running
    already_running: set[str] = set()
    for inst in parallel_instances:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", inst.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            already_running.add(inst.name)

    # Clone config dirs only for containers that aren't already running
    for inst in parallel_instances:
        if inst.name in already_running:
            print(f"  [{inst.name}] Container already running (warm start)")
        else:
            clone_config_dir(inst, force=True)

    # Generate and start docker-compose
    compose_path = generate_compose_file(instances)
    print(f"  Generated: {compose_path}")
    result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "up", "-d"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"  docker compose up failed: {result.stderr[:200]}")
        raise RuntimeError(
            f"Failed to start parallel containers: {result.stderr[:200]}"
        )
    print(f"  Started {len(parallel_instances)} parallel container(s)")

    # Wait for all containers to be ready in parallel (optimization: saves ~30-60s)
    async def _wait_for_ready(inst: InstanceConfig) -> bool:
        """Wait for a single container to be ready (async wrapper for wait_for)."""
        print(f"  [{inst.name}] Waiting for HA to be ready on port {inst.port}...")

        def _ready() -> bool:
            token = set_current_instance(inst)
            try:
                return is_ha_ready()
            finally:
                _current_instance_reset(token)

        ready = wait_for(
            _ready, timeout=120, interval=3, msg=f"[{inst.name}] HA ready", floor=15.0
        )
        if not ready:
            raise RuntimeError(f"[{inst.name}] HA did not become ready within 120s")
        print(f"  [{inst.name}] HA is ready")
        return True

    # Wait for all in parallel
    await asyncio.gather(*[_wait_for_ready(inst) for inst in parallel_instances])


def cleanup_containers(
    instances: list[InstanceConfig], *, remove_configs: bool = False
) -> None:
    """Stop and remove parallel containers (instances 2+).

    :param remove_configs: If True, also remove the cloned config directories.
        Default is False — config dirs are kept so containers can be reused
        for the next run (warm start).  Use ``--cleanup`` CLI flag to enable.
    """
    parallel_instances = instances[1:]
    if not parallel_instances:
        return

    log_section("Parallel: Cleaning up containers")
    compose_path = "/home/willem/docker_files/ha-sim/docker-compose.parallel.yml"
    if os.path.exists(compose_path):
        result = subprocess.run(
            ["docker", "compose", "-f", compose_path, "down", "--remove-orphans"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  Stopped and removed {len(parallel_instances)} container(s)")
        else:
            print(f"  docker compose down failed: {result.stderr[:200]}")

    if remove_configs:
        parent_dir = os.path.dirname(InstanceConfig.default().config_dir)
        for inst in parallel_instances:
            if os.path.exists(inst.config_dir):
                dirname = os.path.basename(inst.config_dir)
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{parent_dir}:/parent",
                        "alpine",
                        "sh",
                        "-c",
                        f"rm -rf /parent/{dirname}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                print(f"  Removed config dir: {inst.config_dir}")


def _current_instance_reset(token: Token[InstanceConfig | None]) -> None:
    """Reset the contextvar to its previous value."""
    _current_instance_var.reset(token)


# ---------------------------------------------------------------------------
# Recipe distribution
# ---------------------------------------------------------------------------
#: Dependency chains — recipes that must be on the same container.
#: These are kept together as atomic units in the shared work queue.
DEPENDENCY_CHAINS: list[list[str]] = [
    ["R07b", "R05"],  # restart → no resurrection
    ["R18", "R20"],  # faked REM
    ["R24", "R25"],  # class mismatch fix
    ["R19", "R26"],  # TRV from broadcast
]

#: Rolling-average timing store — self-calibrating load balancing.
#: The store reads from
#: ``~/.local/share/ramses_extras/ha_sim_reports/recipe_timings.json``
#: and falls back to seed estimates for recipes with no history.
TIMING_STORE = TimingStore()

# Shared progress counter across all containers
_PROGRESS_DONE = 0
_PROGRESS_TOTAL = 0
_PROGRESS_LOCK = asyncio.Lock()
_RUN_START = 0.0


def _fmt_elapsed(seconds: float) -> str:
    """Format seconds as M:SS."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _progress_str() -> str:
    """Return a progress string like [12/64 3:45]."""
    elapsed = time.monotonic() - _RUN_START
    return f"[{_PROGRESS_DONE}/{_PROGRESS_TOTAL} {_fmt_elapsed(elapsed)}]"


def _est(recipe_id: str) -> float:
    """Get the estimated runtime for a recipe (from rolling average)."""
    return TIMING_STORE.get_estimate(recipe_id)


# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------
@dataclass
class InstanceResult:
    """Results from a single container's recipe run."""

    instance: InstanceConfig
    passed: int = 0
    failed: int = 0
    results: list[str] = field(default_factory=list)
    recipe_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    elapsed: float = 0.0
    error: str | None = None
    # Overhead breakdown (seconds) — time NOT spent inside recipe.run()
    setup_time: float = 0.0
    teardown_time: float = 0.0
    cleanup_time: float = 0.0  # delete_test_profiles between recipes
    log_check_time: float = 0.0  # log_monitor.record_recipe between recipes
    queue_wait_time: float = 0.0  # waiting for work_queue.get()
    recipe_time: float = 0.0  # sum of recipe.run() durations


async def run_dynamic_instance(
    instance: InstanceConfig,
    work_queue: asyncio.Queue[list[str] | None],
) -> InstanceResult:
    """Run recipes from a shared dynamic queue on a single container.

    Pulls the next recipe unit (or dependency chain) from the shared
    queue when the container is free.  This distributes load dynamically
    — if one container hits a slow recipe or timeout, other containers
    pick up the slack.

    The queue is pre-loaded with units sorted by estimated time (highest
    first) so the slowest recipes start first (LPT scheduling).  A
    ``None`` sentinel signals queue exhaustion — the container stops.
    """
    result = InstanceResult(instance=instance)
    start = time.monotonic()

    token = set_current_instance(instance)

    try:
        # Authenticate
        print(f"\n  [{instance.name}] Authenticating ({instance.ha_url})...")
        auth_token = get_token()
        print(f"  [{instance.name}] Token acquired")

        # Build context
        log_monitor = LogMonitor()
        ctx = RecipeContext(
            token=auth_token, log_monitor=log_monitor, instance=instance
        )
        log_monitor.start()

        # Setup
        setup_start = time.monotonic()
        await setup(ctx)
        result.setup_time = time.monotonic() - setup_start

        # Pull and run recipes from the shared queue
        while True:
            try:
                queue_wait_start = time.monotonic()
                unit = await work_queue.get()
                result.queue_wait_time += time.monotonic() - queue_wait_start
            except asyncio.CancelledError:
                break
            if unit is None:
                # Sentinel — queue is empty
                work_queue.task_done()
                break

            for rid in unit:
                recipe_cls = REGISTRY.get(rid)
                if recipe_cls is None:
                    print(
                        f"  [{instance.name}] WARNING:"
                        f" recipe {rid!r} not found, skipping"
                    )
                    continue

                recipe = recipe_cls()
                print(
                    f"\n  {_progress_str()} [{instance.name}]"
                    f" >>> Running {recipe.id}"
                    f" (seq={recipe.seq}): {recipe.title}"
                )

                log_snapshot = log_monitor.snapshot()
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
                    print(f"  [{instance.name}] !!! Recipe {recipe.id} raised: {e}")
                recipe_elapsed = time.monotonic() - recipe_start
                result.recipe_time += recipe_elapsed

                ctx.recipe_stats[recipe.id] = {
                    "passed": ctx.passed - passed_before,
                    "failed": ctx.failed - failed_before,
                    "duration": recipe_elapsed,
                    "title": recipe.title,
                }

                # Record timing for rolling-average load balancing
                TIMING_STORE.record_run(recipe.id, recipe_elapsed)

                # Clean up test profiles
                cleanup_start = time.monotonic()
                try:
                    ctx.refresh_token()
                    n = await delete_test_profiles(ctx.token)
                    if n:
                        print(f"  [{instance.name}] Cleaned up {n} test profile(s)")
                except Exception:
                    pass
                result.cleanup_time += time.monotonic() - cleanup_start

                # Per-recipe log check
                log_check_start = time.monotonic()
                recipe_logs = log_monitor.record_recipe(recipe.id, log_snapshot)
                n_err = len(recipe_logs["errors"])
                n_warn = len(recipe_logs["warnings"])
                result.log_check_time += time.monotonic() - log_check_start
                if n_err or n_warn:
                    print(
                        f"  [{instance.name}] [log] {recipe.id}:"
                        f" {n_err} errors, {n_warn} warnings"
                    )

                global _PROGRESS_DONE
                _PROGRESS_DONE += 1
                p_str = green(f"P:{ctx.passed:>3}")
                f_str = (
                    red(f"F:{ctx.failed:>3}") if ctx.failed else f"F:{ctx.failed:>3}"
                )
                print(
                    f"  {_progress_str()} [{instance.name}]"
                    f" [{p_str} {f_str}]"
                    f"  {recipe.id} done ({recipe_elapsed:.1f}s)"
                )

            work_queue.task_done()

        # Collect results
        result.passed = ctx.passed
        result.failed = ctx.failed
        result.results = ctx.results
        result.recipe_stats = ctx.recipe_stats

        # Teardown
        teardown_start = time.monotonic()
        await _teardown_no_exit(ctx, start_time=start, instance=instance)
        result.teardown_time = time.monotonic() - teardown_start

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        print(f"  [{instance.name}] FATAL: {e}")
    finally:
        _current_instance_reset(token)

    result.elapsed = time.monotonic() - start
    return result


async def _teardown_no_exit(
    ctx: RecipeContext,
    *,
    start_time: float,
    instance: InstanceConfig,
) -> None:
    """Teardown without calling sys.exit (for parallel mode)."""
    from .helpers import delete_test_profiles

    try:
        ctx.refresh_token()
        n = await delete_test_profiles(ctx.token)
        if n:
            print(f"  [{instance.name}] Final cleanup: removed {n} test profile(s)")
    except Exception:
        pass

    # Log report (async-friendly — runs in executor for parallel collection)
    if ctx.log_monitor is not None:
        from .runner import _report_path

        # Offload blocking I/O to executor for parallel collection
        loop = asyncio.get_event_loop()
        log_data = await loop.run_in_executor(None, ctx.log_monitor.collect)
        report_path = _report_path(instance.name)
        await loop.run_in_executor(
            None, ctx.log_monitor.write_report, str(report_path), log_data
        )
        print(f"  [{instance.name}] Log report: {report_path}")
        n_errors = len(log_data["errors"])
        n_warnings = len(log_data["warnings"])
        if n_errors:
            print(f"  [{instance.name}] Unexpected errors: {n_errors}")
        if n_warnings:
            print(f"  [{instance.name}] Unexpected warnings: {n_warnings}")


def merge_results(results: list[InstanceResult]) -> int:
    """Merge per-container results and print combined summary."""
    log_section("PARALLEL SUMMARY")

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_elapsed = max(r.elapsed for r in results) if results else 0

    # Per-container summary
    print(f"\n  {'Container':<15} {'Pass':>5} {'Fail':>5} {'Time':>8}  Status")
    print(f"  {'-' * 14} {'-' * 5} {'-' * 5} {'-' * 8}  {'-' * 20}")
    for r in results:
        status_raw = "ERROR" if r.error else ("PASS" if r.failed == 0 else "FAIL")
        status = color_status(status_raw)
        fail_str = red(str(r.failed)) if r.failed else str(r.failed)
        print(
            f"  {r.instance.name:<15} {r.passed:>5} {fail_str:>5}"
            f" {r.elapsed:>7.1f}s  {status}"
        )
        if r.error:
            print(f"    Error: {r.error[:100]}")

    print(f"\n  Total passed: {green(str(total_passed))}")
    fail_total = red(str(total_failed)) if total_failed else str(total_failed)
    print(f"  Total failed: {fail_total}")
    print(f"  Wall time:    {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")
    print()

    # Per-container overhead breakdown
    print("  Overhead breakdown (time NOT inside recipe.run):")
    print(
        f"    {'Container':<15} {'Recipe':>7} {'Setup':>7} {'Cleanup':>8}"
        f" {'LogChk':>7} {'QWait':>7} {'Teardown':>9} {'Unacct':>8}"
    )
    print(
        f"    {'-' * 14} {'-' * 7} {'-' * 7} {'-' * 8}"
        f" {'-' * 7} {'-' * 7} {'-' * 9} {'-' * 8}"
    )
    for r in results:
        accounted = (
            r.recipe_time
            + r.setup_time
            + r.cleanup_time
            + r.log_check_time
            + r.queue_wait_time
            + r.teardown_time
        )
        unacct = r.elapsed - accounted
        print(
            f"    {r.instance.name:<15} {r.recipe_time:>6.0f}s {r.setup_time:>6.0f}s"
            f" {r.cleanup_time:>7.0f}s {r.log_check_time:>6.0f}s"
            f" {r.queue_wait_time:>6.0f}s {r.teardown_time:>8.0f}s"
            f" {unacct:>7.0f}s"
        )
    # Totals
    tot_recipe = sum(r.recipe_time for r in results)
    tot_setup = sum(r.setup_time for r in results)
    tot_cleanup = sum(r.cleanup_time for r in results)
    tot_logchk = sum(r.log_check_time for r in results)
    tot_qwait = sum(r.queue_wait_time for r in results)
    tot_teardown = sum(r.teardown_time for r in results)
    tot_unacct = sum(
        r.elapsed
        - (
            r.recipe_time
            + r.setup_time
            + r.cleanup_time
            + r.log_check_time
            + r.queue_wait_time
            + r.teardown_time
        )
        for r in results
    )
    print(
        f"    {'TOTAL':<15} {tot_recipe:>6.0f}s {tot_setup:>6.0f}s"
        f" {tot_cleanup:>7.0f}s {tot_logchk:>6.0f}s"
        f" {tot_qwait:>6.0f}s {tot_teardown:>8.0f}s"
        f" {tot_unacct:>7.0f}s"
    )
    print()

    # Combined per-recipe timing table
    all_stats: dict[str, dict[str, Any]] = {}
    for r in results:
        for rid, stats in r.recipe_stats.items():
            all_stats[rid] = {**stats, "container": r.instance.name}

    if all_stats:
        print("  Per-recipe timing:")
        print(
            f"    {'Recipe':<8} {'Container':<12}"
            f" {'Pass':>5} {'Fail':>5} {'Time':>8}  Title"
        )
        print(f"    {'-' * 7} {'-' * 11} {'-' * 5} {'-' * 5} {'-' * 8}  {'-' * 30}")
        for rid in sorted(
            all_stats,
            key=lambda k: (REGISTRY.get(k).seq if REGISTRY.get(k) else 999, k),
        ):
            s = all_stats[rid]
            dur = s.get("duration", 0.0)
            p = s.get("passed", 0)
            f = s.get("failed", 0)
            title = s.get("title", "")[:40]
            container = s.get("container", "?")[:11]
            fail_str = red(str(f)) if f else str(f)
            line = f"    {rid:<8} {container:<12} {p:>5} {fail_str:>5}"
            print(f"{line} {dur:>7.1f}s  {title}")
        print()

    # Print all result lines
    for r in results:
        for line in r.results:
            print(f"  [{r.instance.name}] {line}")

    if total_failed > 0:
        print(f"\n  {bold(red('*** SOME TESTS FAILED ***'))}")
        return 1
    print(f"\n  {bold(green('*** ALL TESTS PASSED ***'))}")
    return 0


async def run_parallel(
    n_containers: int,
    *,
    recipe_ids: list[str] | None = None,
    container_base: str = "ha-sim",
    port: int = 8124,
    assignments: list[str] | None = None,
    cleanup: bool = False,
) -> None:
    """Run recipes across N containers in parallel.

    Uses a **dynamic work queue**: all recipe units (dependency chains
    kept together) are placed in a shared ``asyncio.Queue`` sorted by
    estimated runtime (longest first — LPT scheduling).  Each container
    pulls the next unit when it finishes its current recipe.  This
    automatically balances load — if one container draws a slow recipe,
    the others pick up more units from the queue.

    The remaining wall-time imbalance (typically 1-2min) is caused by
    recipe runtime variance under parallel contention, not dispatch
    failure.  A single slow recipe (e.g. R68: 178s) creates a "long
    tail" that can't be parallelised further.
    """
    # Discover recipes
    discover_recipes(__name__.rsplit(".", 1)[0] + ".recipes")
    print(f"  Discovered {len(REGISTRY)} recipes")

    # Verify the MQTT broker is reachable — all containers depend on it
    # for ramses_cc's MQTT transport.  Without it, every recipe will fail
    # with cascading errors (Transport did not bind, MQTT connection
    # failed, etc.).
    from .mqtt_setup import is_mqtt_broker_ready

    if not is_mqtt_broker_ready():
        print(
            f"\n  ERROR: MQTT broker at {MQTT_BROKER_URL} is not reachable.\n"
            "  Start it with:  cd ~/docker_files/ha-sim && "
            "docker compose -f docker-compose.mqtt.yml up -d\n"
            "  Aborting."
        )
        sys.exit(1)
    print(f"  MQTT broker at {MQTT_BROKER_URL} is reachable")

    # Select recipes
    if recipe_ids:
        all_recipe_ids = []
        for rid in recipe_ids:
            if REGISTRY.get(rid) is None:
                print(f"  WARNING: recipe {rid!r} not found, skipping")
                continue
            all_recipe_ids.append(rid)
    else:
        all_recipe_ids = [r.id for r in REGISTRY.sorted()]

    print(f"  Running {len(all_recipe_ids)} recipes across {n_containers} containers")

    # Create instance configs
    instances = make_instances(n_containers, base=container_base, port=port)
    for inst in instances:
        print(
            f"  Instance {inst.index}: {inst.name} port={inst.port} hgi={inst.hgi_id}"
        )

    # Parse manual assignments
    manual: dict[str, list[str]] = {}
    if assignments:
        for spec in assignments:
            parts = spec.split(":", 1)
            if len(parts) != 2:
                print(
                    f"  WARNING: bad --assign spec {spec!r},"
                    " expected CONTAINER:R1,R2,..."
                )
                continue
            container_name = parts[0]
            rids = [r.strip() for r in parts[1].split(",") if r.strip()]
            manual[container_name] = rids
            print(f"  Manual assignment: {container_name} -> {rids}")

    # Switch ha-sim to minimal config for faster startup
    _switch_ha_config("minimal", instances[0].name)

    # Start containers
    await ensure_containers(instances)

    # Build work units (dependency chains kept together as atomic units)
    # Sort by estimated time descending (LPT — Longest Processing Time first)
    # so the slowest recipes start first and containers stay balanced.
    chain_recipe_set: set[str] = set()
    units: list[list[str]] = []
    for chain in DEPENDENCY_CHAINS:
        unit = [r for r in chain if r in all_recipe_ids]
        if unit:
            units.append(unit)
            chain_recipe_set.update(unit)

    # Add standalone recipes as individual units
    for rid in all_recipe_ids:
        if rid not in chain_recipe_set:
            units.append([rid])

    # Sort units by total estimated time (descending)
    units.sort(key=lambda u: sum(_est(r) for r in u), reverse=True)

    # Build a shared work queue
    work_queue: asyncio.Queue[list[str] | None] = asyncio.Queue()
    for unit in units:
        work_queue.put_nowait(unit)
    # Add sentinel values (one per container) to signal completion
    for _ in range(n_containers):
        work_queue.put_nowait(None)

    total_est = sum(sum(_est(r) for r in u) for u in units)
    print(
        f"  Dynamic dispatch: {len(units)} units,"
        f" ~{total_est:.0f}s total across {n_containers} containers"
    )

    # Set shared progress counter
    global _PROGRESS_TOTAL, _PROGRESS_DONE, _RUN_START
    _PROGRESS_TOTAL = len(all_recipe_ids)
    _PROGRESS_DONE = 0
    _RUN_START = time.monotonic()

    # Run in parallel with dynamic dispatch
    log_section("Parallel: Running recipes")
    dash = LiveDashboard([inst.name for inst in instances])
    tasks: list[asyncio.Task[InstanceResult]] = []

    def _on_done(_task: asyncio.Task[InstanceResult], name: str) -> None:
        dash.mark_done(name)

    for inst in instances:
        task = asyncio.ensure_future(run_dynamic_instance(inst, work_queue))
        task.add_done_callback(functools.partial(_on_done, name=inst.name))
        tasks.append(task)

    dash.start()
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await dash.stop()

    # Handle exceptions from gather
    final_results: list[InstanceResult] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            inst = instances[i]
            print(f"  [{inst.name}] CRASHED: {result}")
            final_results.append(InstanceResult(instance=inst, error=str(result)))
        else:
            final_results.append(result)

    # Merge and print summary
    exit_code = merge_results(final_results)

    # Persist timing data for future runs
    TIMING_STORE.save()

    # Cleanup
    if cleanup:
        cleanup_containers(instances, remove_configs=cleanup)

    # Restore ha-sim to full config for normal use
    _switch_ha_config("full", instances[0].name)

    sys.exit(exit_code)
