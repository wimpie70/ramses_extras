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
   **Note:** 22B0 (calendar) builder shipped in 0.59.0 (PR 879). Per-manufacturer
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
  Phase 3e (DONE in 0.59.0): 3e.1 CLI compat (strip_and_map_schema
  called by gateway.py), 3e.2 22B0 builder (build_set_program_enabled).
  Neither affects ramses_cc, but both now available.
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
