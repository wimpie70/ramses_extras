# Ramses Extras - Improvement / Cleanup TODO

> **Testing reminder:** For every task below, evaluate whether we can add or improve tests for the files we touch to keep increasing coverage.
> **Registry reminder:** Changing registries is delicate; keep changes isolated and avoid touching global registries unless strictly required.

## Status: Done

 - [x] **Consolidate WebSocket registries (there are 2 today)**
   - ✅ Confirmed Option A is already implemented:
     - `extras_registry` is the single metadata source (via `register_websocket_commands()`).
     - `websocket_integration.py` is the sole registrar (imports `websocket_commands` modules and calls `websocket_api.async_register_command()`).
     - No double imports or other registrars exist.
     - **Note**: The registrar *cannot* be removed—decorators only tag handlers, explicit registration is required (previous removals broke WS commands).

 - [x] **Remove / rewrite placeholder code paths that were introduced for tests**
   - ✅ Consolidated duplicated `_get_required_entities_from_feature()` implementations:
     - Removed sync version from `framework/helpers/automation/core.py`
     - Kept async version in `framework/helpers/entity/core.py` (more robust)
     - Added sync wrapper `get_required_entities_from_feature_sync()` for backward compatibility
     - Updated `base_automation.py` to use appropriate version (async for async contexts, sync wrapper for sync contexts)
   - The function is now properly implemented and no longer a "placeholder" - it correctly reads `required_entities` from feature const modules.

 - [x] **Fix humidity control persistence issue**
   - ✅ Fixed the issue where `humidity_control` device enablement was not persisting across Home Assistant restarts when configured alone (without changes to other features like `hello_world`).
   - ✅ Added targeted debug logs in options flow to trace matrix state.
   - ✅ Modified options flow to persist `device_feature_matrix` in `config_entry.options` instead of only `config_entry.data`.
   - ✅ Updated platform setup to prioritize `config_entry.options` matrix over `config_entry.data` matrix.
   - ✅ Fixed lint/type errors introduced by new code changes.


## Status: Next (priority)

### High priority (low risk, immediate cleanup)

 - [ ] **Fix duplication inside `PlatformSetup.async_create_and_add_platform_entities()`**
   - `custom_components/ramses_extras/framework/helpers/platform.py`
     - It duplicates device filtering logic already present in `get_filtered_devices_for_feature()`.
   - **Goal**
     - Single helper to filter devices by feature enablement.

### High priority (low risk)

 - [ ] **Reduce noisy logging and emoji logging**
   - `custom_components/ramses_extras/__init__.py`, `extras_registry.py`, `websocket_integration.py`.
   - Convert high-frequency logs to `_LOGGER.debug()`; keep a few key `_LOGGER.info()` at startup.
   - Decide a consistent policy on emojis (either keep only for milestone logs, or remove).


## Status: Next (structural / medium risk)

 - [ ] **Clarify the “feature loading” pipeline (there appear to be multiple overlapping mechanisms)**
   - `custom_components/ramses_extras/__init__.py`
     - Loads feature const modules with `load_feature()`.
     - Imports platform modules from each feature’s `platforms/*.py`.
     - Imports feature `websocket_commands` modules.
   - `custom_components/ramses_extras/extras_registry.py`
     - Has its own `load_all_features()`/`load_feature_definitions()` concept.
   - **Goal**
     - Have one authoritative place that:
       - loads feature definitions (configs/mappings)
       - imports platform modules (registration)
       - imports websocket modules (decorators)

 - [ ] **Pick one WebSocket “integration boundary”**
   - Today, default feature already exposes core WS endpoints (`features/default/websocket_commands.py`).
   - Meanwhile `custom_components/ramses_extras/websocket_integration.py` tries to dynamically import and register.
   - **Goal**
     - Either:
       - (Option A) Keep `websocket_integration.py` minimal: only import modules to trigger decorators, no `async_register_command()` calls.
       - (Option B) Centralize all WS registrations in a single module (probably default feature) and remove the dynamic registrar.


## Status: Later (cleanup / tech debt)

 - [ ] **Prune unused helpers in `framework/helpers/platform.py`**
   - Candidates:
     - `create_entities_for_device()` (looks unused and contains older logging patterns).
     - `calculate_required_entities()` (seems like debug tooling; verify if used anywhere).
   - Replace ad-hoc debug listing (`_LOGGER.info("Debug: ...")`) with structured debug logs.

 - [ ] **Unify feature constants shape**
   - Today features expose varying const structures:
     - `features/default/const.py` uses `DEFAULT_CONST`.
     - `features/hello_world/const.py` uses `HELLO_WORLD_CONST` but still has placeholder configs.
     - `features/humidity_control/const.py` uses `HUMIDITY_CONTROL_CONST`.
   - Goal: one convention for:
     - `FEATURE_ID`
     - `required_entities`
     - cards config
     - WS command metadata (if kept)

## Cards & resources lifecycle (Later)

 - [ ] **Do we know what cards are enabled at startup?**
 - [ ] **Remove deployed cards from `local/www/ramses_extras/*`**
   - On entry removal? feature disable? both?
 - [ ] **Same for registered resources**
 - [ ] **Create JSON file in `local/www/ramses_extras/config`**
   - Card info for card registration without hass instance.

## Sensor control improvements (Later)

 - [ ] **External calculated absolute humidity entities / multi-sensor strategy**
   - Scenario: multiple temp/humidity sensors for one fan (bathroom + kitchen).
   - Desired behaviour:
     - If any zone spikes, ventilate high for N minutes (handshake with automation).
     - Need OR / max logic and a cooldown / decay strategy.
   - Ideas to explore:
     - Add “aggregation strategy” per device (max/avg/weighted) for resolved metrics.
     - Make Humidity Control consume an abstract “effective abs humidity” that can switch sources.

 - [ ] **Restore the Sensor Control / card config 2-step wizard (device select -> entity mapping)**
   - Regression: we previously had a pulldown select box for choosing a device, then a next step where we could choose entities to map.
   - Verify whether the missing step is:
     - the HA options flow feature config (`features/sensor_control/config_flow.py`), and/or
     - the HVAC fan card editor (`features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card-editor.js`).
   - Goal: selecting a device should then provide a guided UI to map/override entities (per metric), and persist the result.
   - **Note**: registry changes are delicate; keep changes isolated and avoid touching global registries unless strictly required.


## Developer experience (Later)

 - [ ] **Add an explicit “Framework API surface” doc section**
   - What helpers are stable for features to call (PlatformSetup, CardRegistry, SensorControlResolver, etc.).
 - [ ] **Add a cleanup test**
   - A unit test asserting there are no duplicate registries / unused registries for WS.
