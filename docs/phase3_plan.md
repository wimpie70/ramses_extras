# Phase 3 Plan: Commands in Schema + ramses_rf Builder Alignment

**Created:** Jul 2026
**Status:** Phase 2.5 DONE (PR 810) — Phase 3a DONE (PR 811, merged) — Phase 3b DONE (branch `feature/phase3b-commands-on-fan`) — Phase 3c/3d TODO
**Depends on:** Phase 2 (DONE, PR 764), Phase 2.5 (DONE, PR 810, migration scaffolding)
**Does NOT depend on:** ramses_rf issue 530 Phase 3 (Builder Pattern — not started, future work that would shrink `_commands`)

> **Naming note:** There are two "Phase 3"s that are easy to confuse:
> - **ramses_cc Phase 3** (this doc) — commands in schema, our work.
>   Split into **3a** (commands on REM, PR 811, DONE), **3b**
>   (commands on FAN with packet templates, DONE), **3c** (flagging,
>   partial), and **3d** (Builder alignment, TODO — after issue 530).
>   See `phase3b_fan_commands_design.md`.
> - **ramses_rf issue 530 Phase 3** (PWhite-Eng) — Builder Pattern,
>   `supported_commands()`, dynamic strategies. NOT started. NOT a
>   dependency for our 3b. When it lands, it shrinks `_commands`
>   (22F7/22B0 get native builders) but `_commands` stays as override.

---

## Table of Contents

- [Overview](#overview)
- [Two Phase 3s — Don't Confuse Them](#two-phase-3s--dont-confuse-them)
- [Current State](#current-state)
- [Goals](#goals)
- [PWhite-Eng's ramses_rf Phase 3 (Builder Pattern)](#pwhite-engs-ramses_rf-phase-3-builder-pattern)
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

| | ramses_cc Phase 3 | ramses_rf Phase 3 (issue 530) |
|---|---|---|
| **What** | Commands move to schema as `_commands` | Device classes → Builder strategies |
| **Who** | wimpie70 / ramses_cc | PWhite-Eng / ramses_rf |
| **Repo** | ramses_cc | ramses_rf |
| **Status** | 3a DONE (PR 811), 3b DONE (branch `feature/phase3b`), 3c partial, 3d TODO | Not started (Phase 2.95 merged) |
| **Depends on** | 3a: strip workaround (DONE). 3b: no ramses_rf PR needed (packet templates). 3d: issue 530 Phase 3 | Phase 2 complete (SQLite + RAM cache) |
| **Blocks?** | No — 3a and 3b shipped independently. 3d needs issue 530 | No — can ship without ramses_cc's `_commands` |

**ramses_cc Phase 3 split:**
- **Phase 3a (DONE, PR 811):** `_commands` on REM entries in schema,
  full packet strings. Services write to schema. Migration from
  `.storage[remotes]` + `known_list[commands]`.
- **Phase 3b (DONE, branch `feature/phase3b-commands-on-fan`):** `_commands`
  moves to FAN entries as `{verb, code, payload}` dicts. Packet template
  builder fills addresses at send time. `remote.py` entity on FAN.
  Runtime migration REM → FAN (no store version bump). See
  `phase3b_fan_commands_design.md`.
- **Phase 3c (partial):** Flagging mismatches in UI (detection DONE,
  UI TODO).
- **Phase 3d (TODO):** Builder alignment — coordinate strategy key names,
  map `_class` to Builder strategies, stop stripping `_` keys when
  ramses_rf accepts them natively. Depends on issue 530 Phase 3.

**Key insight:** ramses_cc's Phase 3a shipped using the same
`_strip_schema_extensions` workaround as Phase 2. Phase 3b moved commands
to FAN using packet templates — no ramses_rf PR needed. Phase 3d (Builder
alignment) will move the strip+map logic to ramses_rf when issue 530 lands.

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

<a id="pwhite-engs-ramses_rf-phase-3-builder-pattern"></a>
## PWhite-Eng's ramses_rf Phase 3 (Builder Pattern)

From ramses_rf issue 530 and Discussion 191:

### 3.1 Dynamic Strategy Implementation

Replace static device classes with an immutable Device "shell" holding a
mutable Strategy object. Devices start with `GenericStrategy` and upgrade
to specialized strategies (e.g. `HoneywellTRVStrategy`) as RF evidence
is gathered.

```
Device shell (immutable ID, mutable strategy)
  └── GenericStrategy → HoneywellTRVStrategy (on first 30C9)
```

**Relevance to ramses_cc:** ramses_cc's `_class` trait is a temporary override for edge
cases. When the Builder is ready, `_class` will be deprecated in favor of
`_profile` or `_strategy` keys that map to Builder strategies.

### 3.2 Event Sourcing for Replay

Store raw hex packets in SQLite so newly promoted strategies can
retroactively re-parse historical device states.

**Relevance to ramses_cc:** This is ramses_rf-internal. ramses_cc's schema doesn't need
to change for this. But it means ramses_rf will have its own command
database (Builder strategies define `supported_commands()`).

### 3.3 Known-List Seeding (Hydration)

The key alignment point. PWhite-Eng proposes:

> "Instead of the `known_list` just being a passive filter (Allow/Block),
> it becomes the **Long-Term Memory** for the Detective."

Workflow:
1. Startup: Gateway passes `known_list` to Builder
2. Builder iterates: for each entry, instantiates Device + calls
   `set_strategy(SpecializedStrategy)` immediately
3. Result: entity is fully functional at t=0, no waiting for RF traffic

**Enriched Entry** proposal:
```json
"13:123456": {
  "alias": "Living Room",
  "traits": ["RelayStrategy", "SensorStrategy"]
}
```

**Conflict resolution:** User config > Detective logic. If the Builder
detects "Generic Relay" but known_list says "Pump Controller", known_list
wins. (silverailscolo prefers flagging over winning — see Open Questions.)

### silverailscolo's concerns

- "class" will be **ignored** in the future — replaced by
  manufacturer+model+revision+options
- Users can enter incorrect stuff — prefer **flagging** over "winning"
- Manual YAML won't work — need pick list or 10E0 codes
- Commands should be on the **device that handles them** (FAN, ...),
  not on the faked REM (wimpie70 agreed in Discussion 191)

### wimpie70's input (Discussion 191, Feb 7 2026)

> "Currently commands are configured on the (faked) REM devices. I think
> it would be better to provide them on the device that will handle that
> command: the FAN, or the heater. So, yes... define them on
> supported_commands() and/or on strategies()."

This is a significant design decision: **commands should move from REM
to FAN** in the long term. ramses_cc's Phase 3 should account for this.

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

**Long term (after ramses_rf issue 530 Phase 3):** Builder's
`supported_commands()` is on the FAN strategy. 22F7/22B0 get native
builders and move out of `_commands`. The faked REM just sends what
the FAN strategy tells it to. `_commands` stays as user override.

**Migration path:** Phase 3a → 3b runtime migration copies `_commands`
from REM entries to FAN entries as dict templates (REM entries kept
for downgrade safety). This did NOT wait for issue 530 — packet
templates bridge the gap until the Builder lands.

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

**Does NOT depend on ramses_rf issue 530.** Packet templates bridge the gap
until the Builder lands. See `phase3b_fan_commands_design.md` for full design.

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

### Phase 3d: ramses_rf Builder alignment (after ramses_rf Phase 3 ships)

**Depends on ramses_rf issue 530 Phase 3 landing.**

These items were originally part of Phase 3b in the initial plan, but were
split out because they depend on the Builder Pattern (issue 530 Phase 3),
which is not started. Phase 3b (commands on FAN) shipped without them.

| Step | Description | Status |
|------|-------------|--------|
| 3d.1 | Coordinate with PWhite-Eng on strategy key names | TODO |
| 3d.2 | Map `_class` to Builder strategy names (or deprecate) | TODO |
| 3d.3 | Stop stripping `_` keys when ramses_rf accepts them natively | TODO |
| 3d.4 | Test with Builder: verify seeding from derived known_list | TODO |
| 3d.5 | Move strip+map pipeline to ramses_rf (so CLI also benefits) | TODO |

### Phase 3c: Flagging mismatches (silverailscolo's concern)

**Can ship independently.**

Class mismatch detection already exists at `coordinator.py:722-725` via
`discovery_manager.check_class_mismatches(schema)` — it logs warnings
when the user's `_class` override differs from what discovery detected.
Phase 3c extends this to surface the mismatch in the UI.

| Step | Description | Status |
|------|-------------|--------|
| 3c.1 | Log warning when user `_class` override differs from detected | DONE (coordinator.py:722-725) |
| 3c.2 | Show mismatch flag in config flow review step | TODO |
| 3c.3 | Still apply override (don't leave device broken) | DONE (schema is authoritative) |

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
   of strategy names). ramses_cc uses `_` prefixed keys for traits. Should
   Builder strategies be `_strategies: [...]` or `_profile: "..."`?
   **Recommendation:** Coordinate with PWhite-Eng. Don't decide until
   Phase 3d (Builder alignment).

5. **Flagging UX:** silverailscolo wants mismatches flagged, not
   silently overridden. How to show this in HA UI? **Recommendation:**
   Add a "mismatch" boolean attribute to the gateway binary sensor,
   and a warning in the config flow review step.

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

---

[top](#phase-3-plan-commands-in-schema--ramses_rf-builder-alignment)
