# Ramses Extras - Architecture / Optimization TODO

This file tracks *big picture* cleanup and refactoring work across the integration.

## Scope

- Framework: `./framework/todo.md`
- Features:
  - `./features/default/todo.md`
  - `./features/humidity_control/todo.md`
  - `./features/sensor_control/todo.md`
  - `./features/hvac_fan_card/todo.md`

## Big picture

- [x] Review integration boundaries (framework vs features vs top-level integration)
- [x] Identify feature-specific code currently living in the framework and propose moves
- [x] Identify duplicate or over-complicated framework utilities and propose simplifications
- [x] Confirm service/websocket/entity/automation responsibility boundaries are consistent across the codebase

## Notes / findings

- `hello_world` is example/template code.
- Resolved framework feature-specific leakage:
  - `framework/helpers/websocket_base.py` no longer applies `sensor_control` overrides inside the framework.
  - `framework/helpers/websocket_base.py` no longer hardcodes feature constant prefixes when scraping const modules.
  - `framework/helpers/config/validation.py` no longer defines feature-specific validation rule constants.

- Base classes cleanup:
  - Removed unused legacy `RamsesSensorEntity` from `framework/base_classes/base_entity.py`.
  - Updated tests to remove the obsolete `RamsesSensorEntity` test suite and add coverage for `ExtrasBaseEntity`.

- Architecture review (initial findings):
  - Enabled-feature resolution is duplicated across:
    - `__init__.py` (entry setup + feature instance creation)
    - `services_integration.py`
    - `websocket_integration.py`
    Consider centralizing this into a single helper (to avoid drift between modules).
  - Integration boundaries are improving (feature-centric services/ws modules), but `__init__.py` remains the "god" orchestrator:
    - It loads feature definitions, imports platforms, registers websocket/services, manages card deployment, creates feature instances, and starts automations.
    Consider extracting orchestration into small, testable helpers (no behavior changes).
  - Config validation appears split between:
    - `framework/helpers/common/validation.py`
    - `framework/helpers/config/validation.py`
    This likely contains duplication; worth inventorying and consolidating patterns.

## Notes / findings (consolidated)

- Boundaries (current state):
  - `__init__.py` is the authoritative integration entrypoint and currently performs multiple roles:
    - Resolves enabled features.
    - Loads feature definitions (registry).
    - Imports feature platform modules.
    - Discovers devices.
    - Forwards platform setups.
    - Registers WebSocket and service integrations.
    - Creates feature instances and starts automations.
    - Manages card deployment + a cards_enabled latch.
  - Framework responsibilities are mostly “shared primitives”, but there is some unavoidable orchestration bleed-through:
    - Entity ID parsing/generation, device helpers, config-flow helpers, config validation.
    - WebSocket base command utilities.
  - Features own their own business logic:
    - Entity configs, service handlers, websocket handlers, automation logic.

- Enabled feature resolution (duplication risks):
  - We currently resolve enabled features from multiple sources (`hass.data`, `entry.data`, `entry.options`) in multiple modules.
  - Tests cover that disabled features should not expose their WebSocket/services surface area, so drift here is a correctness risk.

- Config/UI schema split:
  - Home Assistant UI uses `vol.Schema`/selectors.
  - Some feature modules define JSON-schema-like structures (`get_config_schema`) that are not consumed by HA UI flows.
  - This is a source of conceptual duplication and confusion (two schema representations).

- Error handling policy (boundary implications):
  - Orchestration paths are best-effort: errors in one feature should not prevent other features from loading.
  - Core validation helpers raise typed exceptions for invalid inputs.

## Proposed consolidation directions (low-risk, record now / implement later)

- Single authority for enabled features:
  - Introduce a single helper (module-level function) used by `__init__.py`, `services_integration.py`, and `websocket_integration.py`.
  - Keep “default is always enabled” in exactly one place.

- Extract orchestration helpers out of `__init__.py` (without changing behavior):
  - Keep `async_setup_entry()` as the entrypoint but delegate into small internal helpers:
    - load feature definitions
    - import platform modules
    - register websocket
    - register services
    - create/start feature instances
    - card deployment + latch
  - Goal: reduce “god function” pressure and make unit testing easier.

- Clarify schema responsibilities:
  - Treat `vol.Schema` (selectors) as the single representation for HA UI.
  - If `get_config_schema()` remains, document it as non-HA consumer only (e.g. cards/external tooling), otherwise remove it.

- Consolidate entity metadata derivation:
  - Ensure there is exactly one authority for “what entities exist for a feature” (avoid duplication between helpers and config-flow manager).
