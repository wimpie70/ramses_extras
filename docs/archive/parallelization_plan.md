# Plan: Parallelize ha_sim_test with Multiple Containers

## Goal

Run the ha_sim_test suite across 2+ parallel ha-sim containers to cut total
runtime. Default: 2 containers (~2x speedup). Scales up to 4 if RAM allows.

## CLI Interface

```bash
# Current behaviour — single container (backward compatible)
python -m ha_sim_test

# Parallel — N containers, auto-distribute recipes
python -m ha_sim_test --parallel 2
python -m ha_sim_test --parallel 3
python -m ha_sim_test --parallel 4

# Override container base name (default: ha-sim)
python -m ha_sim_test --parallel 2 --container-base ha-sim

# Override starting port (default: 8124)
python -m ha_sim_test --parallel 2 --port 8124

# Explicit recipe list on specific containers (advanced)
python -m ha_sim_test --parallel 2 --assign ha-sim-1:R01,R02,R03 --assign ha-sim-2:R04,R05
```

### Standard container naming

| Flag | Containers | Ports |
|------|-----------|-------|
| `--parallel 1` (default) | `ha-sim` | 8124 |
| `--parallel 2` | `ha-sim-1`, `ha-sim-2` | 8124, 8125 |
| `--parallel 3` | `ha-sim-1`, `ha-sim-2`, `ha-sim-3` | 8124, 8125, 8126 |
| `--parallel 4` | `ha-sim-1` .. `ha-sim-4` | 8124 .. 8127 |

`--parallel 1` is identical to current behaviour: single `ha-sim` container,
no name suffix, no config dir cloning. This ensures full backward compat.

## Current Architecture (single container)

```
                    MQTT broker (192.168.40.11:1883)
                          │
          ┌───────────────┼───────────────┐
          │  RAMSES/GATEWAY_SIM/18:001234  │  (shared topic namespace)
          └───────────────┬───────────────┘
                          │
                   ha-sim container (port 8124)
                   ├── ramses_cc (config entry with MQTT serial port)
                   ├── ramses_extras device_simulator
                   └── ramses_rf (subscribes to .../rx, publishes .../tx)
```

All 61 recipes run sequentially on this one container, sharing:
- Container name `ha-sim`, port `8124`
- HGI gateway ID `18:001234`
- MQTT topic namespace `RAMSES/GATEWAY_SIM`
- Device IDs (CTL=01:150000, TRV=04:150003, FAN=32:150000, etc.)
- `.storage/core.config_entries`, `.storage/ramses_cc`, `ramses.db`

## System Constraints (verified on this machine)

| Resource | Available | Per HA container | 2 containers | 4 containers |
|----------|-----------|------------------|--------------|--------------|
| CPU | 16 cores | ~1-2% | ~4% | ~8% |
| RAM | **4 GB free** | ~500 MB | ~1 GB (OK) | ~2 GB (**risky**) |
| Disk | 174 GB | 784 MB config | ~1.5 GB | ~3 GB |
| MQTT | External broker | 1 conn | 2 conns | 4 conns |

**Default: 2 containers.** User can override with `--parallel 4` if more RAM
is free (e.g., `hass` container stopped).

## What Needs to Change

### 1. Parameterize hardcoded values

Every hardcoded container name, port, URL, HGI ID, and MQTT topic must become
a parameter that the runner passes to each recipe context.

**Files to change:**

| File | What's hardcoded | New approach |
|------|-----------------|--------------|
| `tools/ha_sim_test/const.py` | `HA_URL`, `HA_USER`, `HA_PASS`, `HGI`, `CTL`, `TRV`, etc. | Add `InstanceConfig` dataclass with all values; keep module-level constants as defaults for backward compat |
| `tools/ha_sim_test/helpers.py` | `HA_URL` in HTTP calls, `docker exec ha-sim` in subprocess calls | Accept `instance` parameter (or use context var) for container name and URL |
| `tools/ha_sim_test/runner.py` | `setup()` loads mixed profile, activates devices | Accept `InstanceConfig`; create one `RecipeContext` per instance |
| `tools/ha_sim_test/base.py` | `RecipeContext` holds token, shared dict | Add `instance: InstanceConfig` field to `RecipeContext` |
| `tools/ha_sim_test/registry.py` | Recipe discovery | No change needed (recipes are classes) |

**New `InstanceConfig` dataclass** (in `const.py` or new `instance.py`):

```python
@dataclass(frozen=True)
class InstanceConfig:
    name: str  # container name, e.g. "ha-sim-2"
    port: int  # e.g. 8125
    ha_url: str  # e.g. "http://localhost:8125"
    ha_user: str = "admin"
    ha_pass: str = "admin123"
    hgi_id: str = "18:001234"  # gateway ID for this instance
    mqtt_topic_ns: str = "RAMSES/GATEWAY_SIM"  # topic root
    config_dir: str = ""  # host path to config dir (for cloning)
    # Device IDs — same across instances (MQTT topic isolation makes this safe)
    ctl: str = "01:150000"
    trv: str = "04:150003"
    fan: str = "32:150000"
    rem: str = "37:170000"
    co2: str = "37:120000"
    dhw: str = "07:150000"

    @property
    def mqtt_url(self) -> str:
        return f"mqtt://slimmemeter:j@diebla@@192.168.40.11:1883/{self.mqtt_topic_ns}/{self.hgi_id}"

    @staticmethod
    def for_index(
        i: int, *, base: str = "ha-sim", port: int = 8124
    ) -> "InstanceConfig":
        """Create config for the i-th parallel instance (1-based)."""
        if i == 1 and base == "ha-sim":
            # First instance uses the original container name (backward compat)
            return InstanceConfig(
                name="ha-sim",
                port=port,
                ha_url=f"http://localhost:{port}",
                hgi_id="18:001234",
            )
        return InstanceConfig(
            name=f"{base}-{i}",
            port=port + i - 1,
            ha_url=f"http://localhost:{port + i - 1}",
            hgi_id=f"18:00{i:02d}234",  # 18:002234, 18:003234, ...
            config_dir=f"/home/willem/docker_files/ha-sim/config-{i}",
        )
```

### 2. Create multiple ha-sim containers

**docker-compose.parallel.yml** (generated or static):

```yaml
services:
  ha-sim-2:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: ha-sim-2
    ports:
      - "8125:8125"    # bridge networking (not host) to avoid port collisions
    environment:
      - TZ=Europe/Amsterdam
      - HASSIO_PORT=8125
      - PYTHONPATH=/config/ramses_rf/src
      - RAMSES_SIM_HGI_ID=18:002234
    volumes:
      - ./config-2:/config
      - /home/willem/dev/ramses_rf:/config/ramses_rf
      - /home/willem/dev/ramses_cc/custom_components/ramses_cc:/config/custom_components/ramses_cc

  ha-sim-3:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: ha-sim-3
    ports:
      - "8126:8126"
    environment:
      - TZ=Europe/Amsterdam
      - HASSIO_PORT=8126
      - PYTHONPATH=/config/ramses_rf/src
      - RAMSES_SIM_HGI_ID=18:003234
    volumes:
      - ./config-3:/config
      - /home/willem/dev/ramses_rf:/config/ramses_rf
      - /home/willem/dev/ramses_cc/custom_components/ramses_cc:/config/custom_components/ramses_cc
```

**Note**: Instance 1 (`ha-sim`) already exists and uses `network_mode: host`.
Instances 2+ use bridge networking with explicit port mappings to avoid
UPnP/zeroconf port collisions.

**Container lifecycle managed by the runner:**

```python
async def ensure_containers(instances: list[InstanceConfig]) -> None:
    """Start all parallel containers. Instance 1 (ha-sim) is assumed running."""
    for inst in instances[1:]:  # skip ha-sim (already running)
        # Clone config dir from ha-sim
        clone_config_dir(inst)
        # Patch configuration.yaml port
        patch_port(inst)
        # Patch core.config_entries MQTT URL
        patch_mqtt_url(inst)
        # Start container
        subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", inst.name])
        # Wait for HA to be ready
        wait_for(is_ha_ready_for(inst), timeout=60)
```

### 3. Isolate MQTT topic namespaces

Each container's ramses_cc config entry must point to a unique MQTT topic:

- Instance 1: `mqtt://...@192.168.40.11:1883/RAMSES/GATEWAY_SIM/18:001234`
- Instance 2: `mqtt://...@192.168.40.11:1883/RAMSES/GATEWAY_SIM/18:002234`
- Instance 3: `mqtt://...@192.168.40.11:1883/RAMSES/GATEWAY_SIM/18:003234`
- Instance 4: `mqtt://...@192.168.40.11:1883/RAMSES/GATEWAY_SIM/18:004234`

This requires two changes:

**a) ramses_extras `SIMULATOR_HGI_ID` — make env-var configurable:**

```python
# ramses_extras/features/device_simulator/const.py
import os

SIMULATOR_HGI_ID = os.environ.get("RAMSES_SIM_HGI_ID", "18:001234")
```

Set `RAMSES_SIM_HGI_ID=18:002234` in docker-compose env for instance 2.

**b) Patch `core.config_entries` MQTT URL in each cloned config dir:**

```python
def patch_mqtt_url(inst: InstanceConfig) -> None:
    """Patch the ramses_cc serial_port URL in the cloned config dir."""
    path = f"{inst.config_dir}/.storage/core.config_entries"
    with open(path) as f:
        data = json.load(f)
    for entry in data["data"]["entries"]:
        if entry["domain"] == "ramses_cc":
            entry["options"]["serial_port"]["port_name"] = inst.mqtt_url
    with open(path, "w") as f:
        json.dump(data, f)
```

### 4. Device IDs — no change needed

Since MQTT topic namespaces are already isolated per HGI ID, device ID
collisions don't matter — each container only subscribes to its own topic
namespace. **Keep the same device IDs across all instances.** This avoids
having to parameterize the profile system and all recipe code.

### 5. Recipe partitioning — auto-distribute

The runner auto-distributes recipes across N containers based on:

1. **Dependency constraints** — chains must stay on same container
2. **Container-affecting recipes** — docker restart / clear_cached_state recipes
   are spread across containers (max 1 per container if possible)
3. **Runtime balancing** — balance total estimated runtime across containers

**Dependency chains** (must be on same container):
- R07b → R05 (restart → no resurrection)
- R18 → R20 (faked REM)
- R24 → R25 (class mismatch fix)
- R19 → R26 (TRV from broadcast)

**Container-affecting recipes** (docker restart or clear_cached_state):
- R07b (docker restart) + R05 (depends on R07b)
- R29 (clear_cached_state)
- R32 (docker stop/start)
- R34 (clear_cached_state)
- R37 (clear_cached_state)
- R38 (clear_cached_state)
- R50 (docker stop/start)
- R59 (docker stop/start)

**Pure function tests** (no HA interaction, ~1s each — run on instance 1
since they don't need a container at all, just `docker exec` for imports):
- R39, R41, R42, R43, R48, R49, R51, R52, R53, R54, R55, R56, R57

**Auto-distribution algorithm:**

```python
def distribute_recipes(
    recipes: list[Recipe], n_containers: int
) -> dict[int, list[str]]:
    """Distribute recipes across N containers.

    1. Group dependency chains into atomic units.
    2. Assign container-affecting recipes to different containers.
    3. Greedy-fill remaining recipes to balance estimated runtime.
    4. Put pure function tests on container 1 (no HA needed).
    """
    # Build atomic groups (dependency chains)
    chains = [
        ["R07b", "R05"],
        ["R18", "R20"],
        ["R24", "R25"],
        ["R19", "R26"],
    ]
    # Container-affecting recipes (spread across containers)
    restart_recipes = ["R29", "R32", "R34", "R37", "R38", "R50", "R59"]
    # Pure tests (always on container 1)
    pure_tests = [
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
    ]

    # Assign restart recipes round-robin across containers
    # Assign chains to containers that have the least estimated runtime
    # Greedy-fill remaining recipes (sorted by estimated runtime desc)
    # to the container with the least current runtime
    ...
```

**Example distributions:**

#### `--parallel 2` (default)

| Container | Recipes | Est. runtime |
|-----------|---------|-------------|
| **ha-sim** (port 8124) | R02, R03, R04, R06, R07, R07b, R05, R08, R09, R10, R12, R14, R15, R16, R18, R19, R19b, R19c, R20, R21, R24, R25, R26, R29, R32 + pure tests (R39, R41-R43, R48-R49, R51-R57, R58) | ~13 min |
| **ha-sim-2** (port 8125) | R01, R11, R17, R22, R23, R27, R28, R30, R31, R33, R34, R35, R36, R37, R38, R40, R44, R45, R46, R47, R50, R59 | ~14 min |

**Critical path**: ~14 min (down from ~27 min) — **~1.9x speedup**

#### `--parallel 3`

| Container | Recipes | Est. runtime |
|-----------|---------|-------------|
| **ha-sim** (port 8124) | R02, R03, R04, R06, R07, R07b, R05, R08, R09, R10, R12, R14, R15, R16 + pure tests | ~8 min |
| **ha-sim-2** (port 8125) | R01, R11, R17, R18, R19, R19b, R19c, R20, R21, R22, R23, R24, R25, R26, R29 | ~9 min |
| **ha-sim-3** (port 8126) | R27, R28, R30, R31, R32, R33, R34, R35, R36, R37, R38, R40, R44, R45, R46, R47, R50, R58, R59 | ~9 min |

**Critical path**: ~9 min — **~3x speedup**

#### `--parallel 4`

| Container | Recipes | Est. runtime |
|-----------|---------|-------------|
| **ha-sim** (port 8124) | R02, R04, R06, R07, R07b, R05, R08, R09, R10, R12, R14, R15, R16 + pure tests | ~6 min |
| **ha-sim-2** (port 8125) | R01, R11, R17, R18, R19, R19b, R19c, R20, R21, R22, R23, R24, R25, R26 | ~6 min |
| **ha-sim-3** (port 8126) | R27, R28, R29, R30, R31, R32, R33, R34, R35, R36, R37 | ~6 min |
| **ha-sim-4** (port 8127) | R38, R40, R44, R45, R46, R47, R50, R58, R59 | ~5 min |

**Critical path**: ~6 min — **~4.5x speedup**

### 6. Runner changes

**Extend `runner.py`** (no separate file):

```python
async def run_parallel(
    n_containers: int,
    *,
    container_base: str = "ha-sim",
    port: int = 8124,
) -> int:
    """Run recipes across N containers in parallel."""
    # 1. Create InstanceConfigs
    instances = [InstanceConfig.for_index(i, base=container_base, port=port)
                 for i in range(1, n_containers + 1)]

    # 2. Start containers (instance 1 assumed running)
    await ensure_containers(instances)

    # 3. Discover recipes and auto-distribute
    recipes = discover_recipes()
    groups = distribute_recipes(recipes, n_containers)

    # 4. Run each container's group in parallel
    tasks = [run_single_instance(inst, groups[i]) for i, inst in enumerate(instances)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 5. Merge results
    return merge_results(results)


async def run_single_instance(
    instance: InstanceConfig,
    recipe_ids: list[str],
) -> InstanceResult:
    """Run a list of recipes on a single container (sequential within container)."""
    ctx = RecipeContext(instance=instance, ...)
    await setup(ctx)
    for recipe_id in recipe_ids:
        recipe = REGISTRY[recipe_id]
        await run_recipe_safely(recipe, ctx)
    await teardown(ctx)
    return ctx.collect_results()


def merge_results(results: list[InstanceResult]) -> int:
    """Merge per-container results into a single report."""
    # Combine pass/fail counts
    # Merge timing tables (sorted by seq)
    # Concatenate unexpected errors/warnings (tagged by container)
    # Return 0 if all pass, 1 if any fail
    ...
```

**CLI parsing** (in `__main__.py`):

```python
parser.add_argument(
    "--parallel",
    type=int,
    default=1,
    metavar="N",
    help="Run across N containers (default: 1 = sequential)",
)
parser.add_argument(
    "--container-base", default="ha-sim", help="Base container name (default: ha-sim)"
)
parser.add_argument(
    "--port", type=int, default=8124, help="Starting port (default: 8124)"
)
parser.add_argument(
    "--assign",
    action="append",
    default=[],
    help="Manual assignment: --assign ha-sim-2:R01,R02,R03",
)
```

**Backward compat**: `python -m ha_sim_test` (no flags) runs on single `ha-sim`
container exactly as today. `--parallel 1` is equivalent.

### 7. Result merging

Each instance writes its own log report. The parallel runner merges them:
- Combine pass/fail counts
- Merge timing tables (sorted by seq, tagged by container)
- Concatenate unexpected errors/warnings (tagged by container name)
- Single exit code (0 = all pass, 1 = any fail)
- Single summary table at the end

### 8. Container cleanup

After the test run:
- Instance 1 (`ha-sim`): left running (it's the dev container)
- Instances 2+: stopped and optionally removed (`--cleanup` flag)
- Config dirs 2+: optionally removed (`--cleanup` flag)

```bash
# Run with cleanup
python -m ha_sim_test --parallel 2 --cleanup

# Run without cleanup (reuse containers for next run — warm start)
python -m ha_sim_test --parallel 2
```

## Implementation Steps

### Phase 1: Parameterization (no parallelism yet)
1. Add `InstanceConfig` dataclass to `const.py` (or new `instance.py`)
2. Add `instance` field to `RecipeContext` in `base.py`
3. Update `helpers.py` — all `docker exec ha-sim` → `docker exec {instance.name}`, all `HA_URL` → `instance.ha_url`
4. Update `runner.py` — `setup()` and `teardown()` accept `InstanceConfig`
5. Update recipe code — replace `from ..const import CTL` with `ctx.instance.ctl` where needed (or keep module constants as defaults and override via context)
6. Make `SIMULATOR_HGI_ID` env-var configurable in ramses_extras `const.py`
7. Add `--parallel`, `--container-base`, `--port`, `--assign`, `--cleanup` CLI args
8. Verify single-container run still works (`--parallel 1` = current behaviour)

### Phase 2: Multi-container setup
1. Create `docker-compose.parallel.yml` template (or generate dynamically)
2. Implement `clone_config_dir()` — copy ha-sim config, patch port + MQTT URL
3. Implement `ensure_containers()` — start containers, wait for HA ready
4. Implement `cleanup_containers()` — stop/remove instances 2+
5. Test: start 2 containers manually, verify both respond on their ports
6. Test: verify MQTT topic isolation (packet on instance 1 doesn't appear on instance 2)

### Phase 3: Parallel runner
1. Implement `distribute_recipes()` — auto-distribute with constraints
2. Implement `run_parallel()` — `asyncio.gather` across containers
3. Implement `merge_results()` — combine reports
4. Test with `--parallel 2` on a subset of recipes
5. Test full suite with `--parallel 2`
6. Test `--parallel 3` and `--parallel 4` (if RAM allows)

### Phase 4: Optimization (optional)
1. Auto-balance by actual runtime (use previous run's timing data)
2. Run pure function tests (R39, R41-R43, R48-R49, R51-R57) locally without `docker exec`
3. Warm-start: reuse containers across runs (skip config dir clone if already exists)
4. Progress reporting: show per-container progress in real-time

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| MQTT broker overload (N connections) | Mosquitto handles hundreds of connections; 2-4 is trivial |
| Cross-talk via MQTT | Unique topic namespaces per HGI ID — already isolated |
| Container startup time (N x ~15s) | Start all in parallel; one-time cost |
| Config dir disk space (N x ~800MB) | Use `cp --reflink` on btrfs; or symlink ramses_rf/ramses_cc (only `.storage` is unique) |
| RAM exhaustion (4 x 500MB = 2GB) | Default to 2 containers; warn if `--parallel 4` and free RAM < 3GB |
| Docker restart recipes disrupt parallel runs | Put restart recipes on different containers; each only affects its own container |
| `clear_cached_state` stops container | Only affects the container running that recipe; others continue |
| Port collision with `hass` container (port 8123) | Instances start at 8124; `hass` is on 8123 — no conflict |
| `network_mode: host` conflicts | Instances 2+ use bridge networking with explicit port mappings |
| Recipe assumes `ha-sim` container name | All `docker exec` calls parameterized via `instance.name` |

## Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Parameterization | ~4-6 hours | Low — mechanical refactoring |
| Phase 2: Multi-container setup | ~2-3 hours | Medium — docker config, MQTT isolation |
| Phase 3: Parallel runner | ~3-4 hours | Medium — asyncio.gather, result merging |
| Phase 4: Optimization | ~2-3 hours | Low — nice-to-have improvements |
| **Total** | **~11-16 hours** | |

## Expected Result

| Configuration | Runtime | Speedup | RAM needed |
|--------------|---------|---------|-----------|
| `--parallel 1` (current) | ~27 min | 1x | ~0.5 GB |
| `--parallel 2` (default) | ~14 min | ~1.9x | ~1 GB |
| `--parallel 3` | ~9 min | ~3x | ~1.5 GB |
| `--parallel 4` | ~6 min | ~4.5x | ~2 GB |

*Runtime estimates assume a healthy ha-sim environment. On the current flaky
environment, runtimes are longer due to timeouts and retries — the speedup
factor remains the same since parallelism reduces wall-clock time regardless.*
