# Phase 4 Plan: known_list Removal + Event-Driven Topology

**Created:** Jul 23 2026
**Updated:** Aug 9 2026
**Status:** Steps 1-3 SHIPPED (PR 863 + PR 882, in ramses_cc 0.59.1/0.59.2). Step 4 optional/not done. **Step 5 UNBLOCKED** — ramses_rf Phase 5 (issue 992) is now CLOSED, shipped in 0.59.3, and PR 997 delivers the `set_schema_updated_callback` API our Step 5 needs; full implementation plan written below. **Step 6 still blocked** on ramses_rf `load_fan` — confirmed NOT on PWhite-Eng's roadmap (searched issues 639/992/1001); a concrete 3-sub-phase implementation plan is now written below, ready to hand off upstream or implement ourselves if we ever get ramses_rf write access. ramses_rf Phase 6 (issue 1001, payload dataclass layer) now in progress, non-breaking so far. **ha-sim test Aug 9 (cc/rf master, post Phase 5): full suite passes** — the previous 19 failures (Aug 6, against 0.59.2 tags) appear resolved by Phase 5 completion + ramses_cc's const-import fix (PR 914).
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
| ramses_rf 0.59.3 (RELEASED Aug 7) | **RELEASED** | Phase 5 fully shipped: PR 986 (RamsesProtocolT export), 987 (L7 payload constants → ramses_rf.const, then re-refactored by PR 999), 994 (const layering cleanup, PR 1A), 995 (polling API, PR 1B), 996 (DTO boundary enforcement, PR 2), 997 (event bus & handshake, PR 3 — **unblocks our Step 5**), 998 (Phase 5 gaps), 999 (final const relocation). **Issue #992 (Phase 5) is CLOSED.** |
| ramses_rf 0.59.4 (RELEASED Aug 8) | **RELEASED** | Phase 6 (unified dataclass payload layer, issue #1001) started — PRs 1002-1010 merged (PayloadBase ABC, Strangler Fig shadow pipeline, per-domain payload dataclasses for heating/HVAC/OpenTherm/system). Also PR 1011 (FAN initialized callback fix). No known breaking changes for ramses_cc so far (shadow-parity pattern keeps legacy dict output during transition). |
| Phase 3a-3e complete | DONE | All sub-phases merged |
| PR 914 (Phase 3.75) | **MERGED, shipped in 0.59.1** | "init and go" from schema `_class` — ensures device class is correct without known_list fallback. |
| Issue 677 fix (0.57.6) | DONE | `enforce_known_list` bug fixed — verified, Step 3 shipped |
| ramses_rf Phase 3.5 (1FC9 → TopologyChangedEvent) | **DONE in 0.59.0** (issue #911, closed) | `_evaluate_rf_bind_rules` in `topology_builder.py` intercepts 1FC9, emits `BIND_DEVICE` events. `CREATE_CONTROLLER` + `CREATE_CIRCUIT` actions also in enum. |
| TopologyChangedEvent public subscription API | **SHIPPED in 0.59.3** (PR 997) | `Gateway.set_schema_updated_callback(cb)` / `.schema_updated_callback` property now exist in `src/ramses_rf/interfaces.py` and `gateway.py`. `DeviceRegistry.handle_topology_event` triggers `_notify_schema_updated()` via background task. `TopologyChangedEvent` also gained `is_single_device`, `is_relationship`, `target_device_id` helpers. **Step 5 is now unblocked — actionable.** |
| ramses_rf HVAC topology (`load_fan`) | **STILL A STUB** | `load_fan()` in `schemas.py:437` still has `fan._update_schema(**schema)` commented out (verified against 0.59.4 checkout, Aug 9). No open PR. Blocks Step 6. |
| ramses_rf Phase 4 (issue #915) | **FULLY COMPLETE** (incl. 4e) | 5-PR strangler fig + Phase 4e (PR 951, Packet→Message). All merged: 916, 919-921, 924-929, 931, 932, 951. |
| ramses_rf Phase 5 (issue #992) | **CLOSED — FULLY SHIPPED** (Aug 7-8, in 0.59.3) | Client API & Consumer DTO Boundary Enforcement. All PRs (986, 987/999, 994-998) merged. PR 3 (997) delivers our Step 5 unblock. |
| ramses_rf Phase 6 (issue #1001) | **OPEN — IN PROGRESS** | Unified Dataclass Payload Layer — replaces the 108 dict-based parsers with typed `PayloadBase` dataclasses, using a Strangler Fig shadow-parity pattern (parallel decode + assert equality) so it should be non-breaking for ramses_cc while in progress. Worth periodic ha-sim regression checks as PRs land. |
| ramses_rf PR 931 (test fixes) | **MERGED** | Our fixes on top of PR 929: DHW None handling + PollingManager build_rq_cmd + test update. Merged Jul 25 2026. |
| ramses_cc PR 869 (compat fixes) | **MERGED** (Jul 26 2026) | Compatibility fixes: merge_schemas traits + sentinel packet + discovery removal + resolve_async_attr cooldown. Shipped in ramses_cc 0.59.1. |
| ramses_cc PR 863 (migration + backup) | **MERGED** (Jul 26 2026) | Phase 4 Step 1: config entry v2→v3 migration with safety net backup. Shipped in ramses_cc 0.59.1. |
| ramses_cc PR 870 (known_list removal) | **CLOSED unmerged** (Jul 30 2026) | Superseded by PR 882. Had merge-conflict issues + failing tests (stale assertions, missing backup logic). |
| ramses_cc PR 882 (superseding) | **MERGED** (Jul 30 2026) | PWhite-Eng: "all Phase 4 commits from PR #870 plus the fixes required to pass all CI checks." Restored backup_store logic + updated test assertions. **This is the PR that shipped Steps 2-3.** Shipped in ramses_cc 0.59.2. |
| ramses_cc PR 881 (migration follow-ups) | **MERGED** (Jul 30 2026) | PWhite-Eng: Phase 4 config migration follow-ups + tech debt (issue 880). |
| ramses_cc PR 914 (0.59.3 const fix) | **MERGED** (Aug 8 2026) | silverailscolo: fixed ramses_cc imports broken by ramses_rf 0.59.3's const relocation (`ramses_tx.const` → `ramses_rf.const`). Necessary companion to PRs 906-909 below. |
| ramses_cc PR 906-909 (Phase 5 consumer PRs) | **ALL MERGED** (Aug 8 2026) | PR 906 (schedule services), 907 (DTO boundary alignment / thermal_demand), 908+909 (polling interval diagnostics). Completes the ramses_cc side of Phase 5. |
| ramses_cc manifest pin | **at `ramses-rf==0.59.3`** | Bumped in PR 911. ha-sim test Aug 9 (cc/rf both at current `master`, post Phase 5): **all recipes pass** — the 19 failures from the Aug 6 run appear resolved by the Phase 5 completion + const fix. Re-verify against tagged releases once 0.59.4/cc-equivalent tags stabilize. |

### Critical path

```
ramses_rf 0.59.1 (RELEASED) ──→ PR 869 (compat) ✅ MERGED ──→ PR 863 (migration) ✅ MERGED
                                                                     │
                                                                     └──→ PR 870 CLOSED ──→ PR 882 ✅ MERGED (Steps 2-3 shipped in cc 0.59.2)
                                                                                 │
                                                                                 └──→ Step 4 (shrink _commands) — optional, not done

ramses_rf 0.59.3 (RELEASED Aug 7) — Phase 5 (issue 992) CLOSED, all PRs merged
    │
    ├──→ PR 997 (event bus & handshake) ✅ MERGED ──→ Step 5 (TopologyChangedEvent)   [UNBLOCKED — actionable]
    │
    └──→ ramses_cc PR 914 (const fix) + PR 906-909 (consumer PRs) ✅ ALL MERGED

ramses_rf 0.59.4 (RELEASED Aug 8) — Phase 6 (issue 1001) IN PROGRESS (payload dataclass layer, shadow-parity, non-breaking so far)

ramses_rf: implement load_fan  ──→ Step 6 (HVAC topology)  [still blocked, no open PR]
```

**Steps 1-3 are SHIPPED** (PR 863 + PR 882, in ramses_cc 0.59.1/0.59.2). Remaining:
- **Step 4** (shrink `_commands`) — optional, non-breaking, not done
- **Step 5** (TopologyChangedEvent) — **UNBLOCKED as of ramses_rf 0.59.3** (PR 997 shipped `set_schema_updated_callback`). Not yet implemented on the ramses_cc side — this is now the top actionable item.
- **Step 6** (HVAC topology) — still blocked on ramses_rf `load_fan` (confirmed still a stub as of 0.59.4)
- **Step 7** (StateUpdatedEvent) — future upgrade

**Status as of Aug 9 2026:** ramses_rf and ramses_cc masters are both fully
up to date with each other (0 ahead/behind on tracked branches). The const
relocation regression from PR 987/999 has been fixed upstream (ramses_cc
PR 914). A full ha_sim_test parallel run against current masters passes
cleanly. The 19 failures noted in the Aug 6 run (against the 0.59.2 tags)
were pre-Phase-5-completion regressions and appear resolved now — but
should be re-confirmed against the next tagged releases (0.59.3/0.59.4
equivalents) once cut, not just against master.

**Immediate TODO:**
1. **Implement Step 5** (TopologyChangedEvent subscription) now that
   `Gateway.set_schema_updated_callback()` exists in ramses_rf 0.59.3+.
   This replaces the 5-min `sync_learned_topology` polling loop with an
   event-driven push from ramses_rf on topology mutations. **See the
   fully detailed implementation plan** (concrete code sketch, debounce
   design, `__init__`/unload wiring, and new ha_sim_test recipe R62) in
   the [Step 5](#step-5-topologychangedevent-subscription) section
   below — added Aug 9 2026 after verifying the API directly against
   the ramses_rf 0.59.4 checkout.
2. Re-run the full ha_sim_test suite once ramses_cc/ramses_rf cut their
   next tagged releases (post Phase 5) to confirm the fix holds outside
   of `master`.
3. Watch ramses_rf Phase 6 (issue #1001, payload dataclass layer) for
   any breaking changes as it progresses — currently shadow-parity
   (non-breaking) but the "cutover" PRs later in the 12-PR plan may
   change parser return types.
4. Step 6 (HVAC topology / `load_fan`) has no upstream movement — could
   be worth raising with PWhite-Eng/silverailscolo as a follow-up now
   that Phase 5 is done, since it's the last remaining hard blocker for
   Phase 4.

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

#### STATUS: UNBLOCKED as of ramses_rf 0.59.3 (PR 997) — API confirmed present

Verified directly against the current `ramses_rf` checkout (Aug 9 2026):

- `SchemaUpdatedCallback = Callable[[dict[str, Any]], Awaitable[None] | None]`
  defined in `src/ramses_rf/interfaces.py:15`.
- `Gateway.schema_updated_callback` (property) and
  `Gateway.set_schema_updated_callback(callback)` in
  `src/ramses_rf/gateway.py:275-292`.
- Wiring already exists end-to-end and needs **no further ramses_rf
  changes**:
  `DeviceRegistry.handle_topology_event()` (`devices/dev_registry.py:96-111`)
  → on any successful mutation, calls `self._on_topology_changed_cb()`
  → `Gateway._on_topology_changed()` (`gateway.py:294-296`) →
  `asyncio.create_task(self._notify_schema_updated())` →
  `Gateway._notify_schema_updated()` (`gateway.py:298-309`) awaits
  `self.schema()` and invokes the registered callback with the
  **full schema dict** (same shape as `gwy.get_state()`'s first
  return value, i.e. identical to what `async_save_client_state`
  already consumes as `schema` today).
- The callback may be sync or async (`Awaitable[None] | None` return).
- This fires on **every** successful topology mutation: `BIND_DEVICE`,
  `UPDATE_DEVICE_CLASS`, `UPDATE_TRAITS`, `CREATE_CONTROLLER`,
  `CREATE_CIRCUIT`. Rejected mutations (`DeviceNotFoundError`,
  `SchemaInconsistentError`, `SystemSchemaInconsistent`) do NOT fire
  the callback (see `dev_registry.py:112-119`).

**No ramses_rf PR is needed anymore** — the earlier idea of
`gwy.add_topology_callback(cb)` is superseded by the simpler
single-callback `set_schema_updated_callback` API that already shipped.

#### Concrete implementation plan (ramses_cc side only)

All changes are in `custom_components/ramses_cc/coordinator.py`.
`self.client` is a `Gateway` instance, so the API is directly usable.

**1. Register the callback in `async_start()`**, right after
`await self.client.start(**start_kwargs)` (or as part of `async_setup`,
wherever `self.client` is guaranteed non-None and stable — check both
`async_setup` and `async_start` since `self.client` can be replaced on
`fresh_start` profile reloads):

```python
if self.client:
    self.client.set_schema_updated_callback(self._on_rf_schema_updated)
    self.entry.async_on_unload(
        lambda: self.client.set_schema_updated_callback(None)
        if self.client else None
    )
```

**2. Implement `_on_rf_schema_updated` with debouncing.** Topology
mutations can arrive in bursts (e.g. a discovery scan processing many
1FC9 packets during startup, or a multi-zone 000C sequence). Firing
`async_save_client_state` (which does schema validation + a full
config-entry write + reload-suppression bookkeeping) on every single
event would cause redundant work and potential config-entry write
storms. Debounce with a short delay (e.g. 2 seconds), cancelling and
rescheduling on each new event — a standard "trailing debounce"
pattern:

```python
def _on_rf_schema_updated(self, schema: dict[str, Any]) -> None:
    """Callback from ramses_rf when topology/schema changes (Step 5).

    Debounced: coalesces bursts of topology events (e.g. a discovery
    scan processing multiple 1FC9 packets) into a single save cycle.
    """
    if self._skip_topology_sync:
        return  # coordinator is unloading/reloading — ignore
    if self._schema_updated_debounce_task is not None:
        self._schema_updated_debounce_task.cancel()
    self._schema_updated_debounce_task = self.hass.async_create_task(
        self._debounced_topology_sync()
    )

async def _debounced_topology_sync(self) -> None:
    try:
        await asyncio.sleep(2.0)
    except asyncio.CancelledError:
        return
    await self.async_save_client_state()
```

Notes:
- Reuse `async_save_client_state()` as-is — it already does the
  `sync_learned_topology` diff, schema validation
  (`_validate_schema_for_ramserf`), reload suppression
  (`_suppress_reload`), and `config_entries.async_update_entry` call.
  No duplicate logic needed.
- The `schema` dict passed into the callback is discarded in favour of
  re-fetching via `self.client.get_state()` inside
  `async_save_client_state` — this keeps a single code path and avoids
  subtle drift between "event schema" and "state-save schema". If
  profiling later shows this is wasteful, `async_save_client_state`
  could be refactored to accept an optional pre-fetched schema.
- Guard on `self._skip_topology_sync` (already exists, set during
  `_async_save_on_unload`, see `coordinator.py:1722/1746`) to avoid
  writing a fresh-start / unloading config entry from a stale event
  that was in flight before unload.

**3. Reduce (not remove) the polling fallback.** Keep
`async_save_client_state` on `async_track_time_interval` as a safety
net (covers any topology change that doesn't go through
`DeviceRegistry.handle_topology_event`, and covers periodic packet-state
persistence which is a separate concern from topology sync). Increase
`SAVE_STATE_INTERVAL` from 5 min to e.g. 15-30 min once the event-driven
path is verified reliable — don't remove it entirely in the first PR.

**4. Add `self._schema_updated_debounce_task: asyncio.Task | None = None`**
to `__init__`, alongside the existing `self._skip_topology_sync` flag.

**5. Cancel the debounce task on unload** (in `_async_save_on_unload`,
before the final `await self.async_save_client_state()`), so an
in-flight debounced save doesn't race with the unload's own save.

#### Testing

New ha_sim_test recipe **R62** (next free number): bind a new TRV via
1FC9 injection (as R11 already does), then instead of `ctx.wait(N)` or
polling for up to 5 minutes, assert the config entry's `CONF_SCHEMA` is
updated within a few seconds (e.g. `wait_for(..., timeout=10)`). This
directly proves the event-driven path fired instead of relying on the
periodic poll. Also verify:
- Multiple rapid 1FC9 injections (burst) result in a single config-entry
  write, not N writes (check `core.config_entries` write timestamp /
  count via a log line, or spy on `async_update_entry` call count in a
  debug log).
- No regression: `sync_learned_topology`'s existing behaviour
  (validation rejection, comments refresh, remotes migration) is
  unchanged since it's the same function, just triggered differently.
- Unload during an in-flight debounce doesn't corrupt the schema
  (start a topology change, immediately reload the config entry,
  verify no crash / no stale write).

#### Rollout

This is a purely additive, non-breaking change to ramses_cc — no
ramses_rf changes, no config schema/migration changes. Safe to ship in
a minor ramses_cc release once ha_sim_test (including new R62) passes.

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

**Status:** No open PR. This is the biggest remaining gap. **Confirmed
NOT planned by PWhite-Eng** — see "Not on PWhite-Eng's roadmap" below.

**What ramses_rf already has (0.59.0):**
- `HvacVentilator` class with `_bound_devices` dict, `add_bound_device`,
  `remove_bound_device`, `get_bound_rem` methods
- `TopologyBuilder._evaluate_hvac_rules` detects HVAC device class
  from verb/code signatures (31D9 = fan on RQ, CO2 on I)
- 1FC9 binding events emit `BIND_DEVICE` (Phase 3.5, done)
- `SCH_TRAITS_HVAC` accepts `remotes`, `sensors`, `bound` as
  `str | list[str]`

#### Not on PWhite-Eng's roadmap (verified Aug 9 2026)

Searched the entire 64-comment thread on issue #639 (last updated Jul
16 2026, entirely about the heating-domain CQRS/OSI decoupling), the
Phase 5 issue #992 (client API/DTO boundaries), and the Phase 6 issue
#1001 (payload dataclass layer) — **`load_fan` is never mentioned**.
Phase 6's only HVAC-related scope is payload *parsing* (2411, 31DA,
CO2 dataclasses), not schema/topology loading. `gh search code
"load_fan" --repo ramses-rf/ramses_rf` returns only the stub itself.
This is a gap unique to our analysis — nobody upstream is tracking it.

#### Important architectural finding: the generic Parent/Child machinery doesn't fit HVAC

Before designing the fix, verified whether `load_fan` could simply
call `_get_device(gwy, dev_id, parent=fan, child_id=...)` the same way
`Evohome._update_schema` does for zones (`tcs.py:798-833`). It cannot,
without a larger refactor:

- `_apply_topology_link()` (`topology.py:450-499`) calls
  `self._get_parent(parent, ...)`, which looks up a hardcoded
  `PARENT_RULES` dict (`topology.py:~380-418`) keyed by
  `parent.__class__.__name__` (`"Evohome"`, `"DhwZone"`, `"MixZone"`,
  `"RadZone"`, `"UfhZone"`, `"ValZone"`). `HvacVentilator` is not in
  this dict, so linking would raise `SchemaInconsistentError` /
  `PARENT RULES EXCEPTION`.
- `_apply_topology_link` also unconditionally derives
  `ctl = getattr(parent, "ctl", None)` and assigns
  `self.ctl = ctl; self.tcs = getattr(ctl, "tcs", None)` — a
  heating-domain-specific concept (every zone/circuit belongs to a
  Controller/TCS) that has no HVAC equivalent (a FAN is not a CTL).
- Extending `PARENT_RULES` + generalizing `_apply_topology_link` to
  not assume `ctl`/`tcs` for non-heat parents is possible, but is a
  much bigger, riskier change than the actual problem requires (it
  touches shared heating-domain code that has extensive test
  coverage and is mid-refactor upstream via Phase 6).

**Recommendation: build a separate, minimal HVAC ownership mechanism
that does not reuse `Parent`/`Child`/`PARENT_RULES` at all.** This
keeps the change additive and isolated to `hvac_ventilators.py` +
`schemas.py` + `dev_registry.py`'s orphan/schema helpers, with zero
risk to the heat-domain topology graph.

#### Concrete implementation plan (three additive sub-phases)

**6a. `load_fan` populates plain ID-list membership (no Parent/Child)**

In `src/ramses_rf/devices/hvac_ventilators.py`, add to `HvacVentilator`:

```python
# alongside the existing _bound_devices dict
_remote_ids: set[DeviceIdT]
_sensor_ids: set[DeviceIdT]
```
initialized in `_init_fan_state()` (`self.__dict__.setdefault("_remote_ids", set())`,
same for `_sensor_ids`), plus a new method:

```python
def _update_schema(self, **schema: Any) -> None:
    """Update this FAN with its remotes/sensors membership from schema.

    Unlike heating Parent/Child, this does NOT use the shared
    ``Parent``/``_apply_topology_link`` machinery (see Step 6 notes in
    ramses_extras/docs/phase4_plan.md for why) — it's a lightweight,
    HVAC-specific membership list.
    """
    from ramses_rf.schemas import SCH_VCS, SZ_REMOTES, SZ_SENSORS

    schema = shrink(SCH_VCS(schema))
    for dev_id in schema.get(SZ_REMOTES, []):
        self._gwy.device_registry.get_device(dev_id)  # ensure it exists
        self._remote_ids.add(DeviceIdT(dev_id))
    for dev_id in schema.get(SZ_SENSORS, []):
        self._gwy.device_registry.get_device(dev_id)  # ensure it exists
        self._sensor_ids.add(DeviceIdT(dev_id))
```

In `src/ramses_rf/schemas.py`, uncomment and fix `load_fan`:

```python
def load_fan(gwy: Gateway, fan_id: DeviceIdT, schema: dict[str, Any]) -> Device:
    fan = _get_device(gwy, fan_id)
    if hasattr(fan, "_update_schema"):
        fan._update_schema(**schema)
    return fan
```

This alone makes `remotes`/`sensors` device IDs get instantiated
(`_get_device` creates them if missing) on schema load, and records
membership on the FAN — without touching the heat topology graph.

**6b. `gateway.schema()` nests FAN membership instead of flattening to `orphans_hvac`**

Add a `schema()` method to `HvacVentilator` (mirroring
`Evohome.schema()`'s shape) returning
`{SZ_REMOTES: sorted(self._remote_ids), SZ_SENSORS: sorted(self._sensor_ids)}`
(empty lists omitted, matching `shrink()` conventions used elsewhere).

In `Gateway.schema()` (`gateway.py:311-317`), add a loop over FAN
devices analogous to the existing TCS loop:

```python
for dev in self.device_registry.devices:
    if isinstance(dev, HvacVentilator) and (dev._remote_ids or dev._sensor_ids):
        schema[dev.id] = await dev.schema()
```

Update `DeviceRegistry.get_hvac_orphans()` (`dev_registry.py:751-765`)
to exclude any device that is a member of *any* FAN's `_remote_ids` /
`_sensor_ids` — build the exclusion set once per call:

```python
async def get_hvac_orphans(self) -> list[DeviceIdT]:
    owned: set[DeviceIdT] = set()
    for d in self.devices:
        if isinstance(d, HvacVentilator):
            owned |= d._remote_ids | d._sensor_ids
    orphans = []
    for d in self.devices:
        if isinstance(d, DeviceHvac) and d.id not in owned:
            is_present = await d._is_present() if hasattr(d, "_is_present") else False
            if is_present:
                orphans.append(d.id)
    return sorted(orphans)
```

**Result:** on restart, `load_schema()` → `load_fan()` restores FAN
membership from the persisted schema, so `gateway.schema()` round-trips
correctly (issue #627-style — matches the analogous heat-domain
round-trip that already works for zones). This directly replaces
ramses_cc's current workaround of caching HVAC schema separately in
`.storage/ramses_cc[hvac_schema]` (PR 764) — that workaround can stay
as a fallback/safety net (same pattern as Step 5's polling fallback)
but is no longer load-bearing once 6a/6b ship.

**6c. CO2 dual-role support (stretch goal, verify after 6a/6b)**

A device ID can already appear in both a FAN's `remotes` and `sensors`
lists today — `SCH_VCS`'s `vol.Unique()` is per-list, not cross-list,
so the schema validation doesn't block it. The open question is
whether the *device class* (e.g. a 37: REM instantiated as `HvacRemoteBase`)
correctly responds to both roles at the ramses_rf device-object level.
This likely needs no new ramses_rf code — just an ha_sim_test recipe
(e.g. extend the planned R41-R43) proving a single 37: device ID
correctly appears in both lists after 6a/6b and behaves correctly as
both REM and CO2 sensor. Treat as a verification task, not a coding
task, unless testing reveals a real gap.

**Note on `add_bound_device` / `_bound_devices`:** this mechanism is
distinct from 6a/6b's `_remote_ids`/`_sensor_ids` — `_bound_devices`
tracks which REM/DIS device is the **2411 command source** for the
FAN (already wired from the schema `_bound` trait, but done entirely
client-side in `ramses_cc/fan_handler.py:setup_fan_bound_devices` as a
workaround). Once 6a/6b ship, `_bound_devices` and `_remote_ids` will
overlap (a bound device is also a remote), but they serve different
purposes and can coexist unchanged — no need to unify them in the
first PR.

**Test:** ha_sim_test recipes R41, R42, R43 (currently SKIP) will
verify HVAC topology when implemented. Recipe assertions to add:
- FAN's `remotes`/`sensors` survive a coordinator restart via
  `gateway.schema()` round-trip (not just the `.storage` cache)
- `get_hvac_orphans()` no longer lists REM/sensor devices that are
  members of a FAN
- `gateway.schema()` output nests remotes/sensors under the FAN ID
  instead of flattening to `orphans_hvac`

**What ramses_cc can do now (workaround, keep as fallback):**
- Cache HVAC schema separately in `.storage/ramses_cc[hvac_schema]`
- Restore HVAC schema from cache on restart
- This is already implemented (PR 764, verified by R07/R07b/R15)
- Once 6a/6b ship, this cache becomes a safety net rather than the
  primary mechanism (same pattern as Step 5's reduced-frequency poll)

#### Next action: raise upstream now that Phase 5 is done

Re-confirmed against the 0.59.4 checkout (Aug 9 2026) that
`load_fan()` (`src/ramses_rf/schemas.py:424-439`) is unchanged — the
`fan._update_schema(**schema)` line is still commented out, and no
open ramses_rf PR/issue references it directly (only the general
tracking issue #639). With Phase 5 now fully closed and Phase 6
(payload dataclass layer) not touching topology/schema code, this is
a good time to raise a focused ramses_rf issue:

- Title suggestion: "load_fan() is a stub — HVAC schema
  (remotes/sensors) is not loaded into FAN devices"
- Reference issue #639 (architecture blueprint) and this doc's Step 6
  analysis above — it's detailed enough to hand off directly: the
  3 sub-phases (6a/6b/6c), the exact files/line numbers, and *why*
  the existing heat-domain `Parent`/`Child`/`PARENT_RULES` machinery
  shouldn't be reused (avoids a wasted back-and-forth on approach).
- We are not positioned to implement this ourselves (it's core
  `ramses_rf` device/topology logic, not a `ramses_cc` change) — but
  the plan above is concrete enough that PWhite-Eng/silverailscolo
  (or an AI coding session briefed with it) could execute it directly,
  and it unblocks our last remaining Phase 4 step.

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
