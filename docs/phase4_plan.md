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

> Full per-PR narrative and the critical-path diagram are in the
> [archive](phase4_plan_archive.md#dependency-narrative-detail-superseded-by-main-docs-summary-table).

| Dependency | Status | Notes |
|---|---|---|
| ramses_rf 0.59.1 → 0.59.4 | **RELEASED** | 0.59.1 (Jul 25): PR 914 + Phase 4. 0.59.2 (Aug 4): Phase 4e. 0.59.3 (Aug 7): Phase 5 fully shipped incl. PR 997 (**unblocks Step 5**), issue #992 CLOSED. 0.59.4 (Aug 8): Phase 6 (issue #1001) started, non-breaking so far. |
| Phase 3a-3e | DONE | All sub-phases merged |
| PR 914 (Phase 3.75) | MERGED, in 0.59.1 | "init and go" from schema `_class` — device class correct without known_list fallback |
| Issue 677 fix (0.57.6) | DONE | `enforce_known_list` bug fixed — Step 3 shipped |
| ramses_rf Phase 3.5 (1FC9 → TopologyChangedEvent) | DONE in 0.59.0 | `_evaluate_rf_bind_rules` intercepts 1FC9, emits `BIND_DEVICE` |
| TopologyChangedEvent public subscription API | **SHIPPED in 0.59.3** (PR 997) | `Gateway.set_schema_updated_callback(cb)` in `interfaces.py`/`gateway.py`. **Step 5 is unblocked — actionable.** |
| ramses_rf HVAC topology (`load_fan`) | **STILL A STUB** | `schemas.py:437` — `fan._update_schema(**schema)` commented out (verified vs 0.59.4, Aug 9). No open PR. Blocks Step 6. |
| ramses_rf Phase 4 (issue #915) | FULLY COMPLETE | 5-PR strangler fig + Phase 4e. All merged. |
| ramses_rf Phase 5 (issue #992) | CLOSED — FULLY SHIPPED | Client API & Consumer DTO Boundary Enforcement. PR 997 delivers our Step 5 unblock. |
| ramses_rf Phase 6 (issue #1001) | OPEN — IN PROGRESS | Dataclass payload layer, shadow-parity (non-breaking so far). Worth periodic ha-sim checks. |
| ramses_cc PRs 863, 869, 882, 881, 914, 906-909 | **ALL MERGED** | Migration+backup, compat fixes, known_list removal (Steps 2-3), const fix, Phase 5 consumer PRs. |
| ramses_cc manifest pin | at `ramses-rf==0.59.3` | ha-sim test Aug 9 (cc/rf at master, post Phase 5): **all recipes pass**. |

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

#### Implementation plan (ramses_cc side only)

All changes are in `custom_components/ramses_cc/coordinator.py`.
`self.client` is a `Gateway` instance, so the API is directly usable.
**Full code sketch (callback registration, debounced save, polling
fallback reduction, unload handling) is in the
[archive](phase4_plan_archive.md#step-5-full-code-sketch-ramses_cc-coordinatorpy).**
Summary:

1. Register `self.client.set_schema_updated_callback(self._on_rf_schema_updated)`
   in `async_start()`/`async_setup()`, unregister on unload.
2. Debounce (~2s trailing) the callback into a single
   `async_save_client_state()` call to coalesce bursts (e.g. a
   discovery scan processing many 1FC9 packets). Reuse
   `async_save_client_state()` as-is — no duplicate validation logic.
3. Keep the polling loop as a reduced-frequency safety net (5 min →
   15-30 min) rather than removing it in the first PR.
4. Guard on the existing `self._skip_topology_sync` flag and cancel any
   in-flight debounce task on unload.

#### Testing

New ha_sim_test recipe **R62**: bind a new TRV via 1FC9 injection (as
R11 does), assert `CONF_SCHEMA` updates within seconds instead of
waiting on the 5-min poll. Also verify a burst of 1FC9 injections
produces a single config-entry write, no regressions in
`sync_learned_topology`, and no corruption if unload races an in-flight
debounce. Full detail archived.

#### Rollout

Purely additive, non-breaking change to ramses_cc — no ramses_rf
changes, no config schema/migration changes. Safe to ship in a minor
ramses_cc release once ha_sim_test (including new R62) passes.

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

Searched the entire 64-comment thread on issue #639, the Phase 5 issue
#992, and the Phase 6 issue #1001 — **`load_fan` is never mentioned**.
Phase 6's only HVAC-related scope is payload *parsing* (2411, 31DA,
CO2 dataclasses), not schema/topology loading. This is a gap unique to
our analysis — nobody upstream is tracking it.

#### Architectural finding: the generic Parent/Child machinery doesn't fit HVAC

`load_fan` can't simply call
`_get_device(gwy, dev_id, parent=fan, child_id=...)` the way
`Evohome._update_schema` does for zones — `_apply_topology_link()`
looks up a hardcoded `PARENT_RULES` dict keyed by `parent.__class__.__name__`
that doesn't include `HvacVentilator`, and it unconditionally derives
`ctl`/`tcs` (heating-only concepts with no HVAC equivalent). Extending
that shared machinery is possible but riskier than the actual problem
requires (touches heavily-tested heating-domain code, mid-refactor
upstream via Phase 6).

**Recommendation:** build a separate, minimal HVAC ownership mechanism
that doesn't reuse `Parent`/`Child`/`PARENT_RULES` — isolated to
`hvac_ventilators.py` + `schemas.py` + `dev_registry.py`'s orphan
helpers, with zero risk to the heat-domain topology graph. **Full code
sketch for all three sub-phases is in the
[archive](phase4_plan_archive.md#step-6-full-code-sketch-ramses_rf-hvac-topology).**

#### Implementation plan (three additive sub-phases)

**6a.** `load_fan` populates plain ID-list membership (no Parent/Child):
add `_remote_ids`/`_sensor_ids` sets to `HvacVentilator`, a
`_update_schema()` method that registers devices and records
membership, and uncomment/fix `load_fan()` in `schemas.py` to call it.

**6b.** `gateway.schema()` nests FAN membership instead of flattening
to `orphans_hvac`: add a `schema()` method to `HvacVentilator`, loop
over FAN devices in `Gateway.schema()`, and update
`get_hvac_orphans()` to exclude devices owned by any FAN. Result: FAN
membership round-trips across restarts via the schema, same as zones
do today — this replaces ramses_cc's `.storage/ramses_cc[hvac_schema]`
workaround (PR 764), which can stay as a fallback/safety net.

**6c (stretch).** CO2 dual-role support — verify a single 37: device ID
can appear in both a FAN's `remotes` and `sensors` lists and behave
correctly as both REM and CO2 sensor. Likely a verification task
(ha_sim_test recipe), not new code, unless testing reveals a gap.

**6d (future enhancement).** Bidirectional FAN→child parent link for
HA device registry grouping.  6a/6b gives FAN→children (via
`_remote_ids`/`_sensor_ids`) but children don't know their parent FAN
(no `_parent_fan` attribute, unlike heat-domain `Child._parent`).
ramses_cc's `via_device` logic (`coordinator.py:2139`) checks
`isinstance(device, Child)` which is False for HVAC devices, so
REM/CO2 appear as standalone devices in the HA UI instead of grouped
under their FAN.  Fix: add `_parent_fan: HvacVentilator | None` to
`DeviceHvac`, set it in `HvacVentilator._update_schema()`, and update
ramses_cc's `via_device` check to also handle `_parent_fan`.  Does NOT
require extending `PARENT_RULES`/`_apply_topology_link` — same isolated
approach as 6a/6b.

**6e (done, PR 924 + PR 1017).** Traffic-based HVAC topology detection
via "belongs to" device comments.

**What we detect:** The scan engine (`discovery_scan.py`) watches RF
traffic.  When a FAN (32:) sends a directed I or RP packet to a 37:/29:
device using an HVAC operational code (22F1, 31E0, 31DA, 10D0, 2411),
the scan engine sets `bound_to = <FAN_id>` on the 37: device.  This is
traffic-based inference, NOT the 1FC9 hardware handshake — the FAN is
the controller, and directed communication with a specific remote
proves binding.  The scan engine now does this for both known and
unknown devices (previously only unknown — the known-device path
returned early before the HVAC inference).

**What gets into the schema:** `refresh_device_comments` writes
"belongs to 32:XXXXXX" in the 37: device's comment (distinct from
"bound to" = heat-domain TCS binding, and from `_bound` = hardware
handshake for 2411 routing).  Then `sync_learned_topology` step 0c/1h
parses "belongs to" comments and places the device under the FAN's
`remotes[]` (REM/DIS) or `sensors[]` (CO2/HUM), using the comment's
"Likely X" phrase or the schema's `_class` trait for classification.

**How it's used:** The FAN's `remotes[]`/`sensors[]` lists are the
HVAC topology — ramses_rf's `load_fan` (6a) reads them to populate
`_remote_ids`/`_sensor_ids`, and `gateway.schema()` (6b) nests them in
the learned schema.  ramses_cc's `sync_learned_topology` syncs them
into the config schema.  This is the same pattern as the heat-domain
comment-based zone binding (step 0b/1g) for TRVs: traffic → comment →
schema → topology.

**Why not reuse the heat-domain Parent/Child machinery (PR 1017
question):** The heat-domain `Child._parent` / `PARENT_RULES` system
is designed for zone sensors/actuators that have a 1:1 zone binding
via 000C/000A packets.  HVAC devices don't have zones — they have a
FAN parent and a remote/sensor role.  The `remotes[]`/`sensors[]` lists
under the FAN entry are the HVAC equivalent of `zones[NN].sensor`/
`actuators[]` under a TCS entry.  Reusing Parent/Child would require
inventing a fake "HVAC zone" concept, which is more complex and less
accurate than the direct `remotes[]`/`sensors[]` lists.  The
`_remote_ids`/`_sensor_ids` attributes on `HvacVentilator` (6a) are
the HVAC equivalent of `Child._parent` — they're set during
`load_fan()` from the schema, not from traffic.

**Three paths that populate `remotes[]`/`sensors[]`:**
1. **Schema preload** (user config flow): user declares `remotes`/`sensors`
   in the FAN's schema entry.  `load_fan` reads them → `_remote_ids`/
   `_sensor_ids`.
2. **Learned schema** (6b, `gateway.schema()`): ramses_rf's runtime
   device registry nests FAN membership → learned schema →
   `sync_learned_topology` syncs into config schema.
3. **Traffic-based** (6e, this step): scan engine `bound_to` → comment
   → `sync_learned_topology` step 0c/1h → `remotes[]`/`sensors[]`.

Paths 2 and 3 are automatic — the user doesn't need to declare the
topology manually.  Path 3 is the fallback when no schema is preloaded
and the learned schema hasn't been built yet (e.g. first run after
adding a FAN).

**Three binding concepts — clearly separated:**

| Phrase | Meaning | Source | Where in schema |
|--------|---------|--------|-----------------|
| `bound to 01:...` | Heat-domain TCS binding | Scan engine zone binding (000A/000C/30C9) | `zones[NN].sensor`/`actuators[]` |
| `belongs to 32:...` | HVAC FAN parent (traffic-inferred) | Scan engine directed FAN→REM I/RP (22F1/31E0/31DA/10D0/2411) | `remotes[]`/`sensors[]` |
| `_bound` schema trait | Hardware handshake (1FC9 pairing) | User-declared, for 2411 routing | FAN entry `_bound` key |

Tested by ha_sim_test R65 (REM gets "belongs to" comment from 2411 RP
FAN→REM, placed in `remotes[]`).  Also requires ramses_rf PR 1017
fixes: 2411 added to `_HVAC_PARENT_INFERENCE_CODES`, and HVAC
`bound_to` inference now runs for known devices too.

**6f (future enhancement).** Active HVAC topology probing via spoofed
RQ 22F1.  Step 6e is passive — it waits for the FAN to send a directed
I/RP to a REM, which may take hours or never happen if the REM doesn't
poll the FAN.  6f actively probes each 37:/29: device against each
known FAN (32:) by sending `RQ 22F1` (fan_mode query) with
`from_id=<REM>` to the FAN via the existing `send_packet` service
(which supports `from_id` for source spoofing).  If the FAN responds
with a directed `RP 22F1` to the REM, the scan engine sets `bound_to`
(passive listener sees the RP) → "belongs to" comment → `remotes[]`.

**Why 22F1 and not 2411:** 2411 (fan_params) has 60+ parameter IDs and
the RQ payload must include the param_id — getting it wrong may return
an error RP.  22F1 (fan_mode) takes a simple `00` payload and returns
the current fan speed — the FAN always has a current speed to report.
We can verify the RP payload matches the FAN's last 31DA broadcast
speed, confirming it's a real response (not a neighbour's FAN).

**Why this works:** the HGI is a passive listener — it sees ALL RF
traffic, including the FAN's RP directed to the REM.  We don't need
the REM to receive the response; we just need the FAN to emit a
directed packet to the REM's address.  The scan engine's raw packet
handler catches it.

**Implementation sketch:**
- New service `probe_hvac_binding` (or extend `send_packet`):
  - For each 37:/29: device in known_list without a FAN parent:
    - Send `RQ 22F1` with `from_id=<37:device>`, `device_id=<32:FAN>`,
      `payload=00`
    - Wait 2s for RP response
    - If RP received: scan engine sets `bound_to` → done
    - If no RP: REM is not bound to this FAN, try next FAN
- Could be triggered automatically on coordinator startup (one-shot)
  or on demand via a service call.
- Safety: 22F1 RQ is read-only (query, not write) — no side effects
  on the FAN's operation.

**Note on `add_bound_device` / `_bound_devices`:** distinct from
6a/6b's `_remote_ids`/`_sensor_ids` — `_bound_devices` tracks the 2411
command source for the FAN (wired client-side in
`ramses_cc/fan_handler.py:setup_fan_bound_devices` today). Once 6a/6b
ship, they'll overlap (a bound device is also a remote) but they serve different
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

ramses_rf Phase 4 (issue 915, PWhite-Eng) is a 5-PR strangler fig that
moved RQ/RP tracking from L3 FSM to L7 event bus and removed active
discovery probing. **All PRs merged to ramses_rf 0.59.1** (Jul 25
2026). **Phase 4e (Packet→Message) completed in 0.59.2** (PR 951,
Aug 4 2026). Verified against ha-sim: 347/347 checks passed
(PR 927/928/929 stack + our test fixes PR 931 + ramses_cc compat
fixes PR 869). All ramses_cc-side impacts (active discovery removal,
transport FSM streamlining, Packet→Message, DevType enums) have since
been resolved via PR 869 and the 0.59.3 pin bump.

Full PR-by-PR table, verification output, and per-PR impact/status
breakdown are in the
[archive](phase4_plan_archive.md#ramses_rf-phase-4-impact-issue-915--full-pr-table).

Polling configuration: issue 915 PR 4c.1 (PR 924) shipped
`polling_interval`/`is_battery` traits into the schema; ramses_cc PR
869 added the schema validation. Future work: expose polling interval
configuration entities in the HA UI (Step 4 territory).

---

<a id="ha-sim-test-0.59.2"></a>
## ha-sim test history

The Aug 6 2026 run (cc/rf 0.59.2 tags) found 19 failures, mostly
timing-sensitive or pre-existing (add_faked_rem HTTP 400, THM 000A
zone binding, etc.), plus 3 skips (R41-R43, blocked on Step 6). **All
of these are superseded** — the Aug 9 2026 run against current
cc/rf masters (post Phase 5) passes the full suite cleanly (see
Status line at the top of this doc). Full breakdown, per-recipe
comparison tables, and triage notes are archived
[here](phase4_plan_archive.md#ha-sim-test-ramses_cc-0592--ramses_rf-0592-aug-6-2026)
for historical reference.

---

<a id="ramses_rf-phase-5-impact"></a>
## ramses_rf Phase 5+ impact (issue 992, issue 639 comment)

PWhite-Eng's full roadmap (issue 639 comment) goes to Phase 10.

### ramses_rf Phase 5: Client API & Consumer DTO Boundary Enforcement (issue 992) — CLOSED, shipped 0.59.3

All six steps (5.1 Event Bus Hardening, 5.2 Ingestion Handshake, 5.3
DTO Boundary Enforcement, 5.4 Shim Removal, 5.5 Identity Constant
Relocation, 5.6 Final Polish) shipped across PRs 986, 987/999, 994-998.
PR 997 (5.1) delivered the `set_schema_updated_callback` API our Step
5 needs. Full step table with per-item ramses_cc risk assessment is
archived
[here](phase4_plan_archive.md#ramses_rf-phase-5-client-api--consumer-dto-boundary-enforcement-issue-992--closed-shipped-0593).

### ramses_cc import audit (Phase 5.5 identity constant relocation)

Files that imported from `ramses_tx.const`/`ramses_tx.typing` and
needed updating when constants relocated to `ramses_rf` — resolved via
PR 914. Full file-by-file audit archived
[here](phase4_plan_archive.md#ramses_cc-import-audit-phase-55-identity-constant-relocation).

### ramses_rf Phase 4.5: Domain Layer Decommissioning — DONE (PR 978, 0.59.2)

Deletes `_handle_msg` methods and legacy synchronous routing. ramses_cc
doesn't call `_handle_msg` directly, so impact was low.

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

Full dated decision history (Jul 23 - Aug 9 2026, ~25 entries) is
archived [here](phase4_plan_archive.md#decision-log-full-history).
Key milestones:

| Date | Decision |
|------|----------|
| Jul 23 2026 | Phase 4 plan created; PR 914 identified as hard blocker for Step 2 |
| Jul 25 2026 | ramses_rf 0.59.1 released (PR 914 + Phase 4 PRs); Steps 1-3 unblocked |
| Jul 30 2026 | PR 882 MERGED — Steps 2-3 SHIPPED (known_list removal + enforce always-on) |
| Aug 7-8 2026 | ramses_rf Phase 5 fully shipped (0.59.3, PR 997 unblocks Step 5); Phase 6 started (0.59.4) |
| Aug 9 2026 | ha-sim full suite passes against current masters; Step 5 implementation plan written; Step 6 confirmed off upstream roadmap, 3-sub-phase plan written |

---

[top](#phase-4-plan-known_list-removal--event-driven-topology)
