# Phase 3b Design: Commands on FAN

**Created:** Jul 2026
**Status:** Implemented and merged — Phase 3a complete (PR 811), Phase 3b complete (merged)
**Depends on:** Phase 3a (complete), ramses_rf issue 547, ramses_rf PR 546
**Does NOT depend on:** ramses_rf Phase 3/3.25 (TX Generation Parity — in progress)

> **Naming note (updated Jul 17 2026):** There are several "Phase 3"s:
> - **ramses_cc Phase 3** (this doc) — commands in schema, our work.
>   Split into **3a** (commands on REM, PR 811, DONE) and **3b** (commands on
>   FAN with packet templates, DONE, merged).
> - **ramses_rf Phase 3/3.25** (PWhite-Eng, issue 639) — TX Generation
>   Parity + Transport Decoupling. In progress. Will bring native TX
>   builders for 22F7/22B0 and `strip_and_map_traits()` pipeline.
> - **ramses_rf Phase 3.75** (PWhite-Eng, issue 639) — Identity
>   Composition. Was "Builder Pattern" (issue 530), now "init and go"
>   from schema. `DeviceRole` and `supported_commands()` scrapped.
>
> **Key shift (Jul 17 2026):** Builder/Strategy pattern scrapped. No
> `supported_commands()` on strategies. `_commands` stays as user override
> layer. Native TX builders (when they land in Phase 3/3.25) become
> defaults; `_commands` overrides them.

## Contents

- [Overview](#overview)
- [Two command layers](#two-command-layers)
- [Current state (after Phase 3a — complete)](#current-state-after-phase-3a--complete)
- [Phase 3b design](#phase-3b-design)
  - [Schema format](#schema-format)
  - [Packet template](#packet-template)
  - [`_bound` as list](#_bound-as-list)
  - [Entity: `remote.30_160000` on the FAN](#entity-remote30_160000-on-the-fan)
  - [Send flow](#send-flow)
  - [Learn flow](#learn-flow)
  - [State attributes](#state-attributes)
  - [What happens to REM entities](#what-happens-to-rem-entities)
- [Changes](#changes)
  - [ramses_cc](#ramses_cc)
  - [ramses_rf](#ramses_rf)
  - [CLI testing (outside HA)](#cli-testing-outside-ha)
- [Migration (runtime — no store version bump)](#migration-runtime--no-store-version-bump)
- [Backward compatibility](#backward-compatibility)
- [Alignment with ramses_rf](#alignment-with-ramses_rf)
  - [Issue 530: master plan](#issue-530-master-plan)
  - [Discussion 191: consensus](#discussion-191-consensus)
  - [Boundaries](#boundaries)
  - [What we can do now (Phase 3a + 3b)](#what-we-can-do-now-phase-3a-changes--all-done-phase-3b--all-done)
- [Open questions](#open-questions)
- [Implementation Plan (Phase 3b)](#implementation-plan-phase-3b)
- [References](#references)

---

## Overview

Phase 3a moved `_commands` from `.storage[remotes]` to the schema, but kept
them on **REM device entries**. Phase 3b moves `_commands` to **FAN device
entries**, where the FAN owns the commands and REMs are just transport.

This solves the multi-REM problem: a FAN with 2+ REMs currently requires
duplicating commands on each REM entry. With this design, commands are
defined once on the FAN.

silverailscolo's direction (Discussion 191): commands should be on the
device that **handles** them, not the faked REM that sends them.

---

## Two command layers

ramses_rf already has `HvacVentilator.set_fan_mode()` (PR 546) and
scheme-aware `Command.set_fan_mode()` (issue 547). Standard fan modes
no longer need raw packet strings. The `_commands` workaround from
issue 210 is only needed for non-standard commands.

| Layer | What | How to send | Where stored |
|-------|------|-------------|--------------|
| **Standard modes** | low, medium, high, boost, away, off | `device.set_fan_mode("low")` — ramses_rf builds from `_scheme` | Not stored — ramses_rf knows the scheme |
| **Non-standard** | bypass_on, bypass_off, calendar_on, calendar_off, custom | `Command(packet)` from `_commands` template | `_commands` on FAN in schema |

**Standard modes** — ramses_cc calls `await device.set_fan_mode("low")`.
ramses_rf picks the bound REM (`get_bound_rem()`), builds the scheme-aware
packet, and sends it. No raw payloads, no packet building, no REM picking.

**Non-standard commands** — issue 210's known_list had commands with no
builder: `22F7` (bypass), `22B0` (calendar). `_commands` is the only way
to send these until ramses_rf gets builders for them (future Phase 3).

---

## Current state (after Phase 3a — complete)

```
SCHEMA:
  "32:153001": {                          ← REM device
    _class: "REM",
    _faked: true,
    _commands: {
      "turn_on": "I --- 32:153001 30:160000 --:------ 22F1 003 000030"
    }
  }
  "30:160000": {                          ← FAN device
    _class: "FAN",
    _bound: "32:153001"                   ← str | list[str] (Phase 3a)
  }
```

**What Phase 3a delivered:**
- `_commands` stores the **full packet string** with hardcoded REM address
- `_bound` accepts `str | list[str]` (multi-REM binding works)
- `remote.py` entity lives on the REM (no change for 3a)
- `learn_command` listens to one REM src (no change for 3a)
- `send_command` uses the hardcoded packet string
- `climate.set_fan_mode` calls `device.set_fan_mode()` + intercepts custom commands
- `bound_to_fan` attribute on REM entity
- Schema `_commands` is SSOT (persists across reloads, migrates from `.storage[remotes]`)
- `_strip_schema_extensions` delegates stage 1 to ramses_rf's `strip_traits`
- Store `max_readable_version=2` for downgrade safety

**What Phase 3a did NOT change (still Phase 3b scope):**
- `_commands` still on REM entries (not FAN)
- `_commands` still full packet strings (not `{verb, code, payload}` dicts)
- `remote.py` entity still on REM (not FAN)
- `learn_command` still listens to one REM src (not all bound REMs)
- `send_command` still uses hardcoded packet (not template builder)
- With 2 REMs, user still duplicates commands on each REM entry

---

## Phase 3b design

### Schema format

```json
"30:160000": {
  "_class": "FAN",
  "_scheme": "vasco",
  "_bound": ["32:153001", "32:153002"],
  "_commands": {
    "bypass_on":   {"verb": "W", "code": "22F7", "payload": "0000EF"},
    "bypass_off":  {"verb": "W", "code": "22F7", "payload": "00C8EF"},
    "bypass_auto": {"verb": "W", "code": "22F7", "payload": "00FFEF"},
    "calendar_on": {"verb": "W", "code": "22B0", "payload": "0005"},
    "calendar_off":{"verb": "W", "code": "22B0", "payload": "0006"}
  }
}
```

Standard modes (low/medium/high/boost/away) are **not in `_commands`** —
they go through `device.set_fan_mode()` which uses `_scheme` to build
the correct payload. Only non-standard commands that have no builder
are stored in `_commands`.

### Packet template

`_commands` stores verb, code, and payload. Addresses are filled at
send time. This makes automations simple — the user calls
`send_command` with just the command name.

```
Packet format:  {verb} --- {src} {dst} {brd} {code} {len} {payload}

Placeholders (filled at send time):
  %src%  → resolved automatically (see below)
  %dst%  → the FAN's own device ID (e.g. "30:160000")
  %brd%  → broadcast address, always "--:------"
```

**src resolution** (same pattern as ramses_rf's `set_fan_mode`):
1. If command has explicit `src` field → use it
2. Otherwise: pick first bound REM from `_bound` list
3. If no bound REM → fallback to HGI gateway ID
4. If no HGI → error

This mirrors `HvacVentilator.set_fan_mode()` (PR 546):
```python
src_id = self.get_bound_rem()    # try bound REM first
if not src_id:
    src_id = self.hgi.id         # fallback to HGI
```

**Three levels of flexibility:**
1. **No `src` field (default)** — system picks bound REM or HGI. Best for automations.
2. **Explicit `src`** — user hardcodes a specific REM (e.g. only that REM is in range):
   ```json
   "bypass_on": {"verb": "W", "code": "22F7", "payload": "0000EF", "src": "32:153002"}
   ```

**At send time:**
```python
src = cmd_def.get("src") or pick_bound_rem(fan) or fan.hgi.id
dst = fan.id
brd = "--:------"
length = f"{len(payload) // 2:03d}"          # calculated from payload

packet = f"{verb} --- {src} {dst} {brd} {code} {length} {payload}"
# → "W --- 32:153001 30:160000 --:------ 22F7 003 0000EF"
```

Length is **calculated** from the payload, not stored. This avoids
mismatches (e.g. payload "0000EF" → 3 bytes → "003").

**Why verb + code + payload (not just payload)?**

`learn_command` captures packets with different codes (`22F1`, `22F3`,
`22F7`, `22B0`). The verb matters because `22F7` can be both `I` and `W`.

| Code | Name | Verb | Example payload | Meaning |
|------|------|------|-----------------|---------|
| 22F1 | fan_mode | I | `000030` | set fan speed (standard — use set_fan_mode) |
| 22F3 | fan_boost | I | `021E000031` | boost (standard — use set_fan_mode) |
| 22F7 | bypass | I/W | `0000EF` | bypass control (no builder — needs _commands) |
| 22B0 | calendar | W | `0005` | calendar on/off (no builder — needs _commands) |

### `_bound` as list

```json
"_bound": ["32:153001", "32:153002", "29:091138"]
```

`_bound` becomes `str | list[str]`. `fan_handler.setup_fan_bound_devices`
loops over all entries instead of returning after the first.

CO2 devices can also appear in `_bound` — they can send `I 22F1` if
declared as `_class: "REM"` (faked). The FAN doesn't care what type of
device sends the `I 22F1` — it just acts on the payload.

### Entity: `remote.30_160000` on the FAN

The `remote.py` entity moves from the REM to the FAN. The FAN gets one
`remote` entity that exposes all non-standard commands. Standard modes
go through the `climate.py` entity on the FAN (calling
`device.set_fan_mode()`), not through `remote.py`.

### Send flow

**Standard modes:**
```
Automation:
  service: climate.set_fan_mode
  target: climate.30_160000
  data: {fan_mode: "low"}

climate.py:
  1. await self._device.set_fan_mode("low")
  2. ramses_rf picks bound REM, builds scheme-aware packet, sends it
```

**Non-standard commands:**
```
Automation:
  service: remote.send_command
  target: remote.30_160000              ← targets the FAN, not a REM
  data: {command: "bypass_on"}

remote.py:
  1. cmd_def = self._commands["bypass_on"]
     → {"verb": "W", "code": "22F7", "payload": "0000EF"}
  2. src = cmd_def.get("src") or pick_bound_rem(fan) or fan.hgi.id
     → "32:153001" (first bound REM, or HGI fallback)
  3. dst = self._device.id              → "30:160000"
  4. length = f"{len(payload) // 2:03d}" → "003"
  5. packet = f"{verb} --- {src} {dst} --:------ {code} {length} {payload}"
     → "W --- 32:153001 30:160000 --:------ 22F7 003 0000EF"
  6. cmd = Command(packet)
  7. ramses_rf sends it → FAN receives W 22F7, acts on it
```

No hardcoded REM address. Any bound REM can send. If no bound REM,
falls back to HGI. If one REM is offline, pick another.

### Learn flow

```
Automation:
  service: remote.learn_command
  target: remote.30_160000
  data: {command: "bypass_on"}

remote.py:
  1. Listen for 22F1/22F3/22F7/22B0 from ANY bound REM
     - filter: src in self._bound_rem_ids AND code in _LEARN_CODES
     - _LEARN_CODES = ("22F1", "22F3", "22F7", "22B0")
  2. Capture packet:
     "W --- 32:153001 30:160000 --:------ 22F7 003 0000EF"
  3. Extract: verb="W", code="22F7", payload="0000EF"
     (src, dst, brd, length are discarded — they're placeholders)
  4. Store: self._commands["bypass_on"] = {"verb": "W", "code": "22F7", "payload": "0000EF"}
  5. Persist to schema[fan_id][_commands]
```

Currently `learn_command` only listens to one REM (`src == self._device.id`).
With this design, it listens to all bound REMs — so the user can press any
physical remote to learn.

### State attributes

```yaml
# remote.30_160000
commands:
  bypass_on:   {"verb": "W", "code": "22F7", "payload": "0000EF"}
  bypass_off:  {"verb": "W", "code": "22F7", "payload": "00C8EF"}
  calendar_on: {"verb": "W", "code": "22B0", "payload": "0005"}
bound_rems:
  - "32:153001"
  - "32:153002"
```

Automation access:
```yaml
{{ state_attr('remote.30_160000', 'commands') }}
{{ state_attr('remote.30_160000', 'bound_rems') }}
```

### What happens to REM entities

REM entities keep existing. The only change: `commands` moves off the
REM to the FAN. The binding is already defined by `_bound` on the FAN
and `_fan_bound_to_remote` in `fan_handler` — no extra attributes needed.

What changes on the REM entity:
- `commands` attribute: **kept** (packet strings, backward compat — existing
  automations targeting `remote.32_153001` keep working)
- `bound_to_fan` attribute: stays (Phase 3a)
- Everything else stays the same

The FAN entity (`climate.30_160000` + `remote.30_160000`) is the
primary interface for sending commands. The REM is transport.

CO2 threshold automation works naturally — the CO2 has its sensor
entity, the automation targets the FAN:
```yaml
alias: "CO2 > 1000ppm → fan high"
trigger:
  platform: numeric_state
  entity_id: sensor.co2_29_091138
  above: 1000
action:
  service: climate.set_fan_mode
  target:
    entity_id: climate.30_160000
  data:
    fan_mode: "high"
```

---

## Changes

### ramses_cc

| Component | Phase 3a (before) | Phase 3a (DONE) | Phase 3b (DONE) |
|-----------|-------------------|-----------------|-----------------|
| `remote.py` entity | On REM (`HvacRemote`) | No change | On REM **and** FAN (`HvacRemote` + `HvacVentilator`) |
| `_commands` content | Full packet string | No change | `{verb, code, payload}` dict (both accepted at runtime) |
| `_commands` location | REM entry in schema | No change | FAN entry in schema (REM entries kept for downgrade) |
| `_commands` scope | All commands (standard + non-standard) | No change | Non-standard only (standard via `set_fan_mode`) |
| `_bound` type | `str` (single REM) | `str \| list[str]` DONE | `str \| list[str]` (no change) |
| `learn_command` | Listens to one REM src | No change | FAN: listens to all bound REM srcs; REM: one src (backward compat) |
| `send_command` | Uses hardcoded packet | No change | FAN: builds from template; REM: uses packet string (backward compat) |
| `climate.set_fan_mode` | Not implemented (NotImplementedError) | Calls `device.set_fan_mode()` DONE | Also checks FAN dict templates first, then REM strings |
| `_remotes` dict | Keyed by REM ID | No change | Mixed keys: FAN IDs → dicts, REM IDs → strings (both coexist) |
| `fan_handler.setup_fan_bound_devices` | Binds one REM, returns | Loops over all bound REMs DONE | Same (no change) |
| `fan_handler` bound device check | REM or DIS only | REM, DIS, CO2 (`_class: REM`) DONE | Same (no change) |
| `extra_state_attributes` | `commands` only | Add `bound_to_fan` DONE | FAN: add `bound_rems` (list); REM: `bound_to_fan` stays |
| `_strip_schema_extensions` | Does all 3 stages inline | Delegates stage 1 to ramses_rf `strip_traits` DONE | Same (no change) |
| `_derive_known_list_from_schema` | Inline `_bound`→`bound` mapping | Uses ramses_rf `strip_and_map_traits` DONE | Same (no change) |
| Store migration | v1 only | `max_readable_version=2`, v2→v1 identity DONE | Runtime migration (no version bump) — `_migrate_rem_commands_to_fan` |
| Startup load | `.storage[remotes]` only | Schema `_commands` → `_remotes` (SSOT) DONE | Same — loads all schema `_commands` (FAN dicts + REM strings) |
| `_discover_new_entities` | REMs to remote platform | No change | REMs **and** FANs to remote platform |

### ramses_rf

| Component | Phase 3a (before) | Phase 3a (DONE) | Phase 3b |
|-----------|-------------------|-----------------|----------|
| `SCH_TRAITS_HVAC` `bound` | `vol.Any(None, str)` | `vol.Any(None, str, list[str])` DONE | Same (no change) |
| Schema strip+map pipeline | Does not exist | `strip_and_map_traits()` + `strip_traits()` DONE | Stage 2 adds `_commands`→`commands` (future, when ramses_rf needs it) |
| `strip_and_map_traits` recursion | N/A | Recursive into nested dicts DONE | Same (no change) |
| `HvacVentilator.set_fan_mode()` | Already works (PR 546) | No change | No change |
| `Command.set_fan_mode()` | Already scheme-aware (issue 547) | No change | No change |
| `get_bound_rem()` | Returns first bound REM/DIS | No change | No change |
| `supported_commands()` | Does not exist | Not needed | ~~Future~~ Scrapped (Jul 17 2026) |

**Phase 3a completed items (no further work needed for 3b):**

1. `_bound` accepts `str | list[str]` — ramses_rf `SCH_TRAITS_HVAC` + ramses_cc `fan_handler`
2. `fan_handler.setup_fan_bound_devices` loops over all bound REMs
3. CO2-as-REM binding works via `_class: REM` override in ramses_rf
4. `bound_to_fan` state attribute on REM entity
5. `climate.set_fan_mode` calls `device.set_fan_mode()` + intercepts custom commands
6. `_strip_schema_extensions` delegates stage 1 to ramses_rf's `strip_traits`
7. `_derive_known_list_from_schema` uses ramses_rf's `strip_and_map_traits`
8. `strip_and_map_traits` is recursive (handles nested dicts like zones)
9. Store `max_readable_version=2` for downgrade safety
10. Startup load: schema `_commands` → `_remotes` (SSOT precedence)
11. `async_save_client_state` else branch syncs remotes to schema
12. Backup with `reason="ssot_phase3a"` before migration

**Phase 3a test coverage (all 15 code paths + extras):**

- 993 ramses_cc unit tests (31 new for Phase 3a)
- 17 ha_sim integration tests (R24-R25)
- 17 ramses_rf strip_and_map tests
- All passing, ruff/mypy clean

**Phase 3b test coverage:**

- 1026 ramses_cc unit tests (33 new: 23 remote, 9 coordinator migration, 1 climate)
- 28 ha_sim integration checks (R24: 10, R25: 6, R26: 12)
- All passing, ruff/mypy clean

### CLI testing (outside HA)

The schema format must also work with `ramses_cli` (the ramses_rf CLI).
Users can paste a working schema into `config.json` and run the CLI
with `-monitor` to load the schema from file, use it as a filter for
RF traffic, and run:

```json
{
    "config": {
        "use_schema": true
    },
    "schema": {
        "controller": "01:145038",
        "system": {
            "heating_control": "13:237335"
        }
    }
}
```

The `known_list` and `block_list` can be provided as part of
`config.json`.

This means any schema changes must be validated against the CLI, not
just HA. There are two issues that affect both Phase 3a and 3b:

**1. `_bound` as list — blocked by ramses_rf schema validation**

ramses_rf's `SCH_TRAITS_HVAC` (config.py:89) only accepts a single string:
```python
vol.Optional(SZ_BOUND_TO): vol.Any(None, vol.Match(DEVICE_ID_REGEX.ANY))
```
A list `["32:153001", "32:153002"]` would be rejected. This needs to
change to `vol.Any(None, str, [str])` in ramses_rf — and it's needed
for **Phase 3a** (the "3a changes needed" column), not just 3b.

**2. `_commands` — stripped by ramses_cc, but CLI has no stripper**

ramses_cc strips `_` prefixed keys via `_strip_schema_extensions`
before passing to ramses_rf. So ramses_rf never sees `_commands`. But
the CLI loads `config.json` directly into ramses_rf — no stripping.
`SCH_TRAITS` has `extra=vol.PREVENT_EXTRA`, so `_commands` would
**reject the entire schema**.

**Does ramses_rf need `_commands` today?** No. ramses_cc reads
`_commands`, builds the packet, sends via ramses_rf. ramses_rf just
sends it. This follows the same pattern as `_bound`:

```
ramses_cc schema    →    ramses_rf known_list
─────────────────         ───────────────────
_bound (underscore)  →    bound (no underscore)    coordinator.py:1277
_scheme (underscore) →    scheme (no underscore)   coordinator.py:1279
_commands (underscore) →   stripped, not passed    ramses_rf doesn't need it
```

ramses_cc maps `_bound` → `bound` when building the known_list for
ramses_rf (coordinator.py:1277). `_commands` is not mapped because
ramses_rf doesn't need it — `HvacVentilator.set_fan_mode()` builds
packets from `_scheme` + `get_bound_rem()`, not from `_commands`.

**Future (ramses_rf Phase 3/3.25):** When ramses_rf gets native TX
builders and the `strip_and_map_traits()` pipeline, `_commands` would
map to `commands` (no underscore), same pattern as `_bound` → `bound`.
ramses_rf's schema would define `commands` as a proper trait.
PWhite-Eng has committed to exposing `strip_and_map_traits()` as a
pre-validation pipeline stage in ramses_rf.

Options for the CLI issue today:
- **a)** ramses_rf's `SCH_TRAITS` changes `PREVENT_EXTRA` to allow `_`
  prefixed keys (ignore them). Simplest, but a blanket ignore — no
  control over which keys are stripped, no logging, no mapping.
- **b)** Move the strip+map logic to ramses_rf as a transformation
  pipeline. Both the CLI and ramses_cc call the same function.
  ramses_cc keeps its own orchestration logic (`_disabled`/`_skipped`/
  orphan routing) on top. Avoids a duplicate stripper.
- **c)** Users don't put `_commands` in `config.json` for the CLI —
  only in HA's schema. The CLI is for monitoring, not sending commands.

**Recommendation: (b)** — gives control over the different stages.

Currently ramses_cc jumbles three stages together. Splitting them gives
clear ownership:

```
Stage 1 (ramses_rf):  strip _ keys ramses_rf doesn't need
                      (_commands, _disabled, _name, _note, etc.)
Stage 2 (ramses_rf):  map _ keys ramses_rf does need
                      (_bound→bound, _scheme→scheme)
                      — ramses_rf knows its own traits
Stage 3 (ramses_cc):  orchestration
                      (orphan routing, HGI dropping, disabled/skipped
                      filtering, foreign-owner handling)
```

ramses_rf owns stages 1+2 (it knows which `_` keys map to which native
traits). ramses_cc owns stage 3 (it knows about disabled/skipped/orphans).

Both the CLI and ramses_cc call ramses_rf's stage 1+2 function. No
duplicate stripper. The CLI doesn't need stage 3 (no orphan routing).

**Impact on Phase 2.95 code (CQRS Read-Models):** None. The strip+map
function runs BEFORE `SCH_TRAITS()` validation (config.py), not in the
device creation or state ingestion path. It doesn't touch:
- `dev_registry.py` (`_handle_promote_class`, `device_factory_cb`)
- `TopologyBuilder` (heuristic eavesdropping rules)
- `state/store.py` (CQRS read-models, SQLite cache)
- `routing.py` (routing keys)

ramses_rf already strips `commands` from known_list before validation
(`dev_registry.py:492`: `_traits_raw.pop("commands", None)`). The
strip+map pipeline generalizes this existing pattern — it doesn't
restructure the CQRS architecture.

**Note:** Phase 3a requires a ramses_rf PR (not just ramses_cc):
1. Add `strip_and_map_traits()` function (stages 1+2)
2. Change `SCH_TRAITS_HVAC` `bound` to accept `str | list[str]`
3. ramses_cc calls ramses_rf's function instead of inline `_strip_traits`

**Future (Phase 3):** Stage 2 just adds `_commands`→`commands` mapping
when ramses_rf needs it. No new stripper, no new function — just add a
line to the existing map.

---

## Migration (runtime — no store version bump)

Phase 3b uses **runtime migration** (same pattern as Phase 3a), not a store
version bump. The migration runs in `_migrate_rem_commands_to_fan` during
`async_save_client_state`, on every save cycle.

`STORAGE_VERSION` stays at 1. The migration is idempotent — it only copies
commands that are NOT already on the FAN entry (FAN is authoritative).

```python
@staticmethod
def _migrate_rem_commands_to_fan(schema: dict[str, Any]) -> dict[str, Any]:
    """Migrate _commands from REM entries to FAN entries (Phase 3b).

    For each FAN entry with _bound, copies _commands from the bound REM
    entries to the FAN entry as {verb, code, payload} dict templates.
    REM _commands (packet strings) are NOT deleted — kept for backward
    compatibility (downgrade path: v2 code ignores FAN _commands, reads
    REM _commands).
    """
    for fan_id, entry in schema.items():
        if not isinstance(entry, dict) or entry.get("_class") != "FAN":
            continue
        bound = entry.get("_bound", [])
        if isinstance(bound, str):
            bound_rems = [bound]
        elif isinstance(bound, list):
            bound_rems = bound
        else:
            continue

        # Collect commands from bound REMs
        rem_commands = {}
        for rem_id in bound_rems:
            rem_entry = schema.get(rem_id, {})
            if isinstance(rem_entry, dict):
                rem_cmds = rem_entry.get("_commands", {})
                for cmd_name, cmd_val in rem_cmds.items():
                    if cmd_name not in rem_commands:
                        rem_commands[cmd_name] = str(cmd_val)

        # Parse packet strings to dict templates, merge into FAN
        fan_commands = entry.get("_commands", {})
        for cmd_name, packet_str in rem_commands.items():
            if cmd_name in fan_commands:
                continue  # FAN is authoritative
            parts = packet_str.split()
            fan_commands[cmd_name] = {
                "verb": parts[0],    # "I"
                "code": parts[5],    # "22F1"
                "payload": parts[7], # "000030"
            }
        entry["_commands"] = fan_commands

    # REM _commands are NOT deleted — downgrade safety
```

Called in all 3 branches of `async_save_client_state`:
1. When topology is richer (enriched path)
2. When only comments refreshed (else-if path)
3. When no topology changes (else path)

## Backward compatibility

- v2 code ignores `_commands` on FAN (stripped by `_strip_schema_extensions`)
- v2 code still reads `_commands` on REM entries (if not yet migrated)
- v3 code reads `_commands` from FAN first, falls back to REM entries
- If user downgrades v3 → v2: `_commands` on FAN ignored, REM entries
  still have `_commands` (NOT deleted during migration — downgrade safety)
- No store version bump — migration is runtime, same as Phase 3a
- REM `remote` entities stay (existing automations targeting
  `remote.32_153001` keep working)

---

## Alignment with ramses_rf

> **Updated Jul 17 2026:** The Builder/Strategy pattern (issue 530) has
> been **scrapped**. PWhite-Eng confirmed in ramses_rf issue 836 that
> `DeviceRole` composition, `supported_commands()`, and dynamic
> strategies are no longer planned. Instead, "init and go" — devices
> instantiate with correct roles from schema traits. This aligns
> perfectly with our schema-as-SSOT approach.

This design aligns with PWhite-Eng's architectural refactor (issue 639)
and the Discussion 191 consensus. Our Phase 3b is ramses_cc-only and does
**not** depend on ramses_rf Phase 3/3.25.

### Issue 639: master roadmap (updated Jul 17 2026)

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Flight Recorder (rotating packet logs) | MERGED |
| 2 | Database & State Architecture (SQLite, RAM cache) | MERGED |
| 2.2 | Strategy Lookup Table (composite keys) | MERGED (PR 559) |
| 2.9 | TopologyBuilder (heuristic eavesdropping) | MERGED (PR 639) |
| 2.95 | CQRS Read-Models, legacy purge | MERGED |
| **3/3.25** | **TX Generation Parity + Transport Decoupling** | **IN PROGRESS** |
| **3.75** | **Identity Composition ("init and go", deprecate `__class__`)** | **PLANNED** |
| 4 | Isolated Routing Logic | NOT STARTED |

**Key changes from original issue 530 plan:**
- ~~Dynamic Strategy Pattern~~ — **scrapped**, replaced by "init and go"
- ~~`supported_commands()`~~ — **scrapped**, no strategy methods needed
- ~~`DeviceRole` composition~~ — **scrapped**, devices get class from schema
- Native TX builders for 22F7/22B0 — still planned (Phase 3/3.25)
- `strip_and_map_traits()` pipeline — still planned (Phase 3/3.25)
- `SCH_TRAITS_HVAC` accepts `str | list[str]` for bindings — still planned
- `TopologyChangedEvent` for `1FC9` discoveries — still planned (Phase 3.75)

**Already done (discovery/classification):**
- `TopologyBuilder` engine — centralizes heuristic eavesdropping (PR 639)
- `TopologyChangedEvent` with `TopologyAction` enum (`PROMOTE_CLASS`, `BIND_DEVICE`)
- `_handle_promote_class` in `dev_registry.py` — safely promotes device class
- `HVAC_KLASS_BY_VC_PAIR` — class detection from verb+code pairs
  (REM from `I 22F1`, CO2 from `I 1298`, FAN from `I 31D9/31DA`)
- Class promotion purged from entities — they're now pure CQRS Read-Models
- REM/CO2 parent FAN inference from RP replies (commit 10939476)

### Discussion 191: consensus (updated Jul 17 2026)

**1. Commands belong on the device that handles them** (wimpie70):
> "Currently commands are configured on the (faked) REM devices. I think
> it would be better to provide them on the device that will handle that
> command: the FAN, CO2, or the heater."

This is exactly what Phase 3b does — `_commands` moves to the FAN. **DONE.**

**2. Native TX builders are the ramses_rf side** (updated):
~~`supported_commands()`~~ — scrapped. Instead, ramses_rf Phase 3/3.25
will have native TX builders for standard codes (22F7 bypass, 22B0
calendar). These become the **defaults**. ramses_cc's `_commands` in
schema is the **authoritative user override** — what the user configured.

**3. Schema as "Seeding Mechanism"** (PWhite-Eng, updated):
> "init and go" — devices instantiate with correct roles from schema traits.

The schema's `_commands` on FAN entries is part of this — it tells
ramses_cc what commands the user has configured. No Builder needed.

**4. `_class` stays** (updated Jul 17 2026):
~~`_class` will be replaced by manufacturer+model+revision~~ — Builder
scrapped, `_class` stays as the schema identity trait. The
manufacturer+model+revision idea is a longer-term enhancement, not a
replacement.

**5. Multi-role devices** (PWhite-Eng + silverailscolo):
> silverailscolo: "the future approach will no longer require to pick
> either one (class) if a device(_id) does both jobs."

A CO2 with buttons can be both a sensor and a REM. In `_bound`, it
appears as a transport device. Its sensor role is separate. `_bound`
doesn't care about the device type, only that it can send packets.

**6. Template-based commands** (wimpie70):
> "In Ramses Extras I create the commands with templates, just needs a
> target and a bound REM to fully control a FAN. No need for the commands
> defined in known devices."

This validates the placeholder approach (`{verb, code, payload}` dicts).
The user defines the command once, the system fills in the
addresses at send time. **DONE in Phase 3b.**

**Issue 714: Strict DTOs (CQRS Read-Models)** — PWhite-Eng also plans to
replace dict-based API boundaries with strict DTOs. Our `_commands`
design stores dicts in the schema, but the send path builds a `Command`
object (already typed), so this is compatible.

### Boundaries

**What we must NOT do:**
- ~~Don't add `supported_commands()` to ramses_rf~~ — scrapped, not needed
- **Don't change `HvacVentilator.set_fan_mode()`** — it already works
  (PR 546). We just need to call it from `climate.py`.
- **Don't change `Command.set_fan_mode()`** — it already handles schemes
  (issue 547). We just need to pass `_scheme` through.
- **Don't remove `known_list`** — it's still the seeding mechanism for
  ramses_rf. Our schema `_commands` is an overlay, not a replacement.

### What we can do now (Phase 3a changes — ALL DONE, Phase 3b — ALL DONE)

These were small changes to PR 811 that aligned with Phase 3b.
All completed and tested:

1. **`_bound` accepts `str | list[str]`** — `fan_handler` loops over
   all bound REMs. ramses_rf `SCH_TRAITS_HVAC` accepts list. DONE.
2. **`bound_to_fan` state attribute on REM entity** — in `remote.py`. DONE.
3. **`climate.set_fan_mode` calls `device.set_fan_mode()`** — wired to
   ramses_rf PR 546. Also intercepts custom commands from `_commands`. DONE.
4. **`_strip_schema_extensions` delegates to ramses_rf** — stage 1 via
   `strip_traits`, stage 2 via `strip_and_map_traits`. DONE.
5. **CO2-as-REM binding** — works via `_class: REM` override in ramses_rf. DONE.
6. **Store `max_readable_version=2`** — downgrade safety. DONE.

---

## Open questions

1. **Which REM to pick at send time?** First available? Round-robin?
   **Resolved:** First available. ramses_rf's `get_bound_rem()` already
   returns the first bound REM/DIS from `_bound_devices` dict. Since
   `fan_handler.setup_fan_bound_devices` loops over all bound REMs
   (Phase 3a), `_bound_devices` has all of them. No change needed.

2. **22F7 (bypass) and 22B0 (calendar) native TX builders?** When
   ramses_rf Phase 3/3.25 lands native TX builders for these, they
   become defaults. `_commands` stays as user override. Same pattern
   as 22F1 → issue 547.
   **Status:** Depends on ramses_rf Phase 3/3.25 (in progress). For now,
   `_commands` is the only way to send these. When native builders
   arrive, they become defaults; `_commands` overrides them.

3. **2411 parameter commands?** Separate from `_commands` (they go
   through `fan_handler` + `add_bound_device`). This design doesn't
   change 2411 routing — `_bound` still tells `fan_handler` which REM
   to use for 2411 RQ/W.
   **Status:** Keep separate for now. Some fans can handle 2411, not
   all. Native TX builders (ramses_rf Phase 3/3.25) may handle this
   in the future. `_commands` does not touch 2411 routing.

4. **What if a FAN has no `_bound`?** No REMs to send through.
   `send_command` raises an error. `learn_command` can't capture
   anything. User must set `_bound` first.
   **Resolved:** Give a warning (rate-limited, not spamming). The user
   must set `_bound` and bind a faked REM. The warning guides them to
   the fix without flooding the log.

5. **Multiple FANs sharing a REM?** A REM could be bound to 2 FANs
   (unusual but possible). The `_bound` list is per-FAN, so the same
   REM ID could appear in multiple FAN entries. No conflict — each
   FAN sends its own commands with its own dst address.
   **Resolved:** A REM should never control more than 1 FAN. This is
   a constraint we enforce — if a user tries to bind a REM to 2 FANs,
   warn or reject. In practice, each REM is bound to exactly one FAN.

6. **Should standard modes also be in `_commands`?** No — that would
   duplicate what ramses_rf already knows via `_scheme`. But a user
   could override a standard mode with a custom payload in `_commands`
   if their device needs a non-standard format (edge case).
   **Status:** Agreed — standard modes go through `set_fan_mode()` +
   `_scheme`. Native TX builders (ramses_rf Phase 3/3.25) may add
   per-manufacturer standard modes in the future. `_commands` stays as
   the user override layer for non-standard commands.

---

## Implementation Plan (Phase 3b)

**Format decision:** Both packet string (v2) and dict (v3) formats
accepted at runtime. Migration copies REM `_commands` to FAN as dicts
but does NOT delete REM entries — this gives a clean downgrade path
(v2 code ignores FAN `_commands`, reads REM `_commands`).

### PR structure

Phase 3b requires changes in 2 repos:

1. **ramses_cc PR** — the main work (schema, entity, send/learn, migration) — DONE, merged
2. **ramses_rf PR** — minor: `strip_and_map_traits` stage 2 adds
   `_commands`→`commands` mapping (deferred to ramses_rf Phase 3/3.25)

The ramses_rf PR is NOT a blocker for 3b. ramses_cc strips `_commands`
before ramses_rf sees the schema (via `strip_traits`). The mapping is
only needed when ramses_rf's `strip_and_map_traits()` pipeline (Phase 3/3.25)
reads `commands` directly.

### Work items (ramses_cc PR)

#### Item 1: Schema format — `_commands` as `{verb, code, payload}` dicts on FAN

**Files:** `coordinator.py`, `const.py`

- `const.py`: Add `SZ_TR_COMMANDS_DICT` type alias (if needed for typing)
- `coordinator.py` `_async_update_schema_commands`: Accept both formats:
  - `str` (v2 packet string) — store as-is on REM entry (backward compat)
  - `dict` with `verb`, `code`, `payload` — store on FAN entry
- `coordinator.py` startup load: Read `_commands` from FAN entries
  (dicts) AND REM entries (packet strings), merge into `_remotes`
  - FAN `_commands` (dicts) keyed by FAN ID
  - REM `_commands` (packet strings) keyed by REM ID (fallback)
  - Both coexist in `_remotes` dict

**No ramses_rf changes needed** — `_commands` is stripped by
`strip_traits` before ramses_rf sees the schema.

#### Item 2: Packet template builder

**Files:** `remote.py` (new helper function)

```python
def _build_packet_from_template(
    cmd_def: dict[str, str],
    fan_device: HvacVentilator,
    coordinator: RamsesCoordinator,
) -> str:
    """Build a packet string from a {verb, code, payload} template."""
    verb = cmd_def["verb"]
    code = cmd_def["code"]
    payload = cmd_def["payload"]
    # src resolution: explicit src > bound REM > HGI fallback
    src = cmd_def.get("src")
    if not src:
        src = str(fan_device.get_bound_rem() or "")
    if not src:
        # Fallback to HGI gateway ID
        client = coordinator.client
        if client:
            hgi = getattr(client, "_gwy", None)
            if hgi:
                hgi_dev = getattr(hgi, "_hgi", None) or getattr(hgi, "hgi", None)
                if hgi_dev:
                    src = str(hgi_dev.id)
    if not src:
        raise HomeAssistantError(
            "No bound REM or HGI available to send command — set _bound on the FAN"
        )
    dst = fan_device.id
    brd = "--:------"
    length = f"{len(payload) // 2:03d}"
    return f"{verb} --- {src} {dst} {brd} {code} {length} {payload}"
```

- Also add `_parse_packet_to_template(packet: str) -> dict[str, str]`
  for `learn_command` (extract verb, code, payload from captured packet)

#### Item 3: `remote.py` entity on FAN

**Files:** `remote.py`, `climate.py` (or `fan_handler.py`)

- `remote.py` `async_setup_entry`: Currently filters `isinstance(device, HvacRemote)`.
  Add `isinstance(device, HvacVentilator)` — FAN devices also get a
  `remote` entity.
- `RamsesRemote.__init__`: Accept `HvacVentilator` as well as `HvacRemote`.
  The `_commands` initialization changes:
  - For REM: `coordinator._remotes.get(device.id, {})` (packet strings)
  - For FAN: `coordinator._remotes.get(device.id, {})` (dicts) +
    `coordinator._remotes.get(bound_rem_id, {})` (fallback to REM's
    packet strings)
- `extra_state_attributes`:
  - For REM: `commands` (packet strings) + `bound_to_fan` (existing)
  - For FAN: `commands` (dicts) + `bound_rems` (list of bound REM IDs)

**Key decision:** Both REM and FAN get `remote` entities. The REM entity
is kept for backward compatibility (existing automations target
`remote.32_153001`). The FAN entity is the new primary
(`remote.30_160000`).

#### Item 4: `send_command` builds from template

**Files:** `remote.py`

- `async_send_command`: If `_commands[command]` is a dict, build packet
  via `_build_packet_from_template()`. If it's a string (v2 format),
  use directly (existing behavior).
- The FAN entity's `send_command` uses `self._device.get_bound_rem()` to
  pick the src REM.
- The REM entity's `send_command` still works (uses hardcoded packet
  string from its own `_commands`).

#### Item 5: `learn_command` listens to all bound REMs

**Files:** `remote.py`

- For FAN entity: `learn_command` callback filter changes from
  `src == self._device.id` to `src in self._bound_rems`
  where `_bound_rems` is read from the schema `_bound` trait.
- Captured packet is parsed via `_parse_packet_to_template()` and stored
  as a dict on the FAN entry.
- For REM entity: `learn_command` still listens to one REM src (backward
  compat). Stores as packet string on REM entry.

#### Item 6: `climate.py` `fan_modes` reads FAN `_commands`

**Files:** `climate.py`

- `fan_modes` property: Currently reads `coordinator._remotes[bound_rem]`.
  Update to also read `coordinator._remotes[fan_id]` (FAN's own dicts).
  Merge both: FAN commands (dicts) + REM commands (packet strings).
- `async_set_fan_mode` intercept: Currently checks `commands[fan_mode]`
  and sends as packet string. Update to handle dict format:
  if `commands[fan_mode]` is a dict, build via
  `_build_packet_from_template()`. If string, use directly.

#### Item 7: Runtime migration REM → FAN dict templates

**Files:** `coordinator.py` (no `store.py` changes needed)

- `coordinator.py`: Add `_migrate_rem_commands_to_fan` static method.
  - For each FAN entry in schema with `_bound`:
    - Normalize `_bound` to list (if string)
    - For each bound REM, copy its `_commands` (packet strings) to the
      FAN entry as dicts (parse via `_parse_packet_to_template`)
    - Do NOT delete REM `_commands` (downgrade safety)
    - Only copy commands NOT already on the FAN (FAN is authoritative)
  - Called in all 3 branches of `async_save_client_state`
- **No store version bump** — `STORAGE_VERSION` stays at 1.
  Migration is runtime (same pattern as Phase 3a's `_sync_remotes_to_schema`).
- Downgrade safety:
  - v3→v2: v2 code ignores FAN `_commands` (stripped), reads REM
    `_commands` (still present as packet strings — NOT deleted)
  - v2→v1: identity (already handled)

#### Item 8: Config flow `_commands` on FAN

**Files:** `config_flow.py`, `schemas.py`

- Config flow schema step already preserves `_commands` through round-trip
  (tested in Phase 3a). No change needed for dict format —
  `strip_traits` strips `_commands` regardless of value type.
- Config flow UI: Consider adding a FAN-specific command editor in a
  future iteration. For now, users edit `_commands` in the schema
  YAML/JSON directly (same as Phase 3a).

### Test plan

#### Unit tests (ramses_cc) — 33 new, 1026 total

1. `_build_packet_from_template` — builds correct packet from dict
2. `_build_packet_from_template` — explicit src override
3. `_build_packet_from_template` — HGI fallback when no bound REM
4. `_build_packet_from_template` — raises when no src resolvable
5. `_build_packet_from_template` — length calculated from payload
6. `_parse_packet_to_template` — extracts verb/code/payload from packet
7. `_parse_packet_to_template` — handles 22F7 (bypass) packets
8. `_parse_packet_to_template` — raises ValueError for short packets
9. `_is_command_dict` — True for valid dict templates
10. `_is_command_dict` — False for packet strings
11. `_is_command_dict` — False for incomplete dicts
12. FAN entity `is_fan_entity` — True for HvacVentilator
13. REM entity `is_fan_entity` — False for HvacRemote
14. FAN entity `_bound_rem_ids` — reads _bound from schema
15. FAN entity loads own `_commands` (dicts) from coordinator._remotes
16. FAN entity loads bound REM's `_commands` (strings) as fallback
17. FAN entity `extra_state_attributes` — includes `bound_rems`
18. REM entity `extra_state_attributes` — includes `bound_to_fan`
19. FAN `send_command` with dict template — builds + sends
20. FAN `send_command` with REM string fallback — uses packet string
21. FAN `add_command` — parses to dict template
22. REM `add_command` — stores packet string (backward compat)
23. `_migrate_rem_commands_to_fan` — no FAN → no change
24. `_migrate_rem_commands_to_fan` — FAN no _bound → no change
25. `_migrate_rem_commands_to_fan` — bound REM no _commands → no change
26. `_migrate_rem_commands_to_fan` — REM commands copied as dicts
27. `_migrate_rem_commands_to_fan` — REM commands NOT deleted (downgrade)
28. `_migrate_rem_commands_to_fan` — FAN commands authoritative
29. `_migrate_rem_commands_to_fan` — multi-REM all copied
30. `_migrate_rem_commands_to_fan` — _bound as str normalized
31. `_migrate_rem_commands_to_fan` — invalid packet skipped, no crash

#### Integration tests (ha_sim) — Recipe 26, 12 checks

32. FAN remote entity exists (`remote.fan_32_150000`)
33. FAN `bound_rems` attribute includes bound REM
34. `add_command` on FAN — stores dict template in schema
35. Dict template has correct verb/code/payload
36. `send_command` on FAN entity — succeeds
37. `fan_modes` includes FAN `_commands`
38. REM `_commands` migrated to FAN as dict templates
39. REM `_commands` not deleted after migration (downgrade safety)

**Backward compat:** R24 (10 checks) + R25 (6 checks) still pass.

### Implementation decisions (resolved)

1. **`_remotes` dict keying** — Mixed keys in a single `_remotes` dict.
   FAN IDs map to dict values (`{verb, code, payload}`), REM IDs map to
   string values (packet strings). The value type indicates the format.
   Simpler than a separate `_fan_commands` dict — no new state to manage.

2. **`remote` entity coexistence** — Both REM and FAN get `remote` entities.
   REM entity (`remote.32_153001`) stays for backward compat — existing
   automations keep working. FAN entity (`remote.30_160000`) is new and
   becomes the primary target for 3b features.

3. **`add_command` service target** — Accepts both REM and FAN entities.
   `add_command` on a FAN stores a `{verb, code, payload}` dict on the
   FAN's schema entry. `add_command` on a REM stores a packet string on
   the REM's schema entry (backward compat).

4. **`get_bound_rem()` with list `_bound`** — **Resolved:** ramses_rf's
   `get_bound_rem()` iterates over `_bound_devices` dict (populated by
   `fan_handler.setup_fan_bound_devices` which loops over all bound REMs)
   and returns the first REM/DIS. Works with multi-REM. No change needed.

5. **No `_bound` warning** — If a FAN has no `_bound`, `send_command` and
   `learn_command` emit a rate-limited warning (not spamming). The user
   must set `_bound` and bind a faked REM.

6. **REM-to-FAN constraint** — A REM should never control more than 1 FAN.
   If a user binds a REM to 2 FANs, warn. Each REM is bound to exactly
   one FAN.

---

## References

- **Discussion 191** (ramses_rf): "Untangling the Organic Code Knot" —
  the big architectural discussion. 34 comments. Key consensus: commands
  on FAN, schema as seeding mechanism.
- **Issue 530** (ramses_rf): Architectural Refactor — original master plan.
  Builder/Strategy pattern scrapped Jul 17 2026. Phase 1+2 merged.
- **Issue 639** (ramses_rf): Current master roadmap. Phase 3/3.25 (TX
  Generation Parity) in progress. Phase 3.75 (Identity Composition,
  "init and go") planned.
- **Issue 836** (ramses_rf): Dynamic class promotion — closed. Resolved
  by scrapping `__class__` mutation in favor of "init and go" from schema.
- **Issue 809** (ramses_cc): Phase 3 Plan — this doc's parent.
  PWhite-Eng confirmed alignment (Jul 17 2026).
- **Issue 714** (ramses_rf): Strict DTOs (CQRS Read-Models) — replace
  dict-based API boundaries. Not started, cross-repo breaking change.
- **Issue 547** (ramses_rf): Native 3-byte 22F1 payloads — scheme-aware
  builder, removed the need for raw command strings for standard modes.
- **PR 546** (ramses_rf): `HvacVentilator.set_fan_mode()` — FAN method
  that picks bound REM and sends.
- **Issue 210** (ramses_cc): `climate/set_fan_mode` NotImplementedError —
  the original problem, Siber DF Evo 4. Workaround was raw command
  strings in known_list.
- **Commit 10939476** (ramses_rf): infer REM/CO2 parent FAN from RP
  replies — binding detection from traffic.
