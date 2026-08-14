# Issue 954 analysis — re-prompting + packet serialization failure

Target: https://github.com/ramses-rf/ramses_cc/issues/954
Reporter: @peternash
Status: open, two comments

---

## Summary

Issue 954 reports that after HA restart, discovery re-prompts for
devices that have already been discovered and placed in the schema.
Two specific symptoms:

1. A TRV already placed in a zone is re-prompted **without** zone info.
   Accepting it makes it a `heat_orphan`, then it gets moved back to the
   correct zone later.
2. A foreign second HGI (marked `not_mine`) is re-prompted every cycle.

A follow-up comment adds a third symptom: a packet serialization error
that aborts the entire save cycle, causing discovery state loss on
restart.

---

## Bug A — Foreign HGI (18:) re-prompted every cycle

### Root cause

`get_devices()` in `custom_components/ramses_cc/discovery.py` (line
1185-1191) merges scan-engine devices with metadata, defaulting any
device without metadata to `DeviceMetadata()` which has
`status=NEW`:

```python
all_ids = set(engine_devices.keys()) | set(self._metadata.keys())
for device_id in all_ids:
    meta = self._metadata.get(device_id, DeviceMetadata())  # defaults to NEW
```

Both `sync_with_schema()` (line 493) and `check_for_new_devices()`
(line 1775) **explicitly skip 18: devices** — they never create
metadata for them. But `get_devices()` does **not** skip 18: devices.
So a foreign HGI that the scan engine sees on the RF network:

1. `sync_with_schema` skips it → no metadata created
2. `check_for_new_devices` skips it → no metadata created
3. `get_devices(status=NEW)` includes it because the default
   `DeviceMetadata()` has `status=NEW`
4. The `review_discovered` form shows it every time

This persists across restarts because the HGI is never given ACCEPTED
metadata.

### Fix

`get_devices()` must skip 18: devices (or default them to a
non-NEW status). The skip already exists in `sync_with_schema` and
`check_for_new_devices` — `get_devices` needs the same guard:

```python
for device_id in all_ids:
    if device_id.startswith("18:"):
        continue  # HGI gateways are not discoverable
    meta = self._metadata.get(device_id)
    if meta is None:
        if device_id in self._schema_device_ids:
            continue  # already in schema, not a new discovery
        meta = DeviceMetadata()  # genuinely new
```

### Code reference

- `discovery.py` lines 1185-1191 (`get_devices` default to NEW)
- `discovery.py` line 493 (`sync_with_schema` skips 18:)
- `discovery.py` line 1775 (`check_for_new_devices` skips 18:)

---

## Bug B — TRV re-prompted without zone (extraction path discrepancy)

### Root cause

There are **two different device-ID extraction paths** that produce
different sets:

- **Save path** (`_extract_schema_device_ids` →
  `_derive_known_list_from_schema` in `coordinator.py` line 1031-1034):
  **includes** global `orphans_heat` / `orphans_hvac` device IDs.
- **Startup path** (`_extract_device_ids_from_stripped` in
  `coordinator.py` line 901-907): **skips** `SZ_ORPHANS_HEAT` and
  `SZ_ORPHANS_HVAC` as top-level keys.

This means devices that are only in global `orphans_heat` are:

1. Included in `_discovery_filter_ids` during save → metadata is saved
2. **NOT included** in `schema_device_ids` during startup →
   `sync_with_schema` marks them REMOVED
3. `check_for_new_devices` re-marks them NEW → re-prompted

For a TRV in a zone, both paths should find it from
`zones[].actuators`. But if the TRV's metadata was lost (e.g.
.storage timing issue) or the save filter excluded it,
`get_devices` defaults to NEW regardless of schema placement.

### Fix

`_extract_device_ids_from_stripped` should include global
`orphans_heat` / `orphans_hvac` device IDs, matching
`_derive_known_list_from_schema`. The skip at line 901-907 should
extract device IDs from the orphan lists, not skip them entirely:

```python
if key in (SZ_MAIN_TCS, "transport_constructor"):
    continue
if key in (SZ_ORPHANS_HEAT, SZ_ORPHANS_HVAC):
    if isinstance(value, list):
        device_ids.update(value)
    continue
```

### Code reference

- `coordinator.py` lines 882-947 (`_extract_device_ids_from_stripped`,
  skips global orphans)
- `coordinator.py` lines 1031-1034
  (`_derive_known_list_from_schema`, includes global orphans)

---

## Bug C — Packet serialization failure (save cycle aborts)

### Root cause

`get_state()` in `ramses_rf/gateway.py` (line 377) passes the **raw
payload dataclass** into the state dict:

```python
state_dict[dtm_str] = {
    ...
    "payload": msg.payload,  # raw Phase 6 dataclass
    ...
}
```

`PuzzlePayload` (7FFF) in `ramses_rf/payloads/system.py` (lines
1781-1782) has `bytes` fields:

```python
msg_type: bytes
payload_data: bytes
```

Unlike every other payload class, `PuzzlePayload` has **no `to_dict()`
method**. When HA's storage layer tries to JSON-serialize the state
dict, it rejects `bytes` objects:

```
Error writing config for ramses_cc: Bad data at
$.data.client_state.packets.*.payload.msg_type=b'\x00\x10'(<class 'bytes'>
```

This causes the **entire save cycle to fail** — not just the
problematic packet, but all state (schema, packets, discovery, HVAC)
is lost. This is why the user sees re-prompting after every restart:
the discovery state is never persisted because the packet
serialization error aborts the save.

### Also at risk

`OpenThermMsgPayload` in `ramses_rf/payloads/opentherm.py` has
`raw_value: bytes`. It does have a `to_dict()` that converts
`raw_value` to `.hex().upper()` (line 124), but `get_state()` passes
the raw object, not `to_dict()`, so it's also vulnerable if any code
path stores the raw dataclass.

### Fix (two parts)

**Part 1 — ramses_rf: add `to_dict()` to `PuzzlePayload`:**

```python
def to_dict(self, msg: Any = None) -> dict[str, Any]:
    """Convert puzzle diagnostic payload to legacy dictionary format."""
    return {
        "msg_type": self.msg_type.hex(),
        "payload_data": self.payload_data.hex(),
    }
```

**Part 2 — ramses_rf: `get_state()` should call `to_dict()` on
payloads:**

```python
payload = msg.payload
if hasattr(payload, "to_dict"):
    try:
        payload = payload.to_dict(msg) if ... else payload.to_dict()
    except Exception:
        payload = str(payload)
state_dict[dtm_str] = {
    ...
    "payload": payload,
    ...
}
```

This protects against future payload classes that forget `to_dict()`
and against any `bytes` fields that slip through.

### Code reference

- `ramses_rf/gateway.py` line 377 (`get_state` passes raw payload)
- `ramses_rf/payloads/system.py` lines 1759-1805 (`PuzzlePayload`,
  no `to_dict()`)
- `ramses_rf/payloads/opentherm.py` lines 44-45
  (`OpenThermMsgPayload`, `raw_value: bytes`)

---

## Connection to ha_sim_test failures

| Recipe | Symptom | Likely cause | Recipe fix | Upstream bug |
|--------|---------|--------------|------------|--------------|
| R26 | 04:200099 not in schema after profile load | Device not in known_list → not auto-started | Add `extra_kl={test_device: {}}` | Bug B (FIXED upstream) |
| R50 | "no scan_state in .storage" | scan_state not persisted before recipe reads it | Trigger `sync_topology` + wait | Bug C (PRESENT — save cycle aborts) |
| R30 | FAN class=None, _bound=None | Schema inconsistent under parallel load (missing `wait_for_transport_ready`) | Add `wait_for_transport_ready(timeout=30)` | Bug C (PRESENT — save failure) |
| R19/R22 | THM comment empty | Device not activated in simulator | Activate device before injection | Bug B (FIXED upstream) |
| R36 | target_temperature=19.0 not 21.0 | CTL autonomous 2349 heartbeat overwrites injected value | `set_suppress=True` in `silence_devices` | N/A (recipe timing) |

### Recipe fixes applied (2026-08-14)

All 5 recipe fixes are in `ramses_extras` on the `fix/post-merge-cleanup`
branch and verified with targeted `ha_sim_test` runs:

- **R26**: `extra_kl={test_device: {}}` adds the device to the known_list
  so the simulator auto-starts it after reload.
- **R50**: `call_service("ramses_cc", "sync_topology")` after
  DiscoveryManager start forces an immediate checkpoint, persisting
  `scan_state` to `.storage` before the recipe manipulates it.
  Also added `wait_for_transport_ready(timeout=30)`.
- **R30**: `wait_for_transport_ready(timeout=30)` after profile reload
  ensures the MQTT transport has reconnected before device activation
  and schema checks.
- **R19/R22**: `activate_profile_device` for the test TRV/THM before
  packet injection ensures the scan engine tracks the device.
- **R36**: `set_suppress=True` in `silence_devices` stops the CTL's
  autonomous 2349 heartbeat (19.0°C) from overwriting the injected
  21.0°C setpoint. Also increased auto-answer disable wait to 3s.

These are **workarounds** for the symptoms. The upstream bugs (A and C)
should still be fixed to prevent the underlying data-loss and
re-prompting issues.

---

## Suggested fix order

1. **Bug C** (ramses_rf) — add `to_dict()` to `PuzzlePayload`, make
   `get_state()` call `to_dict()`. This unblocks the save cycle and
   may resolve several ha_sim_test failures (R50, R30). **FIXED** in
   PR https://github.com/ramses-rf/ramses_rf/pull/1056.
2. **Bug A** (ramses_cc) — skip 18: in `get_devices()`. Small,
   uncontroversial. **FIXED** in PR
   https://github.com/ramses-rf/ramses_cc/pull/957.
3. **Bug B** (ramses_cc) — align the two extraction paths. Small but
   needs careful testing to ensure no devices are lost from the
   known_list. **FIXED** as of 2026-08-14
   (`_extract_device_ids_from_stripped` now extracts from global orphans).

---

## Numbered points for future comments

- **Point A** — Foreign HGI re-prompted: `get_devices()` defaults 18:
  devices to NEW; `sync_with_schema` and `check_for_new_devices` skip
  them but `get_devices` doesn't.
- **Point B** — TRV re-prompted without zone:
  `_extract_device_ids_from_stripped` skips global `orphans_heat`/
  `orphans_hvac` but `_derive_known_list_from_schema` includes them.
- **Point C** — Packet serialization failure: `PuzzlePayload` (7FFF)
  has `bytes` fields and no `to_dict()`; `get_state()` passes the raw
  dataclass; HA storage rejects `bytes`; entire save cycle aborts.
- **Point D** — Bug C is the most urgent: it causes data loss, which
  is the root cause of the restart re-prompting (discovery state is
  never persisted).
