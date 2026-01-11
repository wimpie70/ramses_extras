# Hello World feature cleanup / optimization TODO

This file is a concrete checklist to keep `hello_world` a clean, minimal, *best-practice* template for future features.

## Progress (keep this up to date)

- [x] Feature-level service registration mechanism exists (`services_integration.py`) and is wired into integration setup/unload
- [x] `hello_world` registers services under the integration domain (`ramses_extras.*`) using HA-style `vol.Schema` + `ServiceCall`
- [x] `hello_world` keeps `sensor.py` as the placeholder example, and no longer exposes a placeholder `number` platform via consts/factory
- [x] Hello World editor logging is guarded by `window.ramsesExtras.debug`
- [ ] Run local checks and confirm no lint/type/test regressions
- [ ] Decide the codebase-wide plan to consolidate redundant feature const structures

## 1) Validate + CI checkpoint (do this before committing)

- [ ] **Checkpoint 1: linters**
  - Run:
    - `ruff check custom_components/ramses_extras`
    - `python3 -m compileall custom_components/ramses_extras`
- [ ] **Checkpoint 2: tests**
  - Run:
    - `make local-ci`
    - (or targeted) `pytest`

## 2) Remaining `hello_world` cleanup (still worth doing)

- [ ] **Fix entity mapping key mismatch between backend and card**
  - Current card expects `result.mappings.switch_state` / `sensor_state`.
  - Verify what `ramses_extras/get_entity_mappings` (default feature) actually returns for `feature_id="hello_world"`.
  - Update frontend or backend mapping keys to match.
  - **Checkpoint:** rerun `make local-ci`.

- [ ] **Remove duplicated editor factory methods in `hello-world.js`**
  - `hello-world.js` defines both static and instance `getConfigElement()`.
  - Keep only what the base card / HA requires.
  - **Checkpoint:** run `ruff` + `pytest` (or `make local-ci`).

- [ ] **Make device support consistent**
  - Entities are configured for `HvacVentilator` and `HgiController`, but the current factories still hardcode a `"HvacVentilator"` check.
  - Update the example to demonstrate the *intended* device-type filtering approach.
  - **Checkpoint:** run `make local-ci`.

## 3) Codebase-wide architecture follow-up (not just hello_world)

- [ ] **Consolidate feature const structures**
  - Goal: one authoritative structure per feature for:
    - entity configs
    - device mapping
    - websocket metadata
    - card metadata
  - Proposed direction:
    - make `FEATURE_DEFINITION` the single required dict for registry consumption
    - remove/avoid parallel structures like `FEATURE_WEB_CONFIGS`, `HELLO_WORLD_CONFIG`, etc.
  - This should be done consistently across all features + the framework.
  - **Checkpoint:** after each refactor chunk, run `ruff` and `make local-ci`.

- [ ] **Debug flag configuration**
  - Keep using `window.ramsesExtras.debug` as the frontend switch.
  - Consider adding:
    - a framework/global option to toggle it
    - optional per-feature debug toggles
  - **Checkpoint:** `make local-ci`.
