# Hello World feature cleanup / optimization TODO

This file is a concrete checklist to keep `hello_world` a clean, minimal, *best-practice* template for future features.

## Progress (keep this up to date)

- [x] Feature-level service registration mechanism exists (`services_integration.py`) and is wired into integration setup/unload
- [x] `hello_world` registers services under the integration domain (`ramses_extras.*`) using HA-style `vol.Schema` + `ServiceCall`
- [x] `hello_world` keeps `sensor.py` as the placeholder example, and no longer exposes a placeholder `number` platform via consts/factory
- [x] Hello World editor logging is guarded by `window.ramsesExtras.debug`
- [x] `GetEntityMappingsCommand` uses `FEATURE_DEFINITION` (no legacy *_CONST / attribute scanning)
- [x] `SimpleEntityManager` uses `FEATURE_DEFINITION` for entity generation (mypy clean)
- [ ] Run local checks and confirm no lint/type/test regressions

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
  - Semantics to keep straight:
    - `*_configs` (e.g. `switch_configs`) = *definitions* (how to build an entity if it exists)
    - `required_entities` = *intent* (which entities should be created/validated for the feature)
      - If `required_entities` is omitted, we currently **derive it from the keys of `*_configs`**.
      - Derived required entities exclude configs marked with `optional: True`.
      - Use explicit `required_entities` when:
        - only a subset of configs should exist (optional entities)
        - the feature relies on entities created elsewhere (e.g. ramses_rf sensors)
        - the feature is card-only (configs empty) but automation/UI still needs mappings
    - `entity_mappings` = *frontend/automation mapping* (template strings), may include entities not
      created by this feature.
  - This should be done consistently across all features + the framework.
  - **Checkpoint:** after each refactor chunk, run `ruff` and `make local-ci`.

- [ ] **Next concrete migration steps**
  - [ ] Move `humidity_control` automation off `HUMIDITY_CONTROL_CONST`
    - Add `required_entities` + `entity_mappings` into `FEATURE_DEFINITION`
    - Update consumers to read from `FEATURE_DEFINITION`
    - Remove `HUMIDITY_CONTROL_CONST` exports + update tests
  - [ ] Remove unused per-feature web/card blobs
    - `FEATURE_WEB_CONFIGS`, `HELLO_WORLD_CONFIG`, `HVAC_FAN_CARD_CARD_CONFIG`
    - Keep only `FEATURE_DEFINITION['card_config']` / `*_CARD_CONFIGS` if still needed
  - [ ] Simplify `extras_registry` fallback paths once all features are migrated
    - Remove legacy scanning of `*_SENSOR_CONFIGS`, `*_CONST`, etc.
  - [ ] **Checkpoint:** `mypy .` + `pytest .` (or `make local-ci`).

- [ ] **Debug flag configuration**
  - Keep using `window.ramsesExtras.debug` as the frontend switch.
  - Consider adding:
    - a framework/global option to toggle it
    - optional per-feature debug toggles
  - **Checkpoint:** `make local-ci`.
