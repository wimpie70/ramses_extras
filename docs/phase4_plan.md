# Phase 4 Plan: known_list Removal + Event-Driven Topology

**Created:** Jul 23 2026
**Status:** PLANNING — Phase 3 complete (3a-3e all done), awaiting PR 914 merge
**Depends on:** Phase 2 (DONE), Phase 2.5 (DONE), Phase 3a-3e (ALL DONE)
**Blocks:** nothing (this is the final phase for schema-as-SSOT)

> **Naming note:** There are several "Phase 4"s:
> - **ramses_cc Phase 4** (this doc) — remove `known_list` from config,
>   make `enforce_known_list` always-on, event-driven topology updates.
> - **ramses_rf Phase 4** (PWhite-Eng, issue 639) — FSM conversational
>   parity + passive ingestion. Deprecates active discovery probing in
>   favour of passive scan. Our DiscoveryScan already implements this.
> - **ramses_rf Phase 4** (PWhite-Eng, issue 915, open) — FSM
>   Conversational Parity & Passive Ingestion. 5-PR strangler fig:
>   PR 916 (4a Shadow FSM) + PR 920 (4a.5 Live Parity) done,
>   PRs 4b/4c/4d pending. Removes active discovery probing in favour
>   of passive scan + warm restart. Affects our DiscoveryManager.
> - **RF Binding Handshake Phase 4** (protocol level) — RATIFY step
>   (10E0 device info exchange). Not a development phase.

---

## Table of Contents

- [Overview](#overview)
- [Current State](#current-state)
- [Goals](#goals)
- [Dependencies](#dependencies)
- [Implementation Plan](#implementation-plan)
  - [Step 1: Storage version bump v1→v2](#step-1-storage-version-bump-v1v2)
  - [Step 2: Remove known_list from config entry](#step-2-remove-known_list-from-config-entry)
  - [Step 3: Make enforce_known_list always-on](#step-3-make-enforce_known_list-always-on)
  - [Step 4: Shrink _commands](#step-4-shrink-_commands)
  - [Step 5: TopologyChangedEvent subscription](#step-5-topologychangedevent-subscription)
  - [Step 6: HVAC topology](#step-6-hvac-topology)
  - [Step 7: StateUpdatedEvent subscription (future upgrade)](#step-7-stateupdatedevent-subscription-future-upgrade)
- [ramses_rf Phase 4 impact (issue 915)](#ramses_rf-phase-4-impact)
- [Migration](#migration)
- [Risks & Mitigations](#risks--mitigations)
- [Open Questions](#open-questions)
- [Decision Log](#decision-log)

---

<a id="overview"></a>
## Overview

Phase 4 is the final step in the schema-as-SSOT migration. With Phase 3
complete (all sub-phases 3a-3e done, ramses_rf 0.59.0 pinned), the
schema now carries all device traits (`_class`, `_alias`, `_faked`,
`_bound`, `_scheme`, `_commands`, `_disabled`). The `known_list` in
the config entry is now a redundant fallback — it duplicates
information already in the schema.

Phase 4 removes `known_list` from the config entry, making it fully
derived in-memory from the schema via `_derive_known_list_from_schema()`.
This simplifies the config flow, eliminates dual-source-of-truth
confusion, and prepares the ground for event-driven topology updates
(replacing the 5-min polling loop).

---

<a id="current-state"></a>
## Current State

### What's done (Phase 1-3)

| Capability | Status | Where |
|---|---|---|
| Schema as SSOT (traits in schema) | DONE | Phase 2 (PR 764) |
| Migration scaffolding | DONE | Phase 2.5 (PR 810) |
| `_commands` on REM | DONE | Phase 3a (PR 811) |
| `_commands` on FAN (packet templates) | DONE | Phase 3b (merged) |
| Flagging mismatches | DONE | Phase 3c (PR 831) |
| ramses_rf alignment (stripper consolidation) | DONE | Phase 3d (PR 839) |
| CLI compat (`strip_and_map_schema` in gateway) | DONE | Phase 3e (0.59.0) |
| 22B0 calendar builder | DONE | Phase 3e (0.59.0, PR 879) |
| `known_list` derived from schema | DONE | `_derive_known_list_from_schema()` |
| `enforce_known_list` auto-forcing with passive scan | DONE | PR 764 |
| Device health tracking (orphaned/lost) | DONE | PR 861 (open) |
| Cache → config sync (`sync_learned_topology`) | DONE | PR 764 |
| Passive DiscoveryScan | DONE | PR 764 (ramses_rf `discovery_scan.py`) |

### What's still in place (to be removed/changed in Phase 4)

| What | Where | Why it exists |
|---|---|---|
| `known_list` in config entry options | `core.config_entries` | Fallback for users who haven't migrated to schema |
| `enforce_known_list` config option | config flow | Workaround for issue 677 (now fixed in 0.57.6) |
| `known_list[dev][commands]` | config entry | Legacy command storage (superseded by `_commands`) |
| `.storage[remotes]` | `.storage/ramses_cc` | Command cache (kept for crash recovery) |
| 5-min polling for topology sync | `coordinator.py` | No event-driven alternative yet |
| `asyncio.sleep(0)` for entity updates | `coordinator.py` | Interim solution (issue 794) |

---

<a id="goals"></a>
## Goals

1. **Remove `known_list` from config entry** — schema is the only
   source. `known_list` is derived in-memory by
   `_derive_known_list_from_schema()` at startup.
2. **Make `enforce_known_list` always-on** — remove the config option.
   The fix for issue 677 (0.57.6) has held; passive scan auto-forces
   it already.
3. **Storage version bump v1→v2** — migrate stored config to remove
   `known_list`, keep schema as the single source.
4. **Shrink `_commands`** — 22F7 and 22B0 now have native CQRS builders
   in ramses_rf 0.59.0. Users who only used these codes can drop
   `_commands` entries. (Optional — `_commands` stays as override layer.)
5. **Event-driven topology updates** — subscribe to
   `TopologyChangedEvent` from ramses_rf instead of 5-min polling.
6. **HVAC topology** — `load_fan` implementation, FAN as Parent, HVAC
   binding rules in TopologyBuilder. (Blocked on ramses_rf PR.)

---

<a id="dependencies"></a>
## Dependencies

| Dependency | Status | Notes |
|---|---|---|
| ramses_rf 0.59.0 | DONE (pinned) | `strip_and_map_schema()` called by gateway, 22B0 builder |
| Phase 3a-3e complete | DONE | All sub-phases merged |
| PR 914 (Phase 3.75) | DRAFT (tested 232/232) | "init and go" from schema `_class` — ensures device class is correct without known_list fallback. **Hard blocker for Step 2.** |
| Issue 677 fix (0.57.6) | DONE | `enforce_known_list` bug fixed — verify on real Evohome before Step 3 |
| ramses_rf Phase 3.5 (1FC9 → TopologyChangedEvent) | **DONE in 0.59.0** (issue #911, closed) | `_evaluate_rf_bind_rules` in `topology_builder.py` intercepts 1FC9, emits `BIND_DEVICE` events. `CREATE_CONTROLLER` + `CREATE_CIRCUIT` actions also in enum. |
| TopologyChangedEvent public subscription API | **MISSING** | Events flow internally (TopologyBuilder → DeviceRegistry). No public callback for ramses_cc to subscribe. Needs ramses_rf PR. |
| ramses_rf HVAC topology (`load_fan`) | **STILL A STUB** | `load_fan()` in `schemas.py:397` has `fan._update_schema(**schema)` commented out. No open PR. |
| ramses_rf Phase 4 (issue #915, open) | **IN PROGRESS** | 5-PR strangler fig. PR 916 (4a Shadow FSM) + PR 920 (4a.5 Live Parity) done. PR 921 (4b Execution Cutover), 4c (Active Discovery Removal), 4d (Transport FSM Streamlining) pending. |
| ramses_rf PR 916 (Shadow ConversationManager) | DRAFT (completed per #915) | Phase 4a: L7 ConversationManager built, parity tested (100% match). |
| ramses_rf PR 920 (Live Shadow Parity) | DRAFT (completed per #915) | Phase 4a.5: Shadow FSM hooked into live pipeline as passive observer. 100.0% parity (2126/2126). |

### Critical path

```
PR 914 merge ──→ Step 1 (storage bump) ──→ Step 2 (remove known_list)
                                              │
                                              ├──→ Step 3 (enforce always-on)
                                              ├──→ Step 4 (shrink _commands)

ramses_rf: expose subscription API ──→ Step 5 (TopologyChangedEvent)  [parallel]
ramses_rf: implement load_fan        ──→ Step 6 (HVAC topology)       [parallel]
```

Steps 1-4 are ramses_cc-only. Step 5 needs a small ramses_rf PR to
expose the topology event callback (the events themselves already
exist in 0.59.0). Step 6 needs `load_fan` implementation (still a
stub, no open PR).

---

<a id="implementation-plan"></a>
## Implementation Plan

<a id="step-1-storage-version-bump-v1v2"></a>
### Step 1: Storage version bump v1→v2

**What:** Bump `STORAGE_VERSION` from 1 to 2 in `RamsesCcStore`.
Add a real migration function that strips `known_list` from the
stored config entry data.

**Why:** The config entry currently stores both `schema` and
`known_list`. After Phase 4, only `schema` is stored. The migration
merges any `known_list` traits not already in schema (alias, class,
faked, scheme, bound) into the schema, then drops `known_list`.

**Changes:**
- `store.py`: `STORAGE_VERSION = 2`, implement `_async_migrate_func`
  to merge `known_list` traits into `schema` and remove `known_list`
- `coordinator.py`: remove `known_list` from config entry options
  schema (voluptuous)
- `config_flow.py`: remove `known_list` from options flow

**Migration logic:**
```python
async def _async_migrate_func(self, old_version, old_data):
    if old_version == 1:
        # Merge known_list traits into schema
        schema = old_data.get("schema", {})
        known_list = old_data.get("known_list", {})
        for dev_id, traits in known_list.items():
            if dev_id not in schema:
                schema[dev_id] = {}
            for key, val in traits.items():
                schema_key = f"_{key}" if key != "commands" else "_commands"
                if schema_key not in schema[dev_id] and val is not None:
                    schema[dev_id][schema_key] = val
        old_data["schema"] = schema
        old_data.pop("known_list", None)
        old_data.pop("disabled_devices", None)  # replaced by _disabled trait
    return old_data
```

**Risk:** Users on ramses_cc < 0.58.0 (pre-schema) who upgrade directly
to Phase 4 would lose `known_list` data if the migration fails. The
migration is additive (merges into schema), so data is preserved.

**Test:** ha_sim_test recipe verifying migration from v1 → v2.

---

<a id="step-2-remove-known_list-from-config-entry"></a>
### Step 2: Remove known_list from config entry

**What:** Stop storing `known_list` in `core.config_entries`. Derive
it in-memory from schema at startup via
`_derive_known_list_from_schema()`.

**Why:** `known_list` is now a redundant copy of schema traits. Having
two sources causes confusion (which wins?) and makes the config flow
complex. The derivation function already exists and works.

**Depends on:** PR 914 (Phase 3.75) — "init and go" from schema
`_class` ensures ramses_rf instantiates devices correctly from the
derived known_list. Without PR 914, device class might not be set
correctly from schema, and removing the known_list fallback could
break device instantiation.

**Changes:**
- `coordinator.py`: `_derive_known_list_from_schema()` becomes the
  sole source of `known_list` — no longer merges with config entry
  `known_list`
- `config_flow.py`: remove `known_list` from options flow display
- `schemas.py`: remove `known_list` from `CONF_SCHEMA` voluptuous
  schema (or make it read-only/hidden)
- `store.py`: `async_save_client_state` no longer writes `known_list`
  to config entry

**What stays:**
- `.storage/ramses_cc[remotes]` — command cache, kept for crash recovery
- `.storage/ramses_cc[known_list]` — can be kept as a cached snapshot
  of the derived known_list (for debugging), but not authoritative

**Test:** ha_sim_test recipes R02, R04, R05, R11 (device removal)
verify known_list is derived correctly after schema changes.

---

<a id="step-3-make-enforce_known_list-always-on"></a>
### Step 3: Make enforce_known_list always-on

**What:** Remove the `enforce_known_list` config option. It becomes
always-on (no toggle).

**Why:** The bug that required the toggle (issue 677, "0.56.8 Evohome
device discovery inconsistent") was fixed in 0.57.6. Passive scan
already auto-forces `enforce_known_list=True` when active. With
`known_list` derived from schema (Step 2), there's no reason to
disable it.

**Pre-requisite:** Verify the 0.57.6 fix holds on real Evohome systems.
The ha_sim_test suite (232 checks) passes with enforce always-on, but
real-world testing is needed.

**Changes:**
- `const.py`: remove `CONF_ENFORCE_KNOWN_LIST` or make it deprecated
- `config_flow.py`: remove the toggle from options flow
- `coordinator.py`: hardcode `enforce_known_list=True`
- `schemas.py`: remove from voluptuous schema

**Risk:** If any users still rely on the disable-workaround (issue 677),
they would be forced to enforce. Mitigation: log a warning if the
config entry has `enforce_known_list=False` and override to `True`.

---

<a id="step-4-shrink-_commands"></a>
### Step 4: Shrink _commands (optional)

**What:** With native CQRS builders for 22F1, 22F7, 22B0, 2411, 31DA
shipped in ramses_rf 0.58.3-0.59.0, users who only used these codes
can drop their `_commands` entries. The native builders provide
defaults; `_commands` is the override layer.

**Why:** Reduces config complexity. Users don't need to learn raw
packet strings for common operations — the CQRS builders handle it.

**Changes:**
- Documentation: update config flow help text to mention native builders
- `config_flow.py`: show a hint when `_commands` entries match native
  builder codes ("This command has a native builder — you can remove
  the override if you want defaults")
- No code change needed — `_commands` stays as override layer

**Note:** This step is optional and non-breaking. Users who want
custom payloads (non-default verb, custom payload) still need
`_commands`.

---

<a id="step-5-topologychangedevent-subscription"></a>
### Step 5: TopologyChangedEvent subscription

**What:** Replace the 5-min polling loop (`sync_learned_topology`)
with an event-driven subscription to `TopologyChangedEvent` from
ramses_rf.

**Why:** The current 5-min polling loop:
- Has up to 5 min latency for topology changes
- Runs even when nothing changed (wasteful)
- Can race with pending `_send_cmd` tasks (suppression logic needed)

Event-driven subscription:
- Real-time topology updates
- No wasted cycles
- No race conditions

**What ramses_rf already has (0.59.0):**
- `TopologyChangedEvent` dataclass (frozen, with tracing triad)
- `TopologyAction` enum: `UPDATE_DEVICE_CLASS`, `UPDATE_TRAITS`,
  `BIND_DEVICE`, `CREATE_CONTROLLER`, `CREATE_CIRCUIT`
- `DeviceRegistry` handles all these events (`dev_registry.py`)
- `TopologyBuilder._evaluate_rf_bind_rules` intercepts **1FC9** and
  emits `BIND_DEVICE` events (Phase 3.5 is DONE)
- `TopologyBuilder._evaluate_hvac_rules` emits `UPDATE_DEVICE_CLASS`
  for HVAC signature detection
- Events flow: `TopologyBuilder` → `emit_event_cb` →
  `DeviceRegistry.handle_topology_event()`

**What's missing (needs ramses_rf PR):**
- **No public subscription API** — events flow internally only.
  ramses_cc needs `gwy.add_topology_callback(cb)` or similar to
  receive `TopologyChangedEvent` without polling.
- This is a small PR — the infrastructure exists, just needs an
  external callback hook.

**Changes (ramses_cc side):**
- `coordinator.py`: register a callback with ramses_rf gateway for
  `TopologyChangedEvent`
- On event: update config entry schema with the topology change
- Keep `sync_learned_topology` as a fallback (run on shutdown + every
  30 min as safety net)

**Changes (ramses_rf side — small PR needed):**
- Expose `gwy.add_topology_callback(cb)` or similar
- The events already fire — just need to fan out to external listeners

**Test:** ha_sim_test recipe verifying real-time schema update on
zone binding change (no 5-min wait).

---

<a id="step-6-hvac-topology"></a>
### Step 6: HVAC topology

**What:** Implement HVAC topology learning in ramses_rf so that
FAN/REM/sensor relationships are learned from traffic, not just
cached.

**Why:** `load_fan()` in `schemas.py:397` is still a stub —
`fan._update_schema(**schema)` is commented out. ramses_rf ignores
HVAC schema (remotes/sensors). `gateway.schema()` flattens all HVAC
to `orphans_hvac`. On restart, the HVAC structure is lost unless the
config entry has it.

**Status:** No open PR. This is the biggest remaining gap.

**What ramses_rf already has (0.59.0):**
- `HvacVentilator` class with `_bound_devices` dict, `add_bound_device`,
  `remove_bound_device`, `get_bound_rem` methods
- `TopologyBuilder._evaluate_hvac_rules` detects HVAC device class
  from verb/code signatures (31D9 = fan on RQ, CO2 on I)
- 1FC9 binding events emit `BIND_DEVICE` (Phase 3.5, done)
- `SCH_TRAITS_HVAC` accepts `remotes`, `sensors`, `bound` as
  `str | list[str]`

**What's missing:**
1. `load_fan` implementation — uncomment and implement
   `fan._update_schema(**schema)` so FAN reads `remotes`/`sensors`
   from schema and creates child devices
2. FAN as Parent class — FAN owns its REMs and sensors (the
   `_bound_devices` dict exists but isn't populated from schema)
3. `gateway.schema()` should output HVAC structure (not flat
   `orphans_hvac`) when FAN has remotes/sensors
4. CO2 dual-role support — 37: device can be both REM and sensor

**What ramses_cc can do now (workaround):**
- Cache HVAC schema separately in `.storage/ramses_cc[hvac_schema]`
- Restore HVAC schema from cache on restart
- This is already implemented (PR 764, verified by R07/R07b/R15)

**Test:** ha_sim_test recipes R41, R42, R43 (currently SKIP) will
verify HVAC topology when implemented.

---

<a id="step-7-stateupdatedevent-subscription-future-upgrade"></a>
### Step 7: StateUpdatedEvent subscription (future upgrade)

**What:** Replace `asyncio.sleep(0)` in the coordinator's
`_on_packet` handler with a `StateUpdatedEvent` listener.

**Why:** The current interim solution (issue 794) uses
`asyncio.sleep(0)` as a yield strategy to let ramses_rf finish
ingestion before ramses_cc reads state. A `StateUpdatedEvent`
listener would provide deterministic ingestion-complete signalling.

**Depends on:** ramses_rf CQRS StateProjector emitting
`StateUpdatedEvent` to external subscribers. The dataclass exists
(0.59.0) and is used internally by `dispatcher.py`, but no external
subscription API exists yet.

**Status:** Not a blocker. The interim solution works (232/232 tests
pass). This is a quality-of-life upgrade.

---

<a id="migration"></a>
<a id="ramses_rf-phase-4-impact"></a>
## ramses_rf Phase 4 impact (issue 915)

ramses_rf Phase 4 (issue 915, PWhite-Eng) is a 5-PR strangler fig
that moves RQ/RP tracking from L3 FSM to L7 event bus and removes
active discovery probing. **This affects ramses_cc.**

### ramses_rf Phase 4 PR status

| PR | Phase | Status | What |
|----|-------|--------|------|
| 916 | 4a Shadow FSM | DONE (per issue 915) | L7 ConversationManager built, parity tested |
| 920 | 4a.5 Live Parity | DONE (per issue 915) | Shadow FSM hooked into live pipeline, 100% parity (2126/2126) |
| TBD | 4b Execution Cutover | PENDING | Switch live execution to L7 ConversationManager |
| TBD | 4c Active Discovery Removal | PENDING | Delete active polling, rely on passive ingestion + warm restart |
| TBD | 4d Transport FSM Streamlining | PENDING | Remove L3 conversational tracking, keep Echo tracking |

### Impact on ramses_cc

| ramses_rf Phase 4 PR | ramses_cc impact | Action needed |
|----------------------|------------------|---------------|
| 4a/4a.5 (Shadow FSM) | None — passive observer, doesn't change live path | None |
| 4b (Execution Cutover) | Low — ramses_cc calls `gwy.send_cmd()` which abstracts the execution path | Verify ha_sim_test passes after 4b merge |
| 4c (Active Discovery Removal) | **HIGH** — removes active polling that ramses_cc may rely on for device state | Verify our passive DiscoveryScan + warm restart covers all use cases. Battery devices (TRVs) rely on passive broadcasts — verify they still get state. |
| 4d (Transport FSM Streamlining) | None — ramses_cc doesn't touch L3 FSM | None |

### What ramses_cc needs to do

1. **Before 4b merge:** Run ha_sim_test suite to establish baseline
2. **After 4b merge:** Re-run ha_sim_test, verify no regressions
3. **Before 4c merge:** Verify passive scan + warm restart covers:
   - Battery device state (TRV setpoint, mode)
   - Mains device state (zone setpoint, mode)
   - HVAC device state (fan mode, bypass)
4. **After 4c merge:** Remove any ramses_cc code that triggers active
   polling (if any). Our DiscoveryManager already uses passive scan.

### Polling configuration in schema (ramses_rf Phase 4 design)

Issue 915 mentions polling intervals will be extracted into the
schema (SSOT). This means ramses_cc may need to expose polling
interval configuration entities in HA. Watch for this in PR 4c.

---

<a id="migration"></a>
## Migration

### Storage version v1 → v2

| Step | What | When |
|------|------|------|
| 1 | Bump `STORAGE_VERSION` to 2 | Phase 4 Step 1 |
| 2 | `_async_migrate_func`: merge `known_list` traits into `schema` | On first load after upgrade |
| 3 | Remove `known_list` from stored config | Migration drops it |
| 4 | Remove `disabled_devices` from stored config | Migration drops it (replaced by `_disabled` trait) |
| 5 | Backup v1 data as YAML | Before migration (safety) |

### Config entry migration

| Step | What | When |
|------|------|------|
| 1 | Remove `known_list` from config entry options | Phase 4 Step 2 |
| 2 | Remove `enforce_known_list` from config entry options | Phase 4 Step 3 |
| 3 | Remove `disabled_devices` from config entry options | Phase 4 Step 1 |

### Backward compatibility

- Users on ramses_cc < Phase 4 who downgrade: `known_list` is gone
  from config entry, but schema has all traits. Old code reads
  schema traits and merges into `known_list` at startup (existing
  `_merge_known_list_from_schema` logic). **Safe downgrade.**
- Users who skip Phase 4: no impact. Phase 4 is additive — old config
  with `known_list` still works (merged into schema by migration).

---

<a id="risks--mitigations"></a>
## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `known_list` removal breaks device instantiation | PR 914 ensures "init and go" from schema. Test with ha_sim_test before shipping. |
| `enforce_known_list` always-on breaks real Evohome | Issue 677 fixed in 0.57.6. Verify on real systems before Step 3. Keep override as deprecated option with warning. |
| Storage migration loses data | Backup v1 as YAML before migration. Migration is additive (merges into schema). Test migration with real config files. |
| TopologyChangedEvent API changes in ramses_rf | Coordinate with PWhite-Eng. Keep polling as fallback. |
| HVAC topology PR delays Phase 4 | Steps 1-4 are ramses_cc-only and can ship without HVAC topology. Steps 5-6 are parallel. |

---

<a id="open-questions"></a>
## Open Questions

1. **Does PR 914 need to merge before Step 2?**
   - Yes — "init and go" from schema `_class` is needed to ensure
     device class is correct without `known_list` fallback.
   - Without PR 914, `__class__` mutations at runtime could diverge
     from the schema-derived `known_list`.

2. **Should `.storage[remotes]` be removed?**
   - No — keep as crash recovery cache. Commands are in schema
     `_commands`, but `.storage[remotes]` provides a fast restore
     path without waiting for config entry write.

3. **Should `enforce_known_list` be removed or deprecated?**
   - Deprecate first (log warning if False, override to True), remove
     in a later release. Gives users time to verify the fix works.

4. **When will ramses_rf expose TopologyChangedEvent to external consumers?**
   - The events already fire internally (0.59.0). A small ramses_rf PR
     is needed to add `gwy.add_topology_callback(cb)`. Coordinate with
     PWhite-Eng — the infrastructure exists, just needs an external hook.

5. **Should `_commands` entries matching native builders be auto-removed?**
   - No — `_commands` is the user override layer. Even if a native
     builder exists, the user may want a custom payload. Show a hint
     in config flow, but don't auto-remove.

---

<a id="decision-log"></a>
## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| Jul 23 2026 | Phase 4 plan created | Phase 3 complete (3a-3e all done). ramses_rf 0.59.0 pinned. PR 914 tested 232/232. Ready to plan known_list removal. |
| Jul 23 2026 | PR 914 is a hard blocker for Step 2 | "init and go" from schema `_class` ensures device class is correct without known_list fallback. Without it, removing known_list could break device instantiation. |
| Jul 23 2026 | Steps 1-4 are ramses_cc-only | Storage bump, known_list removal, enforce always-on, and _commands shrink don't need ramses_rf PRs. Can ship independently. |
| Jul 23 2026 | Steps 5-6 are parallel, depend on ramses_rf | TopologyChangedEvent subscription needs ramses_rf Phase 3.5. HVAC topology needs ramses_rf HVAC PR. Both can proceed in parallel once those land. |
| Jul 23 2026 | Keep `.storage[remotes]` as crash recovery cache | Commands are in schema `_commands`, but .storage provides fast restore without config entry write. Don't delete until certain schema path is reliable. |
| Jul 23 2026 | Deprecate `enforce_known_list` before removing | Issue 677 fix may not hold for all real Evohome systems. Deprecate with warning first, remove in later release. |
| Jul 23 2026 | Phase 3.5 (1FC9 → TopologyChangedEvent) is DONE in 0.59.0 | `_evaluate_rf_bind_rules` in `topology_builder.py` intercepts 1FC9 and emits `BIND_DEVICE`. `CREATE_CONTROLLER` + `CREATE_CIRCUIT` also in enum. Step 5 only needs a small ramses_rf PR to expose the callback externally. |
| Jul 23 2026 | `load_fan` is still a stub (0.59.0) | `schemas.py:397` has `fan._update_schema(**schema)` commented out. No open PR. Step 6 (HVAC topology) remains blocked. `HvacVentilator` class has `_bound_devices` infrastructure but it's not populated from schema. |
| Jul 23 2026 | ramses_rf Phase 4 (issue 915) is in progress | 5-PR strangler fig. PR 916 (4a) + PR 920 (4a.5) done — Shadow ConversationManager built and hooked into live pipeline with 100% parity. PRs 4b/4c/4d pending. Phase 4c (Active Discovery Removal) is HIGH impact on ramses_cc — must verify passive scan + warm restart covers all use cases before merge. |

---

[top](#phase-4-plan-known_list-removal--event-driven-topology)
