<a id="schema-as-source-of-truth-architecture"></a>
# Schema-as-Source-of-Truth Architecture

> **Naming note (updated Jul 26 2026):** There are several "Phase 3"s and "Phase 4"s:
> - **ramses_cc Phase 3** — commands in schema, our work.
>   Split into **3a** (commands on REM, PR 811, DONE), **3b**
>   (commands on FAN with packet templates, DONE, merged), **3c** (flagging,
>   DONE, in master), and **3d** (ramses_rf alignment, DONE —
>   `feature/phase3d-alignment`, merged via PR 839). **3e** (CLI compat +
>   22B0 builder, DONE — shipped in ramses_rf 0.59.0).
>   See `phase3b_fan_commands_design.md`.
> - **ramses_cc Phase 4** — known_list removal + event-driven topology.
>   See `phase4_plan.md`. Steps 1-3 implemented (PR 863 + PR 870).
>   Release plan: 0.59.1 (PR 869 + PR 863, migration with fallback),
>   0.59.2 (PR 870, remove known_list — breaking change).
>   Steps 5-6 blocked on ramses_rf subscription API / `load_fan`.
> - **ramses_rf Phase 3/3.25** (PWhite-Eng, issue 639) — TX Generation
>   Parity + Transport Decoupling. **DONE — shipped in 0.58.2/0.58.3
>   (Jul 16-17 2026).** Brought CQRS `CommandDispatcher` + domain builders
>   (22F1, 22F7, 2411, 31DA, etc.), `SCH_TRAITS_HVAC` accepts `str | list[str]`
>   for bindings, and `strip_and_map_traits()` / `strip_and_map_schema()`
>   pre-validation pipeline (functions only — not yet called by
>   Gateway/CLI inside ramses_rf). **Not yet:** 22B0 (calendar) builder,
>   per-manufacturer strategy profiles, CLI wiring of the pipeline.
> - **ramses_rf Phase 3.75** (PWhite-Eng, issue 639) — Identity
>   Composition. Was "Builder Pattern" (issue 530), now "init and go"
>   from schema. `DeviceRole` composition scrapped. Deprecate `__class__`
>   mutations. **PR 914 MERGED, shipped in ramses_rf 0.59.1** (Jul 25 2026).
> - **ramses_rf Phase 4** (PWhite-Eng, issue 915) — FSM Conversational
>   Parity & Passive Ingestion. **MERGED to ramses_rf 0.59.1** (Jul 25 2026).
>   5-PR strangler fig: Shadow FSM → Live Parity → Execution Cutover →
>   Active Discovery Removal → Transport FSM Streamlining. All PRs merged
>   (916, 919-921, 924-929). Only Phase 4e (API Modernization:
>   Packet→Message) remains.
> - **ramses_rf Phase 5** (issue 639/992) — Client API & Consumer DTO
>   Boundary Enforcement. **CLOSED — fully shipped in ramses_rf 0.59.3**
>   (Aug 7-8 2026). PR 997 ("Event Bus & Handshake") added
>   `Gateway.set_schema_updated_callback()` — this is the public
>   subscription API our ramses_cc Phase 4 Step 5 needed. ramses_cc's
>   own Phase 5 consumer PRs (906-909) and the const-import fix (PR 914,
>   needed because PR 987/999 relocated `SZ_*` constants out of
>   `ramses_tx.const`) are also merged.
> - **ramses_rf Phase 6** (issue 1001) — Unified Dataclass Payload
>   Layer. **OPEN — IN PROGRESS** (started Aug 8 2026). Replaces the
>   108 dict-based parsers with typed `PayloadBase` dataclasses via a
>   Strangler Fig shadow-parity pattern (parses both old and new,
>   asserts equality) so it should stay non-breaking for ramses_cc
>   while in progress. Worth periodic ha_sim_test checks as PRs land.
>
> **Key shift (Jul 17 2026, updated Jul 26):** Device identity Builder
> (`DeviceRole`, `supported_commands()`) scrapped in favor of "init and go"
> from schema `_class`. CQRS TX builders (22F1, 22F7, 2411, 31DA, etc.)
> shipped in 0.58.3. 22B0 (calendar) and per-manufacturer strategy profiles
> not yet implemented. `_commands` stays as user override layer. `_class`
> NOT deprecated.

<a id="chapters"></a>
## Chapters

- [Schema-as-Source-of-Truth Architecture](#schema-as-source-of-truth-architecture)
  - [Overview](#overview)
  - [Two Parallel Paths: Observer vs Topology Learning](#two-parallel-paths-observer-vs-topology-learning)
    - [PATH 1: The Observer (DiscoveryScan)](#path-1-the-observer-discoveryscan)
    - [PATH 2: Topology Builder (for known devices)](#path-2-topology-builder-for-known-devices)
    - [The Two Paths Side by Side](#the-two-paths-side-by-side)
    - [How ramses_rf creates devices — schema vs known_list](#how-ramsesrf-creates-devices-schema-vs-knownlist)
    - [The Lifecycle of a Device](#the-lifecycle-of-a-device)
    - [Why Two Paths?](#why-two-paths)
  - [What Lives Where](#what-lives-where)
    - [1. Config Entry Options (`core.config_entries`)](#1-config-entry-options-coreconfigentries)
    - [2. `.storage/ramses_cc` (HA Store)](#2-storageramsescc-ha-store)
    - [3. `ramses.db` (SQLite)](#3-ramsesdb-sqlite)
    - [4. ramses_rf Gateway (in-memory, not persisted)](#4-ramsesrf-gateway-in-memory-not-persisted)
    - [5. Packet Log Files (optional, file-based)](#5-packet-log-files-optional-file-based)
    - [Storage Relationships Diagram](#storage-relationships-diagram)
    - [The Role of known_list in Each Storage](#the-role-of-knownlist-in-each-storage)
  - [Trait Analysis — What Can Move to Schema](#trait-analysis-what-can-move-to-schema)
    - [Current traits in ramses_rf's DeviceTraits](#current-traits-in-ramsesrfs-devicetraits)
    - [Trait-by-trait analysis](#trait-by-trait-analysis)
    - [What ramses_rf already puts in the schema (learned from traffic)](#what-ramsesrf-already-puts-in-the-schema-learned-from-traffic)
    - [Extended schema with traits](#proposed-extended-schema-with-traits)
    - [What stays outside the schema](#what-stays-outside-the-schema)
    - [Why eavesdrop, block_list, disabled_devices become obsolete](#why-eavesdrop-blocklist-disableddevices-become-obsolete)
    - [The `bound` trait — FAN-specific, for faked REMs](#the-bound-trait-fan-specific-for-faked-rems)
    - [The `bind_device` service — RF binding handshake](#the-binddevice-service-rf-binding-handshake)
    - [_disabled trait — implementation details](#disableddevices-implementation-details)
    - [known_list future: view-only, in-memory, derived](#knownlist-future-view-only-in-memory-derived)
    - [commands — can move to schema too](#commands-can-move-to-schema-too)
    - [Migration path](#migration-path)
    - [Summary: what goes where](#summary-what-goes-where)
  - [Precedence Rules](#precedence-rules)
  - [Topology Changes — Current State & Gaps](#topology-changes-current-state-gaps)
    - [What ramses_rf already does (in-memory)](#what-ramsesrf-already-does-in-memory)
    - [The gap: changes don't flow back to config entry schema](#the-gap-changes-dont-flow-back-to-config-entry-schema)
    - [What's needed for true SSOT with topology](#whats-needed-for-true-ssot-with-topology)
    - [Priority order for implementation](#priority-order-for-implementation)
  - [HVAC Schema — Current State & Gaps](#hvac-schema-current-state-gaps)
    - [The fundamental gap: load_fan is a stub](#the-fundamental-gap-loadfan-is-a-stub)
    - [The roundtrip bug](#the-roundtrip-bug)
    - [FAN is not a Parent class](#fan-is-not-a-parent-class)
    - [TopologyBuilder has no HVAC binding rules](#topologybuilder-has-no-hvac-binding-rules)
    - [How HVAC topology COULD be derived from traffic](#how-hvac-topology-could-be-derived-from-traffic)
    - [CO2 sensors are remotes too (dual-role)](#co2-sensors-are-remotes-too-dual-role)
    - [Device ID prefixes for HVAC](#device-id-prefixes-for-hvac)
    - [HVAC binding uses 1FC9, not 000C](#hvac-binding-uses-1fc9-not-000c)
    - [What ramses_cc does right (despite ramses_rf gaps)](#what-ramsescc-does-right-despite-ramsesrf-gaps)
    - [What needs to change in ramses_rf](#what-needs-to-change-in-ramsesrf)
    - [What needs to change in ramses_cc](#what-needs-to-change-in-ramsescc)
  - [Crash Recovery — What Survives, What's Lost](#crash-recovery-what-survives-whats-lost)
    - [The 5 storage layers and their crash behavior](#the-5-storage-layers-and-their-crash-behavior)
    - [Crash scenarios](#crash-scenarios)
    - [What makes crash recovery better (future improvements)](#what-makes-crash-recovery-better-future-improvements)
    - [Current state summary](#current-state-summary)
  - [Key Invariants](#key-invariants)
  - [Schema Evolution & Migration](#schema-evolution-migration)
    - [The schema will no longer be minimal](#the-schema-will-no-longer-be-minimal)
    - [Versioning — what we have today](#versioning-what-we-have-today)
    - [What migrations are needed](#what-migrations-are-needed)
    - [Migration logic — when to create it](#migration-logic-when-to-create-it)
    - [Backward migration — the problem](#backward-migration-the-problem)
    - [Migration steps for each phase](#migration-steps-for-each-phase)
    - [When to create the migration code](#when-to-create-the-migration-code)
  - [Alignment with ramses_rf Roadmap](#alignment-with-ramsesrf-roadmap)
    - [The "Big Knot" — Discussion #191](#the-big-knot-discussion-191)
    - [Issue #530 (Architectural Refactor — umbrella issue)](#issue-530-architectural-refactor-umbrella-issue)
    - [Verification status (checked Jul 2026)](#verification-status-checked-jul-2026)
    - [Alignment Matrix](#alignment-matrix)
    - [Key Conflicts & Bottlenecks](#key-conflicts-bottlenecks)
    - [Recommendations](#recommendations)
  - [Guide on updating this plan](#guide-on-updating-this-plan)

<a id="overview"></a>
## Overview

```
                    USER
                      |
                      | edits via config flow / services
                      v
              ┌───────────────┐
              │ CONFIG ENTRY  │   user's intent (minimal)
              │   options     │   - main_tcs, CTL: {}
              │   schema:     │   - orphans_heat: [...]
              │               │   - _disabled per-device trait
              │   known_list: │   - known_list: overrides only
              │   (overrides) │     {device_id: {alias, class, ...}}
              └───────┬───────┘
                      |
                      | self.options (read at startup)
                      v
              ┌───────────────┐
              │  .storage/    │   ramses_rf's learned reality (rich)
              │  ramses_cc    │   - zones: {03: {sensor, actuators, _name}}
              │  client_state │   - stored_hotwater: {sensor, dhw_valve}
              │   schema:     │   - system: {appliance_control}
              │   packets:    │   - orphans: [...]
              │               │   saved every 5 min + on shutdown
              └───────┬───────┘
                      |
                      | loaded at startup
                      v
              ┌───────────────┐
              │  merge_schemas│   deep_merge(config, cached)
              │  (config wins │   - scalars: config takes precedence
              │   for scalars,│   - lists: union (set merge)
              │   lists union)│   - if config ⊆ cached: use cached
              └───────┬───────┘
                      |
                      | merged schema
                      v
              ┌───────────────┐
              │ _strip_schema │   removes ramses_cc-only keys:
              │ _extensions() │   - _-prefixed traits (_disabled, _name, ...)
              │               │   - device_comments
              │               │   - None values (main_tcs: null)
              │               │   - removes _disabled from orphan lists
              │               │   - moves HVAC without remotes/sensors to orphans_hvac
              └───────┬───────┘
                      |
                      | clean schema for ramses_rf
                      v
              ┌───────────────┐
              │ _derive_known │   walks schema → {device_id: {}}
              │ _list_from_   │   - main_tcs → CTL
              │  schema()     │   - zones[].sensor, zones[].actuators[]
              │               │   - stored_hotwater.sensor
              │               │   - underfloor_heating keys
              │               │   - orphans_heat, orphans_hvac
              │               │   - remotes, sensors (HVAC)
              │               │   excludes _disabled devices
              │               │
              │  + user known │   merge user overrides on top:
              │  _list merge  │   {device_id: {class: CTL, alias: "..."}}
              └───────┬───────┘
                      |
                      | schema + known_list
                      v
              ┌───────────────┐
              │   ramses_rf   │   creates devices from schema
              │   Gateway     │   enforces known_list
              │               │   learns topology from traffic
              │               │   builds zones, assigns sensors/actuators
              └───────┬───────┘
                      |
                      | every 5 min (SAVE_STATE_INTERVAL)
                      | + on shutdown
                      v
              ┌───────────────┐
              │ client.get_   │   returns (schema, packets)
              │ state()       │   schema = await gateway.schema()
              │               │     = {
              │               │       main_tcs: "01:...",
              │               │       "01:...": {
              │               │         system: {appliance_control: "10:..."},
              │               │         zones: {
              │               │           "03": {
              │               │             _name: "Lounge",
              │               │             class: "rad",
              │               │             sensor: "01:150003",
              │               │             actuators: ["04:150003"]
              │               │           },
              │               │           ...
              │               │         },
              │               │         stored_hotwater: {
              │               │           sensor: "07:150000",
              │               │           dhw_valve: "13:042605",
              │               │           htg_valve: null
              │               │         },
              │               │         orphans: [...]
              │               │       },
              │               │       orphans_heat: [...],
              │               │       orphans_hvac: [...]
              │               │     }
              └───────┬───────┘
                      |
                      | saved to .storage/ramses_cc
                      | (NOT to config entry options)
                      v
              ┌───────────────┐
              │  .storage/    │   rich schema cached for next restart
              │  ramses_cc    │
              └───────────────┘
```

[top](#schema-as-source-of-truth-architecture)
<a id="two-parallel-paths-observer-vs-topology-learning"></a>
## Two Parallel Paths: Observer vs Topology Learning

This is the key distinction that causes confusion. When a packet arrives
at ramses_rf, it goes through TWO completely separate paths:

```
                    RF PACKET (MQTT)
                          |
                    ┌─────┴─────┐
                    |           |
              raw handler   msg handler
              (fires FIRST)  (fires SECOND)
                    |               |
                    v               v
            ┌───────────┐   ┌───────────────────┐
            │   PATH 1  │   │      PATH 2       │
            │ OBSERVER  │   │  TOPOLOGY BUILDER │
            │ (unknown  │   │  (known devices)  │
            │  devices) │   │                   │
            └───────────┘   └───────────────────┘
```

<a id="path-1-the-observer-discoveryscan"></a>
### PATH 1: The Observer (DiscoveryScan)

```
  EVERY packet arrives
         |
         v
  add_raw_pkt_handler  ← fires BEFORE known_list filter
         |              sees ALL packets, even from unknown devices
         v
  DiscoveryScan._on_packet(dto)
         |
         |  SPEED: this is a fast path — just dict lookups
         |
         |  for each device_id in packet (src, dst, addr3):
         |    _is_known(dev_id)?
         |      → check known_list (dict lookup)
         |      → check schema keys (dict lookup)
         |      (device_registry is NOT consulted)
         |
         |    YES → skip immediately (already tracked by Path 2)
         |    NO  → classify and add/update _devices dict
         |
         |  Classification is lightweight:
         |    - prefix lookup (04: = TRV, 01: = CTL, 32: = FAN, 30: = RFG, etc.)
         |    - code list check (is it a binding code?)
         |    - zone_idx extraction from payload (if binding code)
         |    - verb+code pair for HVAC class (22F1 = REM, 1298 = CO2)
         |    Note: 37: is ambiguous (REM/CO2/HUM) — needs verb+code
         |    No deep parsing, no state, no I/O
         |
         v
  DiscoveredDevice {
    device_id: "04:056053"
    likely_type: "TRV"           ← from prefix (04: = TRV)
    zone_idx: "03"               ← from binding codes (000C, 30C9, 12B0)
    bound_to: "01:145038"        ← parent CTL
    confidence: "high"           ← high if zone_idx + bound_to known
    rssi: -75
    is_battery: true
    codes_seen: ["30C9", "12B0", "10E0"]
  }
         |
         v
  DiscoveryManager (ramses_cc wrapper)
         |
         |  adds metadata:
         |    status: new / accepted / discarded / skipped
         |    enabled: true/false
         |    owner: "user label"
         |    schema_entry: {fragment to merge into schema}
         |
         |  persists to .storage/ramses_cc[discovery]
         |  (every 5 min + on shutdown, via async_save_client_state)
         |
         v
  ┌─────────────────────────────────────────┐
  │  WAITING FOR USER DECISION              │
  │                                         │
  │  - Notification: "5 devices discovered" │
  │  - Config flow: Review discovered       │
  │    → Accept / Decline / Skip for now    │
  │  - Service: accept_discovered_device    │
  │  - Service: discard_discovered_device   │
  │                                         │
  │  Accept  → schema + known_list, real    │
  │  Decline → _owner: not-me, rejected     │
  │  Skip    → _skipped: true, re-appears   │
  │                                         │
  │  Device does NOT exist in ramses_rf     │
  │  No entities created                    │
  │  No topology learning happens           │
  │  Device is INVISIBLE to Path 2          │
  └─────────────────────────────────────────┘
```

**Key point:** The observer path is READ-ONLY and FAST. It watches
traffic, classifies devices, and waits. It never creates devices in
ramses_rf, never creates HA entities, never learns topology. It just
catalogs what's out there.

**Speed:** `_process_packet` does 2 dict lookups per device ID
(_is_known check: known_list + schema keys, NOT device_registry).
If known → skip (no work). If unknown → classify
(prefix lookup + code list check) + dict update. No disk I/O, no
deep parsing, no state mutation in ramses_rf. The observer is
significantly cheaper than Path 2.

**What the observer does NOT do:**
- No topology learning (that's Path 2's job)
- No entity creation (that's ramses_cc's job after accept)
- No schema mutation (that's the config flow's job)
- No deep packet parsing (just zone_idx extraction for binding codes)

**How does the user find out about discovered devices?**
- Today: 5-min checkpoint + 10s after startup → persistent notification
- Future: on_new_device callback (real-time, no polling) — this needs
  a new ramses_rf PR

**Class mismatch detection (DiscoveryManager):**

When `sync_with_schema` runs (every 5-min checkpoint), the
DiscoveryManager compares each accepted device's `likely_type` (from
the scan engine) with the schema's `_class` (user-authoritative).

```
  scan engine says:  37:169161 → FAN (RQ 31DA, accumulated codes)
  schema says:       37:169161 → _class: DIS (user set this)

  → MISMATCH detected
  → WARNING logged (once, not every cycle)
  → class_mismatch flag set on DeviceMetadata
  → review_discovered step shows it to the user
```

Key design decisions:
- **Schema is authoritative.** The scan engine's classification is
  advisory — it never overwrites `_class`. The user decides.
- **Normalization.** Schema `_class` values are normalized before
  comparison (e.g., `ventilator` → `FAN`) so legacy slugs don't
  trigger false mismatches.
- **Warning frequency.** The top-level WARNING fires only once per
  mismatch (tracked in `_warned_mismatches`). Subsequent checkpoints
  log at DEBUG. When all mismatches resolve, an INFO message is
  logged and the warned set is cleared.
- **Why the scan engine can be wrong.** The scan engine is a passive
  observer that guesses types from packet codes. A DIS sending
  `RQ 31DA` (requesting fan status) can be misclassified as FAN
  because 31DA maps to FAN for `I` and `RP` verbs. The verb-sensitive
  classification fix (see Topology Changes section) mitigates this,
  but other ambiguities may remain — the schema override is the
  final authority.

<a id="path-2-topology-builder-for-known-devices"></a>
### PATH 2: Topology Builder (for known devices)

```
  EVERY packet arrives
         |
         v
  gateway._msg_handler(dto)  ← fires AFTER raw handler
         |
         v
  ApplicationMessage.from_dto(dto)
         |
         v
  process_msg(self, app_msg)
         |
         |  tries to get/create device from registry
         |  → DeviceFilter.check_filter_lists(dev_id)
         |    → enforce_known_list=True?
         |      → dev_id in _include (known_list keys)?
         |        YES → create device (if not exists), process message
         |        NO  → raise DeviceNotFoundError, packet dropped
         |
         |  NOTE: known_list is the FAST LOOKUP for the filter.
         |        ramses_rf creates devices from the SCHEMA (load_schema),
         |        but the filter checks known_list (which is derived
         |        from schema). So:
         |          schema = what to create (topology structure)
         |          known_list = what to allow (device ID filter)
         |        Both are derived from the same source.
         |
         v
  ┌─────────────────────────────────────────┐
  │  Device EXISTS in ramses_rf registry    │
  │  (created at startup by load_schema,    │
  │   or on first packet if in known_list)  │
  │                                         │
  │  TopologyBuilder.consume(msg)           │
  │  evaluates 14 rules:                    │
  │    - 000C zone binding                  │
  │    - 30C9/12B0 zone_idx extraction      │
  │    - directed telemetry (TRV→CTL)       │
  │    - zone sensor matching               │
  │    - HVAC promotion                     │
  │    - DHW/OpenTherm detection            │
  │    - etc.                               │
  │                                         │
  │  Emits TopologyChangedEvent:            │
  │    BIND_DEVICE (zone assignment)        │
  │    PROMOTE_CLASS (TRV → THM)            │
  │    UPDATE_TRAITS (alias/class/etc)      │
  │    CREATE_CONTROLLER (new CTL)          │
  │    CREATE_CIRCUIT (UFH circuit)         │
  │                                         │
  │  → mutates in-memory device registry    │
  │  → zones get sensors, actuators         │
  │  → DHW system gets sensor/valves        │
  │  → device classes get promoted          │
  └─────────────────────────────────────────┘
         |
         v
  gateway.schema()  ← reflects learned topology
  {
    "01:150000": {
      "zones": {
        "03": {
          "_name": "Lounge",        ← learned from 000A/0008
          "sensor": "01:150003",    ← from schema or 000C binding
          "actuators": ["04:150003"] ← from 000C or 3150
        }
      },
      "stored_hotwater": {
        "sensor": "07:150000"       ← from schema or 10A0 heuristic
      }
    }
  }
```

**Key point:** The topology builder only runs for devices that are
already in the schema (and thus in the derived known_list). It learns
their zone assignments, names, and relationships from traffic. It
mutates the in-memory registry, and the next `get_state()` reflects
the learned topology.

<a id="the-two-paths-side-by-side"></a>
### The Two Paths Side by Side

```
                    RF PACKET
                        |
              ┌─────────┴─────────┐
              |                   |
         RAW HANDLER         MSG HANDLER
         (Path 1)            (Path 2)
              |                   |
              v                   v
      ┌───────────────┐   ┌───────────────┐
      │ DiscoveryScan │   │ DeviceFilter  │
      │               │   │               │
      │ Sees: ALL     │   │ Sees: only    │
      │ devices       │   │ known devices │
      │               │   │ (in schema)   │
      │ Does: catalog │   │ Does: create  │
      │ & classify    │   │ & learn       │
      │               │   │               │
      │ Output:       │   │ Output:       │
      │ DiscoveredDev │   │ TopologyEvent │
      │ (pending)     │   │ (immediate)   │
      │               │   │               │
      │ User must     │   │ Automatic     │
      │ accept/       │   │ (no user      │
      │ decline/skip  │   │  action)      │
      │               │   │               │
      │ No entities   │   │ Entities      │
      │ created       │   │ created       │
      │               │   │               │
      │ No topology   │   │ Topology      │
      │ learned       │   │ learned       │
      └───────────────┘   └───────────────┘
              |                   |
              v                   v
      .storage/ramses_cc    .storage/ramses_cc
      [discovery]           [client_state.schema]
              |                   |
              |                   v
              |          merge_schemas(config, cached)
              |                   |
              v                   v
      USER DECIDES          ramses_rf uses
      accept → schema       merged schema
      decline → disabled    to create devices
```

<a id="how-ramsesrf-creates-devices-schema-vs-knownlist"></a>
### How ramses_rf creates devices — schema vs known_list

```
  AT STARTUP:
  ─────────────────────────────────────────────────────
  coordinator._create_client():
    schema = merge_schemas(config_schema, cached_schema)
    known_list = _derive_known_list_from_schema(schema)
                  + user overrides (class, alias, faked, etc.)
    gateway_kwargs["schema"] = _strip_schema_extensions(schema)
    gateway_kwargs["known_list"] = sanitized_known_list

  ramses_rf Gateway.__init__():
    self._gwy_config.schema = schema        ← stored
    self._gwy_config.known_list = known_list ← stored
    engine._include = list(known_list.keys()) ← fast lookup list
    engine._enforce_known_list = True/False

  ramses_rf load_schema(gwy, known_list, **schema):
    # Creates devices from the SCHEMA structure:
    for ctl_id in schema:        → load_tcs(ctl_id)     → CTL + zones + DHW
    for fan_id in schema:        → load_fan(fan_id)     → FAN only (STUB!)
    for dev_id in orphans_heat:  → _get_device(dev_id)  → orphan devices
    for dev_id in orphans_hvac:  → _get_device(dev_id)  → orphan devices
    # Then fakes any devices in known_list with faked=True:
    for dev_id, traits in known_list:
      if traits.get("faked"):    → _get_device(dev_id) → _make_fake()

  NOTE: load_fan is currently a STUB — it creates the FAN device but
  does NOT process remotes/sensors from the schema (the _update_schema
  call is commented out as TODO). See "HVAC Schema" section below.

  So: SCHEMA creates the devices (topology structure).
      KNOWN_LIST is the allow-list (filter) + trait source (class, alias, faked).
      Both are needed, both derived from the same config entry.

  AT RUNTIME (packet arrives):
  ─────────────────────────────────────────────────────
  Path 2 (msg_handler):
    DeviceFilter.check_filter_lists(dev_id):
      if enforce_known_list and dev_id not in _include:
        raise DeviceNotFoundError  ← packet dropped
      if dev_id in _exclude (block_list):
        raise DeviceNotFoundError  ← packet dropped
    → if passes: get/create device, process message

  Path 1 (raw handler, DiscoveryScan):
    _is_known(dev_id):
      dev_id in known_list?          → skip
      dev_id in schema keys?         → skip
      (device_registry NOT consulted)
    → if unknown: classify, add to _devices dict

  SUMMARY:
    schema → creates devices at startup (load_schema)
    known_list → filter at runtime (enforce_known_list)
    known_list → traits at creation (class, alias, faked)
    DiscoveryScan → catalogs unknown devices (observer)
    TopologyBuilder → learns topology for known devices
```


<a id="the-lifecycle-of-a-device"></a>
### The Lifecycle of a Device

```
  DEVICE FIRST APPEARS ON RF
          |
          v
  ┌───────────────────┐
  │ PATH 1: OBSERVER  │  DiscoveryScan sees it
  │ status: NEW       │  classified, zone_idx maybe extracted
  │ no entities       │  no topology learning
  └────────┬──────────┘
           |
     user decides:
     ┌──────┬──────┬──────┐
     │      │      │      │
  ACCEPT  DECLINE  SKIP  (do nothing)
     │      │      │
     v      v      v
  ┌──────┐ ┌──────┐ ┌──────────────────┐
  │ACCEPT│ │DISCAR│ │ stays NEW         │
  │ED    │ │DED   │ │ re-notified later │
  │      │ │      │ │ (next review,     │
  │      │ │      │ │  or next traffic  │
  │      │ │      │ │  burst)           │
  │      │ │      │ │                   │
  │      │ │ added│ │ NOT in schema     │
  │      │ │ to   │ │ NOT in known_list │
  │      │ │disab │ │ NOT in disabled   │
  │      │ │led_  │ │ stays in          │
  │      │ │device│ │ DiscoveryScan     │
  │      │ │s list│ │ _devices dict     │
  │      │ │      │ │                   │
  │      │ │ NOT  │ │ User can review   │
  │      │ │ in   │ │ again later via   │
  │      │ │known │ │ config flow or    │
  │      │ │_list │ │ service call      │
  └──┬───┘ └──────┘ └──────────────────┘
     |
     v
  ┌───────────────────┐
  │ SCHEMA UPDATED    │  generate_schema_entry → config entry
  │ known_list derived│  _derive_known_list_from_schema
  │ ramses_cc reloads │  enforce_known_list now allows it
  └────────┬──────────┘
           |
           v
  ┌───────────────────┐
  │ PATH 2: TOPOLOGY  │  Device now in known_list
  │ device created    │  DeviceFilter allows it through
  │ entities created  │  TopologyBuilder learns zones
  │ topology learned  │  gateway.schema() enriched
  └────────┬──────────┘
           |
           v
  ┌───────────────────┐
  │ CACHE UPDATED     │  async_save_client_state (5 min)
  │ .storage/ramses_cc│  rich schema with zones/names saved
  └────────┬──────────┘
           |
           v
  ┌───────────────────┐
  │ NEXT RESTART      │  merge_schemas(config, cached)
  │ merged schema     │  config + cached topology
  │ used by ramses_rf │  device starts with known topology
  └───────────────────┘
```

**The three user decisions:**

| Decision | What happens | Device in schema? | In known_list? | Mechanism | Re-notified? |
|----------|--------------|-------------------|----------------|-----------|--------------|
| **Accept** | Device becomes real | YES (schema_entry merged) | YES (derived) | — | NO (status=ACCEPTED) |
| **Decline** | Device permanently rejected | YES (`_owner: not-me`) | NO (goes to block_list) | `_owner` trait | NO (status=DISCARDED) |
| **Skip** | Defer decision | YES (`_skipped: true`) | NO (excluded) | `_skipped` trait | YES (stays NEW, re-appears next review) |

**Skip semantics:**
- Device stays in DiscoveryScan's `_devices` dict (still cataloged)
- Metadata status remains `NEW`
- Added to schema with `_skipped: true` trait (excluded from known_list)
- Will re-appear in the next "review discovered devices" flow
- User can also accept/decline later via service call (skip = defer)
- Use case: user isn't sure yet, wants more traffic to accumulate
  (more codes_seen, higher confidence) before deciding

<a id="why-two-paths"></a>
### Why Two Paths?

The two paths exist because of `enforce_known_list`:

- **Without enforce_known_list**: ramses_rf would create ANY device it
  sees → entities for random devices, no user control
- **With enforce_known_list**: ramses_rf only creates devices in the
  known_list → user controls what gets entities

But we still want to KNOW what's out there (for discovery) → the raw
handler bypasses the filter, sees everything, but only catalogs.

```
  enforce_known_list = True
  ┌─────────────────────────────────────────────────┐
  │                                                 │
  │  known_list = {device_A, device_B, device_C}    │
  │                                                 │
  │  Packet from device_A → Path 2 (topology)       │
  │  Packet from device_B → Path 2 (topology)       │
  │  Packet from device_C → Path 2 (topology)       │
  │  Packet from device_X → Path 1 (observer only)  │
  │  Packet from device_Y → Path 1 (observer only)  │
  │                                                 │
  │  device_X and device_Y:                         │
  │    - cataloged by DiscoveryScan                 │
  │    - no entities created                        │
  │    - no topology learned                        │
  │    - user must accept/decline/skip       │
  │    - accept → becomes "real" (Path 2)    │
  │    - decline → permanently rejected      │
  │    - skip → defer (stays NEW)            │
  │                                                 │
  └─────────────────────────────────────────────────┘
```
[top](#schema-as-source-of-truth-architecture)
<a id="what-lives-where"></a>
## What Lives Where

<a id="1-config-entry-options-coreconfigentries"></a>
### 1. Config Entry Options (`core.config_entries`)

User-controlled configuration. Survives cache clears. The only thing
the user directly edits.

```
┌─────────────────────────────────────────────────────────────┐
│ CONFIG ENTRY OPTIONS                                        │
│                                                             │
│ schema:                     ← COMPLETE SYSTEM REFLECTION    │
│   main_tcs: "01:216136"       (endgoal: rich, not minimal)  │
│   "01:216136": {                                            │
│     _alias: "My Controller"   ← traits (future, _ keys)     │
│     _faked: false                                           │
│     system: {appliance_control: "10:064873"}                │
│     zones: {                                                │
│       "03": {                                               │
│         _name: "Lounge"                                     │
│         sensor: "01:150003"                                 │
│         actuators: ["04:150003"]                            │
│       }                                                     │
│     },                                                      │
│     stored_hotwater: {sensor: "07:150000"}                  │
│   }                                                         │
│   "30:160000": {_scheme: "itho", remotes: ["32:153001"]}    │
│   orphans_heat: [...]                                       │
│   device_comments: {...}     ← ramses_cc extension keys    │
│                              (stripped before ramses_rf)    │
│   NOTE: _disabled is now a per-device trait, not a top-level │
│   list. e.g. "04:034692": {_disabled: true}                 │
│                                                             │
│ known_list: (optional)      ← TRAIT OVERRIDES (temporary)   │
│   "01:150003":               ENDGOAL: derived only,         │
│     class: CTL                 not user-editable.           │
│     alias: "Lounge sensor"    Today: still editable for     │
│   "04:150003":                 class/alias/faked/scheme/    │
│     class: TRV                bound overrides.              │
│     alias: "Lounge valve"    Migration: traits move to      │
│   "07:150000":                schema as _ keys (v2),        │
│     class: DHW                then known_list removed (v4)  │
│                                                             │
│ packet_log:                 ← file-based packet logging     │
│   packet_log_path: "/config/ramses_rf_logs/"                │
│   packet_log_prefix: "packet_log"                           │
│   packet_log_retention_days: 7                              │
│                                                             │
│ + other options: eavesdrop, enforce_known_list, etc.        │
│   (both will become obsolete — see migration)               │
│                                                             │
│ WHO WRITES: user (config flow UI)                           │
│             accept/decline/skip discovery flow              │
│             services (update_schema, bind_device, etc.)     │
│             cache→config sync (IMPLEMENTED, auto-enrich schema)│
│ WHO READS:  coordinator at startup → builds gateway_kwargs  │
│ LIFETIME:   permanent, user-controlled                      │
│ CLEARED BY: only by user deleting the config entry          │
└─────────────────────────────────────────────────────────────┘
```

**Role of schema here:** SSOT for the complete system. Today it's
minimal (empty CTL, orphans list). The endgoal is that it reflects
the complete system — topology + traits. Enriched by:
- User accept/decline/skip (adds/removes/defers devices)
- cache→config sync (IMPLEMENTED: writes ramses_rf's learned topology
  back to config entry options via `sync_learned_topology()`)
- Manual editing (config flow schema editor)

**Role of known_list here:** Today: trait overrides (class, alias,
faked, scheme, bound). Endgoal: **derived only, not user-editable.**
The known_list is computed from the schema at startup by
`_derive_known_list_from_schema()`. It becomes a view-only in-memory
dict, rebuilt on every startup/schema change.

**Migration path for known_list:**
```
TODAY (v1):
  config entry has: schema + known_list (both editable)
  coordinator derives: known_list from schema + merges user overrides

CURRENT (v1.5, IMPLEMENTED in PR 764):
  config entry has: schema (with _disabled, _name, _alias, _class, _comment)
  known_list still in config entry but deprecated
  coordinator derives: known_list from schema (reads _ keys)
  _strip_schema_extensions strips _ keys before passing to ramses_rf
  known_list overrides still work for backward compat

NEXT (v2, strip+map pipeline moves to ramses_rf):
  config entry has: schema (with _alias, _class, _faked, _scheme, _bound)
  ramses_rf owns stages 1+2: strip _ keys + map _bound→bound, _scheme→scheme
  ramses_cc keeps stage 3 only: orphan routing, HGI dropping, disabled/skipped
  _strip_schema_extensions becomes a thin wrapper calling ramses_rf's pipeline
  known_list still in config entry but deprecated
  coordinator derives: known_list from schema (reads _ keys)
  known_list overrides still work for backward compat
  Also: SCH_TRAITS_HVAC bound accepts str | list[str] (multi-REM)

LATER (v3, commands in schema — Phase 3a DONE, Phase 3b in design):
  config entry has: schema (with _commands too)
  Phase 3a (DONE, PR 811): _commands on REM entries, full packet strings
  Phase 3b (design): _commands moves to FAN entries, {verb, code, payload} dicts
  Phase 3b: _bound accepts list[str], fan_handler loops over bound REMs
  known_list only for commands (if not yet in schema)

ENDGOAL (v4):
  config entry has: schema only (complete system)
  known_list: REMOVED from config entry
  coordinator derives: known_list from schema at startup
  known_list is in-memory only, view-only, logged at debug
```

Today, traits can't be in the schema because ramses_rf's schema
validator (`SCH_TCS_ZONES_ZON`) uses `PREVENT_EXTRA` — it rejects
unknown keys. The endgoal is to move them to schema as `_`-prefixed
keys (see "Role of known_list" and "Trait Analysis" sections below).

**WORKAROUND (IMPLEMENTED in PR 764, being refactored in Phase 3a):**
ramses_cc stores `_`-prefixed traits in the config entry schema and
strips them via `_strip_schema_extensions` before passing the schema
to ramses_rf. This means ramses_cc can use `_disabled`, `_name`,
`_alias`, `_class`, `_comment` today, without waiting for ramses_rf to
relax its validators. The `_` prefix is the convention: any key
starting with `_` is a ramses_cc extension that is recursively stripped
before ramses_rf sees the schema.

**Phase 3a refactor (planned):** The stripping logic moves to ramses_rf
as a 3-stage pipeline (see `phase3b_fan_commands_design.md`):
- Stage 1 (ramses_rf): strip `_` keys ramses_rf doesn't need
- Stage 2 (ramses_rf): map `_bound`→`bound`, `_scheme`→`scheme`
- Stage 3 (ramses_cc): orchestration (orphans, HGI, disabled/skipped)

This avoids a duplicate stripper — both the CLI (`ramses_cli -monitor`)
and ramses_cc call ramses_rf's stage 1+2. ramses_cc keeps stage 3 only.

**Status (verified Jul 23 2026, ramses_rf 0.59.0):** stages 1+2 exist in
ramses_rf (`strip_traits`, `strip_and_map_traits`/`strip_and_map_schema`)
and ramses_cc's coordinator already delegates to them — but **nothing in
ramses_rf itself calls them** (not the Gateway, not `ramses_cli`), so the
CLI still rejects `_`-prefixed keys. The CLI wiring is a remaining
ramses_rf-side gap (no open PR covers it). Note also that stage 2 mapping
output (`class`, `bound`, …) is only valid for the **known_list** —
`SCH_GLOBAL_SCHEMAS` (the schema validator) rejects mapped trait names,
so validation stripping must use stage 1 (`strip_traits`) only.

**Phase 3d (DONE — see `phase3d_design.md`):** ramses_cc alignment with
ramses_rf 0.58.3+ (current pin: 0.59.0). Five actionable steps, all complete:
- **3d.8** — remove dead `ImportError` fallback for `strip_traits` /
  `strip_and_map_traits` in coordinator.py (manifest now pins `==0.59.0`,
  functions shipped in 0.58.2; ~40 lines of dead code removed)
- **3d.3** — `strip_traits_for_validation()` in schemas.py delegates
  stage 1 to ramses_rf's `strip_traits` (was inline duplicate)
- **3d.3b** — consolidate drifted stage-3 orchestration between
  `strip_traits_for_validation()` (schemas.py) and
  `_strip_schema_extensions()` (coordinator.py) into one shared
  `_strip_and_orchestrate()` function. Bug fix: coordinator path was
  missing `placed_in_lists` check (device in remotes[] could duplicate
  in orphans_hvac). Unified 3 separate `_HEAT_PREFIXES` definitions.
  Fixed `_DEVICE_ID_RE` to hex regex (was decimal-only).
- **3d.4** — remove `isinstance(bound, str)` guard in
  `_derive_known_list_from_schema`; ramses_rf 0.58.2+ accepts
  `str | list[str]` for `bound`. Sanitizer only strips bound from heat
  devices (HVAC defaults class to HVC).
- **3d.6** — 4 precedence tests: `_commands` override wins over native
  CQRS builder. Test-only, no code change.
- **Phase 3e** (DONE — shipped in ramses_rf 0.59.0): 3e.1 CLI compat
  (`strip_and_map_schema()` called by gateway.py), 3e.2 22B0 calendar
  builder (`build_set_program_enabled` in hvac.py). Neither affects
  ramses_cc, but both are now available.

1103 tests pass, ruff + mypy clean. Net -130 lines.


<a id="2-storageramsescc-ha-store"></a>
### 2. `.storage/ramses_cc` (HA Store)

ramses_rf's learned reality + discovery state + warm restart cache.
Can be cleared without losing user config.

```
┌─────────────────────────────────────────────────────────────┐
│ .storage/ramses_cc                                          │
│                                                             │
│ client_state:                                               │
│   schema:    ← ramses_rf's LEARNED rich schema              │
│     "01:216136": {             Built by gateway.schema()    │
│       system: {                                 from live   │
│         appliance_control: "10:064873"         device       │
│       },                                       registry.    │
│       zones: {                                              │
│         "03": {                                             │
│           _name: "Lounge"     ← learned from 000A/0008      │
│           class: "rad"        ← learned from 0009           │
│           sensor: "01:150003" ← from schema or 000C         │
│           actuators: ["04:150003"] ← from 000C/3150         │
│         },                                                  │
│       },                                                    │
│       stored_hotwater: {                                    │
│         sensor: "07:150000"  ← from schema or 10A0          │
│         dhw_valve: "13:042605"                              │
│         htg_valve: null                                     │
│       },                                                    │
│       underfloor_heating: {                                 │
│         "08:150000": {circuits: {...}}                      │
│       },                                                    │
│       orphans: ["22:012299", "34:058721"]                   │
│     }                                                       │
│     NOTE: HVAC devices appear as orphans_hvac here,         │
│     NOT as "32:...": {remotes: [...], sensors: [...]}.      │
│     This is because load_fan is a stub — see HVAC section.  │
│   packets:  ← cached packet DTOs (for warm restart)         │
│     "2026-07-02T20:47:45.551031": {                         │
│       code: "30C9", verb: "I", src: "04:034692", ...        │
│     }                                                       │
│                                                             │
│ discovery:  ← DISCOVERY SCAN STATE (Path 1 observer)        │
│   devices: ← metadata (ramses_cc layer)                     │
│     "04:056053": {                                          │
│       status: "new"         ← new/accepted/discarded        │
│       enabled: true                                         │
│       owner: null            ← user label                   │
│       accepted_at: null                                     │
│       schema_entry: null    ← auto-generated on accept      │
│     }                                                       │
│   engine:  ← DiscoveredDevice dataclass (ramses_rf layer)   │
│     "04:056053": {                                          │
│       device_id: "04:056053"                                │
│       likely_type: "TRV"    ← from prefix 04:               │
│       zone_idx: "03"        ← from binding codes            │
│       bound_to: "01:145038" ← parent CTL                    │
│       confidence: "high"                                    │
│       rssi: -75                                             │
│       is_battery: true                                      │
│       codes_seen: ["30C9", "12B0", "10E0"]                  │
│       src_count: 42                                         │
│       dst_count: 15                                         │
│       first_seen: "2026-07-02T20:47:45"                     │
│       last_seen: "2026-07-02T20:54:32"                      │
│     }                                                       │
│                                                             │
│ schema_backups: ← incremental backups (last 5)              │
│   [{timestamp, schema, known_list}, ...]                    │
│   (also saved as YAML to <config_dir>/ramses_cc_backups/)    │
│                                                             │
│ remotes:    ← HVAC remote control commands                  │
│   "32:153001": {command_name: "code_payload", ...}          │
│                                                             │
│ WHO WRITES: async_save_client_state (every 5 min + stop)    │
│             async_save_backup (before migration steps:      │
│               SSOT Phase 1, Phase 2, review_discovered)     │
│ WHO READS:  coordinator at startup                          │
│             - schema merged with config via merge_schemas   │
│             - packets restored for warm restart             │
│             - discovery state restored to scan engine       │
│ LIFETIME:   persists across restarts                        │
│ CLEARED BY: clear_cache step in config flow                 │
│             (can clear schema, packets, or discovery)       │
└─────────────────────────────────────────────────────────────┘
```

**Role of cached schema:** Warm restart. Without it, ramses_rf starts
with only the minimal config schema and must relearn all topology
from traffic (could take hours). With it, ramses_rf starts with the
full rich schema and entities are immediately available.

**Role of cached packets:** Warm restart. ramses_rf replays recent
packets to restore device states (temperatures, setpoints, modes)
without waiting for fresh traffic.

**Role of discovery state:** Persist the observer's catalog across
restarts. Without it, every restart starts with 0 discovered devices
and must re-observe traffic to rebuild the catalog.


<a id="3-ramsesdb-sqlite"></a>
### 3. `ramses.db` (SQLite)

Message store — the packet database. Separate from `.storage/ramses_cc`.
Today: used by ramses_extras simulator. Future: full MessageStore
architecture per ramses_rf #530 Phase 2 (write-behind, WAL mode).

```
┌─────────────────────────────────────────────────────────────┐
│ ramses.db (SQLite)                                          │
│                                                             │
│ messages table:                                             │
│   dtm:    "2026-07-02T20:47:45.551031"  (PRIMARY KEY)       │
│   verb:   "I"                            (TEXT(2))          │
│   src:    "04:056053"                    (TEXT(12))         │
│   dst:    "01:150000"                    (TEXT(12))         │
│   code:   "30C9"                          (TEXT(4))          │
│   ctx:    null                           (TEXT, nullable)   │
│   hdr:    "..."                           (TEXT, UNIQUE)     │
│   plk:    "..."                           (TEXT)             │
│   payload_blob: "000682"                 (BLOB)             │
│   frame:  "..."                           (TEXT)             │
│                                                             │
│ WHO WRITES: ramses_rf MessageStore (every packet)           │
│ WHO READS:  ramses_rf for:                                  │
│             - schedule lookups (0006/0404)                  │
│             - fan info extraction (_31D9/_31DA)             │
│             - humidity lookups (_12A0/_31DA)                │
│             - state reconstruction                          │
│             - discovery (get_rp_codes, log_by_dtm)          │
│ LIFETIME:   persists across restarts                        │
│ CLEARED BY: "Remove database file" option in simulator      │
│             or manual rm ramses.db                          │
│ NOTE:       NOT managed by ramses_cc's clear_cache.         │
│             Separate storage, managed by ramses_rf.         │
└─────────────────────────────────────────────────────────────┘
```

**Role:** Long-term packet history. Used for schedules, fan info,
humidity history, and discovery lookups. This is the "database" that
the simulator's "Remove database file" option deletes.

**Difference from cached packets:** The cached packets in
`.storage/ramses_cc` are a small subset (recent DTOs for warm
restart). `ramses.db` is the full historical store (all packets,
queryable by code/device/time).


<a id="4-ramsesrf-gateway-in-memory-not-persisted"></a>
### 4. ramses_rf Gateway (in-memory, not persisted)

```
┌─────────────────────────────────────────────────────────────┐
│ ramses_rf Gateway (RAM only)                                │
│                                                             │
│ device_registry:                                            │
│   device_by_id: {device_id: Device object}                  │
│   systems: [TCS, ...]                                       │
│   - tcs: TemperatureControlSystem                           │
│     - ctl: Controller device                                │
│     - zones: {zone_idx: Zone}                               │
│       - sensor: Device                                      │
│       - actuators: [Device, ...]                            │
│     - dhw: StoredHotWater                                   │
│       - sensor, hotwater_valve, heating_valve               │
│     - ufh: {ufc_id: UfhController}                          │
│                                                             │
│ known_list (working copy):                                  │
│   - starts from config's known_list                         │
│   - augmented by TopologyBuilder (adds discovered devices)  │
│   - used by DeviceFilter to allow/block device creation     │
│   - traits: class, alias, faked                             │
│                                                             │
│ _include (engine):                                          │
│   - list of device IDs derived from known_list keys         │
│   - the actual filter used by enforce_known_list            │
│                                                             │
│ TopologyBuilder:                                            │
│   - 14 rules that learn from traffic                        │
│   - emits TopologyChangedEvent → mutates registry           │
│   - learns zone bindings, class promotions, DHW, UFH        │
│                                                             │
│ MessageStore (SQLite bridge):                               │
│   - writes to ramses.db                                     │
│   - reads for schedule/state lookups                        │
│   - state_cache: latest Message per StateHeader (O(1))      │
│                                                             │
│ TRANSITIONAL SHIM (ramses_rf #530 Phase 2.95 / F5 — MERGED):     │
│   PR 780 rewired gateway.get_state() to return the store's      │
│   state_cache (latest packet per StateHeader) instead of        │
│   scraping the legacy _msgs/_msgs_ot dicts. ramses_cc stays     │
│   ignorant of F5: warm restarts still work via event replay.    │
│   PR 782 (open) adds raw addr1/addr2/addr3 keys back to the     │
│   payload for ramses_cc known_list enforcement.                 │
│   Guardrails implemented by Phil (all 3 predicted here):        │
│     ✅ verb filtering: drops W/RQ, only returns I/RP           │
│     ✅ addr1/2/3 preservation (PR 782, not yet merged)         │
│        — ramses_cc fallback: _get_saved_packets now checks      │
│          src/dst as fallback when addr1/2/3 absent (PR 780)     │
│     ✅ granularity: latest per StateHeader (drops intermediate  │
│        transitions — fine for idempotent entities)              │
│   API contract (Phil's PacketStateDTO):                         │
│     {verb, src, dst, addr1, addr2, addr3, code, payload}       │
│   Long-term: deprecate .storage/ramses_cc JSON for packets      │
│   once ramses_cc reads ramses.db natively. NOTE: remotes        │
│   + discovery_state also live in .storage/ramses_cc             │
│   (coordinator.py:845) and need their own migration path       │
│   before the JSON file can be retired.                          │
│                                                             │
│ WHO WRITES: ramses_rf from schema + traffic                 │
│ WHO READS:  coordinator via client.get_state()              │
│             coordinator via client.schema()                 │
│             coordinator via client.device_registry          │
│ LIFETIME:   in-memory only, rebuilt on every restart        │
│             from config schema + cached schema + packets    │
└─────────────────────────────────────────────────────────────┘
```

**Role of known_list here:** This is the WORKING known_list — it
starts as a copy of the config's known_list (derived from schema +
user overrides), but ramses_rf's DeviceRegistry can add to it
dynamically when the TopologyBuilder discovers new bindings. The
`_include` list (just the keys) is what `enforce_known_list` actually
checks.

**enforce_known_list here:** When True, the DeviceFilter raises
`DeviceNotFoundError` for any device_id not in `_include`. This
prevents rogue entity creation. The DiscoveryScan bypasses this via
`add_raw_pkt_handler` (fires before the filter).


<a id="5-packet-log-files-optional-file-based"></a>
### 5. Packet Log Files (optional, file-based)

```
┌─────────────────────────────────────────────────────────────┐
│ /config/ramses_rf_logs/packet_log.log                       │
│                                                             │
│ Human-readable packet log for debugging/analysis.           │
│ Configured via packet_log options in config entry.          │
│                                                             │
│ WHO WRITES: ramses_rf packet logger                         │
│ WHO READS:  user (for debugging)                            │
│ LIFETIME:   rotates based on retention_days                 │
│ NOTE:       Separate from ramses.db and cached packets.     │
└─────────────────────────────────────────────────────────────┘
```
