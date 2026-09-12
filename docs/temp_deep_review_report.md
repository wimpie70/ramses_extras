# Deep Review Report — Multi-HGI Pooling

**Date**: 2026-09-12
**Branches**:
- `ramses_rf`: `feat/phase2-signature-policy`
- `ramses_cc`: `fix/issue-1171-pool-config-bugs`

## 1. Commits Reviewed

### ramses_rf (`feat/phase2-signature-policy`)

| Commit | Description |
|--------|-------------|
| `b82127df` | fix: callback-driven write_routed marks child online + allow stale children |
| `4cac4ad7` | fix: mypy comparison-overlap in stale child tests |
| `96274b82` | test: add tests for stale child fallback and mark_online on TX |
| `6780860b` | fix: allow stale children as last resort for TX + mark online on TX success |
| `0642c100` | fix: mypy unreachable error in _last_rx_time tests |
| `1107bac6` | fix: is_active returns None (unknown) when no packets received yet |
| `00ca8eb5` | fix: allow device creation for pool member HGIs in known_list |
| `392e9178` | test: add regression tests for _last_rx_time gateway health |
| `5adaff71` | fix: gateway status shows problem when traffic is from unknown devices |

### ramses_cc (`fix/issue-1171-pool-config-bugs`)

| Commit | Description |
|--------|-------------|
| `6fe47f80` | fix: update tests for passive_scan default True + improve review messages |
| `261aeafb` | fix: passive_scan defaults to True when missing from old config entries |
| `baa78717` | fix: don't auto-accept primary HGI if explicitly removed from pool |
| `43c2ed64` | fix: health check treats None (unknown) as not offline |
| `26b0793b` | fix: preserve _owner when removing HGI from pool |
| `91a543d5` | fix: auto-accept primary serial HGI as pool member |

## 2. Issues Found & Fixed

### 2.1 Gateway status shows "problem" after restart (ramses_rf + ramses_cc)

**Root cause**: `HgiGateway.is_active()` returned `False` when no packets had been
received yet. The `BinarySensorDeviceClass.PROBLEM` entity inverts this to
`True` ("problem"), causing a false alarm for ~60s after restart until the first
real packet arrives.

**Fix**:
- `is_active()` now returns `None` (unknown) when no packet history exists.
- The entity shows "unknown" during startup, then flips directly to "off" (OK)
  when the first packet arrives — no false "problem" state.
- The coordinator's health check treats `None` as "not offline" (no
  notification during startup).

**Tests**: `test_is_active_rx_but_filtered`, `test_is_active_rx_time_takes_precedence`,
`test_is_active_fallback_to_this_msg`, `test_is_active_rx_but_filtered_expired`.

### 2.2 Gateway status shows "problem" when traffic is from unknown devices (ramses_rf)

**Root cause**: `is_active()` read `protocol._this_msg.timestamp` to determine
gateway health. However, `_this_msg` is only set when a packet passes the
device_id filter — packets from devices not in the schema are dropped before
`_this_msg` is updated. This caused `is_active()` to return `False` even though
the transport was actively receiving RF traffic.

**Fix**: Added `_last_rx_time` to the protocol, set in `packet_received()` for
**every** received packet, before the device_id filter check. `is_active()`
now uses `_last_rx_time` with a fallback to `_this_msg` for backward
compatibility.

**Tests**: `test_last_rx_time_set_on_received`, `test_last_rx_time_set_even_when_filtered`,
`test_last_rx_time_updated_on_each_packet`.

### 2.3 Pool member HGI device not created in ramses_rf registry (ramses_rf)

**Root cause**: `instantiate_devices()` in `validators.py` skipped device
creation for "foreign" HGIs (any HGI that isn't the active gateway). This
prevented the MQTT-only HGI `18:149488` from being created in the device
registry, so the binary_sensor platform couldn't initialize its entity.

**Fix**: Added `and msg.src.id not in gateway.config.known_list` to the foreign
HGI skip condition. Pool member HGIs (in the known_list) are now created
normally as `HgiGateway` devices.

### 2.4 TX fails with "No connected child transport available for send" (ramses_rf)

**Root cause**: `PoolChild.is_sendable` excludes stale children (connected but
no packets within `health_timeout`). If the pool was idle for 180s, all
children became stale and TX failed.

**Fix**: Added a last-resort stale-child fallback in `_select_child()`:
1. First select only normal `is_sendable` children.
2. If none exist, select connected, stale, accepted, send-ready children.
3. Route through those candidates.

Also added `child.mark_online()` after successful writes in all TX paths:
- `write_routed` callback-driven publish path
- `write_routed` `write_frame` path
- `write_routed` `send_frame` path
- Legacy `PooledTransport.write_frame()` path

This allows a successful send to restore online state even for devices like
HGI80 that do not echo.

**Tests**: `test_select_child_falls_back_to_stale_when_no_online`,
`test_select_child_returns_none_when_no_sendable`,
`test_select_child_prefers_online_over_stale`,
`test_write_routed_marks_child_online_on_success`,
`test_write_routed_marks_child_online_on_send_frame`,
`test_write_frame_legacy_marks_child_online`,
`test_write_routed_callback_driven_marks_child_online`.

### 2.5 Callback-driven `write_routed` didn't call `mark_online()` (ramses_rf)

**Root cause**: The callback-driven publish path returned `SUBMITTED` without
calling `child.mark_online()`, unlike all other TX paths. A stale MQTT child
that successfully published stayed stale.

**Fix**: Added `child.mark_online()` after successful `publish_frame()`.

### 2.6 `write_routed` callback-driven `is_sendable` check blocked stale children (ramses_rf)

**Root cause**: The `_select_child` stale fallback was ineffective for
callback-driven children because `write_routed` re-checked `is_sendable`,
which excludes stale children.

**Fix**: Relaxed the guard to also allow stale children (connected, accepted,
send-ready) — the same conditions as the `_select_child` fallback.

### 2.7 Removing HGI from pool wiped `_owner` (ramses_cc)

**Root cause**: `entry.pop(SZ_TR_OWNER, None)` removed ownership, making the
HGI a discovery candidate instead of a removed member, making re-add harder.

**Fix**: Removed the `entry.pop(SZ_TR_OWNER, None)` calls. Now only
`_removed_from_pool = True` is set. `_owner` is preserved so re-adding is a
single click.

Also updated `_get_accepted_hgi_ids()` and `is_pool_enabled` in
`coordinator.py` to check `_removed_from_pool` in addition to `_owner`.

### 2.8 `_auto_accept_primary_hgi` didn't check `_removed_from_pool` (ramses_cc)

**Root cause**: Could incorrectly re-add a removed HGI on old schemas where
`_owner` had previously been wiped.

**Fix**: Added `_removed_from_pool` check before auto-accepting.

### 2.9 Passive scan incorrectly appeared disabled (ramses_cc)

**Root cause**: Existing HA config entries had no `passive_scan` key under
`advanced_features`, even though the schema default is `True`. Runtime code
defaulted missing keys to `False`, so passive discovery did not start and the
Review steps displayed "Passive device scan is not enabled".

**Fix**: Use `True` as the runtime fallback in `coordinator.py` and
`__init__.py`.

### 2.10 "Passive device scan is not enabled" message misleading (ramses_cc)

**Root cause**: The review steps showed "Passive device scan is not enabled"
even when the real issue was a failed transport or the integration not running.

**Fix**: Improved the message to distinguish:
- "not running" (coordinator is None)
- "transport failed to start" (client is None)
- "passive scan disabled" (coordinator running, client OK, but scan disabled)

### 2.11 Mypy errors in tests (ramses_rf)

**Root cause**: Mypy type narrowing — `assert ... is NodeAvailability.STALE`
narrowed the attribute to `Literal[STALE]`, making the subsequent
`assert ... is NodeAvailability.ONLINE` a non-overlapping comparison.

**Fix**: Use explicit `availability: NodeAvailability = ...` type annotation to
override mypy's narrowing.

## 3. Verified Correct (No Issues)

- **Reconnect logic**: Bounded (`max_reconnect_attempts`), exponential backoff
  (1s→30s cap), `_reconnecting` flag prevents duplicate loops, exhaustion
  permanently closes.
- **Stale child fallback**: Only uses STALE children (not OFFLINE) when no
  online children exist. OFFLINE means definitively disconnected.
- **`_auto_accept_primary_hgi`**: Correctly checks `_removed_from_pool` before
  re-adding.
- **`_owner` preservation**: All pool membership checks
  (`_get_accepted_hgi_ids`, `is_pool_enabled`,
  `_extract_pool_hgis_from_schema`) correctly check `_removed_from_pool`.
- **Credential exposure**: `redact_url` used consistently throughout.
- **Translation placeholders**: `{message}` present in both en/nl for all
  three steps.
- **Gateway status**: `is_active()` returns `None` (unknown) when no packets
  received, entity shows "unknown" not "problem".
- **Callback-driven child connection inference**: Correctly infers
  connectivity from inbound packets when LWT is missed.

## 4. Test Results (Unit Tests)

- `ramses_rf`: 3120 passed, 9 skipped
- `ramses_cc`: 1913 passed, 15 skipped
- Lint, mypy, pre-commit: all clean on both repos

## 5. HA Sim Test Results

**Full suite**: 733 passed, 1 failed (pre-existing), 734 total
**Wall time**: 76.3 min
**Log report**: No unexpected ERROR/WARNING logs

### R77 failure (pre-existing, not caused by pool PRs)

**Recipe**: R77 — HGI not re-discovered every cycle (issue 987)
**Symptom**: "no new discovery notifications after checkpoint" failed because
other devices (ownerless HGIs from previous tests) were being re-notified by
the issue 1119 logic, not the foreign HGI under test.

**Root cause**: The test's check was too broad — it checked that NO new
notifications appeared, but ownerless devices from previous tests (e.g.
18:149488) were legitimately being re-flagged by the issue 1119 logic
(devices in schema without `_owner` are re-flagged for review every
checkpoint).

**Fix**: Scoped the check to the foreign HGI only — "no new discovery
notification for foreign HGI after checkpoint". Also set `_owner: me` on
the CTL in the minimal profile so it's not flagged as a discovery
candidate.

**Verified**: R77 now passes (3/3 checks).

### Pool-specific recipes (all pass)

- R98: PooledTransport dedup & routing (14 checks)
- R99: MQTT HGI auto-discovery (2 checks)
- R100: RSSI best-across-HGIs (12 checks)
- R102: Clean-schema startup bind (5 checks)
- R109: Connection loss detection (9 checks)
- R110: Schema mutation and pool type changes (13 checks)
- R111: HGI80 + MQTT source patching (11 checks)
- R112: mqtt_hgi_id with serial primary (6 checks)
- R113: MQTT exclusion reconciliation (19 checks)
- R114: Pool display labels and switching (19 checks)
- R115: End-to-end TX/RX through MQTT broker (15 checks)
- R116: Live pool type switching (10 checks)
- R118: TX/RX after transport type switch (14 checks)
- R119: Live MQTT exclusion and un-exclusion (7 checks)
- R120: Live primary HGI switch and TX routing (10 checks)
- R121: Live failover: primary disconnects, TX fails over (10 checks)
- R122: Live MQTT child disconnect and reconnect (10 checks)
- R123: Non-primary HGI USB→MQTT switch (19 checks)

## 6. Hardware Test Results (hass — 2 USB/MQTT ESPs)

### Setup

- **Serial primary**: `/dev/ttyACM0` (HGI 18:130236, USB)
- **MQTT additional port**: `mqtt://***:***@192.168.40.11:1883/RAMSES/GATEWAY/18:130236`
- **MQTT HGI**: 18:149488 (callback-driven child)
- **Second USB HGI**: `/dev/ttyACM1` — NOT in pool config (not in `additional_ports`)
- **Pool**: 3 children (1 serial + 2 MQTT callback-driven), 2/3 connected

### Pool status after restart

```
PooledTransport: child 0 connected (HGI=18:130236), 1/3 connected
MqttPoolBridge: excluding HGI 18:130236 from MQTT pool (serial primary)
MqttCallbackPool: child 18:130236 offline (definitive=True)
MqttPoolBridge: HGI 18:130236 online (LWT)
MqttPoolBridge: HGI 18:149488 online (LWT)
MqttCallbackPool: child 18:149488 online (HGI=18:149488), 2/3 connected
```

### TX/RX verification

- TX through serial primary (18:130236): working
  - `RQ --- 18:130236 32:153289 --:------ 2411 003 000001`
  - `RQ --- 18:130236 32:153289 --:------ 10D0 001 00`
  - `RQ --- 18:130236 32:153289 --:------ 3150 001 00`
- TX through MQTT HGI (18:149488): working
  - `18:149488 | 32:153289 | RQ | unknown_3150 | 00`
- Both HGIs marked online after receiving replies
- No errors in logs

### Entity initialization

- `binary_sensor.gateway_18_130236_status`: initialized
- `binary_sensor.gateway_18_149488_status`: initialized

### Issues found on hass

1. **Second USB HGI (/dev/ttyACM1) not in pool config** — configuration
   issue, not a code issue. The user should add it to `additional_ports`
   if they want to use it as a pool member.

2. **"Temp_control for 32:153289: required sensor unavailable" warning** —
   pre-existing issue (FAN's indoor_temp sensor is unavailable), not
   related to the pool PRs.

### Issue found on silverailscolo's system (PR 1183 comment)

3. **`!I` command timeout warning on ESP32 running older ramses_esp**
   (reported by silverailscolo on PR 1183, on egbert's system — NOT on
   the user's `hass`).  The ESP32 doesn't support the `!I` command, so
   it times out after 2s and falls back to `configured_hgi_id`.  This is
   expected behavior, but the WARNING level was confusing users.

   **Fix**: Downgraded to INFO when `configured_hgi_id` is available as
   fallback (the timeout is expected for older firmware).  WARNING is
   kept when no fallback is available (genuine problem).

   Commit: `b43733c3` on `feat/phase2-signature-policy`.

### No other code issues found on hass

The pool is working correctly on the user's `hass`:
- Serial + MQTT hybrid pool: working
- TX routing through both HGIs: working
- LWT-based online detection: working
- HGI exclusion (serial primary excluded from MQTT): working
- No errors, no crashes, no timing issues

## 7. Issues Found During Testing

### R77 — HGI not re-discovered every cycle (pre-existing)

**Status**: Fixed (test fix, not code fix)
**Details**: See section 5 above.

### No other issues found

All pool-specific recipes pass. Hardware test shows no code issues.

## 8. Fixes Applied After Testing

### R77 test fix (ramses_extras)

- Scoped the "no new discovery notifications" check to the foreign HGI
  only, instead of checking for any new notifications.
- Set `_owner: me` on the CTL in the minimal profile so it's not flagged
  as a discovery candidate by the issue 1119 logic.
- Commit: `8f33d0b` on `master`

### `!I` timeout warning downgrade (ramses_rf)

- Downgraded the `!I` command timeout warning to INFO when
  `configured_hgi_id` is available as fallback.
- WARNING is kept when no fallback is available (genuine problem).
- Commit: `b43733c3` on `feat/phase2-signature-policy`
- Addresses feedback from silverailscolo on PR 1183.
