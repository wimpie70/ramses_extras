# Phase 3 Plan: Commands in Schema + ramses_rf Alignment

**Created:** Jul 2026
**Status:** Phase 2.5 DONE (PR 810) — Phase 3a DONE (PR 811, merged) — Phase 3b DONE (merged) — Phase 3c DONE (in master) — Phase 3d DONE (`feature/phase3d-alignment`, ready for PR) — Phase 3e BLOCKED (ramses_rf-side)
**Depends on:** Phase 2 (DONE, PR 764), Phase 2.5 (DONE, PR 810, migration scaffolding)
**Phase 3d depends on:** ramses_rf 0.58.3 (DONE — `strip_and_map_traits()` + CQRS CommandDispatcher shipped)

> **Naming note (updated Jul 19 2026):** There are several "Phase 3"s:
> - **ramses_cc Phase 3** (this doc) — commands in schema, our work.
>   Split into **3a** (commands on REM, PR 811, DONE), **3b**
>   (commands on FAN with packet templates, DONE, merged), **3c** (flagging,
>   DONE, in master), and **3d** (ramses_rf alignment, DONE —
>   `feature/phase3d-alignment`, ready for PR). **3e** (CLI compat +
>   22B0 builder, BLOCKED on ramses_rf).
>   See `phase3b_fan_commands_design.md`.
> - **ramses_rf Phase 3/3.25** (PWhite-Eng, issue 639) — **TX Generation
>   Parity + Transport Layer Decoupling**. Moves command-building and
>   payload validation out of `ramses_tx` to L7 inside `ramses_rf`.
>   **DONE — shipped in 0.58.2/0.58.3 (Jul 16-17 2026).** Brought:
>   - CQRS `CommandDispatcher` + domain builders (`zones.py`, `dhw.py`,
>     `hvac.py`, `heat.py`, `schedules.py`, `faultlog.py`, `opentherm.py`)
>   - `SCH_TRAITS_HVAC` accepts `str | list[str]` for binding arrays
>   - `strip_and_map_traits()` / `strip_and_map_schema()` as pre-validation
>     pipeline — the **functions** live in ramses_rf now, but nothing in
>     ramses_rf calls them yet (verified 0.58.3: no callers in `gateway.py`
>     or `ramses_cli`). CLI support for `_`-prefixed keys still needs
>     ramses_rf-side wiring.
>   - **Not yet implemented:** 22B0 (calendar) builder, per-manufacturer
>     HVAC strategy profiles, CLI wiring of the strip+map pipeline, a
>     `commands` trait in `SCH_TRAITS` (`_commands` is *stripped*, not
>     mapped — see correction below). These may come in a later
>     ramses_rf release.
> - **ramses_rf Phase 3.75** (PWhite-Eng, issue 639) — **Identity
>   Composition**. Was originally "Builder Pattern" (issue 530), now
>   reframed as "init and go": devices instantiate with correct, final
>   roles from schema traits — no runtime `__class__` mutation.
>
> **Key shift (Jul 17 2026, updated Jul 19):** PWhite-Eng scrapped the **device identity**
> part of the Builder pattern (`DeviceRole` composition, active discovery
> FSM, `supported_commands()` as a strategy method) in favor of "init and
> go" from schema. The **CQRS TX builders** (22F1, 22F7, 2411, 31DA, etc.)
> **shipped in 0.58.3** (Jul 17 2026). **Not yet:** 22B0 (calendar) builder,
> per-manufacturer HVAC strategy profiles. These are two different things:
>
> | Aspect | Status | Where |
> |---|---|---|
> | Device identity (`DeviceRole`, `__class__` replacement) | **Scrapped** — "init and go" from `_class` | Phase 3.75 |
> | TX generation (CQRS builders: 22F1, 22F7, 2411, 31DA, etc.) | **DONE** — shipped 0.58.3 | Phase 3/3.25 |
> | TX generation (22B0 calendar builder) | **Not yet** | Future ramses_rf |
> | Per-manufacturer HVAC strategy profiles | **Not yet** | Future ramses_rf |
> | `supported_commands()` as strategy method | **Scrapped** | — |
> | `strip_and_map_traits()` in ramses_rf | **DONE** — shipped 0.58.2 | Phase 3/3.25 |
> | `_commands` as user override | **Confirmed** | ramses_cc only (ramses_rf strips it; CLI support blocked on ramses_rf wiring) |
>
> **`_commands` location (corrected Jul 18 2026):** Currently `_commands`
> lives in ramses_cc's config entry schema only. ramses_cc strips
> `_`-prefixed keys before passing the schema to ramses_rf. The CLI
> (which uses ramses_rf directly) cannot use `_commands` today — and
> **still can't in 0.58.3**: `strip_and_map_schema()` exists in ramses_rf
> but nothing in ramses_rf (Gateway or CLI) calls it. Also, contrary to
> earlier versions of this note, `_commands` does **NOT** map to
> `commands` inside ramses_rf — `_TRAIT_KEY_MAP` only maps
> `_bound/_scheme/_alias/_faked/_class`; `_commands` is stripped (stage 1),
> and `SCH_TRAITS_*` (PREVENT_EXTRA) has no `commands` key. CLI support
> for `_commands` needs two ramses_rf-side changes: (a) wire the pipeline
> into CLI/Gateway config loading, (b) accept a `commands` trait (or keep
> `_commands` ramses_cc-only). Coordinate with PWhite-Eng.
>
> **`_class` deprecation:** `_class` is **NOT deprecated**. PWhite-Eng's
> "init and go" approach *uses* `_class` from the schema to instantiate
> devices with the correct class. silverailscolo's longer-term vision
> (manufacturer+model+revision from 10E0) is a future enhancement, not a
> replacement.

---

## Table of Contents

- [Overview](#overview)
- [Two Phase 3s — Don't Confuse Them](#two-phase-3s--dont-confuse-them)
- [Current State](#current-state)
- [Goals](#goals)
- [PWhite-Eng's ramses_rf Phase 3 (TX Generation + Identity Composition)](#pwhite-engs-ramses_rf-phase-3)
- [ramses_cc Phase 3 (Commands in Schema)](#ramses_cc-phase-3-commands-in-schema)
- [Alignment Points](#alignment-points)
- [Implementation Plan](#implementation-plan)
- [Migration](#migration)
- [Risks & Mitigations](#risks--mitigations)
- [Open Questions](#open-questions)
- [Decision Log](#decision-log)

---

<a id="overview"></a>
## Overview

Phase 3 is the next step in the schema-as-SSOT migration. It has two
parallel tracks that must be coordinated but kept separate:

1. **ramses_cc Phase 3** — Move remote commands from `.storage/ramses_cc[remotes]`
   and `known_list[device_id][commands]` into the schema as `_commands`.
2. **ramses_rf Phase 3** (PWhite-Eng) — Replace static device classes with a
   dynamic Builder/Strategy pattern, using `known_list` as a seeding mechanism.

These tracks are complementary: ramses_cc's schema becomes the seed for the Builder.

---

<a id="two-phase-3s--dont-confuse-them"></a>
## Two Phase 3s — Don't Confuse Them

| | ramses_cc Phase 3 | ramses_rf Phase 3/3.25 + 3.75 (issue 639) |
|---|---|---|
| **What** | Commands move to schema as `_commands` | 3/3.25: TX Generation Parity + Transport Decoupling. 3.75: Identity Composition (deprecate `__class__`, "init and go") |
| **Who** | wimpie70 / ramses_cc | PWhite-Eng / ramses_rf |
| **Repo** | ramses_cc | ramses_rf |
| **Status** | 3a DONE (PR 811), 3b DONE (merged), 3c DONE (in master), 3d DONE (`feature/phase3d-alignment`), 3e BLOCKED (ramses_rf) | 3/3.25 DONE (shipped 0.58.3). 3.75 planned (Builder/Strategy scrapped) |
| **Depends on** | 3a: strip workaround (DONE). 3b: no ramses_rf PR needed (packet templates). 3d: ramses_rf 0.58.3 (DONE) | Phase 2 complete (SQLite + RAM cache) |
| **Blocks?** | No — 3a, 3b, 3c shipped independently. 3d benefits from ramses_rf 0.58.3 | No — shipped without ramses_cc's `_commands` alignment |
| **Key change** | — | Builder/Strategy pattern **scrapped** (Jul 17 2026). Replaced by "init and go" from schema. `DeviceRole` composition scrapped. |

**ramses_cc Phase 3 split:**
- **Phase 3a (DONE, PR 811):** `_commands` on REM entries in schema,
  full packet strings. Services write to schema. Migration from
  `.storage[remotes]` + `known_list[commands]`.
- **Phase 3b (DONE, merged):** `_commands`
  moves to FAN entries as `{verb, code, payload}` dicts. Packet template
  builder fills addresses at send time. `remote.py` entity on FAN.
  Runtime migration REM → FAN (no store version bump). See
  `phase3b_fan_commands_design.md`.
- **Phase 3c (DONE, PR 831):** Flagging mismatches — persistent
  notification, entity attributes, bound/missing_class/orphaned detection,
  unified `check_all_mismatches()`. 6 bug fixes for owner handling and
  schema safeguard included.
- **Phase 3d (DONE — `feature/phase3d-alignment`, ready for PR):**
  ramses_rf alignment — 5 actionable steps, all complete:
  - **3d.8** — remove dead `ImportError` fallback (manifest pins 0.58.3)
  - **3d.3** — `strip_traits_for_validation` delegates stage 1 to ramses_rf
  - **3d.3b** — consolidate drifted stage-3 orchestration into one shared
    function `_strip_and_orchestrate` (orphan routing, disabled/skipped/
    foreign filtering, HGI dropping); unify 3 separate `_HEAT_PREFIXES`
    definitions; fix `placed_in_lists` bug in coordinator path
  - **3d.4** — pass `_bound` as `str | list[str]` to ramses_rf (remove
    str-only guard in `_derive_known_list_from_schema`)
  - **3d.6** — precedence tests: `_commands` override wins over CQRS
    builder (test-only, no code change)

  1103 tests pass, ruff + mypy clean. Net -130 lines.
  See `phase3d_design.md` and `phase3d_pr.md`.
- **Phase 3e (BLOCKED on ramses_rf):** CLI compat + 22B0 builder —
  neither affects ramses_cc. Split out from 3d so 3d can merge now.
  - **3e.1** (was 3d.5) — CLI compat: ramses_rf has no callers for
    `strip_and_map_schema`; needs ramses_rf-side wiring
  - **3e.2** (was 3d.7) — 22B0 calendar builder: no builder in 0.58.3

**Key insight:** ramses_cc's Phase 3a shipped using the same
`_strip_schema_extensions` workaround as Phase 2. Phase 3b moved commands
to FAN using packet templates — no ramses_rf PR needed. The coordinator
already delegates stage 1 to ramses_rf's `strip_traits` and uses
`strip_and_map_traits` for known_list derivation (with a local fallback
for older ramses_rf). Phase 3d finishes the consolidation on the
ramses_cc side; CLI-side wiring stays with PWhite-Eng.

---

<a id="current-state"></a>
## Current State

### Where commands live today

Commands (learned RF payloads for REM entities) are stored in **two** places:

1. **`.storage/ramses_cc[remotes]`** — the primary store, persisted every 5 min
   ```json
   "remotes": {
     "32:153001": {
       "turn_on": "I --- 32:153001 18:006402 --:------ 22F1 003 000030",
       "speed_1": "I --- 32:153001 18:006402 --:------ 22F1 003 000031"
     }
   }
   ```

2. **`config_entry.options[known_list][device_id][commands]`** — legacy path,
   extracted at config flow time and merged into `remotes` at startup
   ```json
   "known_list": {
     "32:153001": {
       "class": "REM",
       "faked": true,
       "commands": {"turn_on": "I --- ... 22F1 003 000030"}
     }
   }
   ```

### How commands flow

```
Config flow → known_list[dev][commands] → extracted to remotes dict
                                          ↓
.storage[remotes] ←─── coordinator._remotes (merged at startup)
        ↑
        │ every 5 min + shutdown
        │
remote.py: self._commands = coordinator._remotes.get(device.id, {})
         ↑
         │ learn_command / add_command / delete_command
         │
    HA UI (remote.learn_command service)
```

### What reads commands

- `remote.py:96` — `self._commands = coordinator._remotes.get(device.id, {})`
- `remote.py:280` — `Command(self._commands[command[0]])` to send
- `remote.py:104` — exposed as `extra_state_attributes["commands"]`
- `coordinator.py:1826-1831` — on save, reads `_commands` attr from entities
  back into `_remotes` for persistence

### What writes commands

- `remote.py:192` — `learn_command` saves learned packet to `self._commands`
- `remote.py:351` — `add_command` saves raw packet string to `self._commands`
- `remote.py:133` — `delete_command` removes from `self._commands`
- `coordinator.py:342-347` — at startup, merges `known_list[dev][commands]`
  into `_remotes`

**Problem:** Commands are NOT in the schema. They survive cache clears
(via config entry `known_list`), but they don't follow the SSOT pattern.
A user who clears the cache loses learned commands unless they're also
in `known_list` (which is being deprecated).

---

<a id="goals"></a>
## Goals

1. **Commands live in the schema** as `_commands` per-device trait
2. **`_strip_schema_extensions` strips `_commands`** before ramses_rf sees it
   (same pattern as `_alias`, `_class`, etc.)
3. **A new `_derive_remotes_from_schema` extracts `_commands`** into the
   `_remotes` dict that `remote.py` reads (separate from
   `_derive_known_list_from_schema`, which goes to ramses_rf)
4. **Config flow UI can edit commands** in the schema editor
5. **`learn_command` / `add_command` write to schema** (via config entry update)
6. **`.storage[remotes]` becomes a cache**, not the primary store
7. **`known_list[dev][commands]` deprecated** — commands read from schema

---

<a id="pwhite-engs-ramses_rf-phase-3"></a>
## PWhite-Eng's ramses_rf Phase 3 (TX Generation + Identity Composition)

> **Updated Jul 19 2026:** PWhite-Eng scrapped the **device identity**
> part of the Builder pattern (`DeviceRole` composition, active discovery
> FSM, `supported_commands()` as a strategy method) in favor of "init and
> go" from schema. The **CQRS TX builders** (22F1, 22F7, 2411, 31DA, etc.)
> **shipped in 0.58.3** (Jul 17 2026). **Not yet:** 22B0 (calendar),
> per-manufacturer HVAC strategy profiles. These are two different things — don't conflate them.

From ramses_rf issue 639 (master roadmap), issue 836, and ramses_cc issue 809:

### ramses_rf Phase 3/3.25: TX Generation Parity + Transport Decoupling

Moves the entire command-building and payload validation stack out of
`ramses_tx` and elevates it to L7 inside `ramses_rf`. This is where
native builders for `22F7` (bypass), `22B0` (calendar), etc. live.

**What shipped (0.58.2/0.58.3, Jul 16-17 2026):**
- CQRS `CommandDispatcher` + domain builders (`zones.py`, `dhw.py`,
  `hvac.py`, `heat.py`, `schedules.py`, `faultlog.py`, `opentherm.py`)
- TX builders for standard codes: 22F1 (fan mode), 22F7 (bypass),
  2411 (fan param), 31DA (fan info), 1298 (CO2), 12A0 (humidity),
  plus zones/DHW/heat/schedules/OpenTherm builders
  → these become **defaults**; `_commands` overrides them
- `SCH_TRAITS_HVAC` accepts `str | list[str]` for binding arrays
  → our `_bound` as list works without strip+map workaround
- `strip_and_map_traits()` / `strip_and_map_schema()` as pre-validation
  pipeline in ramses_rf → the functions exist, but **nothing in
  ramses_rf calls them yet** (no callers in Gateway or CLI, verified
  0.58.3). CLI can NOT use `_commands`/`_bound` in config.json yet.

**Not yet shipped (future ramses_rf):**
- 22B0 (calendar) builder — no builder exists yet
- Per-manufacturer HVAC strategy profiles — no strategy/profile concept
  in the code yet
- CLI/Gateway wiring of `strip_and_map_schema()` — functions exist but
  have no callers inside ramses_rf
- `commands` trait in `SCH_TRAITS` — `_commands` is stripped, not mapped

**Relevance to ramses_cc:**
- Native TX builders are the **default** write pathway for standard
  commands. Our `_commands` stays as the **authoritative user override**
  layer — if a user defines `bypass_open` in `_commands`, it overrides
  the native builder.
- `_commands` currently lives in ramses_cc only (stripped before
  ramses_rf sees it) — and stays that way for now: ramses_rf strips
  `_commands` (it's not in `_TRAIT_KEY_MAP`) and has no `commands`
  trait in `SCH_TRAITS`. CLI support needs ramses_rf-side wiring +
  a `commands` trait (coordinate with PWhite-Eng).
- `_class` is **NOT deprecated** — "init and go" uses `_class` from
  schema to instantiate devices with the correct class.

### ramses_rf Phase 3.75: Identity Composition (was "Builder Pattern")

Originally issue 530 proposed a Builder/Strategy pattern with
`DeviceRole` composition and `supported_commands()`. The **device
identity** part has been **scrapped** (Jul 17 2026).

**What's scrapped (device identity side):**
- `DeviceRole` composition pattern (replacing `__class__` mutation)
- Active discovery FSM (probing to discover device type)
- `supported_commands()` as a strategy method

**New approach — "init and go":**
- Devices instantiate with their correct, final roles derived directly
  from the schema traits (`_class`) — no runtime `__class__` mutation.
- Legacy `__class__` mutations will be deprecated and removed.
- Newly discovered passive bounds (like `1FC9` payloads) are routed
  directly into a `TopologyChangedEvent` so the consumer (ramses_cc)
  can update the schema.

**Relevance to ramses_cc:**
- Our schema-as-SSOT approach already delivers this: when the schema
  changes, we tear down and rebuild with correct classes from `_class`.
- `_class` stays as the schema-driven identity trait — NOT deprecated.
  silverailscolo's longer-term vision (manufacturer+model+revision from
  10E0) is a future enhancement, not a replacement.
- `_commands` stays as the user override layer on schema entries —
  it does NOT move to `supported_commands()` on strategies (that
  concept is gone). CQRS TX builders (shipped 0.58.3) provide
  defaults for standard codes (22F1, 22F7, 2411, 31DA). 22B0 (calendar)
  not yet implemented.

### silverailscolo's question (issue 836, Jul 17 2026)

> "If we reset upon every (user initiated) change to the schema, do we
> need class promotion _during running_? Just take the role as in the
> schema, init and go."

**Answer: YES, ramses_cc's config schema can deliver this.**

Current behavior in ramses_cc (with eavesdrop disabled, schema as SSOT):
1. User changes schema → `async_update_entry` → coordinator reload
2. Old gateway torn down → new gateway created
3. New gateway reads schema → creates devices with correct `_class` from
   the start — no `__class__` mutation needed
4. Devices are fully functional at t=0

The gap: ramses_rf still has `__class__` mutation code for eavesdrop
mode. But in schema-SSOT mode, it's not exercised. PWhite-Eng's
Phase 3.75 will deprecate that code path entirely.

**What's still needed for full "tear down and rebuild via packet replays":**
- ramses_rf's SQLite store (Phase 2.95) can replay historical packets
  through new device instances to populate their state — this is the
  "packet replay" part that silverailscolo mentions.
- ramses_cc doesn't currently trigger packet replays on schema update,
  but the infrastructure is there (SQLite store exists). This could be
  a future enhancement.

### silverailscolo's concerns (still valid)

- Users can enter incorrect `_class` — prefer **flagging** over silent
  override (Phase 3c addresses this)
- Manual YAML won't work for complex configs — need pick list or 10E0
  codes (config flow UI handles this)
- Commands should be on the **device that handles them** (FAN, ...),
  not on the faked REM — **DONE in Phase 3b**

### wimpie70's input (Discussion 191, Feb 7 2026)

> "Currently commands are configured on the (faked) REM devices. I think
> it would be better to provide them on the device that will handle that
> command: the FAN, or the heater."

**Status:** DONE in Phase 3b. Commands are now on FAN entries as
`{verb, code, payload}` dict templates. REM entries kept for backward
compat (downgrade safety).

---

<a id="ramses_cc-phase-3-commands-in-schema"></a>
## ramses_cc Phase 3 (Commands in Schema)

### Step 1: Add `_commands` to schema trait constants

```python
# const.py
SZ_TR_COMMANDS: Final = "_commands"
```

No need to add to `_SCHEMA_EXTENSION_KEYS` — `_strip_schema_extensions`
already strips all `_` prefixed keys at both root level and nested device
level (via `_strip_traits`). `_SCHEMA_EXTENSION_KEYS` is only for
non-`_`-prefixed keys like `device_comments` and `owner`.

### Step 2: Write `_commands` to schema

When `learn_command` / `add_command` / `delete_command` is called:

```
remote.py learns command
  → coordinator._update_schema_commands(device_id, commands)
  → config_entry.options[schema][device_id][_commands] = commands
  → hass.config_entries.async_update_entry(entry, options=...)
  → .storage saved on next 5-min cycle
```

This replaces the current flow where `remote.py` mutates `self._commands`
and `coordinator.py` reads it back on save.

### Step 3: Read `_commands` from schema at startup

**Important:** `_commands` must go into `coordinator._remotes` (which
`remote.py` reads), NOT into the derived known_list (which goes to
ramses_rf). ramses_rf already strips `commands` from known_list traits
at `coordinator.py:1476-1484` — it never receives commands via
known_list. Commands are a ramses_cc-only concept.

Use a new `_derive_remotes_from_schema` function, separate from
`_derive_known_list_from_schema`:

```python
# coordinator.py, in _async_load_storage (after line 347)
schema = self.options.get(CONF_SCHEMA, {})
remotes_from_schema = {
    dev_id: entry.get(SZ_TR_COMMANDS, {})
    for dev_id, entry in schema.items()
    if isinstance(entry, dict) and SZ_TR_COMMANDS in entry
}
# Schema _commands takes precedence over .storage[remotes] (SSOT)
self._remotes = storage.get(SZ_REMOTES, {}) | remotes_from_schema
```

The existing startup merge at `coordinator.py:342-347` (known_list
commands → `_remotes`) stays as a fallback for unmigrated users.

**Precedence (highest wins):**
1. Schema `_commands` (SSOT — user edits, learn_command writes here)
2. `.storage[remotes]` (cache — learn_command writes here first, synced
   to schema on 5-min cycle)
3. `known_list[dev][commands]` (legacy fallback — config flow entries)

### Step 4: Migration — move existing commands to schema

One-time migration (similar to `_sync_known_list_traits_to_schema`,
a coordinator method at `coordinator.py:1307`):

```python
def _sync_remotes_to_schema(schema, remotes):
    for device_id, commands in remotes.items():
        if not commands:
            continue
        if SZ_TR_COMMANDS not in schema.get(device_id, {}):
            schema.setdefault(device_id, {})[SZ_TR_COMMANDS] = commands
```

Run after `sync_learned_topology` backfill (note: `sync_learned_topology`
can return `None` if no topology changes — handle that case), before
`_strip_schema_extensions`.

### Step 5: Deprecate `known_list[dev][commands]`

After migration, `commands` in `known_list` is redundant. The config flow
should stop writing commands there. The extraction at
`coordinator.py:342-347` becomes a fallback for users who haven't migrated.

### Step 6: Config flow UI for command editing

The schema step in `config_flow.py` (`async_step_schema`) should support
editing `_commands` per device. This is a UI change — the schema validator
already accepts `_` prefixed keys (they're stripped before ramses_rf).

**Alternative:** Keep `learn_command` / `add_command` services as the
primary editing path, and just persist to schema instead of `.storage`.

---

<a id="alignment-points"></a>
## Alignment Points

### 1. ramses_cc's `_commands` → their `supported_commands()`

PWhite-Eng's Builder strategies will define `supported_commands()` per
strategy. ramses_cc's `_commands` in the schema should be the **override** layer:

```
ramses_rf Builder strategies → default commands (learned/auto)
schema _commands             → user override (wins over Builder)
```

This follows the same precedence as other traits:
ramses_rf learns/detects → schema overrides if present.

### 2. Commands on FAN, not REM

wimpie70's direction (Discussion 191): commands should be on the device
that **handles** them, not the faked REM that sends them.

**Phase 3a (DONE, PR 811):** Commands on REM device IDs in the schema —
this is what `remote.py` expects. The `_commands` key goes on the
REM's schema entry. Full packet strings.

**Phase 3b (DONE):** Commands moved to FAN schema entries as
`{verb, code, payload}` dicts. The `remote.py` entity now exists on
both REM and FAN (REM kept for backward compat). Standard modes go
through `climate.set_fan_mode` → `device.set_fan_mode()` (PR 546).
Only non-standard commands (22F7 bypass, 22B0 calendar) stay in
`_commands`. Packet template builder fills src/dst/length at send
time — no hardcoded REM address. See `phase3b_fan_commands_design.md`.

**Long term (ramses_rf 0.58.3 shipped CQRS builders):** TX builders for
22F1/22F7/2411/31DA are now defaults. `_commands` stays as the authoritative
user override — if a user defines `bypass_open` in `_commands`, it overrides
the CQRS builder. The faked REM just sends what the FAN entity tells it to.
22B0 (calendar) builder not yet available.

**Migration path:** Phase 3a → 3b runtime migration copies `_commands`
from REM entries to FAN entries as dict templates (REM entries kept
for downgrade safety). This did NOT wait for ramses_rf CQRS builders —
packet templates bridged the gap until they landed in 0.58.3.

### 3. `_class` deprecation

silverailscolo: "Existing class entries in config will be ignored in
the future."

ramses_cc's `_class` trait is a temporary override. When the Builder is ready:
- `_class` → `_profile` or `_strategy` (maps to Builder strategy name)
- `_scheme` (HVAC vendor) is closer to what silverailscolo wants
  (manufacturer+model+revision+options)
- Plan for `_class` deprecation but don't remove it yet

### 4. "traits" name collision

PWhite-Eng proposed `"traits": ["RelayStrategy", "SensorStrategy"]` —
a list of Builder strategy names. ramses_cc's "traits" are device properties
(`_class`, `_alias`, etc.). Different concepts, same name.

**Resolution:** ramses_cc's traits stay as `_class`, `_alias`, etc. (individual
`_` prefixed keys). Their Builder strategies would be `_strategies` or
`_profile` when implemented. No collision because ramses_cc uses different keys.

### 5. Seeding: ramses_cc's derived known_list IS their seed

Two derivation paths from the same schema (SSOT):

```
PATH A — to ramses_rf (seeding):
  ramses_cc's schema (SSOT)
    → _derive_known_list_from_schema
    → known_list (derived, in-memory, commands stripped)
    → passed to ramses_rf Gateway as gateway_kwargs["known_list"]
    → Builder reads known_list as seed
    → devices pre-created with correct strategies

PATH B — to remote.py entities (commands, ramses_cc-only):
  ramses_cc's schema (SSOT)
    → _derive_remotes_from_schema (NEW, Phase 3a)
    → _remotes (derived, in-memory)
    → read by remote.py entities
    → NOT passed to ramses_rf
```

This is already how it works for traits. The derived known_list (from
`_derive_known_list_from_schema`) is what ramses_rf receives — not the
raw user `known_list` from config entry options. Commands are already
stripped from the derived known_list at `coordinator.py:1476-1484`
before passing to ramses_rf, so moving `_commands` to schema changes
nothing for ramses_rf.

When ramses_rf's Phase 3.3 lands, the Builder will consume ramses_cc's
derived known_list directly. No change needed on ramses_cc's side for
traits. For commands, the Builder's `supported_commands()` per strategy
will be the ramses_rf-side source; ramses_cc's `_commands` in schema is
the override layer (see Alignment Point 1).

---

<a id="implementation-plan"></a>
## Implementation Plan

### Phase 2.5: Migration scaffolding (DONE — PR 810)

**No format change yet — just register the hook so it exists when needed.**

The arch doc (schema_architecture.md, "When to create the migration code")
recommends registering `async_migrate_func` in store.py NOW as a no-op
identity migration (v1 → v1). This avoids the V1 config-flow pain (no
upgrade method) ever recurring: the hook and version label are in place,
so future bumps (v1 → v2 for commands, v2 → v3 for known_list removal)
just add branches to an existing function.

Currently `STORAGE_VERSION = 1`. HA's `Store` system calls the migrate
function automatically on load if the stored data's version differs from
`STORAGE_VERSION`.

**Implementation note:** HA's `Store` class in the current version does
NOT accept a `migrate_func` constructor parameter. The correct approach
(followed by HA's own components like `tag`, `energy`, `knx`) is to
subclass `Store` and override the `_async_migrate_func` method.

| Step | Description | Status |
|------|-------------|--------|
| 2.5.1 | Subclass `Store` as `RamsesCcStore` with no-op `_async_migrate_func` (v1 → v1) | DONE |
| 2.5.2 | Use `RamsesCcStore` in `RamsesStore.__init__` instead of bare `Store` | DONE |
| 2.5.3 | Test: no-op migration returns v1 data unchanged, subclass is wired up | DONE |

```python
# store.py — scaffolding (no format change yet)
class RamsesCcStore(Store[dict[str, Any]]):
    """HA Store subclass with a migration hook for ramses_cc .storage."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate stored data to the current version.

        Currently v1 → v1 (identity). Future versions will add branches:
        - v1 → v2: commands moved to schema _commands (Phase 3a)
        - v2 → v3: known_list removed, fully derived from schema (Phase 4)
        """
        return old_data

# In RamsesStore.__init__:
self._store = RamsesCcStore(hass, STORAGE_VERSION, STORAGE_KEY)
```

### Phase 3a: Commands in schema (ramses_cc only, no ramses_rf PR needed) — PR 811

**Can ship independently of ramses_rf Phase 3.**

| Step | Description | Status |
|------|-------------|--------|
| 3a.1 | Add `SZ_TR_COMMANDS = "_commands"` to `const.py` | DONE |
| 3a.2 | Verify `_commands` is stripped by `_strip_schema_extensions` (already handled by `_` prefix logic) | DONE |
| 3a.3 | Add `_sync_remotes_to_schema` migration function | DONE |
| 3a.4 | Call migration after `sync_learned_topology` backfill | DONE |
| 3a.5 | Read `_commands` from schema at startup into `_remotes` | DONE |
| 3a.6 | `learn_command` / `add_command` / `delete_command` write to schema | DONE |
| 3a.7 | Config flow schema step supports `_commands` editing (already works via `async_step_schema`) | DONE |
| 3a.8 | Deprecate `known_list[dev][commands]` extraction (keep as fallback) | DONE |
| 3a.9 | ~~Bump `STORAGE_VERSION` to 2~~ — **REVERTED**: storage version stays at 1 (see "Storage version" below) | DONE |
| 3a.10 | Tests: migration, read, write, strip, derive | DONE (11 new tests) |
| 3a.11 | Backup before migration (YAML to ramses_cc_backups/) | DONE |

### Phase 3b: Commands on FAN with packet templates (DONE — no ramses_rf PR needed)

**Did NOT depend on ramses_rf Phase 3/3.25.** Packet templates bridged the gap
until CQRS builders landed in 0.58.3. See `phase3b_fan_commands_design.md` for full design.

| Step | Description | Status |
|------|-------------|--------|
| 3b.1 | Schema format: `_commands` as `{verb, code, payload}` dicts on FAN | DONE |
| 3b.2 | Packet template builder (`_build_packet_from_template` + `_parse_packet_to_template`) | DONE |
| 3b.3 | `remote.py` entity on FAN (`HvacVentilator`) — both REM and FAN get entities | DONE |
| 3b.4 | `send_command` builds from template (FAN) / uses packet string (REM backward compat) | DONE |
| 3b.5 | `learn_command` listens to all bound REMs (FAN) / one src (REM backward compat) | DONE |
| 3b.6 | `climate.py` `fan_modes` reads FAN `_commands` (dicts) + REM `_commands` (strings) | DONE |
| 3b.7 | Runtime migration REM `_commands` → FAN dict templates (no store version bump) | DONE |
| 3b.8 | Config flow — verified no change needed (dicts preserved through round-trip) | DONE |
| 3b.9 | `_discover_new_entities` dispatches FAN to remote platform | DONE |
| 3b.10 | Unit tests: 33 new (23 remote, 9 coordinator migration, 1 climate) — 1026 total | DONE |
| 3b.11 | ha_sim integration tests: R26 (12 checks) + R24/R25 backward compat (16 checks) | DONE |

### Phase 3d: ramses_rf alignment (ramses_rf Phase 3/3.25 has landed)

**Status: DESIGN — see `phase3d_design.md` for full details.**
**ramses_rf 0.58.3 shipped `strip_and_map_traits()` and CQRS CommandDispatcher.**

The ramses_rf dependencies for Phase 3d are now merged:
- PR [820](https://github.com/ramses-rf/ramses_rf/pull/820) — `strip_and_map_traits()` / `strip_and_map_schema()` pipeline + `SCH_TRAITS_HVAC` bound accepts `str | list[str]` (merged Jul 16 2026, released in 0.58.2)
- PR [832](https://github.com/ramses-rf/ramses_rf/pull/832) — recursive `strip_and_map_traits()` + new `strip_traits()` (merged Jul 16 2026, released in 0.58.2)
- PR [842](https://github.com/ramses-rf/ramses_rf/pull/842) — CQRS `CommandDispatcher` + domain builders (`zones.py`, `dhw.py`, `hvac.py`, `heat.py`, `schedules.py`, `faultlog.py`, `opentherm.py`) (merged Jul 17 2026, released in 0.58.3)
- PRs [843](https://github.com/ramses-rf/ramses_rf/pull/843)–[847](https://github.com/ramses-rf/ramses_rf/pull/847) — CQRS Intent cut-over for devices, systems, schedules, fault log, OpenTherm, HVAC (merged Jul 17 2026, released in 0.58.3)

> **ramses_cc manifest already pins `ramses-rf==0.58.3`** (commit `00bdaca`,
> merged from master into `feature/phase3c-flagging`). ramses_cc's
> `services.py` already uses CQRS Intents (`build_dto` + `Intent` from
> `ramses_rf.commands.builders` / `ramses_rf.commands.core`).

**What's verified as available in 0.58.3:**
- `strip_and_map_traits()` / `strip_and_map_schema()` — importable from `ramses_rf.schemas`
- `SCH_TRAITS_HVAC` bound accepts `str | list[str] | None` (config.py:89-93)
- CQRS builders for: 22F1 (fan mode), 22F7 (bypass), 2411 (fan param),
  31DA (fan info), 1298 (CO2), 12A0 (humidity), plus zones/DHW/heat/
  schedules/OpenTherm
- ramses_cc `services.py` uses `build_dto(intent)` for GET_FAN_PARAM and
  SET_FAN_PARAM (lines 359-365, 552-558)

**What's NOT available yet (future ramses_rf):**
- 22B0 (calendar) builder — no builder exists
- Per-manufacturer HVAC strategy profiles — no concept in code

These items were originally part of Phase 3b in the initial plan, but were
split out because they depend on ramses_rf changes. Phase 3b (commands on
FAN) shipped without them. The device identity Builder (`DeviceRole`) is
scrapped, but TX generation CQRS builders (22F1, 22F7, etc.) and
`strip_and_map_traits()` are now available in ramses_rf.

| Step | Description | Status |
|------|-------------|--------|
| 3d.0 | Bump ramses_rf dependency to 0.58.3 | DONE — manifest already pins `ramses-rf==0.58.3` (commit `00bdaca`) |
| 3d.1 | Coordinate TX strategy profile key names with PWhite-Eng (per-manufacturer TX profiles, NOT device identity) | N/A — strategy profiles not yet implemented in ramses_rf |
| 3d.2 | `_class` stays as schema identity trait — no mapping to strategy names needed (DeviceRole scrapped) | N/A |
| 3d.3 | Consolidate stage-1 stripping: `strip_traits_for_validation()` (schemas.py) still has an inline `_strip_traits` duplicate — delegate to ramses_rf's `strip_traits()` like the coordinator already does. **NOT** `strip_and_map_schema()` — `SCH_GLOBAL_SCHEMAS` rejects mapped trait names (`class`, `bound`, `alias`); those belong in the known_list, not the schema | DONE — delegates to ramses_rf's `strip_traits` |
| 3d.3b | Consolidate duplicated stage-3 logic: `strip_traits_for_validation()` and `_strip_schema_extensions()` both do orphan routing / trait-only drop but have drifted (coordinator also handles disabled/skipped/foreign owner, HGI dropping, `None` values). Single shared function + single `_HEAT_PREFIXES` definition (currently 3 prefix sets across the two files) | DONE — shared `_strip_and_orchestrate()` in schemas.py; both callers use it; `placed_in_lists` bug fixed |
| 3d.4 | Pass `_bound` as `str \| list[str]` to ramses_rf — **code change, not just verification**: `_derive_known_list_from_schema` currently drops list-valued `bound` (coordinator.py ~1370-1380). Also re-check the "remove `bound` if no `class`" sanitizer (~1420-1429) — `SCH_TRAITS_HVAC` now defaults `class` to `HVC` | DONE — str-only guard removed; sanitizer only strips bound from heat devices |
| 3d.5 | CLI can use `_commands`/`_bound` in config.json → moved to 3e.1 | BLOCKED (ramses_rf-side) — moved to Phase 3e |
| 3d.6 | Verify CQRS TX builders (22F1, 22F7, 2411) work as defaults, `_commands` overrides them. Add an end-to-end precedence test (`set_fan_mode` with and without `_commands` override) — the precedence lives in ramses_cc and is untested against the new builders | DONE — 4 precedence tests added (test-only, no code change) |
| 3d.7 | 22B0 (calendar) builder — wait for ramses_rf → moved to 3e.2 | BLOCKED — moved to Phase 3e |
| 3d.8 | Cleanup: remove the `ImportError` fallback for `strip_and_map_traits`/`strip_traits` in coordinator.py (~40 lines, comment says "< 0.59.0" but functions shipped in 0.58.2; manifest pins `==0.58.3`) | DONE — ~40 lines removed |

#### Phase 3d implementation plan

1. ~~**Bump ramses_rf pin** to `>=0.58.3`~~ — DONE (manifest already pins 0.58.3).
2. **Consolidate stripping** — make `strip_traits_for_validation()` in
   `schemas.py` delegate stage 1 to `ramses_rf.schemas.strip_traits()`
   (the coordinator's `_strip_schema_extensions` already does this).
   Do **NOT** use `strip_and_map_schema()` here — the result is fed to
   `SCH_GLOBAL_SCHEMAS`, which rejects mapped trait names (`class`,
   `bound`, `alias`); mapping is only for known_list derivation
   (already done via `strip_and_map_traits` in
   `_derive_known_list_from_schema`).  Then unify the drifted stage 3
   logic (orphan routing, HGI dropping, disabled/skipped filtering,
   foreign-owner handling, `_HEAT_PREFIXES`) into one shared function —
   that orchestration stays in ramses_cc.
3. **Pass `_bound` as list** — remove the str-only restriction in
   `_derive_known_list_from_schema` (currently drops list-valued
   `bound`), re-check the "`bound` requires `class`" sanitizer, and test
   that a FAN with `_bound: ["37:170000", "37:170001"]` reaches
   ramses_rf as `bound: ["37:170000", "37:170001"]`.
4. **Verify CQRS Intent builders** — ramses_cc's `services.py` already uses
   `build_dto()` for GET_FAN_PARAM and SET_FAN_PARAM.  Verify that HVAC
   commands (set_fan_mode, boost, bypass) work end-to-end with the new
   builders, and add a precedence test: `_commands` override wins over
   the native builder.  Note: 22B0 (calendar) has no builder yet.
5. ~~**CLI compatibility**~~ — BLOCKED on ramses_rf: `strip_and_map_schema()`
   has no callers inside ramses_rf, so `ramses_cli -monitor` still
   rejects config.json with `_commands`/`_bound` keys (`PREVENT_EXTRA`).
   Needs ramses_rf-side wiring (+ a `commands` trait if `_commands`
   should survive into ramses_rf) — raise with PWhite-Eng.
6. **Cleanup** — drop the `ImportError` fallback for
   `strip_and_map_traits`/`strip_traits` in coordinator.py (dead code
   with the `==0.58.3` pin; comment wrongly says "< 0.59.0").

#### What ramses_rf 0.58.3 provides (verified)

```python
from ramses_rf.schemas import strip_and_map_traits, strip_and_map_schema

# strip_and_map_traits: strip+map a single device's trait dict
#   stage 1: strip _ keys ramses_rf doesn't need
#            (_commands, _disabled, _name, _note, _owner, ...)
#   stage 2: map _ keys ramses_rf does need
#            (_bound→bound, _scheme→scheme, _alias→alias,
#             _faked→faked, _class→class)

# strip_and_map_schema: apply strip+map to every device entry in a schema

# CAVEATS (verified against 0.58.3 source):
#   - Defined in ramses_rf/config.py, re-exported from ramses_rf.schemas
#   - NO callers inside ramses_rf itself (not Gateway, not ramses_cli) —
#     only ramses_cc and ramses_rf's own unit tests use them
#   - _commands is STRIPPED (not in _TRAIT_KEY_MAP), and SCH_TRAITS_*
#     (PREVENT_EXTRA) has no 'commands' key — _commands cannot reach
#     ramses_rf even through this pipeline

# SCH_TRAITS_HVAC bound now accepts: str | list[str] | None
#   (verified: ramses_rf/src/ramses_rf/config.py:89-93)

# CQRS builders available (ramses_rf.commands.builders):
#   hvac:  22F1 (fan_mode), 22F7 (bypass), 2411 (fan_param),
#          31DA (fan_info), 1298 (CO2), 12A0 (humidity)
#   dhw:   get/set params, get/put temp, get/set mode
#   zones: set_temperature, set_mode, set_name, set_config
#   heat:  put_outdoor_temp, put_dhw_temp, put_sensor_temp
#   schedules: get/set version, get/set fragment
#   faultlog:  get_entry
#   opentherm: get_data
#
# NOT yet available: 22B0 (calendar), per-manufacturer strategy profiles
```

#### Open ramses_rf PRs & revised roadmap (checked Jul 18 2026)

PWhite-Eng's in-flight PRs (Strangler Fig purge of legacy L3 builders):

| PR | What | Relevance to us |
|---|---|---|
| [849](https://github.com/ramses-rf/ramses_rf/pull/849) (ready) | Purge legacy `Command.set_fan_mode` / `set_bypass_position` etc. from `ramses_tx/command/hvac.py`, remove `HvacMixins` + `CODE_API_MAP` HVAC routing | ramses_cc does NOT call `Command.set_*` classmethods directly (verified), but climate/water_heater call **device-level** setters (`device.set_fan_mode`, `set_mode`, `set_config`, `set_boost_mode`) — those were cut over to CQRS in PR 847. Our `==0.58.3` pin shields us; retest all device setters when bumping past 0.58.3 |
| [850](https://github.com/ramses-rf/ramses_rf/pull/850)–[852](https://github.com/ramses-rf/ramses_rf/pull/852) (stacked, draft) | Zone parity tests, discovery cut-over to `CommandDTO` + `LegacyCommandShim`, purge legacy zone builders | Internal to ramses_rf; discovery `src` reverted to `HGI_DEV_ADDR` |
| [853](https://github.com/ramses-rf/ramses_rf/pull/853)–[854](https://github.com/ramses-rf/ramses_rf/pull/854) (stacked, draft) | DHW builder parity tests + DHW discovery/ingestion to L7 CQRS | Same — internal cut-over |
| [855](https://github.com/ramses-rf/ramses_rf/pull/855) (ours) | Foreign-HGI exception before block_list check | Already on ramses_rf master |

Revised ramses_rf roadmap (issue 639 blueprint update, Jul 16 2026) —
phases that fill gaps relevant to us:

- **Phase 3.5 (planned): `1FC9` interception** — `_evaluate_rf_bind_rules`
  in `TopologyBuilder` emits a `TopologyChangedEvent` for unmapped
  bindings so the consumer (ramses_cc) can update the schema. This is
  the ramses_rf-side hook our schema-SSOT + Phase 3c flagging can
  subscribe to — watch for it, it replaces polling-based `bound_to`
  detection for new bindings.
- **Phase 3.75 (planned): purge `__class__` mutations** — deletes
  `_handle_promote_class` / `_post_class_promote()`. Confirms "init and
  go" from `_class`; no ramses_cc change needed (we already tear down
  and rebuild on schema change).
- **Phase 4 (planned): FSM conversational parity + passive ingestion** —
  deprecates active discovery probing in favour of a Passive Device
  Scan engine. Aligns with our passive DiscoveryScan; verify our scan
  engine against theirs when it lands.
- **NOT in any open PR or roadmap step:** CLI wiring of
  `strip_and_map_schema()`, a `commands` trait, 22B0 builder,
  per-manufacturer strategy profiles. These remain open gaps — raise
  with PWhite-Eng (the blueprint's Phase 3.25 Step 6 shows CLI
  validation of `_bound` arrays is on their radar, but `_commands`
  is not mentioned).

### Phase 3c: Flagging mismatches (silverailscolo's concern)

**Can ship independently. ramses_cc-only — no ramses_rf dependency.**

Phase 3c extends the existing class mismatch detection to surface
mismatches proactively in the UI, and adds three new mismatch types.

#### What was already done (before Phase 3c branch)

| Step | Description | Status |
|------|-------------|--------|
| 3c.1 | Log warning when user `_class` override differs from detected | DONE |
| 3c.2 | Show class mismatch in config flow review step (with Update/Keep) | DONE |
| 3c.3 | Still apply override (don't leave device broken) | DONE (schema is authoritative) |

#### New in Phase 3c branch (`feature/phase3c-flagging`, PR 831)

| Step | Description | Status |
|------|-------------|--------|
| 3c.4 | Persistent notification for all mismatch types | DONE |
| 3c.5 | Diagnostic entity attributes (`class_mismatch`, `bound_mismatch`, `missing_class`, `orphaned`) | DONE |
| 3c.6 | `_bound` mismatch detection (schema `_bound` vs scan `bound_to`) | DONE |
| 3c.7 | Missing `_class` detection (scan has `likely_type` but schema has no `_class`) | DONE |
| 3c.8 | Orphaned device detection (in schema but not seen by scan for N days) | DONE |
| 3c.9 | Unified `check_all_mismatches()` called from coordinator checkpoint + `sync_topology` service | DONE |
| 3c.10 | Unit tests: 22 new (6 bound, 5 missing_class, 7 orphaned, 4 unified) | DONE |

#### Bug fixes found during integration testing (6 additional commits)

These bugs were discovered while testing Phase 3c on ha-sim and the
production HA instance.  They are included in PR 831.

| Commit | Fix |
|--------|-----|
| `65cca16` | Preserve per-device owner on accept — `accept_device` was overriding the per-device owner with the root owner |
| `c17d363` | Persist `_class` on accepted devices — `generate_schema_entry` was not consistently setting `_class` for all device types |
| `1f79370` | Show `missing_class` devices in `review_discovered` step — the review step was not showing devices with missing `_class` |
| `57bc915` | Add per-device owner fields for mismatch/missing_class devices — the review form only had per-device owner fields for NEW devices, forcing users to use the bulk owner field (which sets root `_owner`) |
| `293b71b` | `sync_with_schema` marks schema devices as ACCEPTED — devices manually added to the schema but never accepted via discovery had NEW status, causing them to appear as "new devices" and be overwritten on accept |
| `ecef357` | Safeguard `_apply_schema_entry` — when a device already has a root entry in the schema, accepting it via discovery no longer overwrites user-configured keys (`_class`, `remotes`, `_commands`) |

**Test results:** 1077 passed, 10 skipped. ha_sim_test Recipe 27
verifies the safeguard on ha-sim.

#### Implementation details

**Persistent notification** (`discovery.py`):
- Separate notification ID: `ramses_cc_discovery_mismatches`
- Shows counts + per-device details for each mismatch type
- Auto-dismissed when all mismatches are resolved
- Called from `check_all_mismatches()` during the periodic checkpoint

**Entity attributes** (`entity.py`):
- `RamsesEntity.extra_state_attributes` checks `discovery_manager._metadata`
- Only adds attributes when the value is a non-empty string (defensive)
- Visible in Developer Tools → States for any entity whose device has a flag

**New `DeviceMetadata` fields**:
- `bound_mismatch: str | None` — "schema=X, discovery=Y"
- `missing_class: str | None` — "discovery=FAN" (scan has a type, schema doesn't)
- `orphaned: str | None` — "not seen by scan" or "last seen {date} (>N days)"
- All serialized/deserialized in `to_dict()` / `from_dict()`

**Orphaned detection**:
- Uses `LOST_DEVICE_THRESHOLD_DAYS` (default 7) — same as lost device detection
- Skips HGI (18:), structural keys (`main_tcs`, `_owner`), and NEW devices
- Checks `last_seen` from scan engine if device is in scan
- If device is in schema but not in scan at all, flags as orphaned

---

<a id="migration"></a>
## Migration

### Storage version: stays at v1 (no bump)

```
STORAGE_VERSION: 1  (unchanged — no version bump in Phase 3a)
max_readable_version: 2  (can read v2 files from the briefly-released v2 code)
```

**Why no version bump:** HA's `Store._async_load_data` raises
`UnsupportedStorageVersionError` when the stored data's version exceeds
`max_readable_version` (which defaults to the code's `STORAGE_VERSION`).
Since 0.58.0/0.58.1 have `STORAGE_VERSION = 1` and don't set
`max_readable_version`, they **cannot read v2 data**. Bumping to v2
would break the downgrade path — the integration would fail to start
on downgrade to 0.58.0/0.58.1.

**v2 recovery (`max_readable_version = 2`):** The v2 code was briefly
released, so some users have `.storage/ramses_cc` files with
`version: 2`. Setting `max_readable_version = 2` on the store allows
the current code (v1) to read these files: HA's `Store` sees
`v2 != v1` but `v2 <= max_readable_version`, so it calls
`_async_migrate_func(2, 1, data)` (no-op identity — v2 format is
identical to v1) and saves the data back as v1. After the first load,
the file is v1 and downgrade to 0.58.0/0.58.1 works normally.

**How migration works instead:** The Phase 3a command migration
(remotes → schema `_commands`) is handled at **runtime** by the
coordinator's `_sync_remotes_to_schema`, which runs on every save
cycle. At startup, the coordinator merges schema `_commands` into
`_remotes` (highest precedence), and on the first save cycle,
`_sync_remotes_to_schema` copies any unmigrated `remotes` into
schema `_commands`. No storage version bump needed.

The `async_migrate_func` hook remains registered as a no-op identity
migration (v1 → v1) from Phase 2.5, ready for future use when a
real format change requires it.

### Data format: v1 (unchanged)

PR 764 (Phase 2) added `_` prefixed traits (`_alias`, `_class`, `_faked`,
`_scheme`, `_bound`, `_disabled`) to the schema. This did **not** require a
storage version bump because `_` keys are additive — old code strips them
via `_strip_schema_extensions`, new code reads them from schema. No
migration needed for traits.

Phase 3a (commands) is the same pattern: `_commands` is another `_`
prefixed key, additive and stripped by old code. The runtime migration
via `_sync_remotes_to_schema` handles copying `remotes` into
`schema[dev][_commands]` on the first save cycle after upgrade.

```
v1 (before Phase 3a):
  .storage/ramses_cc (on disk: {version: 1, data: {...}}):
  data = {
    client_state: {
      schema: {
        main_tcs: "01:...",
        "01:...": {_alias: "My Controller"},  ← _ traits (post-764) or absent (pre-764)
        orphans_heat: [...],
        device_comments: {...},
      },
      packets: {...},
    },
    remotes: {
      "32:153001": {turn_on: "I --- ... 22F1 003 000030"},
    },
  }
  # known_list is in config_entry.options, NOT in .storage

v1 (after Phase 3a — runtime migration, no version bump):
  .storage/ramses_cc (on disk: {version: 1, data: {...}}):
  data = {
    client_state: {
      schema: {
        main_tcs: "01:...",
        "01:...": {_alias: "My Controller"},
        "32:153001": {
          _commands: {turn_on: "I --- ... 22F1 003 000030"},  ← NEW (runtime migration)
        },
        orphans_heat: [...],
        device_comments: {...},
      },
      packets: {...},
    },
    remotes: {
      "32:153001": {turn_on: "I --- ... 22F1 003 000030"},  ← kept as cache
    },
  }
  # known_list still in config_entry.options (kept as fallback)
```

**Note:** `known_list` lives in `config_entry.options`, NOT in `.storage`.

### Runtime migration logic

```python
# coordinator.py — _sync_remotes_to_schema (runs on every save cycle)
def _sync_remotes_to_schema(schema, remotes):
    for device_id, commands in remotes.items():
        if not commands:
            continue
        if SZ_TR_COMMANDS not in schema.get(device_id, {}):
            schema.setdefault(device_id, {})[SZ_TR_COMMANDS] = commands
    # remotes kept in .storage as cache (not deleted)
    # known_list[dev][commands] stays in config_entry.options as fallback
```

### Backup

Before runtime migration, save state as YAML to
`<config_dir>/ramses_cc_backups/` (max 5 retained, same as Phase 2).

### Downgrade path (0.58.2 → 0.58.0/0.58.1)

- Storage stays at v1 — no version mismatch, HA loads it normally
- `remotes` in `.storage` — still present (Phase 3a only copies to
  `_commands`, never deletes). 0.58.0 reads `remotes` normally
- `_commands` in schema — stripped by 0.58.0's own `_strip_traits`
  (recursively removes `_`-prefixed keys). ramses_rf never sees it
- No data loss — learned commands exist in both `remotes` and `_commands`

---

<a id="risks--mitigations"></a>
## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `_commands` in schema breaks ramses_rf validator | `_strip_schema_extensions` already strips all `_` keys. No ramses_rf PR needed. |
| Learn command latency (writing to config entry on every learn) | Debounce writes, or write to `.storage` immediately and sync to config entry on 5-min cycle |
| Commands lost during migration | Backup before migration (YAML). Keep `.storage[remotes]` as cache. Don't delete until Phase 4. |
| `_class` deprecation breaks users | Keep `_class` as override until Builder is ready. Add deprecation warning, not removal. |
| Builder strategy names don't match ramses_cc's trait keys | Coordinate with PWhite-Eng before Phase 3d. Use `_profile` or `_strategy` for Builder keys. |
| Commands on REM vs FAN confusion | Phase 3a: commands on REM. Phase 3b: commands on FAN (DONE, using packet templates — no Builder needed). REM entries kept for backward compat. |
| silverailscolo's "flagging not winning" concern | Phase 3c: log warnings + show in review step, but still apply override |

---

<a id="open-questions"></a>
## Open Questions

1. **Write path for `learn_command`:** Should ramses_cc write to config entry
   immediately (slow, atomic) or to `.storage` first and sync later
   (fast, may lose on crash)? **Recommendation:** Write to `.storage`
   first (fast path), sync to config entry on 5-min cycle. Same as
   current behavior, just add schema sync.

2. **Commands on REM or FAN?** wimpie70 says FAN. But `remote.py`
   entities are on REM devices. **Resolved:** Phase 3a kept on REM
   (no entity change). Phase 3b moved to FAN using packet templates
   (no Builder needed — addresses filled at send time). Both REM and
   FAN entities coexist; REM kept for backward compat.

3. **`async_migrate_func` scaffolding:** The arch doc recommends
   registering it NOW as a no-op. Should ramses_cc do that before Phase 3?
   **Recommendation:** Yes — register no-op migrate_func in store.py
   before Phase 3, so the hook exists.

4. **Builder strategy key name:** PWhite-Eng proposed `"traits"` (list
   of strategy names). ramses_cc uses `_` prefixed keys for traits.
   **Resolved (Jul 17 2026):** Builder/Strategy pattern scrapped. No
   strategy key names needed. `_class` stays as the schema identity trait.

5. **Flagging UX:** silverailscolo wants mismatches flagged, not
   silently overridden. **Resolved (Phase 3c, PR 831):** Mismatch flags
   are surfaced as diagnostic entity attributes (`class_mismatch`,
   `bound_mismatch`, `missing_class`, `orphaned`) on every entity whose
   device has a flag — visible in Developer Tools → States. A persistent
   notification is sent when any mismatch is detected. The config flow
   review step shows mismatches with Update/Keep options. A "mismatch"
   boolean on the gateway binary sensor was considered but is redundant
   with the per-entity attributes.

6. **Command editing in schema editor:** The schema editor is a
   JSON/YAML text editor. Commands are complex packet strings. Should
   ramses_cc add a dedicated command editor UI, or keep `learn_command` /
   `add_command` services as the primary editing path?
   **Recommendation:** Keep services as primary path. Schema editor
   is for advanced users / manual editing only.

---

<a id="decision-log"></a>
## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| Jul 2026 | Phase 3a ships independently of ramses_rf Phase 3 | Stripping workaround means no ramses_rf PR needed |
| Jul 2026 | Commands stay on REM device IDs in Phase 3a | `remote.py` entities are on REMs; moving to FAN requires Builder |
| Jul 2026 | `.storage[remotes]` kept as cache, not deleted | Backward compat + crash recovery safety |
| Jul 2026 | `_class` not deprecated yet | silverailscolo says it will be ignored "in the future" — no timeline |
| Jul 2026 | `known_list[dev][commands]` deprecated, not removed | Fallback for users who haven't migrated |
| Jul 2026 | Phase 2.5: subclass `Store` as `RamsesCcStore`, override `_async_migrate_func` | HA's `Store` has no `migrate_func` constructor param in current version; subclass+override is the pattern HA's own components use (`tag`, `energy`, `knx`) |
| Jul 2026 | Phase 2.5: no-op identity migration (v1 → v1), no `STORAGE_VERSION` bump | Scaffolding only — hook exists so future bumps just add branches; no format change yet |
| Jul 2026 | Phase 3a: **reverted** `STORAGE_VERSION` bump (v2 → back to v1) | HA's Store raises `UnsupportedStorageVersionError` when stored version > `max_readable_version` (defaults to code's version). 0.58.0/0.58.1 can't read v2 data. Runtime migration via `_sync_remotes_to_schema` handles the command migration without a version bump. |
| Jul 2026 | Phase 3b ships without waiting for issue 530 (Builder) | Packet templates (`{verb, code, payload}` dicts) fill addresses at send time — no Builder needed. Builder alignment deferred to Phase 3d. |
| Jul 2026 | Phase 3b: both REM and FAN get `remote` entities | REM entity (`remote.32_153001`) kept for backward compat — existing automations keep working. FAN entity (`remote.30_160000`) is the new primary. |
| Jul 2026 | Phase 3b: runtime migration, no store version bump (same as 3a) | `_migrate_rem_commands_to_fan` copies REM `_commands` to FAN as dict templates on every save cycle. REM entries NOT deleted (downgrade safety). |
| Jul 2026 | Phase 3b: split Builder alignment items to Phase 3d | Original 3b items 3b.1/3b.2/3b.4/3b.5 (strategy keys, `_class` mapping, stop stripping `_` keys, Builder testing) depend on issue 530 — deferred to Phase 3d. |
| Jul 17 2026 | Device identity Builder scrapped (PWhite-Eng, issue 836) | `DeviceRole` composition and active discovery FSM scrapped in favor of "init and go" from schema. Devices instantiate with correct roles from `_class` trait — no runtime `__class__` mutation. CQRS TX builders (22F1, 22F7, 2411, 31DA) shipped in 0.58.3. 22B0 (calendar) and strategy profiles not yet. |
| Jul 17 2026 | ramses_rf Phase 3 terminology updated | Was "issue 530 Phase 3 (Builder Pattern)", now: Phase 3/3.25 = TX Generation Parity (DONE, shipped 0.58.3); Phase 3.75 = Identity Composition ("init and go", deprecate `__class__`). |
| Jul 17 2026 | Phase 3d re-scoped | 3d.2 (`_class` → strategy mapping) marked N/A — DeviceRole scrapped, `_class` stays. 3d.1 re-scoped to TX strategy profile key names (not yet implemented in ramses_rf). New: 3d.4, 3d.6, 3d.7. |
| Jul 17 2026 | `_commands` confirmed as user override layer | PWhite-Eng confirmed: CQRS TX builders = defaults, `_commands` = authoritative user override. `supported_commands()` as strategy method scrapped. Builders shipped in 0.58.3 (22F1, 22F7, 2411, 31DA). 22B0 not yet. |
| Jul 17 2026 | `_commands` currently ramses_cc-only | `_commands` stripped by ramses_cc before ramses_rf sees it. CLI can't use it today. ~~Phase 3d: `strip_and_map_traits()` maps `_commands` → `commands`~~ **CORRECTED Jul 18: `_commands` is stripped, not mapped — see below.** |
| Jul 17 2026 | `_class` NOT deprecated | "init and go" uses `_class` from schema to instantiate devices. silverailscolo's manufacturer+model+revision idea is a future enhancement, not a replacement. |
| Jul 16 2026 | ramses_rf PR 820 merged — `strip_and_map_traits()` pipeline | Two-stage pipeline (strip + map) now in ramses_rf. `SCH_TRAITS_HVAC` bound accepts `str \| list[str]`. Released in 0.58.2. |
| Jul 16 2026 | ramses_rf PR 832 merged — recursive `strip_and_map_traits()` | `strip_traits()` added, `strip_and_map_traits()` made recursive. Released in 0.58.2. |
| Jul 17 2026 | ramses_rf PRs 842-847 merged — CQRS CommandDispatcher + Intent builders | L7 domain intent builders for zones, DHW, HVAC, schedules, fault log, OpenTherm. Released in 0.58.3. ramses_cc `services.py` already uses CQRS Intents (merged from master). |
| Jul 19 2026 | Phase 3c DONE (PR 831) | All 10 items (3c.1-3c.10) implemented + 6 bug fixes for owner handling and schema safeguard. 1077 tests pass. ha_sim_test Recipe 27 verifies safeguard. |
| Jul 19 2026 | Phase 3d unblocked | ramses_rf 0.58.3 shipped all dependencies: `strip_and_map_schema()`, `SCH_TRAITS_HVAC` list bound, CQRS Intent builders. Manifest already pins `ramses-rf==0.58.3`. |
| Jul 18 2026 | Pre-3d review corrections (verified against 0.58.3 source) | (1) `strip_and_map_schema()` has NO callers inside ramses_rf — CLI support for `_` keys is still blocked (3d.5). (2) `_commands` does NOT map to `commands` — it's stripped; no `commands` trait in `SCH_TRAITS`. (3) 3d.3 must use `strip_traits()` for validation, not `strip_and_map_schema()` — `SCH_GLOBAL_SCHEMAS` rejects mapped names. (4) 3d.4 is a code change: `_derive_known_list_from_schema` drops list-valued `bound`. |
| Jul 18 2026 | Checked open ramses_rf PRs 849-855 | Legacy builder purge continues (849 ready, 850-854 stacked drafts). No open PR wires the CLI pipeline, adds a `commands` trait, or adds 22B0 — those gaps remain. Roadmap Phase 3.5 (`1FC9` → `TopologyChangedEvent`) will give us a schema-update hook for new bindings. `==0.58.3` pin shields us from the purge; retest device setters on next bump. |

---

[top](#phase-3-plan-commands-in-schema--ramses_rf-builder-alignment)
