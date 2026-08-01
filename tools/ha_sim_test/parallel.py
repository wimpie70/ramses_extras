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
import os
import re
import subprocess
import time
from contextvars import Token
from dataclasses import dataclass, field
from typing import Any

from .base import RecipeContext
from .const import InstanceConfig, make_instances
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
from .registry import REGISTRY, discover_recipes
from .runner import setup, teardown

#: Path to ramses_cc custom_components (bind-mounted into each container).
_RAMSES_CC_PATH = "/home/willem/dev/ramses_cc/custom_components/ramses_cc"

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
    environment:
      - TZ=Europe/Amsterdam
      - HASSIO_PORT={port}
      - PYTHONPATH=/config/ramses_rf/src
      - RAMSES_SIM_HGI_ID={hgi_id}
    volumes:
      - {config_dir}:/config
      - /home/willem/dev/ramses_rf:/config/ramses_rf
      - {ramses_cc_path}:/config/custom_components/ramses_cc
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
            # Copy everything except logs, caches, and db files
            "cp -a /src/. /dst/ && "
            "rm -rf /dst/home-assistant.log* /dst/ramses.db* "
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
    """Patch the HA port in the cloned configuration.yaml."""
    config_yaml = f"{inst.config_dir}/configuration.yaml"
    if not os.path.exists(config_yaml):
        return
    # Use python container to patch (alpine sed doesn't support \b)
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
            f"import re; "
            f"p='/config/configuration.yaml'; "
            f"c=open(p).read(); "
            f"c=re.sub(r'\\b8124\\b', '{inst.port}', c); "
            f"open(p,'w').write(c); "
            f"print('Patched port to {inst.port}')",
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
    """Patch the ramses_cc serial_port MQTT URL in the cloned config entries."""
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
            f"[e.get('options',{{}}).get('serial_port',{{}}).update("
            f"{{'port_name': '{mqtt_url}'}}) "
            f"for e in d.get('data',{{}}).get('entries',[]) "
            f"if e.get('domain')=='ramses_cc']; "
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
            )
        )
    compose_path = "/home/willem/docker_files/ha-sim/docker-compose.parallel.yml"
    with open(compose_path, "w") as f:
        f.write(COMPOSE_TEMPLATE.format(services="\n".join(services)))
    return compose_path


async def ensure_containers(instances: list[InstanceConfig]) -> None:
    """Start all parallel containers.

    Instance 1 (ha-sim) is assumed to be already running.
    Instances 2+ are cloned from the base config and started via docker-compose.
    If a container is already running and healthy, it is reused as-is
    (warm start — skips clone and HA readiness wait).
    """
    log_section("Parallel: Starting containers")
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

    # Wait for each container to be ready
    for inst in parallel_instances:
        print(f"  [{inst.name}] Waiting for HA to be ready on port {inst.port}...")

        def _ready(inst: InstanceConfig = inst) -> bool:
            token = set_current_instance(inst)
            try:
                return is_ha_ready()
            finally:
                _current_instance_reset(token)

        ready = wait_for(_ready, timeout=120, interval=3, msg=f"[{inst.name}] HA ready")
        if not ready:
            raise RuntimeError(f"[{inst.name}] HA did not become ready within 120s")
        print(f"  [{inst.name}] HA is ready")


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
DEPENDENCY_CHAINS: list[list[str]] = [
    ["R07b", "R05"],  # restart → no resurrection
    ["R18", "R20"],  # faked REM
    ["R24", "R25"],  # class mismatch fix
    ["R19", "R26"],  # TRV from broadcast
]

#: Recipes that do docker restart/stop/start or clear_cached_state.
#: These affect the entire container, so they should be spread across containers.
CONTAINER_AFFECTING: set[str] = {
    "R07b",
    "R29",
    "R32",
    "R34",
    "R37",
    "R38",
    "R50",
    "R59",
}

#: Pure function tests — no HA interaction needed, ~1s each.
#: These run on instance 1 (no container overhead).
PURE_TESTS: set[str] = {
    "R39",
    "R41",
    "R42",
    "R43",
    "R48",
    "R49",
    "R51",
    "R52",
    "R53",
    "R54",
    "R55",
    "R56",
    "R57",
}

#: Estimated runtime per recipe (seconds) — used for load balancing.
ESTIMATED_RUNTIME: dict[str, int] = {
    "R01": 20,
    "R02": 3,
    "R03": 1,
    "R04": 3,
    "R05": 30,
    "R06": 15,
    "R07": 10,
    "R07b": 30,
    "R08": 20,
    "R09": 15,
    "R10": 20,
    "R11": 20,
    "R12": 30,
    "R14": 15,
    "R15": 1,
    "R16": 10,
    "R17": 30,
    "R18": 8,
    "R19": 20,
    "R19b": 15,
    "R19c": 15,
    "R20": 15,
    "R21": 15,
    "R22": 15,
    "R23": 15,
    "R24": 20,
    "R25": 15,
    "R26": 10,
    "R27": 15,
    "R28": 20,
    "R29": 30,
    "R30": 20,
    "R31": 20,
    "R32": 40,
    "R33": 20,
    "R34": 30,
    "R35": 20,
    "R36": 20,
    "R37": 30,
    "R38": 25,
    "R39": 5,
    "R40": 25,
    "R41": 5,
    "R42": 5,
    "R43": 5,
    "R44": 20,
    "R45": 20,
    "R46": 20,
    "R47": 15,
    "R48": 5,
    "R49": 5,
    "R50": 30,
    "R51": 5,
    "R52": 5,
    "R53": 5,
    "R54": 5,
    "R55": 5,
    "R56": 5,
    "R57": 5,
    "R58": 5,
    "R59": 15,
}


def distribute_recipes(
    recipe_ids: list[str],
    n_containers: int,
    *,
    manual_assignments: dict[str, list[str]] | None = None,
) -> dict[int, list[str]]:
    """Distribute recipes across N containers.

    Constraints:
    1. Dependency chains stay together on the same container.
    2. Container-affecting recipes (docker restart / clear_cached_state) are
       spread across containers (max 1 per container if possible).
    3. Pure function tests go on container 1 (no HA needed).
    4. Remaining recipes are greedy-filled to balance estimated runtime.

    :param manual_assignments: If given, these recipes are assigned to specific
        containers and excluded from auto-distribution.
    :return: Mapping of container index (1-based) -> list of recipe IDs.
    """
    if manual_assignments is None:
        manual_assignments = {}

    # Initialize groups
    groups: dict[int, list[str]] = {i: [] for i in range(1, n_containers + 1)}

    # Track which recipes are already assigned
    assigned: set[str] = set()

    # 1. Apply manual assignments
    for container_name, rids in manual_assignments.items():
        # Parse container name to index (ha-sim -> 1, ha-sim-2 -> 2, ...)
        idx = _container_name_to_index(container_name, n_containers)
        if idx is None:
            print(f"  WARNING: unknown container {container_name}, skipping assignment")
            continue
        for rid in rids:
            if rid in recipe_ids and rid not in assigned:
                groups[idx].append(rid)
                assigned.add(rid)

    # 2. Put pure tests on container 1
    for rid in recipe_ids:
        if rid in PURE_TESTS and rid not in assigned:
            groups[1].append(rid)
            assigned.add(rid)

    # 3. Build atomic groups from dependency chains
    # Each chain becomes a single unit that must go on one container.
    chain_units: list[list[str]] = []
    chain_recipe_set: set[str] = set()
    for chain in DEPENDENCY_CHAINS:
        unit = [r for r in chain if r in recipe_ids and r not in assigned]
        if unit:
            chain_units.append(unit)
            chain_recipe_set.update(unit)

    # 4. Assign container-affecting recipes (and their chains) round-robin
    # These are spread across containers to avoid serialization.
    container_affecting_units: list[list[str]] = []
    other_units: list[list[str]] = []

    for unit in chain_units:
        if any(r in CONTAINER_AFFECTING for r in unit):
            container_affecting_units.append(unit)
        else:
            other_units.append(unit)

    # Also check standalone container-affecting recipes (not in chains)
    for rid in recipe_ids:
        if (
            rid in CONTAINER_AFFECTING
            and rid not in assigned
            and rid not in chain_recipe_set
        ):
            container_affecting_units.append([rid])
            assigned.add(rid)

    # Mark chain recipes as assigned
    for unit in container_affecting_units:
        assigned.update(unit)
    for unit in other_units:
        assigned.update(unit)

    # Round-robin assign container-affecting units
    container_runtimes = {
        i: sum(ESTIMATED_RUNTIME.get(r, 10) for r in groups[i]) for i in groups
    }
    for i, unit in enumerate(container_affecting_units):
        # Pick the container with the least runtime, cycling through containers
        target = (i % n_containers) + 1
        # But prefer the container with least load
        target = min(container_runtimes, key=lambda k: container_runtimes[k])
        groups[target].extend(unit)
        unit_time = sum(ESTIMATED_RUNTIME.get(r, 10) for r in unit)
        container_runtimes[target] += unit_time

    # 5. Greedy-fill remaining recipes (including non-affecting chains)
    # Sort by estimated runtime descending for better balance
    other_units.sort(
        key=lambda u: sum(ESTIMATED_RUNTIME.get(r, 10) for r in u), reverse=True
    )

    for unit in other_units:
        target = min(container_runtimes, key=lambda k: container_runtimes[k])
        groups[target].extend(unit)
        unit_time = sum(ESTIMATED_RUNTIME.get(r, 10) for r in unit)
        container_runtimes[target] += unit_time

    # 6. Assign remaining individual recipes
    #    (not in chains, not pure tests, not container-affecting)
    remaining = [r for r in recipe_ids if r not in assigned]
    remaining.sort(key=lambda r: ESTIMATED_RUNTIME.get(r, 10), reverse=True)

    for rid in remaining:
        target = min(container_runtimes, key=lambda k: container_runtimes[k])
        groups[target].append(rid)
        container_runtimes[target] += ESTIMATED_RUNTIME.get(rid, 10)

    # 7. Sort each group by seq order
    for idx in groups:
        groups[idx].sort(
            key=lambda r: (REGISTRY.get(r).seq if REGISTRY.get(r) else 999, r)
        )

    return groups


def _container_name_to_index(name: str, n_containers: int) -> int | None:
    """Convert a container name to its 1-based index."""
    if name in ("ha-sim", "ha-sim-1"):
        return 1
    m = re.match(r"ha-sim-(\d+)$", name)
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= n_containers:
            return idx
    return None


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


async def run_single_instance(
    instance: InstanceConfig,
    recipe_ids: list[str],
) -> InstanceResult:
    """Run a list of recipes on a single container (sequential within container)."""
    result = InstanceResult(instance=instance)
    start = time.monotonic()

    # Set the contextvar for this asyncio task
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
        await setup(ctx)

        # Run recipes
        for rid in recipe_ids:
            recipe_cls = REGISTRY.get(rid)
            if recipe_cls is None:
                print(
                    f"  [{instance.name}] WARNING: recipe {rid!r} not found, skipping"
                )
                continue

            recipe = recipe_cls()
            print(
                f"\n  [{instance.name}] >>> Running {recipe.id}"
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

            ctx.recipe_stats[recipe.id] = {
                "passed": ctx.passed - passed_before,
                "failed": ctx.failed - failed_before,
                "duration": recipe_elapsed,
                "title": recipe.title,
            }

            # Clean up test profiles
            try:
                ctx.refresh_token()
                n = await delete_test_profiles(ctx.token)
                if n:
                    print(f"  [{instance.name}] Cleaned up {n} test profile(s)")
            except Exception:
                pass

            # Per-recipe log check
            recipe_logs = log_monitor.record_recipe(recipe.id, log_snapshot)
            n_err = len(recipe_logs["errors"])
            n_warn = len(recipe_logs["warnings"])
            if n_err or n_warn:
                print(
                    f"  [{instance.name}] [log] {recipe.id}:"
                    f" {n_err} errors, {n_warn} warnings"
                )

        # Collect results
        result.passed = ctx.passed
        result.failed = ctx.failed
        result.results = ctx.results
        result.recipe_stats = ctx.recipe_stats

        # Teardown (without sys.exit)
        await _teardown_no_exit(ctx, start_time=start, instance=instance)

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        print(f"  [{instance.name}] FATAL: {e}")
    finally:
        # Reset contextvar
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

    # Log report
    if ctx.log_monitor is not None:
        log_data = ctx.log_monitor.collect()
        report_path = f"/tmp/ha_sim_test_log_report_{instance.name}.txt"
        ctx.log_monitor.write_report(report_path, log_data)
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
        status = "ERROR" if r.error else ("PASS" if r.failed == 0 else "FAIL")
        print(
            f"  {r.instance.name:<15} {r.passed:>5} {r.failed:>5}"
            f" {r.elapsed:>7.1f}s  {status}"
        )
        if r.error:
            print(f"    Error: {r.error[:100]}")

    print(f"\n  Total passed: {total_passed}")
    print(f"  Total failed: {total_failed}")
    print(f"  Wall time:    {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")
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
            print(f"    {rid:<8} {container:<12} {p:>5} {f:>5} {dur:>7.1f}s  {title}")
        print()

    # Print all result lines
    for r in results:
        for line in r.results:
            print(f"  [{r.instance.name}] {line}")

    if total_failed > 0:
        print("\n  *** SOME TESTS FAILED ***")
        return 1
    print("\n  *** ALL TESTS PASSED ***")
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

    Uses static pre-assignment: recipes are distributed across containers
    before the run, respecting dependency chains and balancing estimated
    runtime.  A dynamic work queue was tested but found slower due to
    resource contention (see comment below).
    """
    # Discover recipes
    discover_recipes()
    print(f"  Discovered {len(REGISTRY)} recipes")

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

    # Start containers
    await ensure_containers(instances)

    # Distribute recipes (static pre-assignment)
    # The dynamic queue was tested and found slower due to resource contention:
    # when all 4 containers run recipes simultaneously, each recipe takes ~2x
    # longer (CPU/disk/network).  The static approach lets ha-sim finish early
    # and reduces contention for the remaining containers.
    groups = distribute_recipes(all_recipe_ids, n_containers, manual_assignments=manual)
    for idx, rids in groups.items():
        inst = instances[idx - 1]
        est = sum(ESTIMATED_RUNTIME.get(r, 10) for r in rids)
        print(
            f"  {inst.name} ({len(rids)} recipes, ~{est}s):"
            f" {', '.join(rids[:10])}{'...' if len(rids) > 10 else ''}"
        )

    # Run in parallel
    log_section("Parallel: Running recipes")
    tasks = [
        run_single_instance(instances[idx - 1], groups[idx]) for idx in sorted(groups)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

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

    # Cleanup
    if cleanup:
        cleanup_containers(instances, remove_configs=cleanup)

    import sys

    sys.exit(exit_code)
