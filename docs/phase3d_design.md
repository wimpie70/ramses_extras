# Phase 3d Design: ramses_rf alignment

**Date:** 2026-07-19
**Status:** DONE — 4 commits on `feature/phase3d-alignment`, all tests pass
**Depends on:** ramses_rf 0.58.3 (DONE — shipped `strip_traits()`, `strip_and_map_traits()`, CQRS builders)
**Branch:** `feature/phase3d-alignment` (from `master`)

> **Phase 3e** (CLI compat + 22B0 builder) split out — both blocked on
> ramses_rf, neither affects ramses_cc. See "Phase 3e" section at the
> bottom of this doc.

---

## Goal

Consolidate the duplicated schema-stripping logic between `schemas.py` and
`coordinator.py`, pass list-valued `_bound` through to ramses_rf, verify
CQRS TX builders work end-to-end with `_commands` overrides, and clean up
dead code (ImportError fallbacks).

---

## Step 3d.3 — Consolidate stage-1 stripping

### Problem

`strip_traits_for_validation()` in `schemas.py` (line 223) has an inline
`_strip_traits` function that duplicates ramses_rf's `strip_traits()`.
The coordinator's `_strip_schema_extensions()` already delegates stage 1
to ramses_rf's `strip_traits` (line 1048: `v = _strip_traits_rf(v)`).

Two implementations of the same recursive `_`-key stripping = drift risk.

### Fix

Replace the inline `_strip_traits` in `strip_traits_for_validation()` with
a call to `ramses_rf.config.strip_traits` (re-exported from
`ramses_rf.schemas`).

**File:** `custom_components/ramses_cc/schemas.py`
**Lines:** 248-256 (remove inline `_strip_traits`), 286 (replace call)

```python
# Before (line 286):
stripped = _strip_traits(value)

# After:
from ramses_rf.config import strip_traits as _strip_traits_rf
stripped = _strip_traits_rf(value) if isinstance(value, dict) else value
```

**Import:** Add `from ramses_rf.config import strip_traits` at module level
(same as coordinator.py already does).

**Risk:** Low — `strip_traits` is a pure function with no side effects.
The ramses_rf version recurses into nested dicts the same way.

**Tests:** Existing `test_strip_traits_for_validation*` tests in
`test_schemas.py` should pass unchanged. Add one test that verifies the
output of `strip_traits_for_validation()` matches
`_strip_schema_extensions()` for a schema with nested zones containing
`_name` traits.

---

## Step 3d.3b — Consolidate stage-3 orchestration

### Problem

Both `strip_traits_for_validation()` (schemas.py) and
`_strip_schema_extensions()` (coordinator.py) do stage-3 orchestration
(orphan routing, trait-only drop, HVAC-to-orphans_hvac), but they have
**drifted**:

| Feature | `strip_traits_for_validation` | `_strip_schema_extensions` |
|---------|-------------------------------|---------------------------|
| Disabled/skipped filtering | NO | YES (lines 999-1006) |
| Foreign-owner handling | NO | YES (lines 1007-1013) |
| HGI (18:) dropping | NO | YES (line 1028) |
| `None` value stripping | NO | YES (line 1022) |
| `device_comments` removal | NO | YES (`_SCHEMA_EXTENSION_KEYS`) |
| Orphan list filtering | NO | YES (lines 1031-1038) |
| Trait-only entry drop | YES (lines 315-321) | YES (lines 1071-1079) |
| HVAC-to-orphans routing | YES (lines 299-311) | YES (lines 1058-1069) |
| `_HEAT_PREFIXES` | frozenset (8 prefixes) | `Final` frozenset (8 prefixes) |

Plus `_HEAT_PREFIXES_SET` in schemas.py (line 335) has **12 prefixes**
(a superset used by `_classify_orphan`), and the coordinator has
`_HEAT_PREFIXES` (8) + `_TCS_ORPHAN_PREFIXES` (3) — **3 different prefix
sets**.

### Fix

Create a single shared function `_strip_and_orchestrate()` in
`schemas.py` that both callers use. It does:

1. **Stage 1:** delegate to `ramses_rf.config.strip_traits`
2. **Stage 3:** orphan routing, disabled/skipped/foreign filtering,
   HGI dropping, `None` stripping, `device_comments` removal,
   trait-only entry drop, HVAC-to-orphans routing

`_strip_schema_extensions()` becomes a thin wrapper that calls
`_strip_and_orchestrate()` (it already does this conceptually).
`strip_traits_for_validation()` also calls it — the validator just
doesn't need the known_list mapping (stage 2).

**Single `_HEAT_PREFIXES` definition** in `schemas.py` (module level),
imported by `coordinator.py`. Use the 8-prefix set (the minimal set
needed for orphan routing). `_HEAT_PREFIXES_SET` (12 prefixes) stays
for `_classify_orphan` — it's a different concern (orphan classification,
not VCS-vs-heat routing).

**File:** `custom_components/ramses_cc/schemas.py` — new function
**File:** `custom_components/ramses_cc/coordinator.py` — refactor
  `_strip_schema_extensions` to call the shared function

**Risk:** Medium — the two functions have subtle differences in edge
cases (e.g. `strip_traits_for_validation` doesn't handle disabled
devices, which means validation could pass a schema that the gateway
would reject, or vice versa). The consolidation must use the
**coordinator's** behaviour as the canonical one (it's the one that
feeds the actual Gateway).

**Tests:**
- Add `test_strip_traits_for_validation_matches_strip_schema_extensions`:
  feed the same schema to both, assert identical output
- Add tests for disabled/skipped/foreign filtering in
  `strip_traits_for_validation` (currently untested)
- Existing `_strip_schema_extensions` tests should pass unchanged

---

## Step 3d.4 — Pass `_bound` as `str | list[str]` to ramses_rf

### Problem

`_derive_known_list_from_schema` (coordinator.py:1387) only passes
`bound` to ramses_rf if it's a string:

```python
if isinstance(mapped["bound"], str):
    traits["bound"] = mapped["bound"]
```

This was correct when `SCH_TRAITS_HVAC` only accepted `str`, but
ramses_rf 0.58.2+ accepts `str | list[str] | None` (verified in
`config.py:89-93`). A FAN with `_bound: ["37:170000", "37:170001"]`
should reach ramses_rf as `bound: ["37:170000", "37:170001"]`.

### Fix

Remove the `isinstance(mapped["bound"], str)` guard. Pass `str` and
`list[str]` through.

```python
# Before:
if isinstance(mapped["bound"], str):
    traits["bound"] = mapped["bound"]

# After:
if mapped.get("bound"):
    traits["bound"] = mapped["bound"]
```

Also re-check the "remove `bound` if no `class`" sanitizer
(coordinator.py ~1420-1429). `SCH_TRAITS_HVAC` now defaults `class` to
`HVC`, so the sanitizer may be overly aggressive — a device with
`_bound` but no `_class` should still get `bound` passed through.

**File:** `custom_components/ramses_cc/coordinator.py`
**Lines:** 1387-1388, ~1420-1429

**Risk:** Low — ramses_rf 0.58.3 is pinned and accepts list-valued
`bound`. The manifest guarantees the version.

**Tests:**
- Add `test_derive_known_list_bound_list` — FAN with
  `_bound: ["37:170000", "37:170001"]` produces
  `known_list["32:..."]["bound"] == ["37:170000", "37:170001"]`
- Add `test_derive_known_list_bound_str` — REM with
  `_bound: "32:150000"` produces
  `known_list["37:..."]["bound"] == "32:150000"` (regression test)
- ha_sim_test: verify multi-REM FAN schema reaches ramses_rf correctly

---

## Step 3d.6 — Verify CQRS TX builders + `_commands` precedence

### Problem

ramses_cc's `services.py` already uses CQRS `build_dto()` for
GET_FAN_PARAM and SET_FAN_PARAM (lines 359-365, 552-558). But
`climate.py`'s `async_set_fan_mode` still uses the legacy path:
`self._device.set_fan_mode(fan_mode)` (line 1211) or custom REM packet
strings (line 1199). The CQRS builder `build_set_fan_mode` (in
`ramses_rf/commands/builders/hvac.py:70`) is available but not called
by ramses_cc for the native (non-`_commands`) path.

The precedence logic in `async_set_fan_mode` is:
1. FAN's own `_commands` (Phase 3b dict templates) → send via
   `Command.from_cli()` or `build_dto()`
2. Bound REM's `_commands` (Phase 3a packet strings) → send via
   `Command.from_cli()` (with `is_faked` check)
3. Native `self._device.set_fan_mode(fan_mode)` → ramses_rf's legacy
   method

Step 3 should eventually use the CQRS builder, but that's a ramses_rf
internal change (the `set_fan_mode` method on `HvacVentilator` should
internally use `build_set_fan_mode`). For Phase 3d, we just need to
**verify** the precedence works and add an end-to-end test.

### Fix

No code change needed for the precedence itself. Add tests:

**Tests:**
- `test_set_fan_mode_with_fan_commands_override` — FAN has
  `_commands: {"boost": ...}`, `set_fan_mode("boost")` sends the
  override, NOT the native builder
- `test_set_fan_mode_with_rem_commands_override` — bound REM has
  `_commands: {"low": ...}`, `set_fan_mode("low")` sends the REM
  override (if REM is faked)
- `test_set_fan_mode_native_fallback` — no `_commands` on FAN or REM,
  `set_fan_mode("auto")` calls `self._device.set_fan_mode("auto")`
- ha_sim_test: inject a FAN with `_commands` and verify
  `set_fan_mode` sends the custom command

---

## Step 3d.8 — Cleanup: remove ImportError fallback

### Problem

coordinator.py lines 64-106 have a `try/except ImportError` fallback
for `strip_and_map_traits` and `strip_traits` from ramses_rf. The
comment says "ramses_rf < 0.59.0" but the functions shipped in 0.58.2,
and the manifest pins `==0.58.3`. The fallback is dead code.

### Fix

Remove the entire `except ImportError` block (lines 69-106). Keep only
the direct import.

**File:** `custom_components/ramses_cc/coordinator.py`
**Lines:** 64-106 → replace with just the import (3 lines)

```python
# Before (43 lines):
try:
    from ramses_rf.config import (
        strip_and_map_traits as _strip_and_map_traits,
        strip_traits as _strip_traits_rf,
    )
except ImportError:  # ramses_rf < 0.59.0 — fallback inline implementation
    _STRIP_MAP: dict[str, str] = { ... }
    def _strip_and_map_traits(traits): ...
    def _strip_traits_rf(traits): ...

# After (4 lines):
from ramses_rf.config import (
    strip_and_map_traits as _strip_and_map_traits,
    strip_traits as _strip_traits_rf,
)
```

**Risk:** None — manifest pins `==0.58.3`, the import is guaranteed
to succeed.

**Tests:** Existing tests pass (the import already succeeds in all
test environments).

---

## Step 3d.5 — CLI compatibility → moved to Phase 3e

Moved to Phase 3e (blocked on ramses_rf, no ramses_cc code change).
See "Phase 3e" section below.

---

## Step 3d.7 — 22B0 calendar builder → moved to Phase 3e

Moved to Phase 3e (blocked on ramses_rf, no ramses_cc code change).
See "Phase 3e" section below.

---

## Implementation order

1. **3d.8** (cleanup ImportError fallback) — DONE
2. **3d.3** (consolidate stage-1 stripping) — DONE
3. **3d.3b** (consolidate stage-3 orchestration) — DONE
4. **3d.4** (pass `_bound` as list) — DONE
5. **3d.6** (verify CQRS builders + precedence tests) — DONE

All 5 steps complete. 1103 tests pass, ruff + mypy clean.

---

## Files touched

| File | Steps | Changes |
|------|-------|---------|
| `custom_components/ramses_cc/coordinator.py` | 3d.3b, 3d.4, 3d.8 | Remove ImportError fallback (3d.8), refactor `_strip_schema_extensions` to use shared function (3d.3b), remove `isinstance(bound, str)` guard (3d.4) |
| `custom_components/ramses_cc/schemas.py` | 3d.3, 3d.3b | Delegate stage 1 to ramses_rf's `strip_traits` (3d.3), create shared `_strip_and_orchestrate` function (3d.3b), single `_HEAT_PREFIXES` definition |
| `tests/tests_new/test_schemas.py` | 3d.3, 3d.3b | Tests for consolidated stripping |
| `tests/tests_new/test_coordinator.py` | 3d.4, 3d.8 | Tests for list-valued `bound`, regression tests |
| `tests/tests_new/test_climate.py` | 3d.6 | Precedence tests for `_commands` vs native builder |
| `tools/ha_sim_test.py` | 3d.4, 3d.6 | E2E tests for multi-REM `bound` and `_commands` precedence |

---

## What's NOT in Phase 3d

- **DeviceRole / strategy profiles** — scrapped (3d.1, 3d.2 = N/A)
- **CLI compatibility** — moved to Phase 3e (blocked on ramses_rf)
- **22B0 calendar builder** — moved to Phase 3e (blocked on ramses_rf)
- **Any change to `_commands` format** — Phase 3b settled the format
  (dict templates with `_comment` metadata). 3d only verifies it works
  with the new CQRS builders.
- **Any change to ramses_rf** — 3d is ramses_cc-only. ramses_rf 0.58.3
  already provides everything we need.

---

## Phase 3e: ramses_rf-side gaps (BLOCKED, future)

Both items are blocked on ramses_rf and neither affects ramses_cc
functionality. They enhance the ecosystem (CLI usability, calendar
support) but ramses_cc works fine without them.

### 3e.1 — CLI compatibility (was 3d.5)

`strip_and_map_schema()` exists in ramses_rf but has **no callers**
inside ramses_rf itself (not Gateway, not ramses_cli). The CLI still
uses `SCH_GLOBAL_SCHEMAS` with `PREVENT_EXTRA`, so `config.json` with
`_commands`/`_bound` keys is rejected.

This needs ramses_rf-side wiring:
- Gateway/CLI should call `strip_and_map_schema()` before validation
- A `commands` trait should be added to `SCH_TRAITS` if `_commands`
  should survive into ramses_rf's internal state

**Action:** Raise an issue on ramses_rf to coordinate with PWhite-Eng.
No ramses_cc code change.

### 3e.2 — 22B0 calendar builder (was 3d.7)

No 22B0 (calendar) builder exists in ramses_rf 0.58.3. This is a
future ramses_rf feature. No ramses_cc code change until the builder
ships.

**Unblock condition:** ramses_rf adds a 22B0 builder to
`ramses_rf/commands/builders/`. Then ramses_cc can use it as the
default for calendar commands, with `_commands` as override.
