# ha-sim Test Tool

**Location:** `tools/ha_sim_test/` (Python package)
**Reports:** `tools/ha_sim_test/reports/` (overridable via `--reports-dir`)

## Overview

`ha_sim_test` is an automated end-to-end test suite for ramses_cc + ramses_extras running on the `ha-sim` Docker container. It exercises all PR 764 features (schema management, discovery services, HVAC/FAN handling, device lifecycle) via the HA websocket + REST API at 100x simulator speed.

Each test recipe lives in its own module under `tools/ha_sim_test/recipes/` and is run by the orchestrator in `tools/ha_sim_test/runner.py`.

## Prerequisites

- The `ha-sim` Docker container must be running with:
  - ramses_cc installed (from `custom_components/ramses_cc/`)
  - ramses_extras installed (from `custom_components/ramses_extras/`)
  - The device_simulator feature enabled
  - Long-lived access token configured (or the test authenticates via login flow)
- HA websocket on `ws://localhost:8124/api/websocket`
- HA REST API on `http://localhost:8124/api/`
- A local MQTT broker on port 1884 (see [Local MQTT broker](#local-mqtt-broker)
  below)

### Local MQTT broker

The ha_sim_test tool uses a **local MQTT broker** on port 1884 (isolated
from any production broker on port 1883).  This is required for both
single-container and parallel runs — ramses_cc's serial port is configured
as `mqtt://localhost:1884/RAMSES/GATEWAY_SIM/<hgi_id>`.

**Setup** (one-time):

```bash
cd /home/willem/docker_files/ha-sim
docker compose -f docker-compose.mqtt.yml up -d
```

This starts an `eclipse-mosquitto:2` container (`ha-sim-mqtt`) with
`network_mode: host`, listening on `0.0.0.0:1884`.  The config file is at
`/home/willem/docker_files/ha-sim/mosquitto.conf`.

**Verify**:

```bash
docker exec ha-sim sh -c "nc -z localhost 1884 && echo OK || echo FAIL"
# Should print: OK
```

**Logs**:

```bash
docker logs -f ha-sim-mqtt
```

**Parallel containers**: Instance 1 (`ha-sim`) uses `network_mode: host`
and connects to `localhost:1884`.  Instances 2+ (`ha-sim-2`, `ha-sim-3`,
...) use bridge networking and connect to `host.docker.internal:1884`.
The `parallel.py` runner automatically patches both the ramses_cc serial
port URL and the HA MQTT integration broker address during config dir
cloning.  The docker-compose template includes
`extra_hosts: ["host.docker.internal:host-gateway"]` for hostname
resolution inside bridge containers.

**MQTT monitor**: To verify packets are reaching the broker, run the
monitor in a separate terminal while tests are running:

```bash
source ~/venvs/extras/bin/activate
python -m tools.ha_sim_test.mqtt_monitor --duration 600 --verbose
```

This subscribes to `RAMSES/GATEWAY_SIM/#` and logs every message with
timestamp, topic, and payload.  Useful for diagnosing whether dropped
packets are a broker-side or consumer-side issue.

### Testing with a local ramses_rf (PYTHONPATH)

HA installs `ramses_rf` from the ramses_cc `manifest.json` (`ramses-rf==0.58.4`)
on every startup, overriding any manually `pip install`ed version.  To test a
local/fixed ramses_rf, the ha-sim docker-compose already bind-mounts
`/home/willem/dev/ramses_rf` to `/config/ramses_rf`.  Adding
`PYTHONPATH=/config/ramses_rf/src` to the container environment makes Python
load the local copy before site-packages (where the pip-installed 0.58.4
lives) — no modification to ramses_cc needed.

The `docker-compose.yml` at `/home/willem/docker_files/ha-sim/docker-compose.yml`
should have:

```yaml
    environment:
      - TZ=Europe/Amsterdam
      - HASSIO_PORT=8124
      - PYTHONPATH=/config/ramses_rf/src
```

After changing the environment, recreate the container (a plain `restart` is
not enough — environment changes require recreation):

```bash
cd /home/willem/docker_files/ha-sim
docker compose up -d
```

To verify the local copy is loaded:

```bash
docker exec ha-sim python3 -c 'import sys; print([p for p in sys.path if "ramses_rf" in p])'
# Should show: ['/config/ramses_rf/src']
```

To revert, remove the `PYTHONPATH` line and `docker compose up -d` again.

## Running the tests

```bash
cd /home/willem/dev/ramses_extras/tools
python3 -m ha_sim_test
```

To run specific recipes only:

```bash
python3 -m ha_sim_test R06 R29
```

The test suite takes ~6 minutes to complete (single container). Output is printed to stdout with:
- A section header for each recipe
- `PASS:` / `FAIL:` lines for each check
- A summary at the end with the total count

Exit code: `0` = all passed, `1` = some failed.

### CLI parameters

```
usage: ha_sim_test [-h] [--parallel N] [--container-base CONTAINER_BASE]
                   [--port PORT] [--assign CONTAINER:R1,R2,...] [--cleanup]
                   [--wait-scale-blind FACTOR] [--wait-scale-poll FACTOR]
                   [recipes ...]
```

| Parameter | Default | Description |
|---|---|---|
| `recipes` (positional) | all | Recipe IDs to run (e.g. `R06 R29`). Order is preserved. |
| `--parallel N` | `1` | Run across N containers in parallel. `1` = sequential on `ha-sim`. See [Parallel mode](#parallel-mode). |
| `--container-base` | `ha-sim` | Base container name. Instance 1 uses this name directly; instances 2+ get a suffix (e.g. `ha-sim-2`). |
| `--port PORT` | `8124` | Starting HA port for instance 1. Instances 2+ use `port+1`, `port+2`, etc. |
| `--assign CONTAINER:R1,R2,...` | (auto) | Manual recipe assignment (advanced). Can be repeated. Unassigned recipes are auto-distributed. Example: `--assign ha-sim-2:R01,R02`. |
| `--cleanup` | off | Stop and remove parallel containers (instances 2+) and their cloned config dirs after the run. Without this flag, containers are stopped but config dirs are kept for warm restarts. Instance 1 (`ha-sim`) is always left running. |
| `--wait-scale-blind FACTOR` | `1.0` | Scale factor for fixed `wait()` blind sleeps. See [Wait scaling](#wait-scaling). |
| `--wait-scale-poll FACTOR` | `1.0` | Scale factor for `wait_for()` timeout ceilings. See [Wait scaling](#wait-scaling). |
| `--wait-floor-blind SECONDS` | `0` | Global minimum (real-time seconds) for all blind `wait()` sleeps. Protects sensitive waits when using aggressive scale factors. |
| `--wait-floor-poll SECONDS` | `0` | Global minimum for all `wait_for()` timeout ceilings. Per-call `floor=` (e.g. `wait_for_ha_ready` uses 10s) takes the max with this. |

### Examples

```bash
# Run all recipes on the default ha-sim container
python3 -m ha_sim_test

# Run two specific recipes
python3 -m ha_sim_test R06 R29

# Run across 4 containers in parallel, clean up afterwards
python3 -m ha_sim_test --parallel 4 --cleanup

# Run on 2 containers, manually assigning recipes to containers
python3 -m ha_sim_test --parallel 2 \
    --assign ha-sim:R01,R02,R03 \
    --assign ha-sim-2:R04,R05,R06

# Run fast: defaults are already 0.5/0.08/3 — no flags needed
python3 -m ha_sim_test --parallel 4 --cleanup

# Run safe (no scaling, full waits)
python3 -m ha_sim_test --wait-scale-blind 1.0 --wait-scale-poll 1.0 --wait-floor-blind 0

# Pipe to a log file (dashboard auto-disables, plain interleaved output)
python3 -m ha_sim_test --parallel 4 > /tmp/run.log 2>&1

# Write reports to a custom directory
python3 -m ha_sim_test --reports-dir /tmp/ha_sim_run_20260812
```

### Parallel mode

When `--parallel N` is greater than 1, the runner spins up N HA containers
(`ha-sim`, `ha-sim-2`, ..., `ha-sim-N`) and distributes the recipes across
them. Each container gets its own config dir (cloned from `ha-sim`'s
`.storage`) and its own HA port.

- **Container naming:** `--container-base ha-sim` → `ha-sim`,
  `ha-sim-2`, `ha-sim-3`, ...
- **Port assignment:** `--port 8124` → 8124, 8125, 8126, ...
- **Recipe distribution:** recipes are split evenly across containers
  in seq order. Use `--assign` for manual control.
- **Warm restarts:** without `--cleanup`, stopped containers keep their
  config dirs so the next run starts faster (no fresh schema learning).
  Use `--cleanup` to remove them for a cold start.
- **Instance 1 (`ha-sim`)** is always left running after the run (it's
  the dev/debug instance); only instances 2+ are stopped.
- **MQTT connectivity:** Instance 1 uses `network_mode: host` and
  connects to the local MQTT broker at `localhost:1884`.  Instances 2+
  use bridge networking with `extra_hosts: ["host.docker.internal:host-gateway"]`
  and connect to `host.docker.internal:1884`.  The runner automatically
  patches both the ramses_cc serial port URL and the HA MQTT integration
  broker address during config dir cloning.  See [Local MQTT broker](#local-mqtt-broker)
  for setup instructions.

### Live dashboard

In parallel mode, when stdout is a real terminal, a live per-container
dashboard is rendered instead of a wall of interleaved raw prints. Each
container gets a fixed-height pane showing:

- Current recipe being executed
- Running pass/fail tally
- Elapsed time
- Last few output lines

The panes refresh in place via ANSI cursor movement. Output is
attributed to the correct container via the existing contextvars-based
`get_current_instance()` mechanism — not by parsing `[name]` text
prefixes — so attribution is correct even when containers execute
concurrently (interleaved at `await` points).

The dashboard auto-disables when stdout isn't a TTY (e.g. piped to a
file or running in CI), so existing `> file.log 2>&1` + `grep`
workflows are completely unaffected.

### Wait scaling

The suite has ~138 fixed blind sleeps (`wait(N)`, totalling ~730s) and
~63 polling waits (`wait_for(timeout=N)`, self-exiting). Two independent
scale knobs let you trade safety for speed:

- **`--wait-scale-blind FACTOR`** (or `HA_SIM_TEST_WAIT_SCALE_BLIND`):
  scales every fixed `wait()`/`ctx.wait()` blind sleep. These are the
  dominant cost — 80 of 138 calls use `wait(5)`, totalling ~400s — and
  also the riskiest to cut: 5s is already a deliberate "let MQTT/HA
  settle" pause, so 5→0.5 is a 10x cut on something that may genuinely
  need 2-3s.

- **`--wait-scale-poll FACTOR`** (or `HA_SIM_TEST_WAIT_SCALE_POLL`):
  scales every `wait_for()` timeout ceiling. These poll and return as
  soon as the condition is met, so the timeout is just a safety margin.
  On the simulator, conditions typically resolve in 2-3s; if they
  haven't, the test has probably failed. Scaling 30s→3s just tightens
  the failure ceiling — safe to cut aggressively.

- **`--wait-floor-blind SECONDS`** (or `HA_SIM_TEST_WAIT_FLOOR_BLIND`):
  global minimum (real-time seconds) that all blind sleeps respect,
  regardless of the scale factor. When using aggressive scale factors,
  this protects sensitive waits (scan engine processing, sync operations,
  entity hydration) that need a hard minimum of ~3s. The output shows
  both the original and scaled values: `Waiting 5s→3s for sync...`.

- **`--wait-floor-poll SECONDS`** (or `HA_SIM_TEST_WAIT_FLOOR_POLL`):
  same for `wait_for()` timeout ceilings. The per-call `floor=` parameter
  (e.g. `wait_for_ha_ready` uses floor=10 for docker restarts) takes the
  max with this global floor.

**Precedence:** CLI flag > per-bucket env var > legacy
`HA_SIM_TEST_WAIT_SCALE` (sets both) > default `1.0`. Floors default to
0 (no protection); per-call `floor=` takes the max with the global floor.

| Goal | Blind | Poll | Floor blind | Notes |
|---|---|---|---|---|
| Safe speedup on failures | 1.0 | 0.1 | 0 | Only tightens poll ceilings |
| **Recommended fast run** | **0.5** | **0.08** | **3** | **0 new failures, ~9 min on 4 containers** |
| Aggressive | 0.5 | 0.05 | 3 | 2-3 new flaky fails (R11/R24/R36 race conditions) |
| Slow machine / debugging | 2.0 | 2.0 | 0 | Give everything more headroom |

Going below 0.08 poll scale introduces flaky failures from timing-sensitive
operations (scan engine processing, entity state writes, class_mismatch
detection) that can't be fixed with floors alone — they're inherent race
conditions in the HA entity state machine.

Per-call floors (built into helpers, no CLI flag needed):
``wait_for_ha_ready``: floor=10s (docker restart)
``wait_for_ramses_cc_loaded``: floor=15s (docker restart cold start)
``wait_for_ramses_cc_reload``: floor=8s (in-process profile reload)
``wait_for_schema_stable``: floor=3s (polls schema, exits early when stable)
``wait_for_schema_populated``: floor=3s (polls schema key count)
``wait_for_schema_has``: floor=3s (polls for specific device in schema)
``wait_for_entity_state``: floor=3s (polls entity state via REST)
``wait_for_transport_reconnect``: floor=3s (polls MQTT subscription log)

**Output format:** when a wait is scaled, the output shows both the
original and actual duration: `Waiting 5s→3s for sync_learned_topology...`
or `Waiting up to 30s→10s for ha-sim to start up...`. This makes it
visible which waits are being shortened and by how much.

**Docker restart floors:** `wait_for_ha_ready()` has a built-in floor of
10s — docker restarts take a hard 3-5s minimum before the API is
reachable, so scaling below 10s makes no sense. This is separate from
the global `--wait-floor-poll` (the effective floor is the max of both).

## Test reports

After each run, two reports are written to the reports directory
(default: `tools/ha_sim_test/reports/`, overridable via `--reports-dir`):

### Log report

```
log_report_{container}_{timestamp}.txt
```

This report contains:
- **Baseline timestamp** — when log monitoring started
- **Pre-restart captured lines** — logs captured before docker restarts (which wipe the log buffer)
- **Total log lines** — across the entire test run
- **Errors** — unexpected ERROR lines from ha-sim logs (should be 0)
- **Warnings** — unexpected WARNING lines from ramses_cc/ramses_rf/ramses_tx (should be 0)
- **Expected warnings (filtered out)** — the full list of known/expected patterns

Up to `MAX_REPORTS_PER_CONTAINER` (5) log reports are kept per container;
older ones are pruned automatically.

### Summary report

```
summary_{container}_{timestamp}.md      # single-container mode
summary_parallel_{timestamp}.md         # parallel mode
```

A Markdown report (readable by both humans and machines) containing:
- **Run metadata** — timestamp, status (PASS/FAIL), totals, wall time
- **Per-container overview** — pass/fail/time/status table (parallel mode)
- **Per-recipe timing** — recipe, container, pass, fail, duration, title
- **Check results** — every PASS/FAIL line with detail
- **Container errors** — fatal errors per container (if any)
- **Log report references** — paths to the corresponding log reports

### Log monitor design

The `LogMonitor` class in the test script:

1. **Captures a baseline** at startup — records the timestamp of the last log line
2. **Captures logs before docker restarts** — `capture_before_restart()` fetches and classifies all logs since the baseline, storing classified ERROR/WARNING lines in an accumulator. This prevents data loss when `docker restart ha-sim` wipes the log buffer.
3. **Resets baseline after restart** — `reset_baseline()` sets a new timestamp for post-restart log collection
4. **Collects and classifies at the end** — `collect()` merges pre-restart accumulated logs with post-restart logs, classifies each line as ERROR/WARNING/none
5. **Writes the report** — `write_report()` generates the human-readable file

### Expected warning filtering

The `EXPECTED_WARNINGS` list contains ~30 patterns that are filtered out because they are known simulator artifacts or expected behaviour:

| Category | Examples |
|---|---|
| Intentional test actions | `Sanitising invalid main_tcs` (R10) |
| Simulator artifacts | `PARENT CHANGE EXCEPTION`, `LINK EXCEPTION`, `FILTER EXCEPTION`, `PacketInvalid` |
| Profile reload transients | `cleared CONF_SCHEMA`, `MQTT disconnected`, `Task exception was never retrieved` |
| ramses_rf cosmetic | `Packet idx is`, `excessive datetime difference`, `Unexpected verb/code` |
| Discovery (fresh_start) | `not an allowed device_id`, `Failed to send discovery cmd`, `No response for` |
| HA core (not our code) | `template.helpers`, `aiohttp.server`, `via_device`, `not been tested` |
| RF config validation | `rf_config_validation` (sim has no bound REM) |

If a new bug introduces an unexpected ERROR or WARNING, it will appear in the report and fail the test — making regressions easy to catch.

## Test recipes

| Recipe | Description | Checks |
|---|---|---|
| Setup | Load mixed profile (100x speed), activate all devices | — |
| R6/14 | Zone binding via inject_message (000C packet) | 2 |
| R3 | remove_device — HGI rejection | 1 |
| R2 | remove_device — remove TRV | 3 |
| R4 | remove_device — CTL / main_tcs removal | 2 |
| R15 | Verify hvac_schema key in .storage | 1 |
| R7 | HVAC schema caching — FAN + REM | 2 |
| R7b | Restart ha-sim, verify HVAC survives | 2 |
| R5 | No resurrection after restart | 2 |
| R11 | Discover → accept → remove lifecycle | 5 |
| R10 | Invalid main_tcs safety net | 3 |
| R8 | HVAC schema caching — merge union on reload | 3 |
| R9 | User schema edits survive sync — _alias | 2 |
| R12 | HVAC device loss scenario | 3 |
| R16 | Concurrency/stress test | 4 |
| R1 | Heat profile activation + schema/entities | 5 |
| R14 | Raw packet injection — zone rebinding | 1 |
| R17 | Discovery service lifecycle | 7 |
| R34 | Water heater DHW CQRS hydration (issue 843) | 4 |
| Log Report | ERROR/WARNING analysis | 2 |
| **Total** | | **54** |

## Services tested

| Service | Tested by |
|---|---|
| `ramses_cc.sync_topology` | R6/14, R9, R14, R16 |
| `ramses_cc.remove_device` | R2, R3, R4, R11, R16 |
| `ramses_cc.accept_discovered_device` | R11, R17 |
| `ramses_cc.get_discovered_devices` | R17 |
| `ramses_cc.discard_discovered_device` | R17 |
| `ramses_cc.enable_discovered_device` | R17 |
| `ramses_cc.disable_discovered_device` | R17 |
| `ramses_cc.remove_discovered_device` | R17 |
| `ramses_cc.add_faked_rem` | Prepared only (stub — WIP) |
| `ramses_extras.device_simulator/load_profile` | Setup, R11 |
| `ramses_extras.device_simulator/activate_device` | Setup, R1 |
| `ramses_extras.device_simulator/load_profile_yaml` | R1, R8, R9, R10, R14, R17 |
| `ramses_extras.device_simulator/inject_message` | R6/14, R11, R14, R16 |
| `ramses_extras.device_simulator/start_scenario` | R12 |
