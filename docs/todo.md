- more cleanup on the features, framework, starting with the hello world feature

Do we know what cards are enabled at startup ?
- removing deployed cards from local/www/ramses_extras/* when removing the entry ? or when removing a feature ?
- same for registered resources
- we can instead show a placeholder card for each feature that is disabled, with a message to enable it in the config flow
- we can create small 'main-card.js' files for each card, that will be registered. It will redirect to the real card if enabled, or show a 'this card is disabled, you can enabled it's feature from the Ramses Extras configuration'
- add update parameters
sensor control improvements

- why external calculated abs humid entities:
We may have a few temp/humid sensors for 1 fan. eg. a bathroom and a kitchen....I want to be able to create logic later that if 1 of them goes high we also should ventilate high (but then for eg 15 minutes) to get rid of the local moisture. But this would need extra logic and handshaking with automations that control the speed....
Or, we would create some kind of OR logic for the different abs humid entities -> select the highest one as the one to work with and fall back to internal after 15 minutes...or always use the highest one....The same but upside-down goes for too dry air.

# Ramses Extras - Improvement / Cleanup TODO

> **Testing reminder:** For every task below, evaluate whether we can add or improve tests for the files we touch to keep increasing coverage.

 ## High priority (low risk, immediate cleanup)

 - **Consolidate WebSocket registries (there are 2 today)**
   - **Problem**
     - `custom_components/ramses_extras/websocket_integration.py` registers commands by iterating registry metadata and then uses import + `getattr()`.
     - Note: `WS_COMMAND_REGISTRY` + `register_ws_commands()` in `custom_components/ramses_extras/const.py` appears to already be removed (todo.md was outdated).
   - **Why this is risky/obsolete**
     - Home Assistant decorators (e.g. `@websocket_api.websocket_command`) only tag handlers (`_ws_command`, `_ws_schema`); they do **not** register handlers.
     - Actual registration requires calling `websocket_api.async_register_command(hass, handler)`.
   - **Goal**
     - Decide on *one* source of truth for “what commands exist” (metadata) and *one* mechanism for “how commands are registered” (decorators).
   - **Concrete actions**
     - Keep decorators for schema/command metadata tagging.
     - Ensure we have exactly one registrar that calls `websocket_api.async_register_command()`.
     - Avoid double-importing websocket modules.
       - Chosen: registrar imports+registers (Option A): `websocket_integration.py` imports feature `websocket_commands` and registers handlers.
       - `__init__.py` should not import per-feature `websocket_commands` modules.

 - **Remove / rewrite placeholder code paths that were introduced for tests**
   - Note: this item was partially outdated.
   - `_get_required_entities_from_feature()` lives in `custom_components/ramses_extras/framework/helpers/entity/core.py`.
     - It is implemented (imports `features.<feature>.const` and reads `*_CONST["required_entities"]`).
     - It still returns `{}` if the const/module/key is missing.
   - Next action:
     - Confirm which call sites still rely on it and whether we want the fallback-to-empty behaviour.

 - **Fix duplication inside `PlatformSetup.async_create_and_add_platform_entities()`**
   - `custom_components/ramses_extras/framework/helpers/platform.py`
     - It duplicates device filtering logic already present in `get_filtered_devices_for_feature()`.
   - **Goal**
     - Single helper to filter devices by feature enablement.

 - **Reduce noisy logging and emoji logging**
   - `custom_components/ramses_extras/__init__.py`, `extras_registry.py`, `websocket_integration.py`.
   - Convert high-frequency logs to `_LOGGER.debug()`; keep a few key `_LOGGER.info()` at startup.
   - Decide a consistent policy on emojis (either keep only for milestone logs, or remove).


 ## High priority (medium risk, structural clarity)

 - **Clarify the “feature loading” pipeline (there appear to be multiple overlapping mechanisms)**
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

 - **Pick one WebSocket “integration boundary”**
   - Today, default feature already exposes core WS endpoints (`features/default/websocket_commands.py`).
   - Meanwhile `custom_components/ramses_extras/websocket_integration.py` tries to dynamically import and register.
   - **Goal**
     - Either:
       - (Option A) Keep `websocket_integration.py` minimal: only import modules to trigger decorators, no `async_register_command()` calls.
       - (Option B) Centralize all WS registrations in a single module (probably default feature) and remove the dynamic registrar.


 ## Medium priority (cleanup / tech debt)

 - **Prune unused helpers in `framework/helpers/platform.py`**
   - Candidates:
     - `create_entities_for_device()` (looks unused and contains older logging patterns).
     - `calculate_required_entities()` (seems like debug tooling; verify if used anywhere).
   - Replace ad-hoc debug listing (`_LOGGER.info("Debug: ...")`) with structured debug logs.

 - **Unify feature constants shape**
   - Today features expose varying const structures:
     - `features/default/const.py` uses `DEFAULT_CONST`.
     - `features/hello_world/const.py` uses `HELLO_WORLD_CONST` but still has placeholder configs.
     - `features/humidity_control/const.py` uses `HUMIDITY_CONTROL_CONST`.
   - Goal: one convention for:
     - `FEATURE_ID`
     - `required_entities`
     - cards config
     - WS command metadata (if kept)


 ## Cards & resources lifecycle

 - **Do we know what cards are enabled at startup?**
 - **Remove deployed cards from `local/www/ramses_extras/*`**
   - On entry removal? feature disable? both?
 - **Same for registered resources**
 - **Create JSON file in `local/www/ramses_extras/config`**
   - Card info for card registration without hass instance.


 ## Sensor control improvements

 - **External calculated absolute humidity entities / multi-sensor strategy**
   - Scenario: multiple temp/humidity sensors for one fan (bathroom + kitchen).
   - Desired behaviour:
     - If any zone spikes, ventilate high for N minutes (handshake with automation).
     - Need OR / max logic and a cooldown / decay strategy.
   - Ideas to explore:
     - Add “aggregation strategy” per device (max/avg/weighted) for resolved metrics.
     - Make Humidity Control consume an abstract “effective abs humidity” that can switch sources.


 ## Developer experience

 - **Add an explicit “Framework API surface” doc section**
   - What helpers are stable for features to call (PlatformSetup, CardRegistry, SensorControlResolver, etc.).
 - **Add a cleanup test**
   - A unit test asserting there are no duplicate registries / unused registries for WS.
