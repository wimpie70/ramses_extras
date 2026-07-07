# ha-sim Test Tool

**Location:** `tools/ha_sim_test.py`
**Report:** `/tmp/ha_sim_test_log_report.txt`

## Overview

`ha_sim_test.py` is an automated end-to-end test suite for ramses_cc + ramses_extras running on the `ha-sim` Docker container. It exercises all PR 764 features (schema management, discovery services, HVAC/FAN handling, device lifecycle) via the HA websocket + REST API at 100x simulator speed.

## Prerequisites

- The `ha-sim` Docker container must be running with:
  - ramses_cc installed (from `custom_components/ramses_cc/`)
  - ramses_extras installed (from `custom_components/ramses_extras/`)
  - The device_simulator feature enabled
  - Long-lived access token configured (or the test authenticates via login flow)
- HA websocket on `ws://localhost:8124/api/websocket`
- HA REST API on `http://localhost:8124/api/`

## Running the tests

```bash
cd /home/willem/dev/ramses_extras
python3 tools/ha_sim_test.py
```

The test suite takes ~6 minutes to complete. Output is printed to stdout with:
- A section header for each recipe
- `PASS:` / `FAIL:` lines for each check
- A summary at the end with the total count

Exit code: `0` = all passed, `1` = some failed.

## Test report

After the run, a log report is written to:

```
/tmp/ha_sim_test_log_report.txt
```

This report contains:
- **Baseline timestamp** — when log monitoring started
- **Pre-restart captured lines** — logs captured before docker restarts (which wipe the log buffer)
- **Total log lines** — across the entire test run
- **Errors** — unexpected ERROR lines from ha-sim logs (should be 0)
- **Warnings** — unexpected WARNING lines from ramses_cc/ramses_rf/ramses_tx (should be 0)
- **Expected warnings (filtered out)** — the full list of known/expected patterns

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
| Log Report | ERROR/WARNING analysis | 2 |
| **Total** | | **50** |

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
