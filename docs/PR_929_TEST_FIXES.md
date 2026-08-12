# Fixes Found While Testing PR 926 (and carried forward to PR 929)

During ha-sim test suite validation of PR 926 (Phase 4a-4c.3: Shadow FSM,
Live Parity, Execution Cutover, PollingManager), three bugs were found and
fixed. These fixes are not part of PR 926 or the 927/928/929 stack and need
to be proposed as separate PRs on top of PR 929.

## 1. ramses_rf: DHW None values in build_set_dhw_params

**Commit**: `53673342` (ramses_rf, cherry-picked to `test/pr929-shadow`)

**Problem**: When the user changes only the water heater setpoint via
`water_heater.async_set_temperature`, `overrun` and `differential` are passed
as `None` through the call chain. `dict.get(key, default)` returns the default
only when the key is missing, not when it's explicitly `None`, causing
`TypeError` on the range validation (`None <= 10`).

**Fix** (`src/ramses_rf/commands/builders/dhw.py`):

```python
# Before:
setpoint = intent.get("setpoint", 50.0)
overrun = intent.get("overrun", 5)
differential = intent.get("differential", 1.0)

# After:
setpoint = intent.get("setpoint")
if setpoint is None:
    setpoint = 50.0
overrun = intent.get("overrun")
if overrun is None:
    overrun = 5
differential = intent.get("differential")
if differential is None:
    differential = 1.0
```

## 2. ramses_rf: PollingManager malformed RQ address convention

**Commit**: `82fdd5d7` (ramses_rf, cherry-picked to `test/pr929-shadow`)

**Problem**: `PollingManager.poll_due_commands` was constructing `CommandDTO`
with `addr1=addr2=device_id` (src=dst=device), which sends malformed RQ
packets. The correct convention is `addr1=HGI` (source), `addr2=device_id`
(destination), `addr3=NON_DEV_ADDR` — exactly what `build_rq_cmd()` already
does.

This caused the scan engine to see packets from the device to itself,
confusing device classification and causing protocol queue backups.

**Fix** (`src/ramses_rf/pipeline/polling.py`):

```python
# Before:
from ramses_tx import CommandDTO

...
cmd_dto = CommandDTO(
    verb="RQ",
    addr1=task.device_id,
    addr2=task.device_id,
    addr3="--:------",
    code=task.code,
    payload="00",
)

# After:
from ramses_rf.devices.helpers import build_rq_cmd

...
cmd_dto = build_rq_cmd(task.device_id, task.code)
```

## 3. ramses_cc: merge_schemas ignores config traits when device sets match

**Commit**: `dfb68b3` (ramses_cc, branch `test/pr920-shadow`)

**Problem**: When the cached schema and config schema had the same device IDs,
`merge_schemas` returned the cached schema as-is, ignoring any trait changes
(e.g. `_class`) in the config schema. This meant changing `_class` in the
config flow was silently ignored if the cached schema had the same device set.

This was the root cause of R24 (class mismatch flagging) failing: the config
schema had `_class: DIS` for the FAN, but `merge_schemas` returned the cached
schema with `_class: FAN`, so the mismatch was never detected.

**Fix** (`custom_components/ramses_cc/schemas.py`, line 664):

```python
# Before:
if cached_device_ids.issubset(config_device_ids) and not config_only_devices:
    _LOGGER.info("Using the cached schema")
    result = cached_schema

# After:
if cached_device_ids.issubset(config_device_ids) and not config_only_devices:
    _LOGGER.info("Using the cached schema (merged with config traits)")
    result = deep_merge(config_schema, cached_schema)
```

`deep_merge(config_schema, cached_schema)` — config is src (precedent), cached
is dst — lets config's `_class: DIS` win over cached's `_class: FAN` while
preserving cached topology.

## Recipe Updates (ramses_extras)

The following recipe updates were made to support PR 926+ testing:

- **R24**: Inject a 1FC9 heartbeat from the FAN after profile reload so the
  scan engine tracks 32:150000 and can detect the `_class=DIS` mismatch.
  Without this, the profile reload stops all simulator devices and the scan
  engine has no data for the FAN.
- **R55**: Updated for Phase 4b execution cutover (`wait_for_reply=False`).
  Needs further update for PR 928/929 which removes `wait_for_reply` entirely.
- **R56**: New recipe for PollingManager live cutover (Phase 4c.3).
  Needs update for PR 927 which removes `DiscoveryService` entirely.
- **R57**: New recipe for schema polling traits (Phase 4c.1).

## PR 929 Stack

PR 929 is stacked on top of:
- **PR 926**: Phase 4a-4c.3 (ConversationManager + PollingManager)
- **PR 927**: Phase 4c.4 (remove legacy DiscoveryService / discovery.py)
- **PR 928**: Deprecate `wait_for_reply` in transport layer
- **PR 929**: Streamline transport FSM, delete WantRply state

### Recipe adaptations needed for PR 929

1. **R55**: The `wait_for_reply=False` check needs to handle the case where
   `wait_for_reply` is removed from the transport layer entirely (PR 928/929).
   The check should pass if either:
   - `wait_for_reply=False` appears in `send()` source (PR 926 style), OR
   - `wait_for_reply` is not passed to `async_send_cmd` (PR 929 style)

2. **R56**: The `DiscoveryService.start_poller` check needs to handle the case
   where `DiscoveryService` is removed entirely (PR 927). The check should pass
   if either:
   - `DiscoveryService` exists and `start_poller` is a no-op (PR 926 style), OR
   - `DiscoveryService` does not exist (PR 927+ style — fully removed)

## 4. ramses_cc: dev.discovery access after PR 927 removal

**Commit**: `00b4dc7` (ramses_cc, branch `fix/merge-schemas-config-traits-pr929`)

**Problem**: PR 927 removed `DiscoveryService` from ramses_rf devices
(`dev.discovery`), but ramses_cc's `services.py` still accessed
`dev.discovery.cmds` and `dev.discovery.discover()`, causing
`'TrvActuator' object has no attribute 'discovery'` warnings and
preventing entity creation for newly accepted devices.

**Fix** (`custom_components/ramses_cc/services.py`): Use
`getattr(dev, 'discovery', None)` to gracefully handle both PR 926
(DiscoveryService exists as no-op) and PR 927+ (removed entirely).

## 5. Pre-existing routing gap exposed by PR 927

**Problem**: `_resolve_logical_targets` in `ramses_rf/dispatcher.py`
looks up zones via the source device's TCS (`tcs = getattr(src_dev,
"tcs", None)`). When a 30C9 (room temperature) packet comes from a
zone sensor (e.g. 01:150003) that is classed as CTL, the sensor has
its own (empty) TCS, so the zone is not found and the temperature is
not propagated to the zone entity.

In PR 926, this was masked by the `DiscoveryService` polling the CTL
for 30C9 via RQ/RP, which set the zone temperature through the CTL's
TCS. PR 927 removed `DiscoveryService`, exposing this gap.

**Fix needed** (ramses_rf, future PR): Update
`_resolve_logical_targets` to also look up zones by sensor ID — when
the source device is a zone sensor, find the zone in the main TCS via
the sensor-to-zone mapping.

**Workaround** (R40 recipe): Inject the 30C9 from the CTL (01:150000)
instead of the zone sensor (01:150003), since the CTL's TCS has the
zone.

## 6. ramses_cc: resolve_async_attr cooldown blocks None→value transitions

**Commit**: `32a6810` (ramses_cc, branch `fix/merge-schemas-config-traits-pr929`)

**Problem**: `resolve_async_attr` in `ramses_cc/helpers.py` has a 30s
cooldown to prevent command floods from async getters with side effects
(e.g. `system_mode()` dispatches RQ commands).  However, when the cached
value is `None` (unhydrated state), the cooldown blocks re-reads even
when the underlying state has been updated (e.g. a 30C9 temperature
broadcast sets `temp_state.temperature`).

In the full test suite, the climate entity's `current_temperature` is
read during the initial 30s wait (before the 30C9 inject), caching
`None`.  The 30C9 then updates `temp_state.temperature` to 27.52, but
the cooldown prevents the entity from re-reading the value.  This only
manifests in the full suite (not in isolation) because earlier recipes
trigger the initial state read.

**Fix** (`custom_components/ramses_cc/helpers.py`): Skip the cooldown
when the cached value is `None` so that the first real data is picked
up immediately.  The cooldown still applies once a non-None value is
cached, preventing command floods for side-effecting getters.

## Final Test Results

After applying all fixes above, the full `ha-sim` test suite passes:

```
Started:  2026-07-24 21:59:05
Elapsed:  1999.2s (33.3 min)
Passed:   347
Failed:   0
Total:    347

Unexpected errors:   0
Unexpected warnings: 0 (ramses_cc/ramses_rf)
```

All 57 recipes pass (3 skipped: R41/R42/R43 — pending ramses_rf HVAC
topology PR, not part of PR 929 scope).

### Branches / commits

- **ramses_rf** (`test/pr929-shadow`): PR 929 + cherry-picked fixes
  - `53673342` fix(dhw): handle None values for build_set_dhw_params
  - `2d1613bc` fix(polling): use build_rq_cmd for correct RQ address convention
- **ramses_cc** (`fix/merge-schemas-config-traits-pr929`):
  - `dfb68b3` fix: merge_schemas ignores config traits when device sets match
  - `8029ebd` fix(services): migrate _adjust_sentinel_packet to CommandDTO positional addressing
  - `00b4dc7` fix(services): handle removal of dev.discovery in PR 927
  - `32a6810` fix: skip resolve_async_attr cooldown when cached value is None
- **ramses_extras** (`master`): recipe updates + this report
  - `98720f1` fix(r24): inject FAN heartbeat so scan engine tracks 32:150000
  - `61ac53b` test(r55,r56): adapt recipes for PR 927/928/929 stack
  - `ec09204` fix(r55): fix syntax error in wait_for_reply check
  - `8e410bd` fix(r40): inject 30C9 from CTL instead of zone sensor
  - `a80f28a` docs: add resolve_async_attr cooldown fix to PR 929 report

### Out of scope (future PRs)

- **ramses_rf `_resolve_logical_targets`**: zone temperature packets
  from sensors classed as CTL (e.g. 01:150003) are not routed to the
  zone in the main TCS.  The R40 recipe works around this by injecting
  from the main CTL.  A proper fix would look up zones by sensor ID
  when the source device's own TCS has no zones.
