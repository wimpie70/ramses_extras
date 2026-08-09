# Phase 4 Plan: Archive (historical detail)

This file holds detailed historical material that was moved out of
[`phase4_plan.md`](phase4_plan.md) on Aug 9 2026 to keep the main plan
short enough to post on GitHub. Nothing here is expected to change —
it's a record of what was investigated/shipped and why. See the main
doc for current status and actionable next steps.

---

## Dependency narrative detail (superseded by main doc's summary table)

| Dependency | Status | Notes |
|---|---|---|
| ramses_rf 0.59.1 | RELEASED (Jul 25 2026) | Includes PR 914 + all Phase 4 PRs (916-929) + PR 931 test fixes. |
| ramses_rf 0.59.2 | RELEASED (Aug 4 2026) | Phase 4e (PR 951 Packet→Message) + Phase 5.5-adjacent (PR 977 DevType enums, PR 964 decouple Message from `_pkt` shim, PR 952-954 typing/cast removal). |
| ramses_rf 0.59.3 | RELEASED (Aug 7 2026) | Phase 5 fully shipped: PR 986 (RamsesProtocolT export), 987/999 (L7 payload constants), 994 (const layering, 1A), 995 (polling API, 1B), 996 (DTO boundary, 2), 997 (event bus & handshake, 3 — unblocks Step 5), 998 (Phase 5 gaps), 999 (final const relocation). Issue #992 CLOSED. |
| ramses_rf 0.59.4 | RELEASED (Aug 8 2026) | Phase 6 (issue #1001) started — PRs 1002-1010 (PayloadBase ABC, shadow pipeline, per-domain payload dataclasses). PR 1011 (FAN initialized callback fix). Non-breaking so far (shadow-parity). |
| ramses_rf Phase 3.5 (1FC9 → TopologyChangedEvent) | DONE in 0.59.0 (issue #911) | `_evaluate_rf_bind_rules` in `topology_builder.py` intercepts 1FC9, emits `BIND_DEVICE`. `CREATE_CONTROLLER`/`CREATE_CIRCUIT` also in enum. |
| ramses_rf PR 931 (test fixes) | MERGED Jul 25 2026 | DHW None handling + PollingManager build_rq_cmd + test update, on top of PR 929. |
| ramses_cc PR 869 (compat fixes) | MERGED Jul 26 2026, in 0.59.1 | merge_schemas traits + sentinel packet + discovery removal + resolve_async_attr cooldown. |
| ramses_cc PR 863 (migration + backup) | MERGED Jul 26 2026, in 0.59.1 | Phase 4 Step 1: config entry v2→v3 migration with safety net backup. |
| ramses_cc PR 870 (known_list removal) | CLOSED unmerged Jul 30 2026 | Superseded by PR 882 — merge-conflict issues + failing tests. |
| ramses_cc PR 882 (superseding) | MERGED Jul 30 2026, in 0.59.2 | PWhite-Eng: all Phase 4 commits from PR #870 plus CI fixes. Restored backup_store logic + updated test assertions. **Shipped Steps 2-3.** |
| ramses_cc PR 881 (migration follow-ups) | MERGED Jul 30 2026 | PWhite-Eng: Phase 4 config migration follow-ups + tech debt (issue 880). |
| ramses_cc PR 914 (0.59.3 const fix) | MERGED Aug 8 2026 | silverailscolo: fixed imports broken by ramses_rf 0.59.3's const relocation (`ramses_tx.const` → `ramses_rf.const`). |
| ramses_cc PR 906-909 (Phase 5 consumer PRs) | ALL MERGED Aug 8 2026 | 906 (schedule services), 907 (DTO boundary/thermal_demand), 908+909 (polling interval diagnostics). |
| ramses_cc manifest pin | at `ramses-rf==0.59.3` (bumped in PR 911) | ha-sim test Aug 9 (cc/rf both at master, post Phase 5): all recipes pass. |

### Critical path (historical)

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

---

## Step 5: full code sketch (ramses_cc coordinator.py)

**1. Register the callback in `async_start()`**, right after
`await self.client.start(**start_kwargs)` (check both `async_setup`
and `async_start` since `self.client` can be replaced on `fresh_start`
profile reloads):

```python
if self.client:
    self.client.set_schema_updated_callback(self._on_rf_schema_updated)
    self.entry.async_on_unload(
        lambda: self.client.set_schema_updated_callback(None)
        if self.client else None
    )
```

**2. Implement `_on_rf_schema_updated` with debouncing** (trailing
debounce, ~2s, to coalesce bursts like a discovery scan processing
many 1FC9 packets):

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
- The `schema` dict passed into the callback is discarded in favour of
  re-fetching via `self.client.get_state()` inside
  `async_save_client_state` — keeps a single code path, avoids drift
  between "event schema" and "state-save schema".
- Guard on `self._skip_topology_sync` (set during
  `_async_save_on_unload`, `coordinator.py:1722/1746`) to avoid writing
  a fresh-start/unloading config entry from a stale in-flight event.

**3. Reduce (not remove) the polling fallback.** Keep
`async_save_client_state` on `async_track_time_interval` as a safety
net (covers changes that don't go through
`DeviceRegistry.handle_topology_event`, and periodic packet-state
persistence). Increase `SAVE_STATE_INTERVAL` from 5 min to 15-30 min
once the event-driven path is verified reliable.

**4.** Add `self._schema_updated_debounce_task: asyncio.Task | None = None`
to `__init__`, alongside `self._skip_topology_sync`.

**5.** Cancel the debounce task on unload (in `_async_save_on_unload`,
before the final `await self.async_save_client_state()`).

### Testing detail

New ha_sim_test recipe **R62**: bind a new TRV via 1FC9 injection (as
R11 does), then assert `CONF_SCHEMA` updates within seconds
(`wait_for(..., timeout=10)`) instead of waiting on the 5-min poll.
Also verify:
- Multiple rapid 1FC9 injections (burst) → a single config-entry write,
  not N writes.
- No regression in `sync_learned_topology`'s existing behaviour.
- Unload during an in-flight debounce doesn't corrupt the schema.

---

## Step 6: full code sketch (ramses_rf HVAC topology)

### Architectural finding: generic Parent/Child machinery doesn't fit HVAC

Verified whether `load_fan` could call
`_get_device(gwy, dev_id, parent=fan, child_id=...)` the same way
`Evohome._update_schema` does for zones (`tcs.py:798-833`). It cannot,
without a larger refactor:

- `_apply_topology_link()` (`topology.py:450-499`) calls
  `self._get_parent(parent, ...)`, which looks up a hardcoded
  `PARENT_RULES` dict (`topology.py:~380-418`) keyed by
  `parent.__class__.__name__` (`"Evohome"`, `"DhwZone"`, `"MixZone"`,
  `"RadZone"`, `"UfhZone"`, `"ValZone"`). `HvacVentilator` isn't in this
  dict, so linking would raise `SchemaInconsistentError`.
- `_apply_topology_link` also unconditionally derives
  `ctl = getattr(parent, "ctl", None)` and assigns
  `self.ctl = ctl; self.tcs = getattr(ctl, "tcs", None)` — heating-only
  concepts with no HVAC equivalent.
- Extending `PARENT_RULES` + generalizing `_apply_topology_link` is
  possible but a much bigger, riskier change than needed (touches
  shared heating-domain code with extensive coverage, mid-refactor
  upstream via Phase 6).

**Recommendation:** build a separate, minimal HVAC ownership mechanism
that doesn't reuse `Parent`/`Child`/`PARENT_RULES` — isolated to
`hvac_ventilators.py` + `schemas.py` + `dev_registry.py`'s orphan
helpers, with zero risk to the heat-domain topology graph.

### 6a. `load_fan` populates plain ID-list membership (no Parent/Child)

In `src/ramses_rf/devices/hvac_ventilators.py`, add to `HvacVentilator`:

```python
# alongside the existing _bound_devices dict
_remote_ids: set[DeviceIdT]
_sensor_ids: set[DeviceIdT]
```

initialized in `_init_fan_state()`
(`self.__dict__.setdefault("_remote_ids", set())`, same for
`_sensor_ids`), plus:

```python
def _update_schema(self, **schema: Any) -> None:
    """Update this FAN with its remotes/sensors membership from schema.

    Unlike heating Parent/Child, this does NOT use the shared
    ``Parent``/``_apply_topology_link`` machinery (see Step 6 notes in
    ramses_extras/docs/phase4_plan_archive.md for why) — it's a
    lightweight, HVAC-specific membership list.
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

### 6b. `gateway.schema()` nests FAN membership instead of flattening to `orphans_hvac`

Add a `schema()` method to `HvacVentilator` (mirroring
`Evohome.schema()`'s shape) returning
`{SZ_REMOTES: sorted(self._remote_ids), SZ_SENSORS: sorted(self._sensor_ids)}`
(empty lists omitted, matching `shrink()` conventions).

In `Gateway.schema()` (`gateway.py:311-317`), add a loop over FAN
devices analogous to the existing TCS loop:

```python
for dev in self.device_registry.devices:
    if isinstance(dev, HvacVentilator) and (dev._remote_ids or dev._sensor_ids):
        schema[dev.id] = await dev.schema()
```

Update `DeviceRegistry.get_hvac_orphans()` (`dev_registry.py:751-765`)
to exclude any device that is a member of *any* FAN's `_remote_ids` /
`_sensor_ids`:

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
correctly (issue #627-style). This replaces ramses_cc's current
workaround of caching HVAC schema separately in
`.storage/ramses_cc[hvac_schema]` (PR 764) — that workaround can stay
as a fallback/safety net but is no longer load-bearing once 6a/6b ship.

### 6c. CO2 dual-role support (stretch goal, verify after 6a/6b)

A device ID can already appear in both a FAN's `remotes` and `sensors`
lists today — `SCH_VCS`'s `vol.Unique()` is per-list, not cross-list.
Open question: does the *device class* (e.g. a 37: REM instantiated as
`HvacRemoteBase`) correctly respond to both roles at the ramses_rf
device-object level? Likely no new ramses_rf code needed — just an
ha_sim_test recipe (extend R41-R43) proving a single 37: device ID
correctly appears in both lists after 6a/6b and behaves correctly as
both REM and CO2 sensor. Treat as a verification task unless testing
reveals a real gap.

**Note on `add_bound_device` / `_bound_devices`:** distinct from
6a/6b's `_remote_ids`/`_sensor_ids` — `_bound_devices` tracks which
REM/DIS device is the **2411 command source** for the FAN (wired from
the schema `_bound` trait, done client-side in
`ramses_cc/fan_handler.py:setup_fan_bound_devices` as a workaround).
Once 6a/6b ship, they'll overlap (a bound device is also a remote) but
can coexist unchanged.

### Test plan detail

ha_sim_test recipes R41, R42, R43 (currently SKIP):
- FAN's `remotes`/`sensors` survive a coordinator restart via
  `gateway.schema()` round-trip (not just the `.storage` cache)
- `get_hvac_orphans()` no longer lists REM/sensor devices that are
  members of a FAN
- `gateway.schema()` output nests remotes/sensors under the FAN ID
  instead of flattening to `orphans_hvac`

**What ramses_cc can do now (workaround, keep as fallback):** cache
HVAC schema separately in `.storage/ramses_cc[hvac_schema]` and restore
on restart — already implemented (PR 764, verified by R07/R07b/R15).
Once 6a/6b ship, this becomes a safety net rather than the primary
mechanism.

### Not on PWhite-Eng's roadmap (verified Aug 9 2026)

Searched the entire 64-comment thread on issue #639 (last updated Jul
16 2026), Phase 5 issue #992, and Phase 6 issue #1001 — `load_fan` is
never mentioned. Phase 6's only HVAC-related scope is payload *parsing*
(2411, 31DA, CO2 dataclasses), not schema/topology loading.
`gh search code "load_fan" --repo ramses-rf/ramses_rf` returns only the
stub itself. Nobody upstream is tracking this gap.

---

## ramses_rf Phase 4 impact (issue 915) — full PR table

ramses_rf Phase 4 (issue 915, PWhite-Eng) is a 5-PR strangler fig that
moved RQ/RP tracking from L3 FSM to L7 event bus and removed active
discovery probing. All PRs merged to ramses_rf 0.59.1 (Jul 25 2026).
Phase 4e (Packet→Message) completed in 0.59.2 (PR 951, Aug 4 2026).

| PR | Phase | Status | What |
|----|-------|--------|------|
| 916 | 4a Shadow FSM | MERGED | L7 ConversationManager built, parity tested |
| 919 | Schedule/OpenTherm refactor | MERGED | Schedule and OpenTherm struct standardisation |
| 920 | 4a.5 Live Parity | MERGED | Shadow FSM hooked into live pipeline, 100% parity (2126/2126) |
| 921 | 4b Execution Cutover | MERGED | Switch live execution to L7 ConversationManager |
| 924 | 4c.1 Schema Polling | MERGED | `polling_interval` + `is_battery` traits, `disable_polling` config |
| 925 | 4c.2 PollingManager Shadow | MERGED | L7 PollingManager built, shadow parity tested |
| 926 | 4c.3 Polling Cutover | MERGED | Live polling switched to L7 PollingManager |
| 927 | 4c.4 Discovery Purge | MERGED | Legacy DiscoveryService deleted, passive scan only |
| 928 | 4d.1 wait_for_reply Deprecation | MERGED | Scrubbed from application layer |
| 929 | 4d.2 Transport FSM Streamlining | MERGED | WantRply state deleted, L3 only tracks Echo |
| 931 | Test fixes (our PR) | MERGED | DHW None + PollingManager build_rq_cmd + test update |
| 932 | Release prep | MERGED | Bump version to 0.59.1 |
| 951 | 4e API Modernization (Packet→Message) | MERGED (0.59.2) | L7 domain API contracts modernised to Message |
| 964 | 4.5.1 Decouple Message from `_pkt` shim | MERGED (0.59.2) | Strict typing, remove legacy `Message._pkt` property |
| 977 | 4.5.x DevType enums replace string slicing | MERGED (0.59.2) | Address type checking via `DevType` enums (Phase 5.5-adjacent) |

### Verification: ha-sim test suite (Jul 25 2026 run)

Full PR 927/928/929 stack tested against ha-sim with test fixes
(PR 931) and ramses_cc compat fixes (PR 869):

```
Passed:   347
Failed:    0
Total:    347
Elapsed:  33.3 min
```

All recipes passed, including R55 (ConversationManager), R56
(PollingManager), R57 (schema polling traits), R40 (PacketDTO RX path),
R35 (DHW CQRS hydration), R37 (BDR re-parent loop prevention).

### Impact on ramses_cc (resolved, PRs merged)

| ramses_rf Phase 4 PR | ramses_cc impact | Status |
|----------------------|------------------|--------|
| 4a/4a.5 (Shadow FSM) | None — passive observer | Verified (ha-sim) |
| 4b (Execution Cutover) | Low — `gwy.send_cmd()` abstracts execution | Verified (R55) |
| 4c (Active Discovery Removal) | HIGH — removed active polling | Verified (R56, R47). Fixed via PR 869 (services.py: `dev.discovery` removal). |
| 4d (Transport FSM Streamlining) | Low — `wait_for_reply` scrubbed | Verified (R55). Fixed via PR 869 (sentinel packet migration). |
| 4e (Packet→Message, PR 951) | Medium — L7 API contracts changed | Resolved once cc pin bumped past 0.59.1. |
| 4.5.1 (Message decouple, PR 964) | Medium — `Message._pkt` shim removed | Resolved once cc pin bumped past 0.59.1. |
| 4.5.x (DevType enums, PR 977) | High — Phase 5.5-adjacent | Resolved via import audit (see below). |

### Polling configuration in schema

Issue 915 PR 4c.1 (PR 924) shipped polling interval traits into the
schema: `polling_interval` (dict[str, int]) and `is_battery` (bool).
ramses_cc PR 869 includes the schema validation for these traits (R57
passes). Future work: expose polling interval configuration entities
in HA UI (Step 4 territory).

---

## ha-sim test: ramses_cc 0.59.2 + ramses_rf 0.59.2 (Aug 6 2026)

**Superseded:** the Aug 9 2026 run against current masters passes the
full suite cleanly (see main doc status line). This section is kept
for historical triage context only.

**Test date:** Aug 6 2026. **ha_sim_test tool:** ramses_extras master
(commit `3dc3b7a`, PRs 114-125). **Container:** ha-sim (port 8124).

Two runs were performed to isolate ramses_rf 0.59.2 compat issues from
unreleased ramses_cc refactors:

### Run 1: cc upstream/master + rf 0.59.2 tag

cc `a77d40d` (unreleased PRs 897-903) + rf 0.59.2 tag (`ade6ce7e`)

```
Passed:   356
Failed:    17
Skipped:    3  (R41, R42, R43 — load_fan/HVAC topology, blocked on rf)
Total:    376
```

### Run 2: cc 0.59.2 release tag + rf 0.59.2 tag (canonical)

cc 0.59.2 tag (`9c354c3`, includes PR 888 `resolve_async_attr` cooldown
fix) + rf 0.59.2 tag (`ade6ce7e`)

```
Passed:   355
Failed:    19
Skipped:    3
Total:    377
```

No const fixes needed: ramses_rf 0.59.2 still has all SZ_* constants
in `ramses_tx/const.py` (PR 987 const relocation is in 0.59.3, not
0.59.2).

### Comparison between runs

| Recipe | Run 1 (cc master) | Run 2 (cc 0.59.2 tag) | Notes |
|--------|-------------------|----------------------|-------|
| R06 | FAIL | PASS | Fixed by unreleased #896 refactor? Or timing |
| R28 | FAIL | PASS | Fixed by unreleased #896 refactor? Or timing |
| R02 | PASS | FAIL (2) | New timing issue — TRV removal timeout |
| R08 | PASS | FAIL (1) | New — 37:180000 not in FAN remotes |
| R16 | PASS | FAIL (1) | New — ERROR logs during stress test |
| R17 | FAIL | FAIL | Same — discovery timing |
| R20 | FAIL (4) | FAIL (4) | Same — add_faked_rem HTTP 400 |
| R22 | FAIL (2) | FAIL (2) | Same — THM 000A zone binding |
| R24 | FAIL (2) | FAIL (2) | Same — class_mismatch attribute |
| R31 | FAIL | FAIL | Same — Intercepted fan_mode |
| R33 | FAIL | FAIL | Same — WS 'Simulator not initialized' |
| R36 | FAIL | FAIL | Same — climate target_temp 19.0 vs 21.0 |
| R40 | FAIL | FAIL | Same — climate entity missing after 30C9 RX |
| Final | FAIL (2) | FAIL (2) | Same — unexpected errors/warnings |

The unreleased #896/#900 refactors (PRs 897-903) fixed R06 and R28 but
the 0.59.2 release had 3 new timing-sensitive fails (R02, R08, R16).
The persistent fails (R17, R20, R22, R24, R31, R33, R36, R40) existed
in both runs — not caused by the unreleased refactors.

### Persistent failures (in both runs)

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

The check count difference (347 to 377) is because recipes R33-R60
were added since Jul 25. (These Aug 6 failures were resolved by the
Aug 9 run against current masters — see main doc.)

---

## ramses_rf Phase 5+ impact — full detail (issue 992, issue 639 comment)

PWhite-Eng's full roadmap (issue 639 comment, updated Jul 23 2026)
goes to Phase 10.

### ramses_rf Phase 5: Client API & Consumer DTO Boundary Enforcement (issue 992) — CLOSED, shipped 0.59.3

| Step | What | ramses_cc impact | Status |
|------|------|------------------|--------|
| 5.1 Event Bus Hardening | `TopologyChangedEvent` queued/delivered reliably | Our Step 5's public API | SHIPPED (PR 997) |
| 5.2 Ingestion Handshake | API contract for cc → rf schema updates + warm-restart safety | Relevant to known_list removal | SHIPPED |
| 5.3 DTO Boundary Enforcement | Remove legacy dict shims; getters return native CQRS dataclasses | Medium risk — `resolve_async_attr` for `heat_demands` is attribute-based (safe) | SHIPPED — consumer PRs 906-909 merged |
| 5.4 Shim Removal | Remove L7 proxy shims in `ramses_tx/address.py` | Low | SHIPPED (PR 977, PR 986) |
| 5.5 Identity Constant Relocation | Move `DevType`, `DevRole`, `ZoneRole`, `DEV_TYPE_MAP`, `DEV_ROLE_MAP`, `DEVICE_ID_REGEX` from `ramses_tx` to `ramses_rf` | High risk — cc imports these from `ramses_tx` | SHIPPED (PR 987/999) — see import audit below |
| 5.6 Final Polish | Mypy/Ruff/Pytest sweeps | None | DONE |

### ramses_cc import audit (Phase 5.5 identity constant relocation)

Files that imported from `ramses_tx.const`/`ramses_tx.typing` and
needed updating when constants relocated to `ramses_rf`:

| File | Import | Risk |
|------|--------|------|
| `coordinator.py` | `DEV_TYPE_MAP` from `ramses_tx.const` | HIGH — used in `_normalize_class_slug` |
| `fan_handler.py` | `DevType` from `ramses_tx.const` | HIGH — type annotation |
| `fan_handler.py` | `DeviceIdT` from `ramses_tx.typing` | HIGH — type annotation |
| `const.py` | `SZ_IS_EVOFW3` from `ramses_tx.const` | LOW |
| `water_heater.py` | `SZ_ACTIVE`, `SZ_MODE`, `SZ_SYSTEM_MODE` from `ramses_tx.const` | LOW |
| `sensor.py` | Multiple `SZ_*` from `ramses_tx.const` | LOW |
| `schemas.py` | Multiple `SZ_*` from `ramses_tx.const` | LOW |
| `remote.py` | `DEFAULT_GAP_DURATION`, `Priority` from `ramses_tx.const` | MEDIUM |
| `binary_sensor.py` | Multiple from `ramses_tx.const` | LOW |
| `coordinator.py` | `SZ_ACTIVE_HGI`, `Code` from `ramses_tx.const` | MEDIUM |
| `climate.py` | `SZ_MODE`, `SZ_SETPOINT`, `SZ_SYSTEM_MODE`, `Priority` from `ramses_tx.const` | MEDIUM |

`ramses_tx` re-exports these for backward compatibility, but imports
should point to `ramses_rf` directly going forward.

### ramses_rf Phase 4.5: Domain Layer Decommissioning — DONE (PR 978, 0.59.2)

Deletes `_handle_msg` methods and legacy synchronous routing. ramses_cc
doesn't call `_handle_msg` directly, so impact was low. Related: PRs
980-982, 984 (dispatcher modularisation, #979), also shipped in 0.59.2.

### ramses_rf Phase 6-10: Future enhancements

| Phase | What | ramses_cc impact |
|-------|------|------------------|
| 6 | Declarative Binary Parsing (replace Regex) | None — internal to ramses_rf |
| 7 | Remove Dual-Routing (setpoint belongs to Zone, not TRV) | Medium — climate entities may change attributes |
| 8 | Dedicated OpenTherm Read-Models | Low — sensor entities may get new attributes |
| 9 | Deprecate SQLite MessageStore for state retrieval | Medium — if ramses_cc uses MessageStore for restore |
| 10 | Centralized CommandBus | Low — ramses_cc calls device setters, not send_cmd directly |

---

## Decision Log (full history)

| Date | Decision | Rationale |
|------|----------|-----------|
| Jul 23 2026 | Phase 4 plan created | Phase 3 complete (3a-3e all done). ramses_rf 0.59.0 pinned. PR 914 tested 232/232. |
| Jul 23 2026 | PR 914 is a hard blocker for Step 2 | "init and go" from schema `_class` ensures device class is correct without known_list fallback. |
| Jul 23 2026 | Steps 1-4 are ramses_cc-only | Storage bump, known_list removal, enforce always-on, and _commands shrink don't need ramses_rf PRs. |
| Jul 23 2026 | Steps 5-6 are parallel, depend on ramses_rf | TopologyChangedEvent subscription needs Phase 3.5. HVAC topology needs a ramses_rf HVAC PR. |
| Jul 23 2026 | Keep `.storage[remotes]` as crash recovery cache | Commands are in schema `_commands`, but .storage provides fast restore without config entry write. |
| Jul 23 2026 | Deprecate `enforce_known_list` before removing | Issue 677 fix may not hold for all real Evohome systems. |
| Jul 23 2026 | Phase 3.5 (1FC9 → TopologyChangedEvent) is DONE in 0.59.0 | `_evaluate_rf_bind_rules` intercepts 1FC9 and emits `BIND_DEVICE`. Step 5 only needs a public API. |
| Jul 23 2026 | `load_fan` is still a stub (0.59.0) | `schemas.py:397` has `fan._update_schema(**schema)` commented out. No open PR. |
| Jul 24 2026 | PR 914 merged to ramses_rf master | Commit `46cdebcc`. Steps 1-3 now unblocked. |
| Jul 24 2026 | ramses_rf Phase 4 (issue 915) work complete, PRs open | PRs 916, 920, 921, 924-929 — issue marked "COMPLETED" but PRs still OPEN. ha-sim: 347/347 pass. |
| Jul 24 2026 | Steps 1-3 ready to implement | PR 914 merged. Can stack on PR 869. |
| Jul 25 2026 | ramses_rf Phase 4 PRs all merged | 916, 919-921, 924-929 merged. PR 931 (test fixes) merged. Version bumped to 0.59.1 (PR 932). |
| Jul 25 2026 | ramses_rf 0.59.1 released | Includes PR 914 + all Phase 4 PRs + PR 931. cc manifest pin bumped 0.59.0 → 0.59.1. |
| Jul 26 2026 | PR 863: migration safety net added | v2→v3 migration saves a deep-copy backup to `.storage/ramses_cc_migration_v2_backup` before the irreversible migration. |
| Jul 26 2026 | Release plan: two releases | cc 0.59.1: PR 869 + PR 863 (keeps known_list as fallback). cc 0.59.2: PR 870 (remove known_list, enforce always-on). |
| Jul 26 2026 | PR 870: finding 2 fix applied | Aligned `_cleanup_stale_known_list` with `async_migrate_entry` for empty/non-dict known_list entries. |
| Jul 26 2026 | ConversationManager cross-matching issue identified | ramses_rf `process_msg` matches RP on `(src.id, code)` only, ignoring `correlation_id`. Filed upstream as an issue. |
| Jul 24 2026 | ramses_rf Phase 5+ roadmap reviewed (issue 639 comment) | Phase 5 directly impacts ramses_cc: 5.1 = our Step 5, 5.3 may break dict access, 5.5 will break `DevType`/`DEV_TYPE_MAP`/`DeviceIdT` imports. |
| Jul 26 2026 | PR 869 + PR 863 MERGED | Compat fixes + migration shipped to ramses_cc 0.59.1. |
| Jul 30 2026 | PR 870 CLOSED unmerged, superseded by PR 882 | Merge-conflict issues (mangled imports, stale assertions, missing backup_store logic). PWhite-Eng created PR 882. |
| Jul 30 2026 | PR 882 MERGED — Steps 2-3 SHIPPED | Shipped in ramses_cc 0.59.2. PR 881 addressed follow-up tech debt (issue 880). |
| Aug 4 2026 | ramses_rf 0.59.2 released | Ships Phase 4e (PR 951) + Phase 4.5.x (PR 964, 978, 980-982/984) + Phase 5.5-adjacent (PR 977). Phase 4 now fully complete. |
| Aug 5 2026 | ramses_rf Phase 5 STARTED (issue 992) | PRs 986 + 987 merged into 0.59.3 milestone. Identity constants not yet relocated; backward-compat re-exports added (commit `15006d80`). |
| Aug 5 2026 | ramses_cc 0.59.2 pre-release | Includes PR 882 + PR 881 + #896/#900 refactors. Does not include Phase 5 consumer-side work. |
| Aug 6 2026 | Plan document updated to reflect reality | Corrected stale PR statuses. Added rf 0.59.2/0.59.3 + Phase 5 status. Marked Steps 1-3 DONE. |
| Aug 6 2026 | ha-sim test run: cc 0.59.2 tag + rf 0.59.2 tag | 355 PASS / 19 FAIL / 3 SKIP. Full detail archived above. |
| Aug 7-8 2026 | ramses_rf Phase 5 fully shipped (0.59.3), Phase 6 started (0.59.4) | PR 997 delivers Step 5's unblock. cc PRs 914, 906-909 merged. |
| Aug 9 2026 | ha-sim full suite passes against current masters | Previous 19 failures resolved by Phase 5 completion + cc's const-import fix (PR 914). Step 5 implementation plan written. Step 6 confirmed off PWhite-Eng's roadmap; 3-sub-phase plan written and archived above. |

---

[back to main plan](phase4_plan.md)
