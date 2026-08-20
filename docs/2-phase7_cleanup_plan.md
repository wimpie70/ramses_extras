# Roadmap Item 2: Phase 7 — Inbound Pipeline Cleanup

**Created:** Aug 19 2026
**Status:** Draft — pending agreement on roadmap (issue 639) and stable 0.60.0 release
**Related:** https://github.com/ramses-rf/ramses_rf/issues/639#issuecomment-5341806836
**Depends on:** All Phase 2.x work (DONE), Phase 6 dataclass payloads (DONE)

> **Naming convention:** From this roadmap forward, we use the
> numbering from the issue 639 roadmap table (items 1-11) as the
> primary identifier, with additional phase/PR/step for
> cross-references. This file covers **roadmap item 2** (Phase 7
> cleanup).  See also `5-strategy-pattern_plan.md` (roadmap item 5).

> **Release policy:** No merges from this roadmap until a stable
> **0.60.0** release is cut.  We prepare and review PRs, but hold
> merges until 0.60.0 is stable.

---

## Goal

Remove dead code, legacy shims, and paused async infrastructure
left over from the Phase 2.x strangler fig migration.  The
inbound pipeline works correctly today — this is pure cleanup
with zero behavior change.

**Risk:** LOW.  All code being removed is either dead (never
called), paused (explicitly not started), or adapter layers
that duplicate working functionality.

---

## Current State

The Phase 2.x strangler fig migration left behind:

1. **Paused async pipeline** — `CentralDispatcher`
   (`pipeline/dispatcher.py`) with async queues for SSOT,
   discovery, binding, and faked devices.  Built but never
   activated — `lifecycle.py:123` says "We do not call .start()
   because the Phase 2.75 async cutover is paused".  The
   synchronous path in `gateway.py:521-525` is used instead.

2. **Legacy parser adapters** — `_LegacyAddress` and
   `_LegacyMessage` classes in `parsers/decoder.py:57-140`,
   mimicking the old ramses_tx interface.  All 108 dataclass
   parsers are registered and active; the legacy path always
   falls through to `parse_unknown_payload`.

3. **29+ `to_legacy_dict()` methods** in `payloads/hvac.py` —
   anti-corruption layer converting dataclass payloads back to
   dicts for ramses_cc.  ramses_cc still receives dict payloads
   via the `payload_to_dict()` boundary adapter (retained in
   Phase 6), so these methods are still called.  **Cannot remove
   until ramses_cc is migrated to dataclass payloads** — out of
   scope for Phase 7.

4. **Legacy `_handle_msg` hook** in `ramses_tx/engine.py:418` —
   `handler = getattr(self, "_handle_msg", None)`.  All device
   `_handle_msg` overrides were deleted in Phase 2.95; the hook
   remains but always falls through to the callback path.

5. **Strangler fig translation** in `gateway.py:504-517` —
   bridges TopologyBuilder to the old routing format.  Works
   but adds an unnecessary translation step.

6. **`shim_status` method** in `hvac_ventilators.py:882-905` —
   maps CQRS keys back to legacy downstream keys.  Still used by
   ramses_cc's `sync_learned_topology`.  **Cannot remove until
   ramses_cc uses CQRS state directly** — out of scope.

7. **Legacy trace logger** — `_TRACE =
   logging.getLogger("ramses_rf.legacy_trace")` in
   `dev_registry.py:41` and `zones.py:86`.  No longer referenced
   for actual tracing.

8. **Phase 3 device registry logic** — `dev_registry.py:957`
   has `if False:` guarding "PHASE 3" logic.  Status unclear —
   needs PWhite-Eng input before enabling.

---

## What's In Scope (safe to remove)

| Item | File(s) | Lines | Risk |
|------|---------|-------|------|
| Remove `_handle_msg` hook | `ramses_tx/engine.py` | ~418 | None — no overrides exist |
| Remove `_LegacyAddress`/`_LegacyMessage` | `parsers/decoder.py` | 57-140 | None — dead code |
| Remove legacy trace logger | `dev_registry.py`, `zones.py` | 41, 86 | None — unused |
| Remove paused `CentralDispatcher` | `pipeline/dispatcher.py` | 18-94 | None — never started |
| Remove paused `DecoderEngine` | `pipeline/decoder.py` | all | None — never activated |
| Remove paused `ReassemblyBuffer` | `pipeline/reassembly.py` | all | None — never activated |
| Remove "legacy parity" comments | multiple | scattered | None — cosmetic |
| Remove `lifecycle.py` pause comment | `lifecycle.py` | 123 | None — cosmetic |

---

## What's OUT of Scope (has dependents)

| Item | Why deferred | Dependency |
|------|-------------|------------|
| `to_legacy_dict()` methods (29+) | Still called by `payload_to_dict()` | ramses_cc dataclass migration |
| `shim_status` method | Still called by ramses_cc `sync_learned_topology` | ramses_cc CQRS state migration |
| Strangler fig translation | Still routes topology events | Needs TopologyBuilder to consume native Message format |
| Phase 3 `if False:` guard | Unclear if logic is ready | PWhite-Eng input needed |
| Async queue cutover | High risk — changes hot path | Separate phase (was Phase 2.99) |

---

## Implementation Plan

**Single PR, ~200-300 lines deleted, ~0 lines added.**

1. Remove dead code items from the "In Scope" table
2. Run full test suite (`pytest tests/` in ramses_rf)
3. Run ha_sim_test to verify no regressions
4. No ramses_cc changes needed — all removed code is internal

---

## Verification

- `pytest tests/tests_rf/` — all tests pass
- `pytest tests/tests_tx/` — all tests pass
- `ha_sim_test` — full suite passes (no behavior change expected)

---

## Risk Assessment

| Aspect | Assessment |
|--------|------------|
| **Risk** | **Very low** — only deletes dead/paused code |
| **Behavior change** | None |
| **Test impact** | Full test suite verifies no regressions |
| **What could go wrong** | Phase 7 removes something still needed.  Mitigation: keep `CentralDispatcher` if PWhite-Eng plans to activate it; only remove if confirmed dead.  The `to_legacy_dict()` methods and `shim_status` are explicitly out of scope. |
