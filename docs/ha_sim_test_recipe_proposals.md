# ha_sim_test Recipe Proposals for Issues 639 and 767

> **Related issues:**
> - https://github.com/ramses-rf/ramses_rf/issues/639 — Architecture Blueprint: ramses_rf/tx Decoupling
> - https://github.com/ramses-rf/ramses_cc/issues/767 — Schema-as-Source-of-Truth

## Design principle: feature-gated recipes

Recipes that test not-yet-implemented features use a **feature-gate** pattern
instead of failing outright.  At the top of `run()`, the recipe checks whether
the upstream feature exists.  If it doesn't, the recipe logs a `SKIP` notice
with the missing feature name and returns — recording zero failures.  When the
feature lands, the gate passes and the full test body executes.

```python
async def run(self, ctx: RecipeContext) -> None:
    ctx.log_section("Recipe R41: HVAC topology roundtrip (load_fan)")

    # --- Feature gate: load_fan must process schema, not be a stub ---
    from ramses_rf.schemas import load_fan
    import inspect

    src = inspect.getsource(load_fan)
    if "_update_schema" not in src or "# TODO" in src:
        ctx.check(
            "load_fan is implemented (not a stub)",
            False,
            "SKIP: load_fan is still a stub — "
            "pending ramses_rf Phase 3.75 / issue 639",
        )
        print("  SKIP: recipe will run when load_fan is implemented")
        return

    # --- Full test body (runs only when feature is live) ---
    ...
```

The `ctx.check()` with `False` records a FAIL, but the immediate `return`
means no further checks run.  This makes the gap visible in the report
without cascading failures.  Alternatively, recipes can use a pure
`print("  SKIP: ...")` + `return` without a check, so the recipe shows as
passed-but-skipped in the summary.  The recommended approach is the latter
(skip without a failed check) to keep the pass/fail ratio meaningful.

## Recipe catalogue

### R38: Faked THM 30C9 uses correct zone_idx (issue 639)

| Field | Value |
|---|---|
| **Issue** | 639 (TX Generation Parity) |
| **Can pass today** | Yes — fix landed in `fix/ufh-zone-idx-fake-30c9` |
| **Priority** | High (regression guard) |
| **Depends on** | ramses_rf >= 0.59.1 (or whatever version ships the fix) |

**What it tests:**

`build_put_sensor_temp` hard-coded `zone_idx="00"` in the 30C9 payload.  For
UFH zone sensors (THM bound to a UFC zone with idx != 00), the fake emitted
30C9 with idx 00 while the real device uses its actual zone idx (e.g. 01).
The UFC ignored the mismatched packets and the zone stayed in comms-lost.

The fix reads `zone_idx` from `self._parent.idx` (the Zone's `_child_id`) and
passes it through the intent data.  This recipe is a regression guard.

**How:**

1. Load a profile with a UFH zone (zone_idx 01) and a THM sensor bound to it.
2. Enable faking on the THM.
3. Call `put_room_temp(22.0)` via the ramses_cc service.
4. Capture the transmitted packet from the ramses log.
5. Verify the 30C9 payload starts with `01` (the zone_idx), not `00`.

**Feature gate:** None needed — the fix is already in place.

---

### R39: CommandDTO carries no application metadata (issue 639 rule 1)

| Field | Value |
|---|---|
| **Issue** | 639 rule 1: "No Application Metadata in TX" |
| **Can pass today** | Yes (structural invariant) |
| **Priority** | Medium |
| **Depends on** | Nothing — tests current state |

**What it tests:**

`CommandDTO` must never contain application-layer flags such as `is_faked`,
`expected_response`, `device_type`, or `wait_for_reply`.  If a virtual device
should not broadcast, `ramses_rf` must simply not send a `CommandDTO`.

This recipe inspects the `CommandDTO` dataclass definition and verifies that
only L2/L3 fields exist: `verb`, `addr1`, `addr2`, `addr3`, `code`, `payload`,
`priority`, `num_repeats`.

**How:**

1. Import `CommandDTO` from `ramses_tx.dtos`.
2. Get the dataclass fields.
3. Assert the field set is exactly the allowed L2/L3 fields.
4. Assert no forbidden fields (`is_faked`, `expected_response`, `device_type`,
   `wait_for_reply`, `device_class`) are present.

**Feature gate:** None needed — this is a structural test that passes today
and should continue to pass after decoupling.

---

### R40: PacketDTO RX path integrity (issue 639 rule 4)

| Field | Value |
|---|---|
| **Issue** | 639 rule 4: "No Decoding Callbacks" |
| **Can pass today** | Yes |
| **Priority** | Medium |
| **Depends on** | Nothing — tests current RX path |

**What it tests:**

A raw `PacketDTO` (timestamp, rssi, verb, addr1-3, code, payload) flows
through the full RX path and hydrates entity state — without any decode
callback in `ramses_tx`.  The `_PAYLOAD_DECODER_CB` bridge is slated for
removal in the decoupling.  This recipe verifies the RX path works purely
via PacketDTO handoff.

**How:**

1. Inject a raw 30C9 packet at the PacketDTO level (not via `inject_message`
   which bypasses the transport).
2. Verify the climate/sensor entity picks up the temperature.
3. Inject a 1260 packet, verify the DHW sensor entity updates.

**Feature gate:** None needed today.  After decoupling, this recipe verifies
the `_PAYLOAD_DECODER_CB` bridge is gone.  A future variant could check
`inspect.getsource(transport)` for `_PAYLOAD_DECODER_CB` and skip if it's
already removed.

---

### R41: HVAC topology roundtrip — load_fan processes remotes/sensors (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "The fundamental gap: load_fan is a stub" |
| **Can pass today** | No — **SKIP** until load_fan is implemented |
| **Priority** | High (biggest HVAC gap) |
| **Depends on** | ramses_rf: `load_fan` must call `fan._update_schema(**schema)` |

**What it tests:**

The biggest gap in issue 767: `load_fan` is a stub.  When implemented, a FAN
with `remotes: [...]` and `sensors: [...]` in schema should create bound child
devices, and `gateway.schema()` should output the HVAC structure (not flatten
to `orphans_hvac`).

Today `load_fan` creates the FAN device but ignores the remotes/sensors (the
`fan._update_schema(**schema)` call is commented out as TODO).  The
remotes/sensors are created separately as orphan devices.  `gateway.schema()`
outputs ALL HVAC devices as `orphans_hvac` — the HVAC structure is lost in
the roundtrip.

**How:**

1. Load a profile with HVAC schema:
   `32:153289: {remotes: [29:153001], sensors: [37:153002]}`.
2. Reload ramses_cc.
3. Verify `gateway.schema()` returns the HVAC structure (not flat
   `orphans_hvac`).
4. Verify the REM entity is bound to the FAN device in HA's device registry.
5. Verify the CO2/sensor entity is bound to the FAN device.

**Feature gate:**

```python
import inspect
from ramses_rf.schemas import load_fan

src = inspect.getsource(load_fan)
if "_update_schema" not in src or "# TODO" in src:
    print("  SKIP: load_fan is still a stub — pending ramses_rf Phase 3.75")
    return
```

---

### R42: HVAC topology learned from traffic — binding rules (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "TopologyBuilder has no HVAC binding rules" |
| **Can pass today** | No — **SKIP** until HVAC BIND_DEVICE rules are added |
| **Priority** | High |
| **Depends on** | ramses_rf: TopologyBuilder `_evaluate_hvac_rules` must emit BIND_DEVICE |

**What it tests:**

TopologyBuilder's `_evaluate_hvac_rules` only does class promotion based on
verb+code pairs.  There is no `BIND_DEVICE` event for HVAC — the REM/CO2 is
promoted to its class but not linked to the FAN as a parent.

When implemented, directed 22F1 from REM to FAN and 1298 from CO2 to FAN
should create `BIND_DEVICE` events, linking the child to the FAN.

**How:**

1. Load fresh_start profile (no schema, no known devices).
2. Inject `31D9 I` from `32:153289` (FAN announces itself).
3. Inject `22F1 I` from `29:153001` to `32:153289` (REM sends command to FAN).
4. Inject `1298 I` from `37:153002` to `32:153289` (CO2 sends reading to FAN).
5. Verify schema shows `32:153289: {remotes: [29:153001], sensors: [37:153002]}`.
6. Verify the REM and CO2 are NOT in `orphans_hvac`.

**Feature gate:**

```python
import inspect
from ramses_rf.pipeline.topology_builder import TopologyBuilder

src = inspect.getsource(TopologyBuilder._evaluate_hvac_rules)
if "BIND_DEVICE" not in src:
    print(
        "  SKIP: TopologyBuilder._evaluate_hvac_rules has no "
        "BIND_DEVICE rules — pending ramses_rf HVAC topology PR"
    )
    return
```

---

### R43: CO2 dual-role device — 1298 + 22F1 from same 37: (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "CO2 sensors are remotes too (dual-role)" |
| **Can pass today** | No — **SKIP** until Phase 3.75 "init and go" |
| **Priority** | Low (deferred to ramses_rf Phase 3.75) |
| **Depends on** | ramses_rf: schema-driven instantiation from `_class` trait |

**What it tests:**

A 37: prefix device can be both a CO2 sensor (sends I|1298) and a REM (sends
I|22F1).  Today ramses_rf forces one class per device — whichever verb+code
pair is seen first wins.  Phase 3.75 "init and go" should allow the device to
be classified from schema `_class` and support both roles.

**How:**

1. Load fresh_start.
2. Inject `1298 I` from `37:153002` to `32:153289` (CO2 reading).
3. Inject `22F1 I` from `37:153002` to `32:153289` (REM command).
4. Verify the device has both a sensor entity (CO2) and a remote entity.
5. Alternatively, verify the device is flagged for dual-role in discovery.

**Feature gate:**

```python
# Check if ramses_rf supports dual-role devices by inspecting the
# HvacCarbonDioxideSensor class for any REM/remote capability.
from ramses_rf.devices.hvac_sensors import HvacCarbonDioxideSensor

# If the class hierarchy still forces single-role, skip.
# The "init and go" pattern would show up as schema-driven class selection.
import inspect
src = inspect.getsource(HvacCarbonDioxideSensor)
if "HvacRemote" not in src and "Remote" not in src:
    print(
        "  SKIP: dual-role CO2+REM not supported — "
        "pending ramses_rf Phase 3.75 'init and go'"
    )
    return
```

---

### R44: Schema migration v1 to v2 — traits survive restart (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — Phase 2 migration (traits in schema) |
| **Can pass today** | Partially — R20 covers sync, this adds restart |
| **Priority** | Medium |
| **Depends on** | Nothing new — tests existing migration |

**What it tests:**

That `_sync_known_list_traits_to_schema` correctly migrates known_list traits
(class, alias, faked, bound, scheme) into schema `_`-prefixed keys, and they
survive a full restart cycle.  R20 tests the sync step; this adds the restart
verification.

**How:**

1. Set up known_list with traits: `{device_id: {class: "CTL", alias: "My CTL",
   faked: true}}`.
2. Trigger `_sync_known_list_traits_to_schema` (via save_state or reload).
3. Verify schema has `_class`, `_alias`, `_faked` keys.
4. Reload ramses_cc (simulating restart).
5. Verify the traits are still present in the merged schema.
6. Verify the known_list is derived from schema (`_derive_known_list_from_schema`).
7. Verify entity names reflect the alias.

**Feature gate:** None needed — migration is implemented (PR 764).

---

### R45: Crash recovery — force reload, topology survives via cache (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "Crash Recovery — What Survives, What's Lost" |
| **Can pass today** | Yes |
| **Priority** | High (real-world reliability) |
| **Depends on** | Nothing — tests existing cache behaviour |

**What it tests:**

That a hard crash (simulated by reloading ramses_cc without clean shutdown)
preserves learned topology from the 5-minute cache checkpoint in
`.storage/ramses_cc`.  Entities should reappear from the merged schema
(config + cache) after reload.

**How:**

1. Load mixed profile with CTL, zones, DHW, and HVAC devices.
2. Wait for topology to be learned (zone names, bindings, actuators).
3. Trigger a save_state (or wait for the 5-min checkpoint).
4. Force-reload ramses_cc (simulating crash — no clean `async_unload_entry`).
5. Verify entities reappear from cached schema.
6. Verify zone names are preserved.
7. Verify zone bindings (sensor, actuators) are preserved.
8. Verify DHW sensor/valve assignments are preserved.

**Feature gate:** None needed — tests existing behaviour.

---

### R46: _disabled trait — device excluded from known_list and entities (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "disabled_devices become obsolete" |
| **Can pass today** | Yes |
| **Priority** | Medium |
| **Depends on** | Nothing — `_disabled` trait is implemented (PR 764) |

**What it tests:**

That a device with `_disabled: true` in schema is excluded from
`_derive_known_list_from_schema`, so ramses_rf doesn't create it, but the
schema entry persists for re-enabling.  This replaces the flat
`disabled_devices` list.

**How:**

1. Add a device to schema with `_disabled: true`.
2. Reload ramses_cc.
3. Verify no entities are created for the disabled device.
4. Verify the device is not in the derived known_list.
5. Verify the device is still in the config entry schema (can be re-enabled).
6. Remove `_disabled` (or set to false), reload.
7. Verify entities now appear.

**Feature gate:** None needed — `_disabled` is implemented.

---

### R47: eavesdrop=False — unknown devices still tracked by DiscoveryScan (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — "eavesdrop, block_list, disabled_devices become obsolete" |
| **Can pass today** | Yes |
| **Priority** | Low |
| **Depends on** | Nothing — tests existing observer path |

**What it tests:**

With `enforce_known_list: true` and `eavesdrop: false`, unknown devices are
still tracked by the DiscoveryScan observer (for classification), but not
created as entities.  The observer path should always run; enforcement only
controls entity creation.

**How:**

1. Load fresh_start with `enforce_known_list: true`.
2. Inject packets from an unknown device (e.g. `04:999999` sending 3150 I).
3. Verify the device appears in discovery state (pending devices).
4. Verify no entities are created for the unknown device.
5. Verify the device is not in the known_list.

**Feature gate:** None needed — tests existing behaviour.

---

### R48: strip_and_map_traits — schema pre-validation pipeline (issue 767)

| Field | Value |
|---|---|
| **Issue** | 767 — Phase 3d (strip_and_map_traits / strip_and_map_schema) |
| **Can pass today** | Yes (functions exist, not yet wired into Gateway) |
| **Priority** | Low |
| **Depends on** | ramses_rf >= 0.58.3 (functions shipped, not wired) |

**What it tests:**

That `strip_and_map_traits()` / `strip_and_map_schema()` correctly remove
`_`-prefixed keys before ramses_rf sees the schema, and map them to the format
ramses_rf expects.  These functions shipped in ramses_rf 0.58.3 but are not
yet called by Gateway/CLI.  When wired in, this verifies the pipeline doesn't
break schema processing.

**How:**

1. Create a schema with `_class`, `_alias`, `_commands`, `_disabled` keys.
2. Pass through `strip_and_map_traits()`.
3. Verify the output schema has no `_`-prefixed keys.
4. Verify the mapped output has the traits in the expected format.
5. Pass through `strip_and_map_schema()`.
6. Verify the output is valid for ramses_rf's `load_schema()`.

**Feature gate:** None needed — the functions exist and can be called
directly.  When they're wired into Gateway, a variant could verify the
Gateway actually calls them.

---

### R49: Positional addressing — addr1/addr2/addr3 to src/dst resolution (issue 639)

| Field | Value |
|---|---|
| **Issue** | 639 rule 2: "Positional Addressing Only" |
| **Can pass today** | Yes |
| **Priority** | Low |
| **Depends on** | Nothing — tests current address resolution |

**What it tests:**

DTOs use `addr1`, `addr2`, `addr3` (positional MAC addresses), not `src` or
`dst`.  Translating positional addresses to logical source/destination based
on verbs is an OSI Layer 7 domain responsibility that lives in `ramses_rf`.

This recipe verifies that various verb+address combinations are correctly
resolved to src/dst in the parsed Message.

**How:**

1. Inject packets with various verb+address combinations:
   - `I` broadcast: `addr1=src, addr2=--:------, addr3=src`
   - `RQ` directed: `addr1=src, addr2=dst, addr3=--:------`
   - `RP` directed: `addr1=dst, addr2=src, addr3=--:------`
   - `W` directed: `addr1=src, addr2=dst, addr3=--:------`
2. Verify the parsed Message has correct `src` and `dst` assignment for each.

**Feature gate:** None needed — tests existing address resolution logic.

---

## Summary table

| Recipe | Issue | Can pass today? | Priority | Feature gate |
|---|---|---|---|---|
| R38 | 639 | Yes | High | None |
| R39 | 639 | Yes | Medium | None |
| R40 | 639 | Yes | Medium | None |
| R41 | 767 | SKIP (load_fan stub) | High | `inspect.getsource(load_fan)` |
| R42 | 767 | SKIP (no BIND_DEVICE) | High | `inspect.getsource(_evaluate_hvac_rules)` |
| R43 | 767 | SKIP (no dual-role) | Low | `inspect.getsource(HvacCarbonDioxideSensor)` |
| R44 | 767 | Yes | Medium | None |
| R45 | 767 | Yes | High | None |
| R46 | 767 | Yes | Medium | None |
| R47 | 767 | Yes | Low | None |
| R48 | 767 | Yes | Low | None |
| R49 | 639 | Yes | Low | None |

## Recommended implementation order

1. **R38** — regression guard for the 30C9 zone_idx fix (just landed)
2. **R45** — crash recovery (high real-world impact, passes today)
3. **R41** — HVAC roundtrip (SKIP today, turns green when load_fan lands)
4. **R42** — HVAC binding rules (SKIP today, turns green when BIND_DEVICE added)
5. **R44** — schema migration restart verification
6. **R46** — _disabled trait
7. **R39** — CommandDTO no app metadata (structural)
8. **R40** — PacketDTO RX path
9. **R49** — positional addressing
10. **R47** — eavesdrop=False observer
11. **R48** — strip_and_map pipeline
12. **R43** — CO2 dual-role (lowest priority, deferred to Phase 3.75)

## Feature-gate pattern reference

For recipes that SKIP until an upstream feature is implemented:

```python
async def run(self, ctx: RecipeContext) -> None:
    ctx.log_section("Recipe Rxx: ...")

    # --- Feature gate ---
    import inspect
    from ramses_rf.some_module import some_function

    src = inspect.getsource(some_function)
    if "expected_marker" not in src:
        print(
            "  SKIP: <feature name> is not yet implemented — "
            "pending <issue/phase reference>"
        )
        return

    # --- Full test body (runs only when feature is live) ---
    ...
```

The SKIP is silent in the pass/fail accounting (no `ctx.check()` call), so
the recipe shows as "ran but skipped" in the report.  When the feature lands,
the gate passes and the full test body executes — turning the recipe into a
real regression test.
