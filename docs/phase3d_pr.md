## Phase 3d: ramses_rf alignment

### Summary

Consolidates duplicated schema-stripping logic, passes list-valued `_bound` through to ramses_rf, and cleans up dead code — aligning ramses_cc with ramses_rf 0.58.3 (already pinned in the manifest).

**4 commits, net -130 lines** (491 insertions, 361 deletions across 4 files).

### Changes

**3d.8 — Remove dead ImportError fallback** (`coordinator.py`)
- Removed ~40 lines of `try/except ImportError` fallback for `strip_traits` / `strip_and_map_traits` (manifest pins `ramses-rf==0.58.3`, functions shipped in 0.58.2; comment wrongly said "< 0.59.0")

**3d.3 — Consolidate stage-1 stripping** (`schemas.py`)
- `strip_traits_for_validation()` now delegates stage-1 stripping to ramses_rf's `strip_traits()` instead of using an inline `_strip_traits` duplicate (the coordinator's `_strip_schema_extensions` already did this)

**3d.3b — Consolidate stage-3 orchestration** (`schemas.py`, `coordinator.py`)
- Both `strip_traits_for_validation()` (config_flow validation) and `_strip_schema_extensions()` (gateway feeding) now call a single shared `_strip_and_orchestrate()` function — ensures validation-passing schemas match what the gateway actually receives
- **Bug fix:** the coordinator path was missing the `placed_in_lists` check — a device in a parent's `remotes[]`/`sensors[]`/`actuators[]` list could also appear in `orphans_hvac` (duplicate). Now fixed.
- Unified 3 separate `_HEAT_PREFIXES` definitions into one (8/8/12 prefixes → single 8-prefix set)
- Unified `_TCS_ORPHAN_PREFIXES`, `_SCHEMA_EXTENSION_KEYS` into single definitions in `schemas.py`
- Fixed `_DEVICE_ID_RE` in `schemas.py` to use hex regex (was decimal-only — missed hex device IDs like `1F:000002`)
- `_strip_schema_extensions` is now a 5-line thin wrapper (was ~200 lines)

**3d.4 — Pass `_bound` as `str | list[str]`** (`coordinator.py`)
- Removed `isinstance(bound, str)` guard in `_derive_known_list_from_schema` — list-valued `_bound` (multi-REM FAN binding) now reaches ramses_rf (0.58.2+ `SCH_TRAITS_HVAC` accepts `str | list[str] | None`)
- Updated the "remove `bound` if no `class`" sanitizer to only strip `bound` from heat devices — HVAC devices without explicit `_class` are valid (`SCH_TRAITS_HVAC` defaults `class` to `HVC`)

**3d.6 — Precedence tests** (`test_climate.py`, test-only)
- Added 4 tests verifying the `async_set_fan_mode` precedence chain: FAN `_commands` (dict template) > REM `_commands` (packet string) > `known_list` (legacy) > native `set_fan_mode` (ramses_rf CQRS builder)

### Moved to Phase 3e (blocked on ramses_rf, not in this PR)
- **3e.1** (was 3d.5 — CLI compatibility) — ramses_rf has no callers for `strip_and_map_schema`; Gateway/CLI still use `PREVENT_EXTRA`. Needs ramses_rf-side wiring. Does not affect ramses_cc.
- **3e.2** (was 3d.7 — 22B0 calendar builder) — no builder exists in ramses_rf 0.58.3. Future ramses_rf feature. Does not affect ramses_cc.

### Test plan
- [x] `pytest tests/tests_new/` — 1103 passed, 10 skipped
- [x] `ruff check .` + `ruff format --check .` — clean
- [x] `mypy custom_components/ramses_cc/` — no issues
- [ ] `ha_sim_test.py` — run against ha-sim container with editable `ramses_rf` install
- [ ] Manual: verify a FAN with `_bound: ["37:170000", "37:170001"]` reaches ramses_rf correctly
- [ ] Manual: verify config_flow validation matches gateway behaviour (consolidated stripper)

---

Design doc: `ramses_extras/docs/phase3d_design.md`
