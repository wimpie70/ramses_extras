# Phase 4 Plan: known_list Removal + Event-Driven Topology

**Created:** Jul 23 2026
**Updated:** Aug 6 2026
**Status:** Steps 1-3 SHIPPED (PR 863 + PR 882, in ramses_cc 0.59.1/0.59.2). Step 4 optional/not done. Steps 5-6 still blocked on ramses_rf Phase 5 (issue 992). ramses_rf Phase 4 fully complete (incl. 4e, shipped 0.59.2). ramses_rf Phase 5 STARTED (PRs 986, 987 in 0.59.3 milestone). **ha-sim test Aug 6 (cc 0.59.2 tag + rf 0.59.2 tag): 355/377 pass, 19 fail, 3 skip — persistent fails need triage.**
**Depends on:** Phase 2 (DONE), Phase 2.5 (DONE), Phase 3a-3e (ALL DONE), PR 914 (MERGED, shipped in ramses_rf 0.59.1)
**Blocks:** nothing (this is the final phase for schema-as-SSOT)

> **Naming note:** There are several "Phase 4"s:
> - **ramses_cc Phase 4** (this doc) — remove `known_list` from config,
>   make `enforce_known_list` always-on, event-driven topology updates.
>   **Steps 1-3 are DONE** (shipped via PR 863 + PR 882, not PR 870
>   which was closed unmerged and superseded by PR 882).
> - **ramses_rf Phase 4** (PWhite-Eng, issue 915) — FSM
>   Conversational Parity & Passive Ingestion. 5-PR strangler fig:
>   **FULLY COMPLETE, including Phase 4e** (API Modernization:
>   Packet→Message, PR 951 shipped in ramses_rf 0.59.2, Aug 4 2026).
>   All PRs merged (916, 919-921, 924-929, 931, 932, 951).
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
- [ramses_rf Phase 5+ impact (issue 639 comment)](#ramses_rf-phase-5-impact)
- [Migration](#migration)
- [Risks & Mitigations](#risks--mitigations)
- [Open Questions](#open-questions)
- [Decision Log](#decision-log)

---

<a id="overview"></a>
## Overview

Phase 4 is the final step in the schema-as-SSOT migration. With Phase 3
complete (all sub-phases 3a-3e done, ramses_rf 0.59.1 released), the
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
| Device health tracking (orphaned/lost) | DONE | PR 861 (merged) |
| Cache → config sync (`sync_learned_topology`) | DONE | PR 764 |
| Passive DiscoveryScan | DONE | PR 764 (ramses_rf `discovery_scan.py`) |

### What's still in place (to be removed/changed in Phase 4)

| What | Where | Why it exists | Step |
|---|---|---|---|
| ~~`known_list` in config entry options~~ | ~~`core.config_entries`~~ | ~~Fallback for users who haven't migrated to schema~~ | ~~Step 2~~ **DONE (PR 882)** — stripped idempotently in `__init__.py` |
| ~~`enforce_known_list` config option~~ | ~~config flow~~ | ~~Workaround for issue 677 (now fixed in 0.57.6)~~ | ~~Step 3~~ **DONE (PR 882)** — hardcoded `True` in `coordinator.py:271`, removed from voluptuous schema |
| ~~`known_list[dev][commands]`~~ | ~~config entry~~ | ~~Legacy command storage (superseded by `_commands`)~~ | ~~Step 2~~ **DONE (PR 882)** |
| `.storage[remotes]` | `.storage/ramses_cc` | Command cache (kept for crash recovery) | Keep |
| 5-min polling for topology sync | `coordinator.py` | No event-driven alternative yet | Step 5 (blocked on rf Phase 5.1) |
| `asyncio.sleep(0)` for entity updates | `coordinator.py` | Interim solution (issue 794) | Step 7 (future) |
| Stale `enforce_known_list` text in `translations/{en,nl}.json` | translations | Cosmetic — toggle no longer rendered | Cleanup (minor) |

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
| ramses_rf 0.59.1 | **RELEASED** (Jul 25 2026) | Includes PR 914 + all Phase 4 PRs (916-929) + PR 931 test fixes. |
| ramses_rf 0.59.2 | **RELEASED** (Aug 4 2026) | Includes Phase 4e (PR 951 Packet→Message) + Phase 5.5-adjacent work (PR 977 DevType enums, PR 964 decouple Message from `_pkt` shim, PR 952-954 typing/cast removal). **ramses_cc pin still at 0.59.1 — needs bumping + compat check.** |
| ramses_rf 0.59.3 (milestone) | **IN PROGRESS** | Phase 5 PRs 986 (RamsesProtocolT export) + 987 (L7 payload constants → ramses_rf.const) merged. Identity constants (`DevType`, `DEV_TYPE_MAP`, etc.) NOT yet relocated — still in `ramses_tx/const.py:291-514`. Backward-compat re-exports added (commit `15006d80`). |
| Phase 3a-3e complete | DONE | All sub-phases merged |
| PR 914 (Phase 3.75) | **MERGED, shipped in 0.59.1** | "init and go" from schema `_class` — ensures device class is correct without known_list fallback. |
| Issue 677 fix (0.57.6) | DONE | `enforce_known_list` bug fixed — verified, Step 3 shipped |
| ramses_rf Phase 3.5 (1FC9 → TopologyChangedEvent) | **DONE in 0.59.0** (issue #911, closed) | `_evaluate_rf_bind_rules` in `topology_builder.py` intercepts 1FC9, emits `BIND_DEVICE` events. `CREATE_CONTROLLER` + `CREATE_CIRCUIT` actions also in enum. |
| TopologyChangedEvent public subscription API | **MISSING** | Events flow internally (TopologyBuilder → DeviceRegistry). No public callback for ramses_cc to subscribe. **Tracked by ramses_rf Phase 5 PR 3 (issue 992).** Blocks Step 5. |
| ramses_rf HVAC topology (`load_fan`) | **STILL A STUB** | `load_fan()` in `schemas.py:397` has `fan._update_schema(**schema)` commented out. No open PR. Blocks Step 6. |
| ramses_rf Phase 4 (issue #915) | **FULLY COMPLETE** (incl. 4e) | 5-PR strangler fig + Phase 4e (PR 951, Packet→Message). All merged: 916, 919-921, 924-929, 931, 932, 951. |
| ramses_rf Phase 5 (issue #992) | **OPEN — STARTED** | Client API & Consumer DTO Boundary Enforcement. PRs 986, 987 merged (0.59.3 milestone). Remaining: PR 1 remainder (identity constants, polling API), PR 2 (DTO boundary — breaking for cc), PR 3 (event bus + handshake = our Step 5 unblock). |
| ramses_rf PR 931 (test fixes) | **MERGED** | Our fixes on top of PR 929: DHW None handling + PollingManager build_rq_cmd + test update. Merged Jul 25 2026. |
| ramses_cc PR 869 (compat fixes) | **MERGED** (Jul 26 2026) | Compatibility fixes: merge_schemas traits + sentinel packet + discovery removal + resolve_async_attr cooldown. Shipped in ramses_cc 0.59.1. |
| ramses_cc PR 863 (migration + backup) | **MERGED** (Jul 26 2026) | Phase 4 Step 1: config entry v2→v3 migration with safety net backup. Shipped in ramses_cc 0.59.1. |
| ramses_cc PR 870 (known_list removal) | **CLOSED unmerged** (Jul 30 2026) | Superseded by PR 882. Had merge-conflict issues + failing tests (stale assertions, missing backup logic). |
| ramses_cc PR 882 (superseding) | **MERGED** (Jul 30 2026) | PWhite-Eng: "all Phase 4 commits from PR #870 plus the fixes required to pass all CI checks." Restored backup_store logic + updated test assertions. **This is the PR that shipped Steps 2-3.** Shipped in ramses_cc 0.59.2. |
| ramses_cc PR 881 (migration follow-ups) | **MERGED** (Jul 30 2026) | PWhite-Eng: Phase 4 config migration follow-ups + tech debt (issue 880). |
| ramses_cc manifest pin | **at `ramses-rf==0.59.2`** (0.59.2 release) | Updated to 0.59.2 in ramses_cc 0.59.2 release. ha-sim test Aug 6 against rf 0.59.2 tag + cc 0.59.2 tag: 355/377 pass, 19 fail (need triage). No const fixes needed (PR 987 is in 0.59.3, not 0.59.2). |

### Critical path

```
ramses_rf 0.59.1 (RELEASED) ──→ PR 869 (compat) ✅ MERGED ──→ PR 863 (migration) ✅ MERGED
                                                                     │
                                                                     └──→ PR 870 CLOSED ──→ PR 882 ✅ MERGED (Steps 2-3 shipped in cc 0.59.2)
                                                                                 │
                                                                                 └──→ Step 4 (shrink _commands) — optional, not done

ramses_rf 0.59.2 (RELEASED Aug 4) -- cc pin at 0.59.2 (release) -- ha-sim test: 355/377 pass, 19 fail [TRIAGE NEEDED]
ramses_rf Phase 5 PR 3 (issue 992) ──→ Step 5 (TopologyChangedEvent)             [blocked]
ramses_rf: implement load_fan        ──→ Step 6 (HVAC topology)                  [blocked]
```

**Steps 1-3 are SHIPPED** (PR 863 + PR 882, in ramses_cc 0.59.1/0.59.2). Remaining:
- **Step 4** (shrink `_commands`) — optional, non-breaking, not done
- **Step 5** (TopologyChangedEvent) — blocked on ramses_rf Phase 5 PR 3 (issue 992)
- **Step 6** (HVAC topology) — blocked on ramses_rf `load_fan` (still a stub)
- **Step 7** (StateUpdatedEvent) — future upgrade

**Immediate TODO:** triage the 19 persistent ha-sim test failures from
the Aug 6 run (cc 0.59.2 tag + rf 0.59.2 tag). Most likely 0.59.2
regressions: R36/R40 (Message API affecting 2349/30C9 parsing), R24
(class_mismatch attribute), R20 (add_faked_rem service validation).
R02/R08/R16 are timing-sensitive (only in release tag run). See ha-sim
test section below for full details.

---

<a id="implementation-plan"></a>
## Implementation Plan

<a id="step-1-storage-version-bump-v1v2"></a>
### Step 1: Storage version bump v1→v2  ✅ DONE (PR 863 + PR 882)

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

**Status:** Shipped in ramses_cc 0.59.1 (PR 863) + 0.59.2 (PR 882
restored backup_store logic that was lost in a merge conflict).
PR 881 (PWhite-Eng) addressed follow-up tech debt (issue 880).

---

<a id="step-2-remove-known_list-from-config-entry"></a>
### Step 2: Remove known_list from config entry  ✅ DONE (PR 882)

**What:** Stop storing `known_list` in `core.config_entries`. Derive
it in-memory from schema at startup via
`_derive_known_list_from_schema()`.

**Why:** `known_list` is now a redundant copy of schema traits. Having
two sources causes confusion (which wins?) and makes the config flow
complex. The derivation function already exists and works.

**Depends on:** PR 914 (Phase 3.75) — **MERGED, shipped in ramses_rf 0.59.1**.
"init and go" from schema `_class` ensures ramses_rf instantiates devices
correctly from the derived known_list.

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

**Status:** Shipped in ramses_cc 0.59.2 (PR 882). `schemas.py` no
longer has `enforce_known_list`/`SZ_KNOWN_LIST` in the voluptuous
schema. `__init__.py` strips stale `known_list`/`enforce_known_list`
from options idempotently (lines 214, 287, 370-374, 390-424).

---

<a id="step-3-make-enforce_known_list-always-on"></a>
### Step 3: Make enforce_known_list always-on  ✅ DONE (PR 882)

**What:** Remove the `enforce_known_list` config option. It becomes
always-on (no toggle).

**Why:** The bug that required the toggle (issue 677, "0.56.8 Evohome
device discovery inconsistent") was fixed in 0.57.6. Passive scan
already auto-forces `enforce_known_list=True` when active. With
`known_list` derived from schema (Step 2), there's no reason to
disable it.

**Pre-requisite:** Verify the 0.57.6 fix holds on real Evohome systems.
The ha_sim_test suite (347 checks) passes with enforce always-on, but
real-world testing is needed.

**Changes:**
- `const.py`: remove `CONF_ENFORCE_KNOWN_LIST` or make it deprecated
- `config_flow.py`: remove the toggle from options flow
- `coordinator.py`: hardcode `enforce_known_list=True`
- `schemas.py`: remove from voluptuous schema

**Risk:** If any users still rely on the disable-workaround (issue 677),
they would be forced to enforce. Mitigation: log a warning if the
config entry has `enforce_known_list=False` and override to `True`.

**Status:** Shipped in ramses_cc 0.59.2 (PR 882). `coordinator.py:271`
hardcodes `enforce_known_list = True  # Phase 4: always-on`. Toggle
removed from voluptuous schema and config flow. `config_flow.py:1396`
strips `enforce_known_list` from `ramses_rf` sub-dict. Stale text
remains in `translations/{en,nl}.json` (cosmetic — toggle no longer
rendered).

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
- **Tracked by ramses_rf Phase 5 PR 3 (issue 992)** — "Event Bus &
  Handshake": harden `TopologyChangedEvent` with typed payload
  dataclasses + define `SchemaUpdatedCallback` in `interfaces.py`.
  This is the planned delivery mechanism for our Step 5.

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

**Status:** Not a blocker. The interim solution works (347/347 tests
pass). This is a quality-of-life upgrade.

---

<a id="migration"></a>
<a id="ramses_rf-phase-4-impact"></a>
## ramses_rf Phase 4 impact (issue 915)

ramses_rf Phase 4 (issue 915, PWhite-Eng) is a 5-PR strangler fig
that moves RQ/RP tracking from L3 FSM to L7 event bus and removes
active discovery probing. **All PRs merged to ramses_rf 0.59.1**
(Jul 25 2026). **Phase 4e (API Modernization: Packet→Message)
completed in 0.59.2** (PR 951, Aug 4 2026).

### ramses_rf Phase 4 PR status

| PR | Phase | Status | What |
|----|-------|--------|------|
| 916 | 4a Shadow FSM | ✅ MERGED | L7 ConversationManager built, parity tested |
| 919 | Schedule/OpenTherm refactor | ✅ MERGED | Schedule and OpenTherm struct standardisation |
| 920 | 4a.5 Live Parity | ✅ MERGED | Shadow FSM hooked into live pipeline, 100% parity (2126/2126) |
| 921 | 4b Execution Cutover | ✅ MERGED | Switch live execution to L7 ConversationManager |
| 924 | 4c.1 Schema Polling | ✅ MERGED | `polling_interval` + `is_battery` traits, `disable_polling` config |
| 925 | 4c.2 PollingManager Shadow | ✅ MERGED | L7 PollingManager built, shadow parity tested |
| 926 | 4c.3 Polling Cutover | ✅ MERGED | Live polling switched to L7 PollingManager |
| 927 | 4c.4 Discovery Purge | ✅ MERGED | Legacy DiscoveryService deleted, passive scan only |
| 928 | 4d.1 wait_for_reply Deprecation | ✅ MERGED | Scrubbed from application layer |
| 929 | 4d.2 Transport FSM Streamlining | ✅ MERGED | WantRply state deleted, L3 only tracks Echo |
| 931 | Test fixes (our PR) | ✅ MERGED | DHW None + PollingManager build_rq_cmd + test update |
| 932 | Release prep (silverailscolo) | ✅ MERGED | Bump version to 0.59.1 |
| 951 | 4e API Modernization (Packet→Message) | ✅ MERGED (0.59.2) | L7 domain API contracts modernised to Message |
| 964 | 4.5.1 Decouple Message from `_pkt` shim | ✅ MERGED (0.59.2) | Strict typing, remove legacy `Message._pkt` property |
| 977 | 4.5.x DevType enums replace string slicing | ✅ MERGED (0.59.2) | Address type checking via `DevType` enums (Phase 5.5-adjacent) |

### Verification: ha-sim test suite

The full PR 927/928/929 stack was tested against ha-sim with our
test fixes (PR 931) and ramses_cc compatibility fixes (PR 869):

```
Passed:   347
Failed:   0
Total:    347
Elapsed:  33.3 min
Unexpected errors:   0
Unexpected warnings: 0
```

All recipes pass, including R55 (ConversationManager), R56
(PollingManager), R57 (schema polling traits), R40 (PacketDTO RX
path), R35 (DHW CQRS hydration), R37 (BDR re-parent loop prevention).

### Impact on ramses_cc — RESOLVED (PRs merged)

| ramses_rf Phase 4 PR | ramses_cc impact | Status |
|----------------------|------------------|--------|
| 4a/4a.5 (Shadow FSM) | None — passive observer | ✅ Verified (ha-sim) |
| 4b (Execution Cutover) | Low — `gwy.send_cmd()` abstracts execution | ✅ Verified (R55 passes) |
| 4c (Active Discovery Removal) | **HIGH** — removed active polling | ✅ Verified (R56, R47 pass). Passive scan + warm restart covers all use cases. ramses_cc compatibility fix in PR 869 (services.py: handle `dev.discovery` removal). **PR 869 MERGED.** |
| 4d (Transport FSM Streamlining) | Low — `wait_for_reply` scrubbed | ✅ Verified (R55 passes). ramses_cc compatibility fix in PR 869 (services.py: sentinel packet migration). **PR 869 MERGED.** |
| 4e (Packet→Message, PR 951) | **MEDIUM** — L7 API contracts changed | ⚠️ Shipped in rf 0.59.2. **cc pin still at 0.59.1 — compat not yet verified.** |
| 4.5.1 (Message decouple, PR 964) | **MEDIUM** — `Message._pkt` shim removed | ⚠️ Shipped in rf 0.59.2. **cc pin still at 0.59.1 — compat not yet verified.** |
| 4.5.x (DevType enums, PR 977) | **HIGH** — Phase 5.5-adjacent | ⚠️ Shipped in rf 0.59.2. See import audit below. **cc pin still at 0.59.1 — compat not yet verified.** |

### Polling configuration in schema

Issue 915 PR 4c.1 (PR 924) shipped polling interval traits into the
schema: `polling_interval` (dict[str, int]) and `is_battery` (bool).
ramses_cc PR 869 includes the schema validation for these traits
(R57 passes). Future work: expose polling interval configuration
entities in HA UI (Step 4 territory).

---

<a id="ha-sim-test-0.59.2"></a>
## ha-sim test: ramses_cc 0.59.2 + ramses_rf 0.59.2 (Aug 6 2026)

**Test date:** Aug 6 2026
**ha_sim_test tool:** ramses_extras master (commit `3dc3b7a`, includes
PRs 114-125 — all recipe fixes: R11/R17 DiscoveryManager counting,
R05/R36 wait_for, R28 re-inject, R24 1FC9 re-injection, etc.)
**Container:** ha-sim (port 8124), ramses_rf loaded via PYTHONPATH
bind-mount, ramses_cc from bind-mounted `custom_components/`

Two runs were performed to isolate ramses_rf 0.59.2 compat issues from
unreleased ramses_cc refactors:

### Run 1: cc upstream/master + rf 0.59.2 tag

**Tested:** ramses_cc upstream/master (`a77d40d`, includes unreleased
PRs 897-903 = #896/#900 refactors) + ramses_rf 0.59.2 tag (`ade6ce7e`)

```
Passed:   356
Failed:    17
Skipped:    3  (R41, R42, R43 — load_fan/HVAC topology, blocked on rf)
Total:    376
```

### Run 2: cc 0.59.2 release tag + rf 0.59.2 tag  (canonical)

**Tested:** ramses_cc 0.59.2 release tag (`9c354c3`, includes our
PR 888 `resolve_async_attr` cooldown fix — the only wimpie70 PR since
Aug 1) + ramses_rf 0.59.2 tag (`ade6ce7e`)

```
Passed:   355
Failed:    19
Skipped:    3  (R41, R42, R43 — load_fan/HVAC topology, blocked on rf)
Total:    377
```

**No const fixes needed:** ramses_rf 0.59.2 still has all SZ_*
constants in `ramses_tx/const.py` (PR 987 const relocation is in the
0.59.3 milestone, not 0.59.2). Our re-export fix (commit `15006d80`)
is only needed for 0.59.3.

### Comparison between runs

| Recipe | Run 1 (cc master) | Run 2 (cc 0.59.2 tag) | Notes |
|--------|-------------------|----------------------|-------|
| R06 | FAIL | **PASS** | Fixed by unreleased #896 refactor? Or timing |
| R28 | FAIL | **PASS** | Fixed by unreleased #896 refactor? Or timing |
| R02 | PASS | **FAIL** (2) | New timing issue — TRV removal timeout |
| R08 | PASS | **FAIL** (1) | New — 37:180000 not in FAN remotes |
| R16 | PASS | **FAIL** (1) | New — ERROR logs during stress test |
| R17 | FAIL | FAIL | Same — discovery timing |
| R20 | FAIL (4) | FAIL (4) | Same — add_faked_rem HTTP 400 |
| R22 | FAIL (2) | FAIL (2) | Same — THM 000A zone binding |
| R24 | FAIL (2) | FAIL (2) | Same — class_mismatch attribute |
| R31 | FAIL | FAIL | Same — Intercepted fan_mode |
| R33 | FAIL | FAIL | Same — WS 'Simulator not initialized' |
| R36 | FAIL | FAIL | Same — climate target_temp 19.0 vs 21.0 |
| R40 | FAIL | FAIL | Same — climate entity missing after 30C9 RX |
| Final | FAIL (2) | FAIL (2) | Same — unexpected errors/warnings |

**Key finding:** The unreleased #896/#900 refactors (PRs 897-903) fixed
R06 and R28 but the 0.59.2 release has 3 new timing-sensitive fails
(R02, R08, R16). The persistent fails (R17, R20, R22, R24, R31, R33,
R36, R40) exist in **both** runs — they are NOT caused by the
unreleased refactors.

### Persistent failures (in both runs — need investigation)

| Recipe | Fails | Symptom | Likely cause |
|--------|-------|---------|--------------|
| R36 | 1 | climate target_temperature 19.0C vs expected 21.0C from 2349 | Issue 843 — PR 951 (Message API) may affect 2349 parsing/hydration |
| R40 | 1 | climate entity for zone 03 not found after 30C9 RX | PR 964 (Message decouple) may affect RX path entity creation |
| R24 | 2 | class_mismatch attribute not appearing on FAN remote entity | PR 977 (DevType enums) may affect entity attribute exposure |
| R20 | 4 | add_faked_rem HTTP 400 — REM not added to schema | Service validation — pre-existing in 0.59.2 release |
| R31 | 1 | 'Intercepted fan_mode' not found in log | Fan handler intercept path |
| R33 | 1 | Config_flow validation — WS 'Simulator not initialized' | Timing — ha-sim not ready when config_flow validation runs |
| R17 | 1 | 04:500001 not in discovered devices | Discovery service timing |
| R22 | 2 | THM 22:200001 comment doesn't include zone 01 / bound_to | 000A zone binding for 22: devices — pre-existing |
| Final | 2 | unexpected ERROR/WARNING logs | Profile reload race: `async_config_entry_first_refresh` on NOT_LOADED entry |

### Skipped (3)

| Recipe | Reason |
|--------|--------|
| R41 | `load_fan` is still a stub — pending ramses_rf (our Step 6) |
| R42 | `TopologyBuilder._evaluate_hvac_rules` not importable — pending ramses_rf |
| R43 | dual-role CO2+REM not supported — pending ramses_rf 'init and go' |

### Comparison with Jul 25 run

| Run | Date | rf version | cc version | Checks | Pass | Fail | Skip |
|-----|------|-----------|-----------|--------|------|------|------|
| Jul 25 | Jul 25 2026 | 0.59.1 (PR stack) | PR 869+870 | 347 | 347 | 0 | 0 |
| Aug 6 (run 1) | Aug 6 2026 | 0.59.2 (tag) | master (unreleased) | 376 | 356 | 17 | 3 |
| Aug 6 (run 2) | Aug 6 2026 | 0.59.2 (tag) | 0.59.2 (tag) | 377 | 355 | 19 | 3 |

The Jul 25 run was against the PR stack (not released code) with a
smaller suite (347 checks). The Aug 6 runs test the actual released
versions with a larger suite (~377 checks). The check count difference
(347 to 377) is because recipes R33-R60 were added since Jul 25.

### Action items

1. **Triage R36/R40** — most likely 0.59.2 regressions (Message API
   changes affecting 2349/30C9 parsing). Check if PR 951/964 changed
   how zone climate state is hydrated.
2. **Triage R20** — add_faked_rem HTTP 400 is pre-existing in 0.59.2
   release (not caused by unreleased refactors).
3. **Triage R24** — class_mismatch attribute may be affected by PR 977
   (DevType enums replacing string slicing).
4. **R02/R08/R16** — timing-sensitive, only in release tag run. Re-run
   individually to confirm.
5. **R22** — THM 000A zone binding, pre-existing. May need a recipe fix
   or a ramses_rf topology handler fix.
6. **Profile reload race** — `async_config_entry_first_refresh` on
   NOT_LOADED entry. Not a 0.59.2 regression but worth investigating.

---

<a id="ramses_rf-phase-5-impact"></a>
## ramses_rf Phase 5+ impact (issue 992, issue 639 comment)

PWhite-Eng's full roadmap (issue 639 comment, updated Jul 23 2026)
goes beyond Phase 4 to Phase 10. **Phase 5 directly impacts ramses_cc.**

**Phase 5 is now tracked as issue 992** ("Client API & Consumer DTO
Boundary Enforcement") and has **STARTED** — two PRs merged into the
rf 0.59.3 milestone (PR 986, PR 987). The coordinating issue is OPEN.

### ramses_rf Phase 5: Client API & Consumer DTO Boundary Enforcement (issue 992)

| Step | What | ramses_cc impact | Status |
|------|------|------------------|--------|
| 5.1 Event Bus Hardening | `TopologyChangedEvent` queued and delivered reliably to consumer | **This is our Step 5** — the public subscription API we need | **NOT STARTED** — Phase 5 PR 3 territory. Blocks our Step 5. |
| 5.2 Ingestion Handshake | API contract for ramses_cc → ramses_rf schema updates + warm-restart safety | Relevant to our known_list removal — defines how schema updates flow back | **NOT STARTED** — Phase 5 PR 3 territory. Monitor. |
| 5.3 DTO Boundary Enforcement | Remove legacy dict shims; getters return native CQRS dataclasses | **MEDIUM RISK** — ramses_cc uses `resolve_async_attr` for `heat_demands` (attribute access, safe). But other getters may use dict patterns. | **NOT STARTED** — Phase 5 PR 2. This is the breaking change for cc. |
| 5.4 Shim Removal | Remove L7 proxy shims in `ramses_tx/address.py` | Low — ramses_cc doesn't touch address parsing | **PARTIALLY DONE** — PR 977 (0.59.2) replaced string slicing with DevType enums. PR 986 (0.59.3) exported `RamsesProtocolT`. |
| 5.5 Identity Constant Relocation | Move `DevType`, `DevRole`, `ZoneRole`, `DEV_TYPE_MAP`, `DEV_ROLE_MAP`, `DEVICE_ID_REGEX` from `ramses_tx` to `ramses_rf` | **HIGH RISK** — ramses_cc imports `DevType`, `DEV_TYPE_MAP` from `ramses_tx.const`, `DeviceIdT` from `ramses_tx.typing` | **PARTIALLY DONE** — PR 987 (0.59.3) relocated L7 *payload* constants (HVAC 31DA, OpenTherm, schedule keys) from `ramses_tx.const` to `ramses_rf.const`. **Identity constants (`DevType`, `DEV_TYPE_MAP`, etc.) NOT yet relocated** — still in `ramses_tx/const.py:291-514`. Backward-compat re-exports added (commit `15006d80`) so cc doesn't break yet. Update imports when full 5.5 lands. |
| 5.6 Final Polish | Mypy/Ruff/Pytest sweeps | None | N/A |

### Phase 5 PRs merged into rf 0.59.3 milestone

| PR | Title | Phase 5 step |
|----|-------|--------------|
| 986 | Export `RamsesProtocolT` + importlinter layer contracts | 5.4 prep (layer decoupling) |
| 987 | Decouple L7 application payload constants to `ramses_rf` | 5.5 partial (payload constants only) |

**Not yet started (per issue 992's plan):**
- Phase 5 PR 1 remainder: identity constants relocation (`DevType` etc.),
  `DeviceTraitsT`/`DeviceListT`, L7 proxy shim deletion, polling API
  (`effective_polling_interval`, `set_polling_interval`)
- Phase 5 PR 2: DTO Boundary (return CQRS dataclasses) — **breaking for cc**
- Phase 5 PR 3: Event Bus & Handshake — **unblocks our Step 5**
- All three ramses_cc consumer PRs (Schedules, DTO Alignment, Polling Diagnostics)

### ramses_cc import audit (for Phase 5.5)

Files importing from `ramses_tx.const` or `ramses_tx.typing` that
would break if constants are relocated to `ramses_rf`:

| File | Import | Risk |
|------|--------|------|
| `coordinator.py` | `DEV_TYPE_MAP` from `ramses_tx.const` | HIGH — used in `_normalize_class_slug` |
| `fan_handler.py` | `DevType` from `ramses_tx.const` | HIGH — type annotation |
| `fan_handler.py` | `DeviceIdT` from `ramses_tx.typing` | HIGH — type annotation |
| `const.py` | `SZ_IS_EVOFW3` from `ramses_tx.const` | LOW — string constant, unlikely to move |
| `water_heater.py` | `SZ_ACTIVE`, `SZ_MODE`, `SZ_SYSTEM_MODE` from `ramses_tx.const` | LOW — string constants |
| `sensor.py` | Multiple `SZ_*` from `ramses_tx.const` | LOW — string constants |
| `schemas.py` | Multiple `SZ_*` from `ramses_tx.const` | LOW — string constants |
| `remote.py` | `DEFAULT_GAP_DURATION`, `Priority` from `ramses_tx.const` | MEDIUM — `Priority` may move |
| `binary_sensor.py` | Multiple from `ramses_tx.const` | LOW — string constants |
| `coordinator.py` | `SZ_ACTIVE_HGI`, `Code` from `ramses_tx.const` | MEDIUM — `Code` may move |
| `climate.py` | `SZ_MODE`, `SZ_SETPOINT`, `SZ_SYSTEM_MODE`, `Priority` from `ramses_tx.const` | MEDIUM — `Priority` may move |

**Mitigation:** When Phase 5.5 lands, ramses_tx will likely re-export
the constants for backward compatibility. But we should update our
imports to point to `ramses_rf` directly. The `SZ_*` string constants
are unlikely to move (they're schema keys, not identity constants).

### ramses_rf Phase 4.5: Domain Layer Decommissioning  ✅ DONE (PR 978, 0.59.2)

Deletes `_handle_msg` methods and legacy synchronous routing (PR 978,
"decommission legacy _handle_msg routing (Step 4.5.7)", shipped 0.59.2).
ramses_cc doesn't call `_handle_msg` directly, so impact is low. All
data now flows through asyncio.Queue pipelines. Related: PRs 980-982,
984 (dispatcher modularisation, #979) also shipped in 0.59.2.

### ramses_rf Phase 6-10: Future enhancements

| Phase | What | ramses_cc impact |
|-------|------|------------------|
| 6 | Declarative Binary Parsing (replace Regex) | None — internal to ramses_rf |
| 7 | Remove Dual-Routing (setpoint belongs to Zone, not TRV) | **MEDIUM** — climate entities may change attributes |
| 8 | Dedicated OpenTherm Read-Models | LOW — sensor entities may get new attributes |
| 9 | Deprecate SQLite MessageStore for state retrieval | **MEDIUM** — if ramses_cc uses MessageStore for restore |
| 10 | Centralized CommandBus | LOW — ramses_cc calls device setters, not send_cmd directly |

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
| TopologyChangedEvent API changes in ramses_rf | Coordinate with PWhite-Eng. Keep polling as fallback. Phase 5.1 (Event Bus Hardening) is the planned delivery mechanism. |
| HVAC topology PR delays Phase 4 | Steps 1-4 are ramses_cc-only and can ship without HVAC topology. Steps 5-6 are parallel. |
| ramses_rf Phase 5.3 (DTO Boundary) breaks dict access | Audit ramses_cc for dict access on device properties. `heat_demands` uses `resolve_async_attr` (safe). Check other getters. |
| ramses_rf Phase 5.5 (Identity Relocation) breaks imports | ramses_cc imports `DevType`, `DEV_TYPE_MAP`, `DeviceIdT` from `ramses_tx`. Update to `ramses_rf` when Phase 5.5 lands. See import audit above. |
| ramses_rf Phase 4b (Execution Cutover) changes send path | ramses_cc calls `gwy.send_cmd()` which abstracts the path. Verify ha_sim_test after 4b merge. |
| ramses_rf Phase 4c (Active Discovery Removal) breaks battery devices | Verify passive scan + warm restart covers TRV/SEN state. Run ha_sim_test after 4c merge. |

---

<a id="open-questions"></a>
## Open Questions

1. **~~Does PR 914 need to merge before Step 2?~~** — **RESOLVED**
   - PR 914 merged to ramses_rf master on Jul 23 2026 (commit `46cdebcc`).
   - Shipped in ramses_rf 0.59.1 (Jul 25 2026). Steps 1-3 are unblocked.

2. **Should `.storage[remotes]` be removed?**
   - No — keep as crash recovery cache. Commands are in schema
     `_commands`, but `.storage[remotes]` provides a fast restore
     path without waiting for config entry write.

3. **~~Should `enforce_known_list` be removed or deprecated?~~** — **RESOLVED**
   - Shipped as always-on (hardcoded `True` in `coordinator.py:271`).
     Stale entries stripped idempotently. Toggle removed from config
     flow. Shipped in ramses_cc 0.59.2 (PR 882).

4. **When will ramses_rf expose TopologyChangedEvent to external consumers?**
   - The events already fire internally (0.59.0). **Tracked by ramses_rf
     Phase 5 PR 3 (issue 992)** — "Event Bus & Handshake": harden
     `TopologyChangedEvent` with typed payload dataclasses + define
     `SchemaUpdatedCallback` in `interfaces.py`. Not yet started.

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
| Jul 24 2026 | **PR 914 merged to ramses_rf master** | Phase 3.75 "init and go" from schema `_class` is merged (commit `46cdebcc`). Steps 1-3 are now unblocked. |
| Jul 24 2026 | **ramses_rf Phase 4 (issue 915) work complete, PRs open** | PRs 916, 920, 921, 924-929 — issue 915 marks all "✅ COMPLETED" but PRs are still OPEN (most in draft). Verified by ha-sim: 347/347 tests pass. Only Phase 4e (API Modernization: Packet→Message) remains. |
| Jul 24 2026 | **Steps 1-3 ready to implement** | PR 914 merged (hard blocker resolved). ramses_rf Phase 4 work complete (PRs open, not merged). Can stack on PR 869. |
| Jul 25 2026 | **ramses_rf Phase 4 PRs all merged** | PRs 916, 919-921, 924-929 all merged to ramses_rf master. PR 931 (our test fixes) merged. Version bumped to 0.59.1 (PR 932). |
| Jul 25 2026 | **ramses_rf 0.59.1 released** | Includes PR 914 + all Phase 4 PRs + PR 931 test fixes. ramses_cc manifest pin needs bumping from `0.59.0` to `0.59.1`. No 0.60.0 release needed — 0.59.1 contains everything. |
| Jul 26 2026 | **PR 863: migration safety net added** | v2→v3 config entry migration now saves a deep-copy backup to `.storage/ramses_cc_migration_v2_backup` before the irreversible migration. Allows manual recovery if user downgrades. |
| Jul 26 2026 | **Release plan: two releases** | ramses_cc 0.59.1: PR 869 (compat) + PR 863 (migration with backup, keeps known_list as fallback). ramses_cc 0.59.2: PR 870 (remove known_list, enforce always-on — breaking change). Split gives production bake time with fallback before removing it. |
| Jul 26 2026 | **PR 870: finding 2 fix applied** | Aligned `_cleanup_stale_known_list` with `async_migrate_entry` for empty/non-dict known_list entries — both now create `schema[dev_id] = {}` so the device survives `enforce_known_list`. |
| Jul 26 2026 | **ConversationManager cross-matching issue identified** | ramses_rf `process_msg` matches RP on `(src.id, code)` only, ignoring `correlation_id`. Two concurrent RQs to same device+code can resolve each other's futures with wrong payload. Issue to be filed on ramses_rf. |
| Jul 24 2026 | ramses_rf Phase 5+ roadmap reviewed (issue 639 comment) | PWhite-Eng's full roadmap goes to Phase 10. Phase 5 directly impacts ramses_cc: Step 5.1 (Event Bus Hardening) = our Step 5 (TopologyChangedEvent subscription). Step 5.3 (DTO Boundary) may break dict access patterns. Step 5.5 (Identity Relocation) will break `DevType`/`DEV_TYPE_MAP`/`DeviceIdT` imports from `ramses_tx`. Added import audit to plan. |
| Jul 26 2026 | **PR 869 + PR 863 MERGED** | Compat fixes + migration shipped to ramses_cc 0.59.1. |
| Jul 30 2026 | **PR 870 CLOSED unmerged, superseded by PR 882** | PR 870 had merge-conflict issues (mangled imports, stale test assertions, missing backup_store logic). PWhite-Eng created PR 882 with "all Phase 4 commits from PR #870 plus the fixes required to pass all CI checks." silverailscolo closed 870: "Closed and replaced by #882". |
| Jul 30 2026 | **PR 882 MERGED — Steps 2-3 SHIPPED** | The actual known_list removal + enforce always-on shipped via PR 882, not PR 870. Shipped in ramses_cc 0.59.2. PR 881 (PWhite-Eng) addressed follow-up tech debt (issue 880). |
| Aug 4 2026 | **ramses_rf 0.59.2 released** | Ships Phase 4e (PR 951 Packet→Message) + Phase 4.5.x (PR 964 Message decouple, PR 978 _handle_msg decommission, PRs 980-982/984 dispatcher modularisation) + Phase 5.5-adjacent (PR 977 DevType enums). ramses_rf Phase 4 is now FULLY complete. |
| Aug 5 2026 | **ramses_rf Phase 5 STARTED (issue 992)** | PRs 986 (RamsesProtocolT export) + 987 (L7 payload constants → ramses_rf.const) merged into 0.59.3 milestone. Identity constants NOT yet relocated. Backward-compat re-exports added (commit `15006d80`) so ramses_cc doesn't break yet. |
| Aug 5 2026 | **ramses_cc 0.59.2 pre-release** | Includes PR 882 (Steps 2-3) + PR 881 (migration follow-ups) + #896 typing refactors + #900 exception hierarchy. Does NOT include Phase 5 consumer-side work. |
| Aug 6 2026 | **Plan document updated to reflect reality** | Corrected stale PR statuses (869/863 merged, 870 closed, 882 is the real ship PR). Added rf 0.59.2/0.59.3 + Phase 5 (issue 992) status. Marked Steps 1-3 as DONE. Phase 4 (cc) actionable work is complete; remaining steps blocked on rf. **Next TODO: bump cc pin 0.59.1→0.59.2 + compat check.** |
| Aug 6 2026 | **ha-sim test run: cc 0.59.2 tag + rf 0.59.2 tag** | 355 PASS / 19 FAIL / 3 SKIP (377 total). Two runs performed: (1) cc upstream/master + rf 0.59.2 tag = 356/17/3, (2) cc 0.59.2 release tag + rf 0.59.2 tag = 355/19/3. Persistent fails in both runs: R36/R40 (Message API 2349/30C9), R24 (class_mismatch), R20 (add_faked_rem HTTP 400), R31, R33, R17, R22. No const fixes needed (PR 987 is in 0.59.3, not 0.59.2). ramses_cc 0.59.2 release includes our PR 888 fix. |

---

[top](#phase-4-plan-known_list-removal--event-driven-topology)
