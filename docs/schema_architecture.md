<a id="schema-as-source-of-truth-architecture"></a>
# Schema-as-Source-of-Truth Architecture

> **Naming note (updated Jul 19 2026):** There are several "Phase 3"s:
> - **ramses_cc Phase 3** — commands in schema, our work.
>   Split into **3a** (commands on REM, PR 811, DONE), **3b**
>   (commands on FAN with packet templates, DONE, merged), **3c** (flagging,
>   DONE, in master), and **3d** (ramses_rf alignment, DONE —
>   `feature/phase3d-alignment`, merged via PR 839). **3e** (CLI compat +
>   22B0 builder, BLOCKED on ramses_rf).
>   See `phase3b_fan_commands_design.md`.
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
>   mutations. **PR 914** (draft) implements this — tested with
>   ha_sim_test: 232/232 pass (Jul 23 2026).
>
> **Key shift (Jul 17 2026, updated Jul 19):** Device identity Builder
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
- **Phase 3e** (BLOCKED on ramses_rf): 3e.1 CLI compat (was 3d.5),
  3e.2 22B0 calendar builder (was 3d.7). Neither affects ramses_cc.

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


<a id="storage-relationships-diagram"></a>
### Storage Relationships Diagram

```
  ┌──────────────────────────────────────────────────────────┐
  │                    USER EDITS                            │
  │                                                          │
  │  config flow  services  accept/decline/skip              │
  │       │           │           │                          │
  │       v           v           v                          │
  │  ┌─────────────────────────────────┐                     │
  │  │   CONFIG ENTRY OPTIONS          │                     │
  │  │                                 │                     │
  │  │  schema ─────────────┐          │                     │
  │  │  known_list ─────────┤          │                     │
  │  │  packet_log ─────────┤          │                     │
  │  │  enforce_known_list ─┤          │                     │
  │  │  eavesdrop ──────────┘          │                     │
  │  └──────────────┬──────────────────┘                     │
  │                 │                                        │
  │                 │ at startup                             │
  │                 v                                        │
  │  ┌──────────────────────────────────┐                    │
  │  │  .storage/ramses_cc              │                    │
  │  │                                  │                    │
  │  │  cached schema ─────┐            │                    │
  │  │  cached packets ────┤            │                    │
  │  │  discovery state ───┤            │                    │
  │  │  backups ───────────┤            │                    │
  │  │  remotes ───────────┘            │                    │
  │  └──────────────┬───────────────────┘                    │
  │                 │                                        │
  │                 │ merge_schemas(config, cached)          │
  │                 │ + restore packets                      │
  │                 │ + restore discovery                    │
  │                 v                                        │
  │  ┌──────────────────────────────────┐                    │
  │  │  ramses_rf Gateway (RAM)         │                    │
  │  │                                  │                    │
  │  │  merged schema ──────┐           │                    │
  │  │  derived known_list ─┤           │                    │
  │  │  device registry ────┤           │                    │
  │  │  TopologyBuilder ────┤           │                    │
  │  │  MessageStore ───────┤           │                    │
  │  │                      │           │                    │
  │  │                      v           │                    │
  │  │  ┌────────────────────────┐      │                    │
  │  │  │  ramses.db (SQLite)    │      │                    │
  │  │  │  full packet history   │      │                    │
  │  │  └────────────────────────┘      │                    │
  │  └──────────────┬───────────────────┘                    │
  │                 │                                        │
  │                 │ every 5 min + on shutdown              │
  │                 │ client.get_state()                     │
  │                 │ → schema, packets                      │
  │                 │ (post-F5: reads MessageStore.state_    │
  │                 │  cache via the transitional shim —     │
  │                 │  see MessageStore bridge block above)  │
  │                 v                                        │
  │  ┌──────────────────────────────────┐                    │
  │  │  .storage/ramses_cc              │                    │
  │  │  (updated with learned reality)  │                    │
  │  └──────────────────────────────────┘                    │
  │                                                          │
  │  SEPARATE (not in this loop):                            │
  │  ┌──────────────────────────────────┐                    │
  │  │  packet_log files                │                    │
  │  │  /config/ramses_rf_logs/*.log    │                    │
  │  └──────────────────────────────────┘                    │
  └──────────────────────────────────────────────────────────┘
```


<a id="the-role-of-knownlist-in-each-storage"></a>
### The Role of known_list in Each Storage

```
  STORAGE              known_list ROLE TODAY         ENDGOAL
  ─────────────────────────────────────────────────────────────────
  config entry         trait overrides:              REMOVED — traits
                       class, alias, faked,          move to schema as
                       scheme, bound                 _ keys (_class,
                                                     _alias, _faked,
                                                     _scheme, _bound)
                                                     known_list derived
                                                     from schema only

  .storage/ramses_cc   NOT stored here               N/A
                       (discovery state is here,
                        but that's different)

  ramses_rf gateway    working copy:                 IN-MEMORY ONLY —
                       starts from config's           derived from
                       known_list, augmented          schema at startup
                       by TopologyBuilder             by coordinator,
                                                     not passed as
                                                     config

  ramses_rf engine     _include list (keys only):    IN-MEMORY ONLY —
  DeviceFilter         the actual filter list         derived from
                                                     schema keys
```

**Endgoal: known_list is fully derived, not stored in config.**

The *device list* role is already replaced by the schema (we derive
it). The *trait override* role will also move to the schema:

```
TODAY:                          ENDGOAL:
──────────────────────────────  ──────────────────────────────
config entry:                   config entry:
  schema: {topology}              schema: {
  known_list: {                     "01:150003": {
    "01:150003":                      _class: "SEN",     ← in schema
      class: "SEN",                   _alias: "Lounge",  ← in schema
      alias: "Lounge",                _faked: false,     ← in schema
      faked: false                    sensor_of: "01:216136"  ← topology
    }                               },
  }                                 "30:160000": {
                                      _scheme: "itho",   ← in schema
                                      remotes: [...]
                                    }
                                  }
                                known_list: (REMOVED from config)
                                  → derived in-memory by
                                    _derive_known_list_from_schema()
                                    reading the _ keys
```

**What needs to change for this endgoal:**

1. ramses_rf schema validators must accept `_` prefixed keys
   (today: `PREVENT_EXTRA` rejects them)
   - `_class`, `_alias`, `_faked`, `_scheme`, `_bound`
   - This is the v2 migration step
   - NOTE: ramses_cc already works around this by stripping `_` keys
     before passing to ramses_rf (IMPLEMENTED in PR 764). The traits
     `_disabled`, `_name`, `_alias`, `_class`, `_comment` are already
     stored in the schema and stripped before ramses_rf sees them.
   - **Phase 3a plan:** move strip+map to ramses_rf as a pipeline
     (stages 1+2 in ramses_rf, stage 3 in ramses_cc). See
     `phase3b_fan_commands_design.md` "CLI testing" section.
     **Update (Jul 18 2026):** stages 1+2 shipped in ramses_rf 0.58.2+
     and ramses_cc delegates to them, but the CLI is NOT fixed yet —
     ramses_rf never calls the pipeline itself (`ramses_cli -monitor`
     still rejects `_commands`/`_bound` via `PREVENT_EXTRA`). CLI
     wiring is a remaining ramses_rf-side gap.
   - ~~**Also needed:** `SCH_TRAITS_HVAC` `bound` must accept
     `str | list[str]` (multi-REM binding).~~ DONE in 0.58.2 — but
     ramses_cc's `_derive_known_list_from_schema` still drops
     list-valued `bound` (Phase 3d code change).

2. ramses_cc `_derive_known_list_from_schema` reads `_` keys
   from schema and produces the known_list dict that ramses_rf
   expects (with `class`, `alias`, `faked`, `scheme`, `bound`)
   - This is already implemented (reads from schema, falls back
     to user known_list for backward compat)

3. Config entry no longer stores `known_list` — only `schema`
   - Migration: move existing known_list traits into schema as
     `_` keys, then remove known_list from config entry
   - This is the v4 migration step

4. `enforce_known_list` becomes always-on (option removed)
   - The filter checks against schema-derived device IDs
   - No separate known_list needed for filtering

**Why this is possible now (and wasn't before):**

The trait analysis below shows that ALL current known_list traits
can be expressed in the schema:
- `class` → `_class` (override for edge cases like 01: sensors)
- `alias` → `_alias` (friendly name, like zone `_name` today)
- `faked` → `_faked` (fake sensor mode flag)
- `scheme` → `_scheme` (HVAC vendor, already proposed for #87)
- `bound` → `_bound` (FAN binding for faked REMs)
- `commands` → `_commands` (remote control payloads)

The only blocker for **native ramses_rf support** is the `PREVENT_EXTRA`
validator. Once that's relaxed to allow `_` prefixed keys (a targeted
change, not a full schema rewrite), all traits can live in the schema
without the ramses_cc stripping workaround.

**Current status:** ramses_cc already stores `_`-prefixed traits in the
schema and strips them before passing to ramses_rf (PR 764). All
planned traits are now IMPLEMENTED: `_disabled`, `_name`, `_alias`,
`_class`, `_comment`, `_owner`, `_faked`, `_bound`, `_scheme`,
`_skipped`.

**enforce_known_list future:**

When passive scan is enabled, ramses_cc already forces
`enforce_known_list=True` (see coordinator.py, `_create_client`).
In the
endgoal, `enforce_known_list` becomes always-on and the option is
removed:

```
TODAY:                              ENDGOAL:
────────────────────────────────    ────────────────────────────────
enforce_known_list: True/False      enforce_known_list: (removed)
  (user option)                       → always-on internally

filter checks:                      filter checks:
  dev_id in _include?                 dev_id in schema_keys?
  (_include = known_list keys)        (derived from schema)

known_list in config:               known_list in config:
  YES (user edits traits)             NO (removed)

known_list in memory:               known_list in memory:
  YES (merged from config +           YES (derived from schema
       derived from schema)              by _derive_known_list)

eavesdrop: True/False               eavesdrop: (removed)
  (user option)                       → obsolete, see below
```

**eavesdrop becomes obsolete:**

`enable_eavesdrop` is a ramses_rf option that enables heuristic class
promotion and zone sensor discovery from traffic patterns. It lets
ramses_rf "guess" device classes and zone assignments by watching
broadcasts (e.g., promote a TRV to THM, detect a DHW sensor from
10A0 broadcasts, learn appliance_control from relay sync packets).

In the endgoal, eavesdrop is no longer needed because:

```
WHAT EAVESDROP DOES TODAY          → ENDGOAL REPLACEMENT
─────────────────────────────────── ───────────────────────────────
promote device class from traffic  → _class in schema (user or
  (TRV → THM, etc.)                  cache→config sync sets it)

discover zone sensors from          → TopologyBuilder learns zone
  broadcasts (10A0, 30C9)             sensors for known devices,
  (only if device in known_list)      persisted to schema via cache

discover DHW sensor from            → same: TopologyBuilder learns
  10A0 broadcasts                     it, persisted to schema

discover appliance_control          → same: TopologyBuilder learns
  from relay sync                     it, persisted to schema

fingerprint HVAC device class       → _scheme in schema (user sets
  from message patterns               it, or 10E0 parser suggests)
```

The key difference: eavesdrop is a **ramses_rf-internal heuristic**
that mutates in-memory state (not persisted, lost on restart). The
endgoal replaces it with:
1. **TopologyBuilder** — learns topology for known devices, persisted
   via cache→config sync (survives restart)
2. **Schema traits** — `_class`, `_scheme` set explicitly by user or
   by cache→config sync (survives restart)
3. **DiscoveryScan** — catalogs unknown devices without needing
   eavesdrop (Path 1 observer)

ramses_rf's TopologyBuilder already does most of what eavesdrop does
(via its 14 rules), and it does it for known devices regardless of
the eavesdrop flag. The eavesdrop-only rules (class promotion, zone
type guessing) become unnecessary when classes are in the schema.

**Why eavesdrop is problematic today:**
- ramses_rf warns "there be dragons here" when enabled
- Heuristic class promotion can be wrong (e.g., promote a TRV that's
  actually a sensor)
- Results are in-memory only — lost on restart, must re-learn
- Conflicts with `enforce_known_list` (eavesdrop creates devices that
  the filter would otherwise block)

**Prerequisite for always-on enforce_known_list:** ramses_cc issue 677
(discovery failures; users disabled `enforce_known_list` as workaround)
is now closed — fixed in 0.57.6. Before making it always-on, verify the
fix holds on real Evohome systems. See "Alignment with ramses_rf
Roadmap" section for details.

[top](#schema-as-source-of-truth-architecture)
<a id="trait-analysis-what-can-move-to-schema"></a>
## Trait Analysis — What Can Move to Schema

<a id="current-traits-in-ramsesrfs-devicetraits"></a>
### Current traits in ramses_rf's DeviceTraits

From `ramses_rf/models/state_base.py`:

```python
class DeviceTraits:
    device_class: str | None = None    # class (CTL, TRV, DHW, FAN, ...)
    alias: str | None = None           # friendly name
    faked: bool | None = None          # fake sensor mode
    scheme: str | None = None          # HVAC vendor scheme (itho, nuaire, ...)
```

Plus from `ramses_rf/config.py` SCH_TRAITS:
- `_domain`: "heat" or "hvac" (auto-detected, not user-set)
- `bound`: parent device ID (HVAC only — REM → FAN binding, config key
  is `"bound"`, constant `SZ_BOUND_TO`)

And separately:
- `block_list`: dict of blocked device IDs (like known_list but deny-list)
- `commands`: remote control command payloads (stored in `_remotes`)

<a id="trait-by-trait-analysis"></a>
### Trait-by-trait analysis

**IMPLEMENTED in PR 764** (stored as `_`-prefixed keys in schema,
stripped by `_strip_schema_extensions` before ramses_rf sees them,
extracted into known_list by `_derive_known_list_from_schema`):
- `_disabled` (bool): exclude from entity creation (stays in known_list
  to avoid DeviceNotFoundError log spam, entities suppressed in
  `_discover_new_entities`)
- `_name` (str): human-friendly display name (maps to `alias` in
  known_list)
- `_alias` (str): alternate name (e.g. for entities, maps to `alias`)
- `_class` (str): override device class (CTL, TRV, DHW, ...)
- `_comment` (str): free-form per-device comment (display only)
- `_owner` (str): owner name — devices matching root `_owner` are
  "ours" (known_list), others are "foreign" (block_list)
- `_faked` (bool): create a virtual/fake device (no RF traffic needed)
- `_bound` (str | list[str]): for FAN, the bound REM/DIS device ID(s)
  for 2411 command routing. Phase 3a: accepts list (multi-REM binding).
  ramses_rf's `HvacVentilator._bound_devices` is already a dict and
  `add_bound_device()` can be called multiple times — the limitation
  was only in `SCH_TRAITS_HVAC` (single string) and `fan_handler`
  (one call, `isinstance(str)` check).
- `_scheme` (str): FAN manufacturer scheme (orcon/itho/vasco/nuaire)
  for 22F1 fan mode commands

**PROPOSED** (not yet implemented):
- None currently — all planned traits are implemented (see trait table below)

```
TRAIT        | WHERE NOW           | CAN MOVE TO SCHEMA? | HOW
-------------|---------------------|---------------------|------------------
class        | known_list          | YES — already is    | CTL: main_tcs key
             |                     | for topology keys   | TRV: zone.sensor
             |                     | (schema IS the      | DHW: stored_hotwater.sensor
             |                     | class declaration)  | FAN: top-level 30: key
             |                     |                     | REM: fan.remotes[]
             |                     | Override for edge   | "01:150003":
             |                     | cases (01: that's   |   {_class: "SEN"}
             |                     | sensor, not CTL)    |
             |                     |                     |
alias        | known_list          | YES — _name already | Zone: zones.03._name
             |                     | exists for zones    | Device: "01:150003":
             |                     |                     |   {_alias: "Lounge sensor"}
             |                     | SSOT: alias =       | ramses_rf needs to accept
             |                     | _name when same     | _alias key natively
             |                     | device              | (ramses_cc strips it for now)
             |                     |                     |
faked        | known_list          | YES — implemented   | "01:150003":
             |                     | in PR 764           |   {_faked: true}
             |                     |                     | Extracted to known_list as
             |                     |                     | faked=True; ramses_rf creates
             |                     |                     | the fake device via
             |                     |                     | load_schema() loop
             |                     |                     |
scheme       | known_list (HVAC    | YES — implemented   | "30:160000":
             | only)               | in PR 764           |   {_scheme: "itho",
             |                     |                     |    remotes: [...]}
             |                     |                     | Extracted to known_list as
             |                     |                     | scheme="itho" for 22F1 cmds
             |                     |                     |
bound        | known_list (FAN     | YES — implemented   | "32:153289": {
             | only, for faked     | in PR 764           |   _bound: ["37:168270", "32:153001"],
             | REMs sending 2411)  | Phase 3a: list[str] |   remotes: [...]
             |                     |                     | }
             | remotes[] (topology)| NOT same as         | Extracted to known_list as
             |                     | _bound = which REM  | bound=["37:168270", "32:153001"]
             |                     | can send 2411 params| fan_handler.py loops over list
             |                     | to FAN              | (Phase 3a: was single string,
             |                     |                     | isinstance(str) check removed)
             |                     |                     |
_domain      | auto-detected       | NO — internal       | Stays internal to ramses_rf
             | (not user-set)      |                     |
             |                     |                     |
commands     | _remotes in         | YES — Phase 3a DONE | Phase 3a (PR 811): on REM entry
             | .storage/ramses_cc  | (PR 811, on REM)    | "32:153001": {
             | + known_list        | Phase 3b: on FAN    |   _commands: {
             |                     | (design)            |     "turn_on": "I --- 32:153001 ...",
             |                     |                     |     "speed_1": "I --- 32:153001 ..."
             |                     |                     |   }
             |                     |                     | }
             |                     |                     | Phase 3b: moves to FAN entry as
             |                     |                     |   {verb, code, payload} dicts
             |                     |                     |   (see phase3b_fan_commands_design.md)
             |                     |                     | ramses_rf doesn't need _commands
             |                     |                     | today — stripped by pipeline
```

<a id="what-ramsesrf-already-puts-in-the-schema-learned-from-traffic"></a>
### What ramses_rf already puts in the schema (learned from traffic)

```
SCHEMA KEY          | LEARNED FROM          | TRAIT EQUIVALENT
--------------------|-----------------------|------------------
_name (zones)       | 000A/0008 (zone name) | alias for zone
class (zones)       | 0009 (zone type)      | class for zone
sensor (zones)      | 000C/30C9 (binding)   | which device is sensor
actuators (zones)   | 000C/3150 (binding)   | which devices are actuators
appliance_control   | 1FC9 (OTB detection)  | class = OTB
sensor (DHW)        | 10A0 (DHW binding)    | class = DHW
dhw_valve (DHW)     | 000C (binding)        | class = BDR
htg_valve (DHW)     | 000C (binding)        | class = BDR
orphans (TCS)       | unbound devices       | class = orphan
remotes (HVAC)       | 22F1 (class promo)    | class = REM (NOT bound to FAN)
sensors (HVAC)       | 1298 (class promo)    | class = CO2 (NOT bound to FAN)
```

**IMPORTANT — HVAC topology is NOT learned by TopologyBuilder.**
The table above shows class promotion only (via verb+code pairs in
`HVAC_KLASS_BY_VC_PAIR`). TopologyBuilder has NO binding rules for
HVAC — it does not link REM/CO2 to FAN. The `bound = FAN` in the
previous version of this table was WRONG. See "HVAC Schema"
section below for details.

So ramses_rf learns most HEAT topology from traffic and puts it in
the schema. The traits that CAN'T be learned from traffic are:
- `alias` for devices (only zones get _name from traffic)
- `faked` (user choice, not detectable)
- `scheme` for HVAC (vendor-specific, sometimes detectable from 22F1
  but not always)
- `class` override (when auto-detection is wrong)

<a id="proposed-extended-schema-with-traits"></a>
### Extended schema with traits

**IMPLEMENTED traits** (`_disabled`, `_name`, `_alias`, `_class`,
`_comment`, `_owner`, `_faked`, `_bound`, `_scheme`, `_skipped`) are
stored in the schema and stripped before ramses_rf sees them. All
planned traits are now implemented (PR 764).

```
CURRENT schema (ramses_rf SCH_TCS):
  "01:150000": {
    zones: {
      "03": {
        _name: "Lounge",          ← already accepted
        class: "rad",             ← already accepted
        sensor: "01:150003",      ← already accepted
        actuators: ["04:150003"]  ← already accepted
      }
    },
    stored_hotwater: {
      sensor: "07:150000"         ← already accepted
    }
  }

IMPLEMENTED extended schema (PR 764, _ keys stripped before ramses_rf):
  "01:150000": {
    _alias: "My Controller",      ← IMPL: device alias
    _comment: "Main controller",  ← IMPL: free-form comment
    zones: {
      "03": {
        _name: "Lounge",
        class: "rad",
        sensor: "01:150003",
        actuators: ["04:150003"]
      }
    },
    stored_hotwater: {
      sensor: "07:150000"
    }
  }

  "04:034692": {
    _disabled: true,              ← IMPL: excluded from known_list
    _comment: "Broken TRV"        ← IMPL: free-form comment
  }

  "01:150003": {                  ← IMPL: device-level traits
    _alias: "Lounge sensor",      ←   alias override
    _class: "SEN",                ←   class override (01: that's sensor)
    _name: "Lounge sensor"        ←   display name
  }

ALSO IMPLEMENTED (PR 764, same _ key pattern):
  "01:150000": {
    _faked: false,                ← IMPL: faked flag (was known_list)
  }

  "30:160000": {
    _scheme: "itho",              ← IMPL: HVAC scheme (was known_list)
    remotes: ["32:150001"],       ← NOTE: ramses_rf accepts this in
    sensors: []                   ← SCH_VCS_DATA but load_fan is a
  }                               ←   STUB — doesn't process it yet

  "32:153289": {
    _bound: "37:168270",          ← IMPL: which faked REM can send 2411
  }
```

**Stale devices:** A device is marked `_stale` when `_last_seen` is
older than a configurable threshold. Stale devices are **not** auto-
removed from the schema (RF issues are often temporary and the device
reappears). Instead user can delete the device via the `remove_device` service
(see "DEVICE REMOVAL" below).

**HVAC schema caveat:** The `remotes` and `sensors` keys in a HVAC
schema entry are accepted by ramses_rf's validator (`SCH_VCS_DATA`)
and ramses_cc generates them correctly (see `generate_schema_entry`
in discovery.py). However, `load_fan` in ramses_rf is currently a
stub — it creates the FAN device but does NOT process the
remotes/sensors lists. See "HVAC Schema" section below.

**Key design choice:** trait keys are prefixed with `_` (like `_name`)
to distinguish them from topology keys. ramses_rf's schema validator
would need to accept these as `vol.Optional` keys in:
- `SCH_TCS_ZONES_ZON` (zone-level traits)
- `SCH_TCS` (TCS-level traits)
- `SCH_VCS_DATA` (HVAC-level traits)
- A new `SCH_DEVICE_TRAITS` for orphan/device-level traits

<a id="what-stays-outside-the-schema"></a>
### What stays outside the schema

See "Summary: what goes where" section below for the comprehensive
overview of what's in schema, what moves to schema, what becomes
obsolete, and what stays in config/storage/ramses.db.


<a id="why-eavesdrop-blocklist-disableddevices-become-obsolete"></a>
### Why eavesdrop, block_list, disabled_devices become obsolete

**eavesdrop:** See detailed explanation in "enforce_known_list future"
section above. Short version: TopologyBuilder already does most of
what eavesdrop does; the eavesdrop-only rules (class promotion, zone
type guessing) become unnecessary when classes are in the schema.
→ eavesdrop becomes always-on, then flag removed.

**block_list:**
Today block_list is a deny-list of device IDs that ramses_rf refuses
to create. It's the inverse of known_list. In ramses_cc, it's not
even configurable via config flow — it's only exposed as a diagnostic
attribute on a binary sensor.

With schema as SSOT: if a device is not in the schema, it's not
created (enforce_known_list always-on). If a user wants to block a
device, they simply don't add it to the schema (or remove it).
block_list becomes redundant — the schema IS the allow-list, and
"not in schema" = "blocked."

So: block_list → removed, replaced by "not in schema."

**disabled_devices → _disabled trait (IMPLEMENTED):**
Today `_disabled` is a ramses_cc per-device trait in the schema
(see "_disabled trait — implementation details" section below).
With schema as SSOT + traits in schema: a device can be in the schema
but marked as disabled via the `_disabled: true` trait. This replaces
the old top-level `disabled_devices` list.

So: `disabled_devices` list → replaced by `_disabled: true` per-device
trait in schema (IMPLEMENTED in PR 764).


<a id="the-bound-trait-fan-specific-for-faked-rems"></a>
### The `bound` trait — FAN-specific, for faked REMs

The `bound` trait is FAN-specific. It tells a FAN which faked REM
can send 2411 parameter messages to it. A FAN only responds to 2411
Set messages from a bound REM.

```
Current known_list:
  "32:153289":
    bound: "37:168270"     ← this REM can send 2411 to this FAN
    class: FAN
  "37:168270":
    class: REM
    faked: true

Could be in schema:
  "32:153289": {
    _bound: "37:168270",   ← bound REM for 2411 params
    remotes: ["37:168270", "32:153001"],
    sensors: []
  }
  "37:168270": {
    _class: "REM",
    _faked: true
  }
```

Note: `bound` is different from `remotes[]`. `remotes[]` is the
topology list of REMs associated with a HVAC. `bound` is specifically
the faked REM authorized to send 2411 parameter messages. A FAN
can have multiple remotes but only one bound device for 2411.

The `bound_to` in DiscoveryScan is different — it's the observed
parent device (CTL for TRV, FAN for REM) from traffic analysis.
That's discovery metadata, not a trait.

**Four different "binding" concepts — don't confuse them:**
1. **`bound` trait** (known_list/schema) — which faked REM can send
   2411 params to a FAN (authorization for parameter updates)
2. **`bound_to` in DiscoveryScan** — observed parent device from
   traffic (discovery metadata, not persistent)
3. **`bind_device` service** — RF binding handshake using 1FC9 packets
   (offer/accept/confirm/ratify) that pairs a device with a controller
   at the RF protocol level (one-time action, see below)
4. **000C zone binding** (heat only) — CTL broadcasts the zone map,
   TopologyBuilder links sensors/actuators to zones. NO HVAC equivalent
   exists yet (see "HVAC Schema" section)


<a id="the-binddevice-service-rf-binding-handshake"></a>
### The `bind_device` service — RF binding handshake

The `bind_device` service is unrelated to the `bound` trait. It
performs the actual RF binding protocol — a 4-phase handshake
defined in `ramses_rf/binding_fsm.py`. This uses **1FC9** packets
(not 000C, which is heat-only zone binding):

```
  SUPPLICANT (device being bound)    RESPONDENT (CTL/FAN)
  ─────────────────────────────────  ──────────────────────

  Phase 1: TENDER (Offer)
  ────────────────────────────────────────────────────────
  Supp → Resp:  Offer (I, code, payload)
                "I want to bind for these command codes"
                ← waits for Accept

  Phase 2: ACCEPT
  ────────────────────────────────────────────────────────
                Resp → Supp:  Accept (I, code, payload)
                             "I accept your offer"
                ← waits for Confirm

  Phase 3: AFFIRM (Confirm)
  ────────────────────────────────────────────────────────
  Supp → Resp:  Confirm (I, code, payload)
                "I confirm the binding"
                ← auto-bound after CONFIRM_TIMEOUT_SECS (3s)
                  or waits for Ratify

  Phase 4: RATIFY (Addenda, optional)
  ────────────────────────────────────────────────────────
                Resp → Supp:  10E0 (device info)
                             "Here's my OEM code / device info"
                ← binding complete

  Result: both sides are Bound (RespHasBoundAsRespondent /
          SuppHasBoundAsSupplicant)
```

**Roles:**
- **Supplicant**: the device being bound (e.g., a faked REM, sensor)
  — must have `faked: true` in known_list
- **Respondent**: the controller or FAN that accepts the binding

**Service parameters:**
- `device_id`: the supplicant (must be faked)
- `offer`: dict of `{command_code: domain_idx}` pairs to bind
- `confirm`: dict with the confirm code (optional, FFFF = auto)
- `device_info`: 10E0 payload for ratify phase (needed if offer
  includes 10E0)

**This is a one-time RF-level operation, not a persistent trait.**
After binding, the binding is permanent at the RF level — the
devices remember each other. The `bind_device` service stays as a
service — it's an action, not a trait.

**Relationship to schema/known_list:**
- The supplicant must be in known_list with `faked: true` (so
  ramses_rf can send packets on its behalf)
- After binding, the device appears in traffic and is discovered
  by DiscoveryScan (if not already in schema)
- The user accepts it → goes into schema
- The `bound` trait (for FAN/REM 2411 params) is separate — it's
  about which REM can send parameter updates, not about the RF
  binding handshake


<a id="disableddevices-implementation-details"></a>
### _disabled trait — implementation details

The `_disabled` trait is a ramses_cc per-device trait in the schema,
introduced in PR 764. It replaces the old top-level `disabled_devices`
list. It is a per-device `_`-prefixed key:

```
schema: {
  "01:216136": {},
  "04:034692": {_disabled: true},
  "04:036068": {_disabled: true}
}
```

It's used in three places:
1. `_derive_known_list_from_schema` — excludes `_disabled` devices from
   the derived known_list (so ramses_rf doesn't create them)
2. `_strip_schema_extensions` — removes `_disabled` devices from
   `orphans_heat` and `orphans_hvac` lists before passing to ramses_rf
   (which doesn't understand `_` keys), and strips all `_`-prefixed keys
   from the schema dict recursively
3. `config_flow.py` review step — when user declines a device, it's
   marked with `_disabled: true` instead of being silently dropped

It lives in the config entry, NOT in .storage cache — so it survives
cache loss (by design). The `_` prefix ensures it is stripped before
ramses_rf sees the schema (ramses_rf's validators use `PREVENT_EXTRA`).

**Related traits implemented in PR 764:**
- `_disabled` (bool): exclude from known_list / device creation
- `_name` (str): human-friendly display name
- `_alias` (str): alternate name (e.g. for entities)
- `_class` (str): override device class (CTL, TRV, DHW, ...)
- `_comment` (str): free-form per-device comment

All are stripped by `_strip_schema_extensions` before passing to ramses_rf.
`_name`, `_alias`, and `_class` are also propagated into the derived
known_list entries by `_derive_known_list_from_schema`.

**Future:** `_faked`, `_scheme`, `_bound` traits will follow the same
pattern once implemented.


<a id="knownlist-future-view-only-in-memory-derived"></a>
### known_list future: view-only, in-memory, derived

The endgoal for known_list is described in "The Role of known_list
in Each Storage" section above. In short: it becomes a **derived
view** — computed from the schema at startup, not user-editable.

**Where it resides:**

| Stage | Location | Lifetime | Editable? |
|-------|----------|----------|-----------|
| Source | schema in config entry options | permanent | YES (user) |
| Derivation | `_derive_known_list_from_schema()` | on startup/change | NO (computed) |
| Working copy | ramses_rf `GatewayConfig.known_list` | in-memory | NO (auto) |
| Debug | log output | ephemeral | NO (view only) |

**Rebuilt when:**
- HA restart (from schema)
- Config entry reload (from schema)
- Schema change via service/config flow (re-derive + reload)
- TopologyBuilder adds device (augments working copy in-memory only)

**Why view-only is safe:** There's nothing the user needs to add to
known_list that can't be expressed in the schema. Making it view-only
prevents the confusion of having two places to edit the same thing.


<a id="commands-can-move-to-schema-too"></a>
### commands — can move to schema too

Yes, commands can eventually move to the schema as well. They're
per-device data, just like traits:

```
CURRENT:
  .storage/ramses_cc:
    remotes: {
      "32:153001": {
        "turn_on": "22F100...",
        "turn_off": "22F100...",
        "speed_1": "22F101..."
      }
    }

  known_list (config entry, optional):
    "32:153001": {
      commands: {...}    ← some commands stored here too?
    }

FUTURE (in schema):
  schema:
    "32:153001": {
      _commands: {              ← per-device command payloads
        "turn_on": "22F100...",
        "turn_off": "22F100...",
        "speed_1": "22F101..."
      },
      _class: "REM",
      _faked: true
    }

  derived known_list (if ramses_rf still needs it):
    "32:153001": {
      class: "REM",
      faked: true,
      commands: {...}    ← extracted from _commands in schema
    }
```

**Why it can move:** Commands are per-device data, just like alias
and faked. They're stored in `.storage/ramses_cc` today because
ramses_rf's schema validator doesn't accept a `commands` key. The
`_` prefix convention + strip+map pipeline (Phase 3a) means ramses_rf
never sees `_commands` — it's stripped before validation.

**Why "for now" stays in known_list/remotes:** Commands are edited
via the HA UI (learn command flow) and need to be persistent + editable.
Moving them to the schema means the schema editor needs to support
command editing, or a service writes them to the schema. That's a
UI/UX change, not just a schema change.

**Migration path:**
1. ~~Now: commands in `.storage/ramses_cc[remotes]` + known_list~~
2. ~~Next: commands in schema as `_commands` key (ramses_rf accepts it)~~
   **DONE (Phase 3a, PR 811):** `_commands` on REM entries in schema,
   full packet strings. Services write to schema. Migration from
   `.storage[remotes]` + `known_list[commands]` implemented.
3. **Phase 3b (DONE, merged):** `_commands` moves from REM entries to FAN
   entries. Format changes from full packet strings to
   `{verb, code, payload}` dicts. `_bound` accepts `list[str]`.
   See `phase3b_fan_commands_design.md`.
4. ramses_rf 0.58.3 CQRS builders (issue 639, shipped Jul 17 2026) —
   ramses_rf manages its own command generation for standard codes
   (22F1 fan mode, 22F7 bypass, 2411 fan param, 31DA fan info, etc.).
   These become the **defaults**. `_commands` in the schema stays as the
   **authoritative user override**.
   **Note:** 22B0 (calendar) builder not yet implemented. Per-manufacturer
   strategy profiles not yet implemented. The Builder/Strategy pattern
   (issue 530) was scrapped in favor of "init and go" from schema
   (Jul 17 2026). ramses_cc Phase 3d = align with 0.58.3+ (current pin 0.59.0).

   **However:** even with CQRS TX builders,
   the schema must still be able to **overrule** them. A user may need
   to override a learned/automatic command with a custom one (e.g.,
   a non-standard remote, a modified payload, a device that sends
   unexpected codes). So `_commands` in the schema stays as an
   override mechanism:

   ```
   ramses_rf CQRS TX builders  → default commands (learned/auto)
   schema _commands            → user override (wins over native)
   ```

   This follows the same precedence pattern as other traits:
   ramses_rf learns/detects → schema overrides if present.

<a id="migration-path"></a>
### Migration path

```
PHASE 1 (DONE):
  schema = topology only (zones, sensors, actuators, DHW, remotes)
  known_list = {device_id: {class, alias, faked, scheme, bound}}
  _derive_known_list_from_schema → {device_id: {}} + user overrides

PHASE 1.5 (DONE — PR 764, ramses_cc workaround):
  schema = topology + _ traits (stripped before ramses_rf sees them)
  "01:150003": {_alias: "Lounge sensor", _class: "SEN", _disabled: false}
  _disabled, _skipped, _name, _alias, _class, _comment IMPLEMENTED
  _strip_schema_extensions strips _ keys before passing to ramses_rf
  _derive_known_list_from_schema → reads _alias, _class, _name
    from schema entries, excludes _disabled and _skipped devices
  cache→config sync IMPLEMENTED (sync_learned_topology)
  _skip_topology_sync on unload prevents stale topology overwriting fresh schema
  un-disabled/un-skipped devices auto-added to orphans
  _get_saved_packets: src/dst fallback for ramses_rf PR 780 (addr1/2/3 in PR 782)
  known_list still in config entry for faked/scheme/bound overrides

PHASE 2 (ramses_rf PR — strip+map pipeline moves to ramses_rf):
  schema = topology + traits (stages 1+2 in ramses_rf, stage 3 in ramses_cc)
  "01:150003": {_alias: "Lounge sensor", _class: "SEN"}
  _strip_schema_extensions = thin wrapper calling ramses_rf pipeline + stage 3
  SCH_TRAITS_HVAC bound accepts str | list[str]
  known_list = only for backward compat / overrides not yet in schema
  _derive_known_list_from_schema → reads _alias, _class, _faked, _scheme
    from schema entries (mapping done by ramses_rf pipeline)

PHASE 3a (ramses_cc — commands in schema on REM, DONE PR 811):
  _commands on REM entries, full packet strings
  _faked, _scheme, _bound traits implemented (same _ key pattern)
  accept_discovered_device → writes _alias, _class to schema
  config flow → user edits traits in schema editor
  known_list deprecated for most users

PHASE 3b (ramses_cc — commands move to FAN, design stage):
  _commands moves from REM entries to FAN entries
  format: {verb, code, payload} dicts (not full packet strings)
  _bound accepts list[str] (multi-REM)
  fan_handler loops over bound REMs
  climate.set_fan_mode reads from schema _commands on FAN
  See phase3b_fan_commands_design.md
  Does NOT depend on ramses_rf Phase 3/3.25

PHASE 4 (ramses_rf Phase 3/3.25 — DONE, shipped 0.58.3):
  CQRS CommandDispatcher + domain builders for zones/DHW/HVAC/heat/
  schedules/faultlog/opentherm
  TX builders: 22F1, 22F7, 2411, 31DA, 1298, 12A0 (defaults)
  NOT yet: 22B0 (calendar), per-manufacturer strategy profiles
  schema _commands stays as OVERRIDE (user wins over native)
  strip_and_map_traits() pipeline in ramses_rf (functions only —
    NOT called by Gateway/CLI yet, so CLI does NOT benefit yet)
  SCH_TRAITS_HVAC accepts str | list[str] for bindings
  known_list fully removed (or only for legacy compat)
  NOTE: ramses_rf 0.58.3 shipped Jul 17 2026. Builder/Strategy
  pattern scrapped (Jul 17 2026) — no supported_commands() on strategies.
  ramses_cc Phase 3d = align with this (pin now 0.59.0; consolidate
  local stage-1/stage-3 stripping — validation must use strip_traits(),
  NOT strip_and_map_schema(), since SCH_GLOBAL_SCHEMAS rejects mapped
  trait names; pass _bound lists through to known_list).

PHASE 3d (ramses_cc — DONE, see phase3d_design.md):
  Align ramses_cc with ramses_rf 0.58.3. No new features — consolidation
  and cleanup only. All 5 steps complete:
  3d.8: remove ImportError fallback (dead code, manifest now pins 0.59.0)
  3d.3: strip_traits_for_validation delegates stage 1 to ramses_rf
  3d.3b: consolidate stage-3 orchestration (orphan routing, disabled/
         skipped/foreign filtering, HGI dropping) into one shared
         function — was duplicated & drifted between schemas.py
         and coordinator.py. Unify _HEAT_PREFIXES (3 definitions → 1).
         Fix placed_in_lists bug in coordinator path.
  3d.4: pass _bound as str | list[str] to ramses_rf (remove str-only
         guard in _derive_known_list_from_schema)
  3d.6: precedence tests — _commands override wins over CQRS builder
  Phase 3e (BLOCKED on ramses_rf): 3e.1 CLI compat (was 3d.5),
  3e.2 22B0 calendar builder (was 3d.7). Neither affects ramses_cc.
```

<a id="summary-what-goes-where"></a>
### Summary: what goes where

```
TOPOLOGY (in schema, learned + user-set):
  ✅ already (heat): main_tcs, zones, sensor, actuators,
              stored_hotwater, underfloor_heating, orphans
  ✅ already (heat): _name (zones), class (zones), appliance_control
  ⚠️ partial (HVAC): remotes, sensors — schema STRUCTURE exists in
              SCH_VCS_DATA and ramses_cc generates it, BUT ramses_rf's
              load_fan is a stub and doesn't process it. gateway.schema()
              flattens HVAC to orphans_hvac. See "HVAC Schema" section.

TRAITS (in schema with _ prefix, stripped before ramses_rf):
  ✅ implemented: _disabled (exclude from known_list)
  ✅ implemented: _skipped (user deferred, re-appears in review, survives cache loss)
  ✅ implemented: _name (human-friendly display name)
  ✅ implemented: _alias (device-level friendly name)
  ✅ implemented: _class (device class override)
  ✅ implemented: _comment (free-form per-device comment)
  ✅ implemented: _faked (fake sensor mode — PR 764)
  ✅ implemented: _scheme (HVAC vendor scheme — PR 764)
  ✅ implemented: _bound (FAN-specific: which faked REM can send 2411 — PR 764)
     Phase 3a: accepts str | list[str] (multi-REM)
  ✅ implemented: _owner (device ownership: me / not-me — PR 764)
  ✅ implemented: _commands (Phase 3a, PR 811 — on REM entries, full packets)
     Phase 3b: moves to FAN entries, {verb, code, payload} dicts

PHASE 2 MIGRATION (known_list traits → schema _ traits):
  ✅ implemented: _sync_known_list_traits_to_schema copies class, faked,
     bound, scheme, alias from known_list into schema root entries
     (PR 764, commit 3249178). Runs after sync_learned_topology backfill.
     Schema is authoritative — known_list only fills gaps.
  ✅ implemented: generate_schema_entry creates root entries for ALL device
     types (PR 764, commit 8b025d7). Previously list-based devices (REM/CO2
     in remotes[], TRV in zones[]) got no root entry — traits couldn't be set.
  ✅ implemented: sync_learned_topology backfills root entries for pre-existing
     list devices (PR 764, commit 8448cbd). One-time migration for devices
     accepted before the generate_schema_entry fix.
  ✅ implemented: strip_traits_for_validation prevents duplicates when a
     device is in both a root entry and a list (PR 764, commit 485bba2).
  ✅ implemented: order_schema for human-readable key ordering — root traits,
     main_tcs, comments, orphans (at top), devices sorted by _owner then ID
     (PR 764, commits bf02322, a013d00).

WILL BECOME OBSOLETE (not in schema, not in config):
  ❌ enforce_known_list → always-on, then option removed
  ❌ eavesdrop → always-on (schema has topology, heuristics redundant)
  ❌ block_list → "not in schema" = "blocked"
  ✅ disabled_devices → _disabled: true per-device trait (DONE, PR 764)

STAYS IN known_list (for now):
  📋 commands → Phase 3a DONE: _commands on REM entries in schema (PR 811)
                 Phase 3b: _commands moves to FAN entries as {verb,code,payload}
                 ramses_rf doesn't need _commands today (stripped by pipeline
                 — NOT mapped to 'commands': no such trait in SCH_TRAITS)
                 ramses_rf 0.58.3: CQRS Intent builders available as defaults
                 schema _commands stays as OVERRIDE (user wins)
                 Phase 3d: consolidate strippers (strip_traits for validation;
                 strip_and_map_traits for known_list — already wired);
                 remove ImportError fallback (dead code);
                 pass _bound as str | list[str] (remove str-only guard)

STAYS IN CONFIG OPTIONS (not device traits):
  📋 packet_log → logging config (path, prefix, retention)

STAYS IN .storage/ramses_cc (storage mechanics):
  📋 cached packets → warm restart data
  📋 discovery state → observer catalog (Path 1)
  📋 schema_backups → safety backups (also as YAML in ramses_cc_backups/)

STAYS IN ramses.db:
  📋 packet history → message store (schedules, fan info, etc.)
```

[top](#schema-as-source-of-truth-architecture)
<a id="precedence-rules"></a>
## Precedence Rules

```
At startup, merge_schemas(config_schema, cached_schema):

  config_schema = {                          cached_schema = {
    "main_tcs": "01:150000",                   "main_tcs": "01:150000",
    "01:150000": {                             "01:150000": {
      "zones": {                                 "zones": {
        "03": {                                     "03": {
          "_name": "My Lounge",   ← USER             "_name": "Lounge",  ← ramses_rf
          "sensor": "01:150003",                     "sensor": "01:150003",
          "actuators": ["04:150003"]                 "actuators": ["04:150003", "04:150099"]
        }                                          }
      }                                          },
    }                                            "stored_hotwater": {"sensor": "07:150000"}
  }                                            }
                                             }

  MERGED = deep_merge(config, cached):
  {
    "main_tcs": "01:150000",
    "01:150000": {
      "zones": {
        "03": {
          "_name": "My Lounge",     ← CONFIG WINS (scalar)
          "sensor": "01:150003",    ← same value
          "actuators": ["04:150003", "04:150099"]  ← UNION (list)
        }
      },
      "stored_hotwater": {"sensor": "07:150000"}  ← from cached (not in config)
    }
  }
```
[top](#schema-as-source-of-truth-architecture)
<a id="topology-changes-current-state-gaps"></a>
## Topology Changes — Current State & Gaps

<a id="what-ramsesrf-already-does-in-memory"></a>
### What ramses_rf already does (in-memory)

ramses_rf has a `TopologyBuilder` that listens to traffic and emits
`TopologyChangedEvent`s:

```
Traffic → TopologyBuilder rules → TopologyChangedEvent
                                   |
                   ┌───────────────┼───────────────┐
                   |               |               |
              BIND_DEVICE     PROMOTE_CLASS   UPDATE_TRAITS
              (zone assign)   (TRV→THM etc)   (alias/class/etc)

              CREATE_CONTROLLER   CREATE_CIRCUIT
              (new CTL detected)  (UFH circuit)

HVAC: only PROMOTE_CLASS (no BIND_DEVICE for HVAC — see HVAC section)
```

Events that fire:
- **000C** — explicit zone binding (CTL broadcasts device map) [heat only]
- **30C9/12B0/1260** — zone binding from payload (zone_idx in payload) [heat only]
- **directed telemetry** — TRV sends to CTL → implies binding [heat only]
- **zone sensor matching** — temperature matching heuristic [heat only]
- **HVAC verb+code pairs** — class promotion only (22F1→REM, 1298→CO2,
  31D9/31DA→FAN, 12A0→HUM). NO binding events for HVAC.

**Verb sensitivity (31DA fix):** The scan engine's `_classify` function
checks the **current verb** when classifying from accumulated codes.
This matters for 31DA:
- `I|31DA` (broadcast) → FAN (the FAN broadcasts its own status)
- `RP|31DA` (response) → FAN (the FAN replies to a request)
- `RQ|31DA` (request) → NOT FAN (a DIS asks the FAN for status)

Without this distinction, a DIS sending `RQ|31DA` to a FAN would be
misclassified as FAN, because the accumulated-codes check tried all
verbs and found `(I, 31DA) → FAN` even though the device never sent
`I|31DA`. The fix: only check the current verb, so `RQ|31DA` does not
match any VC pair and the device falls through to prefix fallback.

These events mutate ramses_rf's in-memory device registry. The next
`client.get_state()` → `gateway.schema()` reflects the changes, and
they land in `.storage/ramses_cc` cache within 5 minutes.

<a id="the-gap-changes-dont-flow-back-to-config-entry-schema"></a>
### The gap: changes don't flow back to config entry schema

**PARTIALLY CLOSED in PR 764** — `sync_learned_topology()` now writes
learned topology back to the config entry. Problems 1 and 4 are
mitigated. Problems 2, 3, and 5 remain.

```
                    CONFIG ENTRY          .storage CACHE        ramses_rf
                    (user intent)         (learned reality)     (live)
                          |                     |                  |
  device moves zone  -----+---- NOW synced ----+---- updated -----+-- updated
                          |    (sync_learned_   |                  |
                          |     topology)       |                  |
  new device added   -----+---- NOT updated ----+---- updated -----+-- updated
                          |    (needs discovery |                  |
                          |     accept flow)    |                  |
  device unavailable -----+---- NOT updated ----+---- NOT updated -+-- marked unavail
                          |                     |                  |
  user clears cache  -----+---- preserved ------+---- WIPED --------+-- rebuilt from
                          |    (topology now    |                  |   config only
                          |     synced to config|                  |
                          |     so survives)    |                  |
```

**Problem 1: Device moves zone**
- ramses_rf learns new binding from 000C/30C9 → in-memory updated
- Cache updated within 5 min (new zone_idx in schema)
- Config entry still has old zone assignment
- On restart: merge_schemas(config, cached) — config wins for scalars
  (old zone_idx), but zone keys are dict keys so BOTH old and new
  zone entries survive → device appears in two zones

**Problem 2: New device added to existing zone**
- ramses_rf with enforce_known_list=True won't create it (not in
  known_list) → shows up in DiscoveryScan instead
- User accepts → generate_schema_entry puts it in orphans_heat
  (no zone_idx from scan engine in most cases)
- ramses_rf learns zone from traffic → cache has it in correct zone
- On restart: merged schema has device in orphans (config) AND in
  zone (cache) → both survive

**Problem 3: Device unavailable / removed**
- ramses_rf marks device unavailable (no packets for X minutes)
- Schema unchanged — device stays in schema forever
- MITIGATED (PR 764): `remove_device` service now allows clean removal
  from schema, known_list, and HA device registry

**Problem 4: Cache cleared = topology lost (MITIGATED)**
- User clears cache → only config entry schema remains
- BUT: `sync_learned_topology()` has already written learned topology
  back to the config entry (every 5 min), so config now has the rich
  schema, not just the minimal one
- ramses_rf starts with the full rich schema from config → entities
  are immediately available
- Remaining gap: topology learned in the last 5 min may be lost

**Problem 5: HVAC topology lost on every roundtrip (HVAC-specific)**
- ramses_cc generates HVAC schema: `"32:153289": {remotes: [...], sensors: [...]}`
- ramses_rf's `load_fan` is a stub — ignores remotes/sensors
- `gateway.schema()` outputs ALL HVAC as `orphans_hvac` (flat list)
- On next restart, cache has `orphans_hvac`, not HVAC structure
- Config entry may still have HVAC structure (if user wrote it)
- See "HVAC Schema" section for details

<a id="whats-needed-for-true-ssot-with-topology"></a>
### What's needed for true SSOT with topology

```
┌─────────────────────────────────────────────────────────────┐
│ GOAL: Schema reflects current topology, auto-updated        │
│                                                             │
│ 1. TOPOLOGY CALLBACK (ramses_rf PR needed)                  │
│    ramses_rf emits TopologyChangedEvent via callback        │
│    ramses_cc listens and updates config entry schema        │
│    → real-time, no 5-min polling                            │
│                                                             │
│ 2. CACHE → CONFIG SYNC (IMPLEMENTED in PR 764)              │
│    sync_learned_topology() runs in async_save_client_state,  │
│    comparing cached schema vs config schema and updating     │
│    config entry options with the richer cached topology      │
│    (new zones, moved devices).                              │
│    Never overwrites user-authored keys (_alias, _disabled,   │
│    _class, _name, _comment) — only learned/topology keys.    │
│    Reload is suppressed during the update to avoid tearing   │
│    down the transport while pending _send_cmd tasks are in   │
│    flight.                                                  │
│    → config becomes the rich schema, not just minimal       │
│                                                             │
│    Future upgrade: swap the 5-min polling loop for a         │
│    StateUpdatedEvent listener when ramses_rf's CQRS events   │
│    are live (confirmed sound by ramses_rf author).           │
│    Note: entity-level SIGNAL_UPDATE is now emitted by the    │
│    coordinator's _on_packet handler (issue 794, shipped in   │
│    0.58.0), so this polling-loop upgrade is about topology   │
│    sync only, not entity state updates.                      │
│                                                             │
│ 3. ZONE REASSIGNMENT (ramses_cc change)                     │
│    When a device moves zones:                               │
│      - remove from old zone in config schema                │
│      - add to new zone in config schema                     │
│    → no duplicate zone entries                              │
│                                                             │
│ 4. DEVICE REMOVAL (ramses_cc change, user-triggered)        │
│    Service: remove_device(device_id)                        │
│      - removes from schema (zones, orphans, main_tcs)       │
│      - removes from known_list                              │
│      - removes HA device registry entry                     │
│    → schema stays clean                                     │
│                                                             │
│ 5. DISCOVERY WITH ZONE INFO (ramses_rf + ramses_cc)         │
│    DiscoveryScan already extracts zone_idx + bound_to       │
│    from binding codes (000C, 30C9, 12B0, etc.)              │
│    generate_schema_entry already uses zone_idx when present │
│    → accepted devices go to correct zone, not orphans       │
│    Gap: many devices are discovered without binding codes   │
│    → need to wait for traffic or query CTL for zone map     │
│                                                             │
│ 6. HVAC TOPOLOGY (ramses_rf PR needed — see HVAC section)    │
│    Implement load_fan schema processing                     │
│    Model FAN as a Climate entity (HA's preferred shape),    │
│      not a HA FAN integration object; place HVAC at the      │
│      same schema level as main_tcs (peer, "level with HEAT")│
│    "Init and go" from schema (ramses_rf Phase 3.75) —      │
│      devices get correct class from _class trait, no       │
│      runtime __class__ mutation                            │
│    Add HVAC binding rules to TopologyBuilder                │
│    Fix gateway.schema() to output HVAC structure             │
│    Dual-role devices: deferred to Builder (see HVAC section)│
└─────────────────────────────────────────────────────────────┘
```

<a id="priority-order-for-implementation"></a>
### Priority order for implementation

```
NOW (works):
  ✅ Accept device → minimal schema fragment → entities created
  ✅ ramses_rf learns HEAT topology → cached schema enriched every 5 min
  ✅ Restart: merged schema = config + cache (config wins scalars)
  ✅ Manual schema edits preserved (config takes precedence)
  ✅ ramses_cc generates HVAC schema (remotes/sensors) on accept
  ⚠️ ramses_rf ignores HVAC schema (load_fan stub) — see HVAC section

NEXT (ramses_cc only):
  1. Cache → config sync (DONE, PR 764): on save_state, write rich
     schema back to config entry options (preserving _disabled, comments)
  2. remove_device service: clean removal from schema + registry
     - DONE (PR 764): SVC_REMOVE_DEVICE registered in __init__.py,
       handler in services.py, delegate in coordinator.py.
       Removes from schema (zones, orphans, main_tcs, DHW, HVAC
       remotes/sensors), known_list, HA device registry, and ramses_rf
       client _include lists. HGI gateway cannot be removed.
       17 tests in test_services.py + 1 in test_init.py.
     - Schema helper remove_device_from_schema (schemas.py:305) used
       internally, plus top-level key deletion and main_tcs clearing.
  3. Zone reassignment: detect device in two zones, keep latest
     - DONE (PR 764): sync_learned_topology now handles zone→zone,
       zone→DHW, and DHW→zone moves. Section 1e builds a
       learned_device_zones map and learned_dhw_devices set from the
       learned schema, then scans config zones and removes devices
       placed in a different location. Section 1f clears DHW
       sensor/valves when the learned schema has them in a zone.
       9 tests in test_schemas.py.
  4. Cache HVAC schema separately (workaround for load_fan stub)
     - DONE (PR 764): HVAC topology (FAN entries with remotes/sensors,
       orphans_hvac) is cached separately under SZ_HVAC_SCHEMA in
       .storage/ramses_cc. extract_hvac_schema pulls HVAC entries from
       the config schema on save; merge_hvac_schema unions them back
       into the config schema on startup. This works around ramses_rf's
       load_fan stub which causes gateway.schema() to omit HVAC topology.
       17 tests (14 in test_schemas.py, 3 in test_store.py).
  5. CO2 sensor classification in generate_schema_entry
     - DONE (PR 764): 37: devices with likely_type="CO2" now go to the
       parent FAN's remotes[] (same as REM), or orphans_hvac if no parent.
       Previously fell through to orphans_heat (wrong domain).
     - Design decision: CO2 and REM share a branch because the scan engine
       flips 37: between CO2 and REM depending on which packet arrived last
       (they send both I 1298 and I 22F1). The sensors[] vs remotes[]
       distinction is deferred to the Builder pattern (LATER item 10).
  6. Comprehensive test coverage (see PR 764 status doc section C)
     - Tests for new functions, user schema edits, corruption scenarios

LATER (needs ramses_rf PR):
  5. TopologyChangedEvent callback → real-time schema updates
  6. Query CTL for zone map (000C) on accept → immediate zone info
  7. Device health: track unavailable devices, suggest removal
  8. HVAC: implement load_fan, FAN as Parent, HVAC binding rules
  9. HVAC: fix gateway.schema() to output HVAC structure
  10. HVAC: support dual-role devices (CO2 + REM)
```

[top](#schema-as-source-of-truth-architecture)
<a id="hvac-schema-current-state-gaps"></a>
## HVAC Schema — Current State & Gaps

This section addresses the HVAC (ventilation) side of the schema,
which is significantly less mature than the heat (TCS) side. The
reviewer feedback on the posted design doc highlighted that HVAC
devices all end up in `orphans_hvac` with schema `{}`, when the
real topology is:

```
"32:123456":              ← HRU (heat recovery unit / FAN)
  remotes:
    - "29:123456"         ← battery-powered remote
  sensors:
    - "37:123456"         ← mains-powered CO2 sensor / remote
    - "37:123457"         ← mains-powered CO2 sensor / remote
```

<a id="the-fundamental-gap-loadfan-is-a-stub"></a>
### The fundamental gap: load_fan is a stub

ramses_rf's `load_fan` (src/ramses_rf/schemas.py:394-400) is a **stub**:

```python
def load_fan(gwy: Gateway, fan_id: DeviceIdT, schema: dict[str, Any]) -> Device:
    """Create a FAN using its schema (i.e. with remotes, sensors)."""
    fan = _get_device(gwy, fan_id)
    # fan._update_schema(**schema)  # TODO    ← COMMENTED OUT
    return fan
```

Compare with `load_tcs` which DOES call `ctl.tcs._update_schema(**schema)`
and processes zones, DHW, UFH, etc. The FAN equivalent is not
implemented. This means:

- ramses_cc generates proper HVAC schema: `"32:153289": {remotes: [...], sensors: [...]}`
- ramses_rf accepts it (SCH_VCS_DATA validator passes)
- `load_fan` creates the FAN device but **ignores the remotes/sensors**
- The remotes and sensors are created separately as orphan devices
  (via `orphans_hvac` list or via known_list filter)
- `gateway.schema()` outputs ALL HVAC devices as `orphans_hvac` —
  the HVAC structure is lost in the roundtrip

<a id="the-roundtrip-bug"></a>
### The roundtrip bug

```
  ramses_cc config entry schema:
    "32:153289": {
      remotes: ["29:153001", "37:153002"],
      sensors: ["37:153002", "37:153003"]
    }
           |
           | _strip_schema_extensions (moves HVAC without remotes/sensors to orphans_hvac)
           v
  ramses_rf load_schema:
    load_fan("32:153289", {remotes: [...], sensors: [...]})
      → creates FAN device
      → IGNORES remotes and sensors (stub)
      → remotes/sensors created as separate orphan devices
           |
           v
  ramses_rf gateway.schema():
    {
      orphans_hvac: ["32:153289", "29:153001", "37:153002", "37:153003"]
    }
      ← HVAC structure LOST — all devices flat-listed as orphans
           |
           v
  ramses_cc caches this:
    .storage/ramses_cc schema = {orphans_hvac: [...]}
      ← on next restart, HVAC structure is gone from cache
      ← config entry still has it (if user wrote it there)
      ← merge_schemas(config, cached) — config wins for the HVAC keys
```

**Impact:** The HVAC topology survives only if the user manually wrote
it in the config entry schema. If it was learned from traffic or
generated by `generate_schema_entry`, it's lost on the next restart
because `gateway.schema()` flattens it to `orphans_hvac`.

<a id="fan-is-not-a-parent-class"></a>
### FAN is not a Parent class

Unlike TCS (which is a `System` / `Parent` class that manages zones,
DHW, UFH as children), FAN (`HvacVentilator`) is just a `Device`. It
has no `_update_schema` method, no child management, no `schema()`
method that outputs its remotes/sensors.

```
TCS (heat):                          FAN (HVAC):
  System (Parent)                      HvacVentilator (Device)
    ├── _update_schema(**schema)       ├── NO _update_schema
    ├── _add_child(device)             ├── NO _add_child
    ├── zones: {idx: Zone}             ├── _bound_devices: dict
    ├── dhw: StoredHotWater            │   (just device_id → type)
    ├── ufh: {ufc_id: UfhController}   └── NO schema() output
    └── schema() → rich topology
```

The `_bound_devices` dict on FAN stores `{device_id: DevType.REM/DIS}`
but this is populated at runtime (via `add_bound_device`), not from
schema. And it's not included in `gateway.schema()` output.

<a id="topologybuilder-has-no-hvac-binding-rules"></a>
### TopologyBuilder has no HVAC binding rules

TopologyBuilder's `_evaluate_hvac_rules` (topology_builder.py:359-408)
only does **class promotion** based on verb+code pairs:

```
HVAC_KLASS_BY_VC_PAIR (protocol/ramses.py):
  I|31D9, I|31DA, RP|31DA  → FAN
  I|1298                    → CO2
  I|12A0                    → HUM
  I|22F1, I|22F3            → REM
```

When a packet matches one of these pairs, TopologyBuilder emits a
`PROMOTE_CLASS` event for the source and/or destination device. That's
all — there is **no BIND_DEVICE event** for HVAC. The REM/CO2 is
promoted to its class but **not linked to the FAN** as a parent.

This is fundamentally different from the heat side, where 000C/30C9
packets create explicit zone bindings (BIND_DEVICE events that link
sensors/actuators to zones).

<a id="how-hvac-topology-could-be-derived-from-traffic"></a>
### How HVAC topology COULD be derived from traffic

The reviewer correctly noted that HVAC topology can be derived from
network traffic:

```
OBSERVATION                              INFERRED TOPOLOGY
──────────────────────────────────────────────────────────────
37:153002 sends I|1298 to 32:153289     37: is CO2 sensor, 32: is FAN
                                         → sensor bound to FAN

29:153001 sends I|22F1 to 32:153289     29: is REM, 32: is FAN
                                         → remote bound to FAN

37:153002 sends I|22F1 to 32:153289     37: is ALSO a remote
                                         → dual-role device (see below)

32:153289 broadcasts I|31DA             32: is FAN (signature code)
32:153289 sends RP|31DA                 confirms FAN class
```

The `dst` address of directed packets reveals the parent FAN. This
is the same principle as heat-side directed telemetry (TRV → CTL
implies binding), but no TopologyBuilder rule implements it for HVAC.

<a id="co2-sensors-are-remotes-too-dual-role"></a>
### CO2 sensors are remotes too (dual-role)

The reviewer raised that "CO2 sensors are actually remotes too."
This is confirmed by ramses_rf's fingerprints database:

```
fingerprints.py:
  "00010028080101FEFF": {slug: "CO2", dev_type: "37",
    desc: "VMS-12C39"},  # sends 1298, 31E0, 2E10, 3120, AND I|22F1!

  "0001C88D030167FEFF": {slug: "REM", dev_type: "37",
    desc: "VMI-15MC01"},  # sends 1298/31E0, 22F1, 22F3
                           # (integrated CO2 sensor)
```

A 37: prefix device can be:
- **CO2 sensor** — sends I|1298 (CO2 reading)
- **REM** — sends I|22F1 (fan mode command), I|22F3 (boost timer)
- **Both** — sends 1298 AND 22F1 (dual-role device)

**Current limitation:** ramses_rf's architecture forces ONE device
class per device. The class is set by whichever verb+code pair is
seen first:
- I|1298 seen first → promoted to CO2 (HvacCarbonDioxideSensor)
- I|22F1 seen first → promoted to REM (HvacRemote)

Once promoted, the device stays in that class. A CO2 sensor that
also sends 22F1 will be either a CO2 sensor OR a remote, not both.
This means:
- If classified as CO2: no Remote entity, no command learning/sending
- If classified as REM: no Sensor entity, no CO2 readings

ramses_cc issue 186 acknowledges this: "There is currently no
support for this scenario - there should be."

**Chosen solution (deferred to ramses_rf Phase 3.75, "init and go"):**
- Devices instantiate with correct role from schema `_class` trait.
- No runtime `__class__` mutation or strategy composition needed.
- Composite classes (`HvacCarbonDioxideRemote`) and multiple class
  promotions are rejected — users have managed faking these remotes
  for years, and ramses_cc must not block HVAC work on dual-role.
- Ship single-role FAN/REM/CO2 first; dual-role is upstream's job.

**ramses_cc interim handling (PR 764, implemented):**
- `generate_schema_entry` in `discovery.py` merges CO2 and REM into a
  single branch — both go to the parent FAN's `remotes[]` list (or
  `orphans_hvac` if no parent is known).
- This stops CO2 sensors from going to `orphans_heat` (the previous
  default fallback — wrong domain).
- The `sensors[]` list under a FAN is reserved for the future when
  `load_fan` is implemented and ramses_rf can distinguish dual-role
  devices (CO2 sensor + REM in the same physical device).
- The scan engine's `_classify` flips `37:` between `CO2` and `REM`
  depending on which packet arrived last; merging them into one branch
  avoids the device "jumping" between `sensors[]` and `remotes[]` as
  packets arrive.

<a id="device-id-prefixes-for-hvac"></a>
### Device ID prefixes for HVAC

```
PREFIX  | DEVICE TYPES              | AMBIGUITY
--------|---------------------------|----------
30:     | RFG / PIV (FAN variant)   | Low — usually FAN/PIV
32:     | FAN / REM (Nuaire)        | Medium — Nuaire uses 32: for both
29:     | FAN / REM / CO2 / HUM     | High — battery-powered variants
37:     | REM / CO2 / HUM           | HIGH — needs verb+code to distinguish
18:     | HGI / FAN                 | Medium — some FANs use 18: (BRDG-02A55)
```

ramses_rf's DiscoveryScan has `_UNAMBIGUOUS_HVAC_PREFIXES = {"18", "32"}`
— only 18: (HGI) and 32: (FAN) are considered unambiguous. All others
need verb+code pairs to classify.

Note: 30: is RFG/PIV (Positive Input Ventilation), which is a FAN
variant. ramses_cc's `_strip_schema_extensions` moves HVAC devices
without remotes/sensors to `orphans_hvac` (both 30: and 32: prefixes).

<a id="hvac-binding-uses-1fc9-not-000c"></a>
### HVAC binding uses 1FC9, not 000C

The heat side uses 000C for zone binding (CTL broadcasts device map).
HVAC uses a different mechanism — the 1FC9 binding handshake:

```
REM (supplicant)                     FAN (respondent)
─────────────                       ─────────────────
1. 1FC9 Offer  ──────────────────→  "I want to bind for 22F1, 22F3"
2.               ←──────────────────  1FC9 Accept
3. 1FC9 Confirm ──────────────────→  "I confirm the binding"
4.               ←──────────────────  10E0 Ratify (device info)
                                       "Here's my OEM code"
```

This is the same `bind_device` service handshake described in the
"bind_device service" section above. After binding, the REM can send
22F1/22F3 commands to the FAN, and the FAN accepts them.

**Key difference from heat:** 000C is a broadcast (CTL tells everyone
the zone map). 1FC9 is a directed handshake (REM ↔ FAN, one-to-one).
TopologyBuilder has rules for 000C but NOT for 1FC9 binding events.

<a id="what-ramsescc-does-right-despite-ramsesrf-gaps"></a>
### What ramses_cc does right (despite ramses_rf gaps)

ramses_cc's `generate_schema_entry` (discovery.py:269-381) correctly
generates HVAC schema entries when accepting discovered devices:

```
FAN discovered:
  generate_schema_entry("32:153289", likely_type="FAN")
  → {"32:153289": {remotes: []}}

REM discovered (with bound_to="32:153289"):
  generate_schema_entry("29:153001", likely_type="REM", bound_to="32:153289")
  → {"32:153289": {remotes: ["29:153001"]}}

REM discovered (no bound_to):
  → {orphans_hvac: ["29:153001"]}
```

ramses_cc's `_derive_known_list_from_schema` (coordinator.py:589-593)
correctly extracts remotes and sensors from HVAC entries:

```python
for remote_id in value.get(SZ_REMOTES, []):
    device_ids.add(remote_id)
for sensor_id in value.get(SZ_SENSORS, []):
    device_ids.add(sensor_id)
```

ramses_cc's `_strip_schema_extensions` (coordinator.py:871-980)
moves HVAC devices (30: and 32: prefixes) without remotes/sensors
to `orphans_hvac`.

ramses_cc's `fan_handler.py` correctly handles the `bound` trait
for 2411 parameter messages (which REM can send params to which FAN).

**The gap is entirely on the ramses_rf side** — load_fan stub, no
HVAC Parent class, no topology binding rules, no schema() output for
FAN topology.

<a id="what-needs-to-change-in-ramsesrf"></a>
### What needs to change in ramses_rf

```
1. IMPLEMENT load_fan schema processing
   - Uncomment and implement fan._update_schema(**schema)
   - The FAN surface in ramses_cc is a Climate entity (HA's preferred
     shape), not a HA FAN integration object. Place HVAC at the same
     schema level as main_tcs (peer, "level with HEAT", per @PWhite-
     Eng's work in ramses_rf).

2. FAN DEVICE STRUCTURE (ramses_rf Phase 3.75 — "init and go")
   - Do NOT make HvacVentilator inherit from Parent, and do NOT build
     a hand-built HVAC wrapper class purely for TCS/Evohome symmetry.
   - Devices instantiate with correct class from schema `_class` trait.
     No runtime `__class__` mutation or strategy composition.
   - The device still needs child management (_add_child, child_by_id)
     and a schema() that outputs remotes and sensors — but supplied
     by the class itself, not by a Builder or strategy composition.

3. ADD HVAC topology binding rules to TopologyBuilder
   - Rule: directed 22F1/22F3 from REM → FAN → BIND_DEVICE
   - Rule: directed 1298 from CO2 → FAN → BIND_DEVICE (as sensor)
   - Rule: 1FC9 binding handshake → BIND_DEVICE
   - These are the HVAC equivalents of 000C/30C9 for heat

4. FIX gateway.schema() to output HVAC topology
   - Instead of orphans_hvac: [all HVAC devices]
   - Output: "32:153289": {remotes: [...], sensors: [...]}
   - Only truly unbound HVAC devices go to orphans_hvac

5. DUAL-ROLE DEVICES (CO2 + REM) — DEFERRED TO ramses_rf
   - Requires ramses_rf to support dual-role devices (CO2 sensor +
     REM in the same physical device) via schema-driven instantiation.
   - Composite classes (HvacCarbonDioxideRemote) and multi-promotion
     are rejected.
   - ramses_cc must NOT block HVAC work on dual-role; ship single-role
     FAN/REM/CO2 first.

6. CLARIFY 30: prefix handling
   - 30: is RFG (relay gateway), 32: is FAN — both treated as HVAC
   - _strip_schema_extensions moves both to orphans_hvac if no remotes/sensors
```

<a id="what-needs-to-change-in-ramsescc"></a>
### What needs to change in ramses_cc

```
1. POPULATE HVAC SCHEMA FROM TRAFFIC (Observer path)
   - Do NOT cache HVAC schema separately as a workaround. A separate
     cache creates two sources of truth and risks divergence.
   - Use the existing dummy/stub device path and accept that HVAC
     topology is rebuilt from traffic on each restart until ramses_rf's
     load_fan is properly implemented. Single source of truth (the
     schema, even if sparse for HVAC) is preferred.
   - Restart survival for HVAC comes when load_fan lands upstream.

2. ADD HVAC-SPECIFIC UI in config flow
   - Currently the schema editor is generic YAML/JSON
   - A HVAC-specific editor would let users add remotes/sensors to a
     FAN without editing raw YAML

3. DISCOVERY: CLASSIFY CO2 SENSORS
   - generate_schema_entry handles FAN and REM but CO2 sensors
     may fall through to orphans_hvac
   - Should add: if likely_type == "CO2": add to parent's sensors[]

4. DUAL-ROLE DEVICES — DO NOT INVEST (deferred to ramses_rf Builder)
   - No composite-class, no multi-promotion, no user-override UI in
     ramses_cc.
   - Ship single-role FAN/REM/CO2 first; dual-role is a ramses_rf
     concern (Phase 3.75), not a ramses_cc concern.
```

[top](#schema-as-source-of-truth-architecture)
<a id="crash-recovery-what-survives-whats-lost"></a>
## Crash Recovery — What Survives, What's Lost

<a id="the-5-storage-layers-and-their-crash-behavior"></a>
### The 5 storage layers and their crash behavior

```
STORAGE              WRITE TIMING              CRASH BEHAVIOR
────────────────────────────────────────────────────────────────────────
config entry         immediate                 SURVIVES — HA writes
(core.config_        (async_update_entry)       to .storage/core.
entries)                                        config_entries on every
                                                update. Atomic write.

.storage/ramses_cc   every 5 min                MAY LOSE up to 5 min
                     + on shutdown               of learned topology.
                     (async_save_client_state)   Last checkpoint may
                                                be stale. Discovery
                                                state (pending devices)
                                                may lose recent
                                                classifications.

ramses.db            exists today (simulator)    SURVIVES — separate file
(SQLite packet       new MessageStore arch       from .storage. Today used
 cache)              planned in #530 Phase 2     by simulator. Future: full
                                                 packet store with WAL mode

packet log files     per-packet (immediate)     SURVIVES — each packet
                     (ramses_rf transport)       written before decode.
                                                May have partial last
                                                line (corrupt packet).

ramses_rf gateway    in-memory only             LOST — rebuilt from
(in-memory state)                               config + cache on
                                                restart.
```

<a id="crash-scenarios"></a>
### Crash scenarios

```
SCENARIO 1: HA restart (clean shutdown)
─────────────────────────────────────────────────────────────────────────
  1. HA calls async_unload_entry
  2. Coordinator._async_stop_discovery_scan:
     - exports discovery state
     - calls async_save_client_state (saves schema, packets, remotes,
       discovery to .storage/ramses_cc)
  3. async_on_unload callbacks fire (including final save)
  4. Everything is persisted

  RESULT: nothing lost


SCENARIO 2: HA crash / power failure / kill -9
─────────────────────────────────────────────────────────────────────────
  What survives:
  ✅ config entry schema (last async_update_entry — atomic)
  ✅ config entry known_list (last async_update_entry)
  ✅ packet log files (per-packet write)
  ✅ .storage/ramses_cc (last 5-min checkpoint)

  What's lost:
  ❌ up to 5 min of TopologyBuilder learning (zones, names, bindings)
  ❌ up to 5 min of DiscoveryScan classifications (new devices seen
     in last 5 min, codes_seen enrichment, RSSI updates)
  ❌ all in-memory device state (current temps, setpoints, battery
     levels) — rebuilt from RF traffic on restart
  ❌ any accepted device whose async_update_entry didn't complete
     (service call was mid-flight)

  On restart:
  1. coordinator._create_client:
     - merge_schemas(config_schema, cached_schema)
     - cached schema has topology up to last checkpoint
     - config schema has user intent (may be minimal)
     - merged = config wins scalars + cache fills gaps
  2. ramses_rf load_schema:
     - creates devices from merged schema
     - entities restored with last known topology
  3. RF traffic resumes:
     - TopologyBuilder relearns (fast — most rules fire on first
       packet from each device)
     - DiscoveryScan resumes (restored from .storage checkpoint)
     - device state (temps, etc.) updates from first packets

  RECOVERY TIME: seconds to minutes (entities appear immediately
  from merged schema, state updates as packets arrive)


SCENARIO 3: .storage/ramses_cc corrupted or deleted
─────────────────────────────────────────────────────────────────────────
  What survives:
  ✅ config entry schema (separate file)
  ✅ config entry known_list (separate file)
  ✅ packet log files

  What's lost:
  ❌ all learned topology (zones, names, actuators, bindings)
  ❌ all discovery state (pending devices, classifications)
  ❌ all cached packets (warm restart DTOs in .storage)

  What survives (separate files):
  ✅ ramses.db (SQLite — separate file, NOT in .storage/ramses_cc)
  ✅ packet log files (separate directory)

  On restart:
  1. merge_schemas(config, None) → just config schema
  2. If config schema is minimal (empty CTL, orphans):
     - ramses_rf creates devices but with no topology
     - entities created but zones/sensors not linked
  3. TopologyBuilder relearns from traffic:
     - 000C zone bindings: minutes to hours (CTL broadcasts
       periodically)
     - zone names (000A/0008): hours (depends on broadcast cycle)
     - DHW sensor: hours (10A0 broadcast cycle)
  4. DiscoveryScan starts fresh:
     - unknown devices re-discovered
     - previously accepted devices: still in config schema, so
       NOT re-discovered (they're "known")
     - previously declined devices: still marked _disabled in config
       schema (in config entry, NOT cache) → NOT re-discovered
       (_disabled survives cache loss by design)

  RECOVERY TIME: hours to days for full topology
  MITIGATION: cache→config sync (IMPLEMENTED) means config has rich
  schema, so cache loss = no topology loss


SCENARIO 4: config entry corrupted or deleted
─────────────────────────────────────────────────────────────────────────
  What survives:
  ✅ .storage/ramses_cc (cached schema + discovery)
  ✅ packet log files

  What's lost:
  ❌ user intent (schema, known_list, _disabled traits, comments)
  ❌ config options (eavesdrop, enforce_known_list, packet_log)

  On restart:
  - HA shows config entry as needing setup
  - User must reconfigure (config flow)
  - If user re-enters same CTL ID:
     - merge_schemas(new_config, cached) → cached topology restored
     - but user overrides (_name, _disabled) are gone

  RECOVERY TIME: manual reconfiguration required
  MITIGATION: backup mechanism (store.py async_save_backup) saves
  schema + known_list as human-readable YAML files to
  <config_dir>/ramses_cc_backups/ before every migration step.
  Backups are created before:
  - SSOT Phase 1 (known_list-only devices → schema)
  - SSOT Phase 2 (known_list traits → schema)
  - review_discovered _class updates
  Max 5 backups retained (oldest trimmed). User can copy/paste
  from YAML to restore.


SCENARIO 5: Both config entry AND cache lost
─────────────────────────────────────────────────────────────────────────
  What survives:
  ✅ packet log files (forensic record only)

  What's lost:
  ❌ everything except packet logs

  On restart:
  - Full reconfiguration required
  - ramses_rf must learn from scratch
  - DiscoveryScan starts fresh
  - Packet logs can be replayed via device_simulator to speed up
    learning (but this is a manual process)

  RECOVERY TIME: hours to days + manual reconfiguration
```

<a id="what-makes-crash-recovery-better-future-improvements"></a>
### What makes crash recovery better (future improvements)

```
1. CACHE → CONFIG SYNC (ramses_cc, NEXT priority)
   ────────────────────────────────────────────────────────────────
   Today: config = minimal, cache = rich topology
   Future: config = rich topology (synced from cache)

   Impact on crash:
   - Scenario 2: no topology loss (config has it)
   - Scenario 3: no topology loss (config has it, cache is backup)
   - Scenario 4: cache still has topology as fallback

   How: on async_save_client_state, compare cached schema vs config
   schema. If cached is richer, write it back to config entry
   options (preserving user overrides like _name, _disabled).

2. TOPOLOGY CALLBACK (ramses_rf PR needed)
   ────────────────────────────────────────────────────────────────
   Today: 5-min polling (SAVE_STATE_INTERVAL)
   Future: ramses_rf emits TopologyChangedEvent → immediate save

   Impact on crash:
   - Scenario 2: no topology loss at all (saved on every change)
   - Reduces window from 5 min to seconds

3. SQLite PACKET CACHE (ramses_rf #530 Phase 2)
   ────────────────────────────────────────────────────────────────
   Today: packets in .storage/ramses_cc (JSON, 5-min checkpoint)
   Future: packets in ramses.db (SQLite, write-behind)

   Impact on crash:
   - Packet history survives crash (SQLite WAL mode)
   - Can replay recent packets to rebuild in-memory state
   - No more 5-min packet loss window

   TRANSITIONAL SHIM (Phase 2.95 / F5 — MERGED via PR 780, PR 782
   open): gateway.get_state() returns state_cache (latest per
   StateHeader) instead of scraping the deleted _msgs/_msgs_ot
   dicts. ramses_cc warm restarts keep working; granularity shifts
   from "all wanted ≤24h" to "latest per StateHeader". ramses_cc
   _get_saved_packets now checks src/dst as fallback for addr1/2/3
   (PR 780 returns src/dst only; PR 782 adds addr1/2/3 back).
   Retiring .storage/ramses_cc JSON for packets also requires
   migrating remotes + discovery_state out of that file
   (coordinator.py:845).

4. PERIODIC CONFIG BACKUP (ramses_cc, proposed)
   ────────────────────────────────────────────────────────────────
   Today: backups before every migration step (store.py async_save_backup)
          → saved as human-readable YAML to <config_dir>/ramses_cc_backups/
          → max 5 retained (oldest trimmed)
          → created before SSOT Phase 1, Phase 2, and review_discovered _class updates
   Future: periodic backup of config entry to .storage/ramses_cc

   Impact on crash:
   - Scenario 4: can restore from backup
   - Catches config entry corruption

5. _DISABLED TRAIT IN CONFIG (IMPLEMENTED in PR 764)
   ────────────────────────────────────────────────────────────────
   Today: _disabled is a per-device trait in config entry schema
   Future: stays in config

   Impact on crash:
   - Scenario 3: declined devices stay declined (in config, not
     cache) — this was a design decision: _disabled lives
     in config entry, not in .storage cache
```

<a id="current-state-summary"></a>
### Current state summary

```
DATA                   CLEAN SHUTDOWN   CRASH (kill -9)   CACHE LOST   CONFIG LOST
──────────────────────────────────────────────────────────────────────────────────
user schema            ✅ saved          ✅ saved           ✅ saved      ❌ lost
user known_list        ✅ saved          ✅ saved           ✅ saved      ❌ lost
_disabled traits        ✅ saved          ✅ saved           ✅ saved      ❌ lost
learned topology       ✅ saved          ⚠️ ≤5 min lost    ❌ lost       ✅ saved*
discovery (pending)    ✅ saved          ⚠️ ≤5 min lost    ❌ lost       ✅ saved*
device state (temps)   ❌ in-memory      ❌ in-memory       ❌ in-memory  ❌ in-memory
packet log             ✅ per-packet     ✅ per-packet      ✅ per-packet ✅ per-packet

* = cache→config sync is implemented (sync_learned_topology)
   without it: learned topology is only in cache, lost if cache lost
```

[top](#schema-as-source-of-truth-architecture)
<a id="key-invariants"></a>
## Key Invariants

1. **Schema is the source of truth for topology** — known_list is derived from it
2. **Config entry options are user-controlled** — never overwritten by ramses_rf
3. **Cache is ramses_rf's learned reality** — enriched every 5 min, never touches config
4. **Manual edits are safe** — config wins for scalars, lists are unioned
5. **Disabled devices are excluded** — from derived known_list and from entity creation
6. **Clearing cache = fresh start** — ramses_rf relearns from traffic, config schema preserved
7. **Backups before migration** — schema + known_list saved before any migration logic runs
8. **Config entry is crash-safe** — HA writes atomically, survives kill -9
9. **Cache may lose up to 5 min** — SAVE_STATE_INTERVAL=5min, only mitigated
   by topology callback (future) or cache→config sync (IMPLEMENTED)
10. **_disabled trait lives in config, not cache** — declined devices stay
    declined even if cache is lost (design decision, IMPLEMENTED in PR 764)
11. **HVAC topology is NOT roundtripped** — ramses_cc generates HVAC schema
    (remotes/sensors), but ramses_rf's load_fan is a stub and
    gateway.schema() flattens HVAC to orphans_hvac. This is a known gap
    (see "HVAC Schema" section). Heat topology roundtrips correctly.

[top](#schema-as-source-of-truth-architecture)
<a id="schema-evolution-migration"></a>
## Schema Evolution & Migration

<a id="the-schema-will-no-longer-be-minimal"></a>
### The schema will no longer be minimal

Today the config entry schema is minimal (empty CTL, orphans list).
The rich topology lives in the `.storage/ramses_cc` cache. With
`sync_learned_topology()` (IMPLEMENTED in PR 764), the config entry
schema BECOMES the rich schema — it reflects the complete system:

```
TODAY:
  config entry schema (minimal):
    main_tcs: "01:216136"
    "01:216136": {}
    orphans_heat: ["04:208998"]

  .storage cache (rich):
    "01:216136": {
      zones: {03: {sensor, actuators, _name}},
      stored_hotwater: {sensor},
      system: {appliance_control}
    }

IMPLEMENTED (PR 764):
  config entry schema (complete):
    main_tcs: "01:216136"
    "01:216136": {
      _alias: "My Controller",
      system: {appliance_control: "10:064873"},
      zones: {
        "03": {
          _name: "Lounge",
          class: "rad",
          sensor: "01:150003",
          actuators: ["04:150003"]
        }
      },
      stored_hotwater: {sensor: "07:150000"}
    }
    "01:150003": {_alias: "Lounge sensor", _class: "SEN"}
    "30:160000": {_scheme: "itho", remotes: ["32:153001"]}

  .storage cache:
    (still used for packets, discovery, backups)
    (schema in cache = same as config entry, or superset)
```

This means schema changes are structural — going from minimal to
rich, from known_list traits to schema `_`-prefixed keys, from
`disabled_devices` list to `_disabled` per-device trait (DONE in PR 764).
Each of these is a migration step.


<a id="versioning-what-we-have-today"></a>
### Versioning — what we have today

```
TWO separate version tracks:

1. CONFIG ENTRY version (HA's config_entries system):
   - config_flow.py: VERSION = 2, MINOR_VERSION = 1
   - async_migrate_entry() in __init__.py handles v1 → v2
   - HA calls this automatically on startup if entry.version < VERSION
   - Used for: config flow schema changes, option key renames
   - Current v1→v2: removed deprecated packet_log keys, database keys

2. STORAGE version (HA's Store system):
   - const.py: STORAGE_VERSION = 1 (unchanged — no bump in Phase 3a)
   - Store(hass, STORAGE_VERSION, STORAGE_KEY)
   - HA's Store has built-in migration via async_migrate_func
   - Used for: .storage/ramses_cc data format changes
   - RamsesCcStore subclass registers _async_migrate_func (PR 810)
   - Phase 3a: NO version bump — runtime migration via
     _sync_remotes_to_schema handles remotes → _commands.
     Bumping would break downgrade (HA raises
     UnsupportedStorageVersionError when stored version >
     max_readable_version, which defaults to code's version).
```

<a id="what-migrations-are-needed"></a>
### What migrations are needed

```
SCHEMA FORMAT VERSIONS (stored in .storage/ramses_cc):

v1 (pre-Phase 3a):
  schema: {
    main_tcs: "01:...",
    "01:...": {},
    orphans_heat: [...],
    "04:034692": {_disabled: true},  ← ramses_cc _ trait (PR 764)
    "04:036068": {_disabled: true},  ← replaces old disabled_devices list
    device_comments: {...},          ← ramses_cc extension
  }
  known_list: {device_id: {class, alias, faked, scheme, bound}}
  remotes: {device_id: {command_name: payload}}

v1 (commands in schema — IMPLEMENTED, PR 811, no version bump):
  schema: {
    main_tcs: "01:...",
    "01:...": {
      _alias: "My Controller",     ← was known_list alias
      _faked: false,               ← was known_list faked
      system: {appliance_control: "10:..."},
      zones: {...},
      stored_hotwater: {...}
    },
    "01:150003": {
      _alias: "Lounge sensor",     ← was known_list
      _class: "SEN"                ← was known_list class override
    },
    "30:160000": {
      _scheme: "itho",             ← was known_list scheme
      _bound: "37:168270",         ← was known_list bound
      remotes: [...]
    },
    "32:153001": {
      _commands: {turn_on: "22F1..."},  ← was remotes/known_list (PR 811)
      _class: "REM",
      _faked: true
    },
    orphans_heat: [...],
    # _disabled stays as per-device trait (no change from v1)
  }
  known_list: {device_id: {class, alias, ...}}  ← kept as fallback
  remotes: {device_id: {command_name: payload}}  ← kept as cache

v3 (known_list removed, fully derived from schema — future):
  schema: {
    "32:153001": {
      _commands: {turn_on: "22F1..."},
      _class: "REM",
      _faked: true
    }
  }
  known_list: REMOVED (fully derived from schema)
  remotes: REMOVED (merged into schema)
```

<a id="migration-logic-when-to-create-it"></a>
### Migration logic — when to create it

```
WHEN: At the moment we change the schema format, BEFORE releasing it.

  1. ~~Bump STORAGE_VERSION in const.py (v1 → v2)~~ — REVERTED: no bump
     (see "Backward migration" below for why)
  2. Runtime migration via _sync_remotes_to_schema in coordinator.py
     (DONE — runs on every save cycle, copies remotes → schema _commands)
  3. Bump config_flow VERSION if config entry options change too
  4. Add async_migrate_entry() branch in __init__.py for new version

  The runtime migration runs on every save cycle after the user
  updates ramses_cc. It copies remotes → schema _commands (only
  if _commands not already present). No storage version bump needed.
```

<a id="backward-migration-the-problem"></a>
### Backward migration — the problem

```
HA/HACS does NOT support downgrade:

  - HACS: installs a specific version, no "rollback" button
  - HA config_entries: version only goes UP, never down
  - HA Store: version only goes UP, never down
  - Git: user can checkout old code, but storage format may have changed

  So if a user:
    1. Updates ramses_cc (Phase 3a — _commands added to schema)
    2. Runtime migration copies remotes → schema _commands
    3. Downgrades ramses_cc (0.58.0/0.58.1 code)
    4. 0.58.0 code strips _commands (via _strip_traits), reads remotes
       from .storage (kept as cache) → WORKS, no data loss

  Why no storage version bump (lesson learned):
    HA's Store._async_load_data checks:
      if data["version"] > self._max_readable_version:
          raise UnsupportedStorageVersionError(...)
    _max_readable_version defaults to the code's STORAGE_VERSION.
    Since 0.58.0/0.58.1 have STORAGE_VERSION=1 and don't set
    max_readable_version, they CANNOT read v2 data. Bumping to v2
    would make the integration fail to start on downgrade.

    Fix: STORAGE_VERSION stays at 1. The Phase 3a command migration
    is handled at runtime by _sync_remotes_to_schema, which is
    redundant with a storage migration anyway.

  Workarounds (still available if needed in future):
  a) schema_backups: we save backups as human-readable YAML files to
     <config_dir>/ramses_cc_backups/ before every migration step
     → user can copy/paste from YAML to restore
     → max 5 backups retained (oldest trimmed)
  b) Forward-compatible code: v1 code ignores unknown _ keys
     → schema with _alias/_commands keys works in v1 code (just ignores them)
  c) Set max_readable_version in Store constructor if a future bump
     is truly needed (allows older code to read newer data)
```

**The pragmatic approach:**

```
1. Make schema BACKWARD-READABLE by older code (no version bump):
   - Old code already strips unknown keys via _strip_schema_extensions
   - _alias, _class, _faked, _scheme, _bound, _commands are unknown
     keys → stripped before passing to ramses_rf
   - Old code still reads topology keys (zones, sensor, actuators)
   - Old code still reads known_list (if present, as overrides)
   - Old code still reads remotes from .storage (kept as cache)
   - So: Phase 3a schema works in 0.58.0 code, just without _commands

2. Make runtime migration create a backup:
   - async_save_backup() already exists
   - Saves v1 schema + known_list as human-readable YAML to
     <config_dir>/ramses_cc_backups/ before migrating to v2
   - Max 5 backups retained (oldest trimmed)
   - User can copy/paste from YAML to restore manually

3. Don't support formal downgrade (but it works anyway):
   - If user downgrades, old code reads schema (forward-compatible)
   - _commands is stripped (ignored), remotes still in .storage
   - Traits are lost (ignored), topology still works
   - known_list is empty (traits moved to schema), but derivation
     still works from topology
   - Not perfect, but not broken
```

<a id="migration-steps-for-each-phase"></a>
### Migration steps for each phase

```
PHASE 2 (traits in schema) — IMPLEMENTED in PR 764:

  STATUS: ✅ Done. No ramses_rf PR needed — strip_traits_for_validation
  removes _ keys before ramses_rf sees the schema, and
  _derive_known_list_from_schema extracts traits to the known_list
  that ramses_rf reads as it always has.

  MIGRATION (implemented as _sync_known_list_traits_to_schema):
    for each device_id in known_list:
      traits = known_list[device_id]
      if traits.get("alias") and "_alias" not in schema[device_id]:
        schema[device_id]["_alias"] = traits["alias"]
      if traits.get("class") and "_class" not in schema[device_id]:
        schema[device_id]["_class"] = traits["class"]
      if traits.get("faked") and "_faked" not in schema[device_id]:
        schema[device_id]["_faked"] = traits["faked"]
      if traits.get("scheme") and "_scheme" not in schema[device_id]:
        schema[device_id]["_scheme"] = traits["scheme"]
      if traits.get("bound") and "_bound" not in schema[device_id]:
        schema[device_id]["_bound"] = traits["bound"]

    # Schema is authoritative — known_list only fills gaps.
    # known_list stays as fallback container (Phase 4 removal deferred).
    # disabled_devices list already replaced by _disabled per-device trait.
    # No STORAGE_VERSION bump — _ keys are additive, old code strips them.

  BACKUP: save v1 schema + known_list + disabled_devices as YAML to
          <config_dir>/ramses_cc_backups/ (max 5 retained)

  BACKWARD COMPAT: v1 code ignores _ keys, still reads topology


PHASE 3a (commands in schema) — IMPLEMENTED in PR 811:

  STATUS: Done. No ramses_rf PR needed — _strip_schema_extensions
  removes _commands before ramses_rf sees the schema. learn_command /
  add_command / delete_command now write to schema via
  _async_update_schema_commands. Startup merges schema _commands into
  _remotes (highest precedence).

  MIGRATION (runtime, no storage version bump — implemented as
  _sync_remotes_to_schema in coordinator.py):
    for device_id, commands in remotes.items():
      if "_commands" not in schema[device_id]:
        schema[device_id]["_commands"] = commands

    # remotes kept in .storage as cache (not deleted)
    # known_list[dev][commands] kept as fallback (runtime merge at startup)
    # NO STORAGE_VERSION bump — would break downgrade to 0.58.0/0.58.1

  BACKUP: save schema + known_list as YAML to
          <config_dir>/ramses_cc_backups/ (reason="ssot_phase3a")

  BACKWARD COMPAT: old code ignores _commands (stripped by _ keys),
                   still reads remotes from .storage (kept as cache)


PHASE 4 (known_list fully removed) — DEFERRED:

  WHEN: when all traits are in schema, commands in schema, and
        ramses_rf derives everything from schema.
  NOTE: deferred pending Phase 2/3 field experience. known_list
        stays as the fallback container (with _derive_known_list_
        from_schema as the bridge) until traffic proves the schema
        path covers the edge cases (class override for 01:-that's-
        actually-a-sensor, faked_temperature). Don't rip out the
        derivation in the same PR as Phase 2/3.

  MIGRATION v3 → v4:
    # Remove known_list from config entry options
    # known_list is now 100% derived from schema at startup

  BACKUP: save v3 config entry options (including known_list) as YAML
          to <config_dir>/ramses_cc_backups/ (max 5 retained)

  BACKWARD COMPAT: v3 code still has known_list in options (ignored)
```

<a id="when-to-create-the-migration-code"></a>
### When to create the migration code

```
NOW (scaffolding) — DONE (Phase 2.5, PR 810)
  - Register async_migrate_func in store.py NOW, even as a no-op
    identity migration for v1 → v1, so the hook exists and the
    version label is in place.
  - This avoids the V1 config-flow pain (no upgrade() method) ever
    recurring: we have upgrade() and a V2 label, so we can go up to
    V3 and back.
  - Bump STORAGE_VERSION only when the format actually changes.
  - Track each step (v1→v2 traits, v2→v3 commands, v3→v4 known_list
    removal) as checkboxes in a SMALL issue, not a giant umbrella.
  - IMPLEMENTED: RamsesCcStore subclass in store.py overrides
    _async_migrate_func as identity (v1 → v1). Tests in
    tests/tests_new/test_store.py verify data is returned unchanged.

WHEN commands move to schema — DONE (Phase 3a, PR 811):
  1. ~~Bump STORAGE_VERSION to 2~~ — REVERTED: no bump, would break
     downgrade (HA raises UnsupportedStorageVersionError when stored
     version > max_readable_version, which defaults to code's version)
  2. Runtime migration via _sync_remotes_to_schema in coordinator.py
     (runs on every save cycle, copies remotes → schema _commands)
  3. Test backward compat (v1 data loads, runtime migration copies
     remotes to _commands, code reads _commands from schema first,
     falls back to remotes)

WHEN ramses_rf PR is ready (accepts _ keys):
  1. Bump STORAGE_VERSION to 3
  2. Flesh out async_migrate_func in store.py (v2 → v3)
  3. Bump config_flow VERSION to 3 (if config entry changes)
  4. Write async_migrate_entry branch in __init__.py
  5. Test: load v2 .storage, verify migration to v3, verify v3 works
  6. Test: load v3 .storage in v2 code (forward compat)

The scaffolding is created NOW; the real per-version migration logic
is created AT FORMAT-CHANGE TIME. But the schema format should be
DESIGNED now (the _ key convention, the structure) so that when we
implement it, the migration is straightforward.
```


[top](#schema-as-source-of-truth-architecture)
<a id="alignment-with-ramsesrf-roadmap"></a>
## Alignment with ramses_rf Roadmap

<a id="the-big-knot-discussion-191"></a>
### The "Big Knot" — Discussion #191

ramses_rf Discussion #191 ("Untangling the Organic Code Knot") is the
main architectural discussion, started by zxdavb (original author)
in April 2025. Key points:

**zxdavb's original concerns:**
1. Packet cache (dictionaries) → migrate to SQLite database
2. Device classes (static) → "init and go" from schema (Phase 3.75)

**PWhite-Eng's Phase 3.75 proposal (schema as "Seeding Mechanism"):**
- Schema becomes the source of truth for device identity
- On startup, devices instantiate with correct class from `_class` trait
- "Enriched Entry": schema entries carry traits (class, alias, bound, etc.)
- User config > Detective logic (known_list wins over auto-detection)
- Proposed `traits` as list of strategy names:
  `"traits": ["RelayStrategy", "SensorStrategy"]`

**silverailscolo's concerns:**
- Users can enter incorrect stuff — prefer flagging over "winning"
- "Using 'class' in this context is confusing" — class entries in
  config will be ignored in the future
- Wants manufacturer+model+revision+options instead of class
- Manual YAML won't work — need pick list or 10E0 codes

<a id="issue-530-architectural-refactor-umbrella-issue"></a>
### Issue #530 (Architectural Refactor — umbrella issue)

4 phases:
1. Rotating Packet Logs & Write Buffer (Flight Recorder)
2. Database & State Architecture (SQLite + RAM-First Cache)
3. **Device Identity & Discovery (Phase 3.75 — "init and go")**
   - 3.1 Schema-driven instantiation (no `__class__` mutation)
   - 3.2 Event Sourcing for Replay (SQLite packet replay)
   - 3.3 **Schema Seeding** — schema traits seed device creation
4. Isolated Routing Logic

**Phase 3.3 is directly relevant to our schema-as-SSOT plan.** Their
plan: known_list seeds the Builder at startup. Our plan: schema is
SSOT, known_list is derived from schema. These are complementary —
the derived known_list IS the seed for the Builder.

Full phase details (verified against the issue, Jul 2026):
- 1.1-1.3: packet log paths, midnight rotation, write buffering
- 2.1-2.5: "Fat" SQLite MessageStore (orjson payloads), strategy
  lookup table for composite keys, RAM-first write-behind cache,
  hydration + disk snapshots, legacy `device._msgs` cleanup
- 3.1-3.3: dynamic strategy (GenericStrategy → HoneywellTRVStrategy),
  event sourcing for replay, known-list seeding
- 4.1-4.2: routing table by RSSI, write path freshness protection

**Beware — two "schemas" in ramses_rf:** ramses_rf issue 627
("Relocate ramses.py schema to ramses_rf") is about `CODES_SCHEMA` —
the per-packet payload validation regexes in ramses_tx — NOT the
topology/device schema this document is about. Unrelated to our plan
(but a reminder to always prefix issue numbers with the repo).


<a id="verification-status-checked-jul-2026"></a>
### Verification status (checked Jul 23 2026)

```
REFERENCE                    STATE    NOTES
──────────────────────────────────────────────────────────────────
ramses_rf discussion 191     open     started by zxdavb, 19 Apr 2025
ramses_rf issue 530          closed   Builder/Strategy pattern scrapped (Jul 17 2026)
ramses_rf issue 639          open     master roadmap (Phase 3/3.25 TX DONE 0.58.3, 3.75 PR 914 draft; current pin 0.59.0)
ramses_rf issue 836          closed   Dynamic class promotion → "init and go"
ramses_rf issue 87           open     Itho fan states / manufacturer
ramses_rf issue 627          open     CODES_SCHEMA reloc (unrelated)
ramses_rf PR 914             draft    Phase 3.75: eradicate __class__ mutations (PWhite-Eng)
                                      TESTED: 232/232 ha_sim_test pass (Jul 23 2026)
ramses_rf PR 917             open     fix: declared hotwater_valve BDR not FC domain (wimpie70)
ramses_rf PR 916             draft    Phase 4a: Shadow ConversationManager (hold)
ramses_rf PR 918             open     refactor(hvac): binary struct packing (PWhite-Eng)
ramses_rf PR 919             open     refactor(protocol): schedule BOFM struct (PWhite-Eng)
ramses_cc PR 861             open     feat: device health tracking (wimpie70)
ramses_cc issue 677          CLOSED   fixed in 0.57.6 (Jun 2026)
ramses_cc issue 666          CLOSED   CPU ramp up (0.56.7)
ramses_cc issue 627          open     milestone 0.57.8 (wimpie70)
ramses_cc issue 601          open     version switching
ramses_cc issue 834          open     BDR hotwater_valve vs appliance_control classification
ramses_cc issue 767          open     device health tracking (PR 861 implements item 7)
ramses_cc issue 857          open     Test with ha_sim_test before every release
```


<a id="alignment-matrix"></a>
### Alignment Matrix

```
OUR PLAN                | RAMSES_RF PLAN          | STATUS
------------------------|-------------------------|----------
schema as SSOT          | #530 Phase 3.3:         | ALIGNED
                        | known_list seeding      | Our derived known_list
                        |                         | = their seed

traits in schema        | #191: PWhite-Eng        | PARTIAL ALIGNMENT
(_class, _alias,        | proposed "traits" as    | Their "traits" = Builder
 _faked, _scheme,       | strategy list           | strategies, not device
 _bound)                |                         | properties. Different
                        |                         | concept, same name.

_scheme trait           | #87: need manufacturer  | ALIGNED
                        | in schema               | Our _scheme addresses
                        |                         | this

enforce_known_list      | Not explicitly in       | VERIFY FIRST
always-on               | roadmap                 | ramses_cc 677 (closed,
                        |                         | fixed 0.57.6): verify
                        |                         | fix before always-on.

eavesdrop obsolete      | Not in roadmap          | NO CONFLICT
                        |                         | But their Builder
                        |                         | pattern may make
                        |                         | eavesdrop irrelevant
                        |                         | differently

block_list obsolete     | Not in roadmap          | NO CONFLICT

DiscoveryScan           | ramses_cc issue 627:    | ALIGNED
(observer path)         | finding devices on      | Our observer addresses
                        | clean system            | this. NOTE: ramses_rf
                        |                         | also has an issue 627
                        |                         | (CODES_SCHEMA reloc,
                        |                         | unrelated — different
                        |                         | "schema"!)

cache → config sync     | Not in roadmap          | NO CONFLICT
                        |                         | ramses_cc-specific

commands in schema      | Not in roadmap          | NO CONFLICT
                        |                         | ramses_cc-specific

HVAC topology (load_fan, | #530 Phase 3: Builder   | ALIGNED — Builder
FAN as Parent, HVAC     | pattern may replace     | strategies could
binding rules)          | static FAN class        | handle HVAC parent/child

dual-role CO2+REM       | #530 Phase 3.1: dynamic | ALIGNED — dynamic
                        | strategy (mutable)      | strategies could
                        |                         | allow CO2 + REM on
                        |                         | same device shell

migration v1→v2→v3→v4   | #530 has its own        | NEEDS COORDINATION
                        | phases 1→2→3→4          | Our migration must
                        |                         | align with their phases
```


<a id="key-conflicts-bottlenecks"></a>
### Key Conflicts & Bottlenecks

**1. "class" will be ignored in the future (silverailscolo)**

silverailscolo explicitly stated in Discussion #191:
> "Using 'class' in this context is confusing, as device (software)
> classes made this whole exercise necessary. We can replace it with
> some manufacturer+model+revision+options code... Existing class
> entries in config will be ignored in the future."

Our plan has `_class` as a trait in the schema. This conflicts with
silverailscolo's direction. The resolution (updated Jul 17 2026):
- Our `_class` is the schema identity trait — NOT temporary
- Builder/Strategy pattern scrapped; `_class` stays as-is
- Our `_scheme` (HVAC vendor) is closer to what silverailscolo wants
- No `_profile` or `_strategy` keys needed — "init and go" from `_class`

**2. User overrides: "winning" vs "flagging"**

Our plan: config wins for scalars (user override takes precedence).
silverailscolo: prefer flagging mismatches to user rather than
silently winning.

This is a UX difference, not a technical conflict. We could:
- Apply the override (current plan)
- Log a warning when override differs from detected
- Show a "mismatch" flag in the config flow review step
- Both: apply override AND flag for review

**3. "traits" name collision**

PWhite-Eng originally proposed `"traits": ["RelayStrategy", "SensorStrategy"]`
— a list of Builder strategy names. **This concept has been scrapped**
(Jul 17 2026). Our plan uses "traits" for device properties (class,
alias, faked, scheme, bound). No conflict — the Builder strategy names
are no longer planned.

Resolution: our traits stay as `_class`, `_alias`, etc. No
`_strategies` or `_profile` keys needed.

**4. enforce_known_list bugs (ramses_cc issue 677) — CLOSED**

Issue 677 ("0.56.8 Evohome device discovery inconsistent",
https://github.com/ramses-rf/ramses_cc/issues/677) is now **closed**
(fixed in milestone 0.57.6, Jun 2026). The workaround was real —
peternash confirmed in comments: "I can get it to load if I turn off
'enforce known ids'". The fix landed, but before making
enforce_known_list always-on we should:
- Verify the 0.57.6 fix holds on real Evohome systems
- Check no users still rely on the disable-workaround

Downgraded from **blocker** to **verify-before-shipping**.

**5. CPU ramp up + discovery issues (ramses_cc issue 666) — CLOSED**

Issue 666 ("0.56.7 CPU ramp up and discovery issues",
https://github.com/ramses-rf/ramses_cc/issues/666) is also **closed**.
CPU ramped up over hours until HA restarted; zones unavailable after
cache clear. Our observer path (DiscoveryScan) should still be
profiled to verify the raw packet handler doesn't reintroduce
CPU growth (it's on the per-packet hot path).

**6. CQRS refactor timing**

The ramses_rf CQRS refactor (#530) is ongoing:
- Phase 2.95 CQRS State Ingestion: MERGED (PR 780 rewired
  gateway.get_state() to L7 MessageStore; PR 782 open adds
  addr1/2/3 keys for ramses_cc known_list enforcement)
- Step F5 ("The Great Lobotomy" — delete legacy dicts): UNBLOCKED
  per PWhite-Eng, not yet executed
- Phase 3 (Strict DTO Boundaries, issue 714): not started
- Phase 3.75 (Identity Composition, "init and go"): **PR 914 open (draft)**
  — eradicates dynamic `__class__` mutations. **Tested with ha_sim_test:
  232/232 pass** (Jul 23 2026). No regressions in ramses_cc.
- StateUpdatedEvent bus: confirmed by PWhite-Eng as the future
  signal source for ramses_cc entity updates (Step 4).  However,
  issue 794 shipped an interim solution in 0.58.0: the coordinator
  emits SIGNAL_UPDATE via an _on_packet msg handler with
  asyncio.sleep(0) as the yield strategy.  This means Step 4 is
  functionally done — StateUpdatedEvent remains a future upgrade
  for deterministic ingestion-complete signalling, but it is no
  longer a blocker.

Our schema changes align as agreed:
- Step 2 (Schema SSOT + Passive Scan, PR 764): DONE
- Step 2.5 (Migration scaffolding, PR 810): DONE
- Step 3a (Commands in schema, PR 811): DONE, awaiting review
- Step 3 (Strict DTOs): after Phil's Phase 2.95 F5
- Step 4 (Coordinator SIGNAL_UPDATE wiring): DONE (interim, issue 794).
  The coordinator owns signal emission via _on_packet (registered with
  add_msg_handler); event.py is slimmed (no longer load-bearing);
  should_poll + async_update + poll_codes add a poll-driven path for
  entities that opt in.
  StateUpdatedEvent from CQRS StateProjector is no longer a blocker
  — it remains a future upgrade to replace asyncio.sleep(0) with a
  deterministic ingestion-complete hook.


<a id="recommendations"></a>
### Recommendations

```
1. COORDINATE with ramses_rf maintainers (silverailscolo, PWhite-Eng)
   - Share our schema_architecture.md
   - ramses_rf Phase 3/3.25 DONE (shipped 0.58.3, current pin 0.59.0)
   - ramses_rf Phase 3.75 PR 914 (draft) — tested 232/232 ha_sim_test pass
   - ramses_rf PR 917 (open) — BDR hotwater_valve domain fix (our contribution)

2. VERIFY enforce_known_list fix BEFORE making it always-on
   - ramses_cc issue 677 closed (fixed in 0.57.6)
   - Test with real Evohome systems to confirm fix holds

3. _class STAYS (no deprecation needed)
   - Builder/Strategy pattern scrapped (Jul 17 2026)
   - _class is the schema identity trait — "init and go"
   - _scheme (HVAC vendor) is the model for future traits
   - No _profile or _strategy key needed

4. IMPLEMENT flagging, not just winning
   - When user override differs from detected: log warning
   - Show mismatch in config flow review step
   - Still apply override (don't leave device broken)

5. SEPARATE our migration from their migration
   - Our v1→v2 (traits in schema) is ramses_cc-only
   - Their Phase 3 (Builder) is ramses_rf-only
   - Coordinate timing but keep migration logic separate
   - Our schema format can adapt to their Builder when ready

6. ADDRESS ramses_cc issue 627 (finding devices on clean system)
   - Our DiscoveryScan observer path is the solution
   - But also: cache → config sync means schema is always rich
   - On fresh start (cache cleared), schema is minimal again
   - Need: query CTL for zone map (000C) on startup to rebuild

7. PRIORITIZE HVAC topology (HVAC) — biggest gap
   - load_fan stub means HVAC schema is generated but ignored
   - gateway.schema() flattens HVAC to orphans_hvac (roundtrip bug)
   - No HVAC binding rules in TopologyBuilder
   - CO2 dual-role unsupported
   - This is a ramses_rf PR — coordinate with maintainers
   - Workaround in ramses_cc: cache HVAC schema separately

8. CLARIFY 30: prefix — is it always FAN/PIV?
   - 30: is RFG (relay gateway) in ramses_rf, 32: is FAN
   - _strip_schema_extensions moves both to orphans_hvac if no remotes/sensors
   - Both are treated as HVAC controllers by ramses_cc
```


[top](#schema-as-source-of-truth-architecture)
<a id="guide-on-updating-this-plan"></a>
## Guide on updating this plan

This is a large doc, if you make any changes, please add a comment below
on what was changed. I keep and edit this file local and don't want to
copy/paste over changes someone else made, without an easy way to find
those changes.

### Changes Jul 23 2026

- Updated verification status table: added PRs 914, 916, 917, 918, 919
  (ramses_rf) and PR 861 (ramses_cc). Added issues 834, 767, 857.
- Updated Phase 3.75 note: PR 914 is draft, tested 232/232 ha_sim_test pass.
- Updated CQRS refactor timing section: added Phase 3.75 PR 914 status.
- Updated recommendations: added PR 917 and PR 914 test results.
- Fixed stale 0.58.3 references: manifest now pins 0.59.0 (131 commits
  since 0.58.3, including our fixes 834/840/822/835/843/851/852 and
  PWhite-Eng refactors). PR 914 and PR 917 NOT in 0.59.0.
- Fixed stale Phase 3d status: was "ready for PR", actually merged via PR 839.


[top](#schema-as-source-of-truth-architecture)
