# Schema as Single Source of Truth — Upgrade & Downgrade Guide

This document explains what changes for existing users when upgrading to
the schema-as-source-of-truth (SSOT) architecture introduced in PR 764
(`feature/passive-scan-cc`), and what happens when turning passive scan
off or downgrading to a previous version.

## Background

Previously, `ramses_cc` maintained **two** parallel device lists:

- **`known_list`** — the primary device list in the config entry, manually
  maintained by the user (device IDs with optional traits like alias, class,
  faked, etc.)
- **`schema`** — an optional topology structure in the config entry
  (zones, orphans, HVAC remotes/sensors)

With PR 764, the **schema** becomes the single source of truth for which
devices exist. The `known_list` is now **derived from the schema** at
startup via `_derive_known_list_from_schema()`, with user overrides
(alias, class, faked, scheme, bound) merged on top.

This eliminates the dual-maintenance problem (keeping schema and
known_list in sync) and enables the passive device scan / discovery
services.

## The startup flow

```
Config entry (user's intent)
  ├── schema: main_tcs, zones, orphans, HVAC
  └── known_list: overrides only (alias, class, faked)
        │
        ▼
.storage/ramses_cc (ramses_rf's learned reality)
  └── client_state: rich topology from traffic
        │
        ▼
merge_schemas(config, cached)
  └── config wins scalars, lists union
        │
        ▼
_strip_schema_extensions()
  └── removes _-prefixed traits, comments, None values
        │
        ▼
_derive_known_list_from_schema()
  └── walks schema → {device_id: {}} for every device
  └── merges user overrides on top
        │
        ▼
ramses_rf Gateway
  ├── schema: clean topology for device creation
  └── known_list: derived + overrides for enforcement
```

## Two modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Legacy** | Passive scan OFF (default) | `schema_is_ssot=False` — devices in known_list but not in schema are **kept** (backward compat) |
| **SSOT** | Passive scan ON | `schema_is_ssot=True` — devices not in schema are **dropped** (schema is authoritative) |

## What changes for existing users

### Passive scan OFF (default — most existing users)

**Nothing visible changes.**

1. `_derive_known_list_from_schema` runs with `schema_is_ssot=False`
2. Devices in the user's known_list but not in schema are kept
3. The derived known_list = schema device IDs + user known_list entries,
   with user overrides merged on top
4. ramses_rf receives the same devices it always did, with the same traits

**Net effect:** the known_list is now derived instead of passed directly,
but the end result is the same or a superset. No devices disappear.

### Passive scan ON (new feature, opt-in)

1. `schema_is_ssot=True` — schema is the single source of truth
2. A **one-time migration** runs: any known_list-only devices are added
   to the schema as `orphans_heat` before the derivation, so they survive
   the transition
3. A **backup** is saved to `.storage/ramses_cc` before migration
4. After migration, the schema fully controls which devices exist
5. The user manages devices via schema services (accept/discard/remove_device)

**Net effect:** one-time migration moves known_list-only devices into the
schema. After that, the user manages devices via the schema, not the
known_list.

## Turning passive scan off again

When a user disables passive scan, the config entry reloads:

1. `schema_is_ssot` becomes `False` (legacy mode)
2. `_derive_known_list_from_schema` keeps known_list-only devices
3. The schema still has all devices (from migration + subsequent operations)
4. The known_list still has user overrides (alias, class, faked, etc.)
5. **All devices remain visible** — the user just loses the passive scan
   discovery services

**Nothing breaks.** The user can go back to manually editing the known_list.

## Editing the schema directly

Yes, users can still manually edit the schema in the config entry. The
schema is a regular YAML/dict structure in the integration's options.
Manual edits are respected — but some are **preserved** across
cache→config sync cycles while others may be **overwritten** by learned
topology.

### What is preserved (user-authored, never overwritten)

These keys and traits are user-authored and always kept as-is:

| Key / trait | Type | Example | Why preserved |
|-------------|------|---------|---------------|
| `_disabled` | per-device trait | `"04:111111": {"_disabled": true}` | User intent — device should be skipped |
| `_name` | per-zone or per-device trait | `"zones": {"02": {"_name": "Lounge"}}` | User-authored label |
| `_alias` | per-device trait | `"04:111111": {"_alias": "Kitchen TRV"}` | User-authored alias |
| `_class` | per-device trait | `"04:111111": {"_class": "radiator_valve"}` | User override of inferred class |
| `device_comments` | top-level list | `["comment1", "comment2"]` | User-authored notes |
| `main_tcs` | top-level scalar | `"01:216136"` | User-defined primary controller |

The `sync_learned_topology` function (which runs every 5 minutes and on
shutdown) explicitly preserves these keys — it only enriches topology
(sensors, actuators, zones) when ramses_rf has learned something the
config doesn't have yet.

### What may be overwritten (learned topology)

These are topology facts that ramses_rf learns from network traffic. The
sync merges them into the config schema using a "config wins for
scalars, lists union" policy:

| Key | Type | Sync behavior |
|-----|------|---------------|
| `appliance_control` | scalar | Overwritten if learned differs from config (ramses_rf knows the real CTL) |
| `zones[].sensor` | scalar | Only set if config doesn't already have one (config wins) |
| `zones[].actuators` | list | Union — learned actuators added, existing ones kept |
| `zones[].class` | scalar | Only set if config doesn't already have one (config wins) |
| `stored_hotwater.sensor` | scalar | Only set if config doesn't already have one |
| `orphans` (within TCS) | list | Devices moved out of orphans when they appear in a zone |
| `orphans_heat` | top-level list | Devices removed when promoted to a zone |
| `orphans_hvac` | top-level list | Managed by accept/discard services |

### What is never touched by sync

| Key | Why |
|-----|-----|
| `remotes` / `sensors` (HVAC) | Managed by accept/discard services, not by topology sync (ramses_rf's `load_fan` is a stub — it can't learn HVAC topology yet) |
| `faked` / `scheme` / `bound` | These are `known_list` traits, not schema keys — they stay in the user's known_list overrides and are merged on top of the derived known_list at startup |

### Faking devices (faked trait)

Faking allows a device to **send commands** as if it were real — e.g. a faked
zone sensor can announce a temperature, a faked REM can send FAN commands.
This is used by the `put_zone_temp`, `put_dhw_temp`, `put_indoor_humidity`,
and `send_command` services.

**Faking is NOT limited to REMs.** The following device classes are fakeable
in ramses_rf:

| Device class | Address prefix | Service that uses it |
|---|---|---|
| `HvacRemote` (REM) | `37:` | `send_command` |
| `Thermostat` (THM/STA) | `08:`/`13:` | — |
| `DhwSensor` (DHW) | `07:` | `put_dhw_temp` |
| `OutSensor` (OUT) | `17:` | — |
| `HvacHumiditySensor` (HUM) | `1F:` | `put_indoor_humidity` |
| `HvacCarbonDioxideSensor` (CO2) | `1F:` | — |

Zone temperature sensors (`Temperature`, `34:`) also support faking via
`put_zone_temp` — they check `is_faked` at runtime even though they don't
inherit `Fakeable` directly (the trait is applied through device promotion).

**How to set up a faked device:**

Add `faked: true` to the device's entry in the `known_list` (not the schema).
The known_list is in the config entry under Advanced Features → Known Devices.

```yaml
# Example: faked REM bound to a FAN
known_list:
  "37:000001":
    class: "REM"
    faked: true
    bound: "32:150000"
```

```yaml
# Example: faked zone sensor for put_zone_temp
known_list:
  "34:000001":
    class: "sensor"
    faked: true
```

At startup, `_derive_known_list_from_schema` merges these user overrides on
top of the schema-derived known_list. ramses_rf's `load_schema()` then
iterates the known_list and calls `_make_fake()` on any device with
`faked: true`, creating a virtual device that can send commands.

**Important:** The device must also exist in the schema (either in a zone,
as an orphan, or in the HVAC remotes/sensors) for ramses_rf to create it.
The `faked` trait in the known_list only enables faking — it doesn't create
the device. In SSOT mode (passive scan ON), the device must be in the schema
first; in legacy mode, the known_list entry alone is sufficient.

**The `add_faked_rem` service** (ramses_cc) is a convenience stub that
registers a faked REM in the discovery manager's metadata. It does NOT add
the REM to the schema or known_list — the user must still manually add it
to the known_list with `faked: true` and to the FAN's remotes in the schema.
Full automation of this flow (schema + known_list + entity creation) is WIP
for a future PR.

### Practical guidance

- **Adding a device manually:** Add it to the schema (as an orphan or in
  a zone). On next reload, `_derive_known_list_from_schema` will pick it
  up and ramses_rf will create it.
- **Setting a zone name:** Add `_name` to the zone dict. It will survive
  all sync cycles.
- **Disabling a device:** Set `_disabled: true` on the device entry. The
  schema validator strips it before passing to ramses_rf, and
  `_derive_known_list_from_schema` excludes disabled devices from the
  known_list.
- **Moving a device between zones:** Edit the schema directly. The sync
  will not move it back — it only adds devices to zones, never removes
  user-placed devices from their config zone (except when the learned
  schema places them in a different zone, in which case the old location
  is cleaned up to avoid duplicates).
- **Faking a device:** Add the device to the schema (so ramses_rf creates
  it), then add `faked: true` to its known_list entry. The known_list
  override is merged on top of the derived known_list at startup and
  ramses_rf's `load_schema()` will call `_make_fake()`. See [Faking
  devices](#faking-devices-faked-trait) above for the full list of
  fakeable device classes and examples.

## Downgrading to a previous version (without this branch)

This is the riskier scenario. The old version does not derive the
known_list from the schema — it reads the known_list directly.

| What | State after passive scan ON | After downgrade |
|------|---------------------------|-----------------|
| Config entry schema | Populated with devices | Old version ignores it |
| Config entry known_list | User overrides only | Old version uses this as primary device list |
| `.storage/ramses_cc` backup | Saved before migration | Old version can't read backups |
| Devices visible | All devices from schema | **Only known_list devices** — schema-only devices may be missing |

**The risk:** If the user accepted discovered devices via the passive
scan services, those devices were added to the **schema** but may not
have been added to the **known_list** (they were derived from the schema
at runtime). On downgrade, the old version doesn't derive from schema —
it reads known_list directly. Devices that exist only in the schema
would **disappear**.

**Mitigation already in place:**
- The migration adds known_list-only devices to the schema as orphans
  — but the reverse (schema-only back to known_list) is not done
- Backups are saved in `.storage/ramses_cc` before migration — but the
  old version can't read them

**Recommendation for downgrade safety:** Before downgrading, manually
copy any schema-only device IDs into the known_list in the config entry.

## Summary table

| Aspect | Before upgrade | Passive scan OFF | Passive scan ON | Turn OFF again | Downgrade to old version |
|--------|---------------|-----------------|-----------------|---------------|-------------------------|
| Devices visible | From known_list | Same (derived = superset) | Same (migrated to schema first) | All remain (legacy mode keeps them) | **Only known_list devices** — schema-only devices lost |
| known_list | Primary device list | Still works as overrides | Overrides only (alias, class, faked) | Works as primary again | Works as primary (schema ignored) |
| Schema | Optional | Optional | Required (SSOT) | Still populated, not required | Ignored by old version |
| Adding devices | Edit known_list | Edit schema or services | Use discover/accept services | Edit known_list or schema | Edit known_list |
| Removing devices | Edit known_list | Edit schema, remove_device, or set `_disabled` | remove_device, discard, or set `_disabled` | Edit known_list or schema | Edit known_list |
| Disabling devices | Remove from known_list | Set `_disabled` trait in schema | Set `_disabled` trait in schema | Set `_disabled` or remove from known_list | Remove from known_list |
| Faking devices | `faked: true` in known_list | Same — known_list overrides merged | Same — known_list overrides merged | Same | Same — known_list is primary |
| Backup | N/A | N/A | Saved to .storage before migration | Retained | Can't be read by old version |
| Risk | None | None | One-time migration (safe) | None | **Schema-only devices disappear** |

## References

- PR 764: https://github.com/ramses-rf/ramses_cc/pull/764
- Architecture discussion: https://github.com/ramses-rf/ramses_cc/pull/764#issuecomment-4882418373
- ramses_rf timing fixes: https://github.com/ramses-rf/ramses_rf/issues/788
