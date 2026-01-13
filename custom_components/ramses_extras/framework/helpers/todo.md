# Framework / Helpers - Optimization TODO

Major areas:

- `entity/` (entity ID generation, entity lookup, entity manager)
- `config/` + `config_flow.py` (option schemas, validation)
- `websocket_base.py` (WS command registration and dispatch)
- `ramses_commands.py` + `commands/registry.py` (command send/registry)
- `paths.py` (feature/module path helpers)
- `platform.py` (platform setup helpers)
- `brand_customization/` (brand detection/customizers)

## Tasks

- [x] Identify duplicated validation helpers between `helpers/common/validation.py` and `helpers/config/validation.py`
- [x] Review `helpers/entity/core.py` vs `helpers/entity/simple_entity_manager.py` for overlap and simplification opportunities
- [x] Review `websocket_base.py` for feature-specific leakage and reduce surface area
- [x] Review config schema patterns for consistency (feature config vs integration options)
- [x] Review error handling patterns (what exceptions are caught vs allowed to bubble)

## Notes / findings

- Resolved framework leakage:
  - `websocket_base.py` no longer imports `sensor_control` or applies overlays in the framework.
  - `websocket_base.py` no longer scrapes const module attributes using hardcoded prefixes.
  - `config/validation.py` no longer contains feature-specific constants.

- Validation duplication findings:
  - `helpers/common/validation.py` (`RamsesValidator`) provides runtime validation (device IDs, entity IDs, entity states, entity template expansion) and throws `ValidationError`.
  - `helpers/config/validation.py` (`ConfigValidator`) provides config-dict validation patterns (numeric ranges, bool, string, list, dependency and range relationship) and returns `(bool, error)` pairs.
  - `helpers/config/core.py` (`ExtrasConfigManager`) re-implements overlapping config checks (`enabled` boolean, `min_value/max_value` relationship) and also contains convenience validators (`get_numeric_validation`, `get_boolean_validation`, `get_string_validation`) that overlap with `ConfigValidator`.
  - Features currently mix approaches:
    - `humidity_control/config.py` uses `ConfigValidator` + `ExtrasConfigManager.validate_config()`.
    - `hello_world/config.py` uses voluptuous schema + `ExtrasConfigManager.validate_config()`.

- Proposed consolidation direction (low-risk):
  - Keep the split by responsibility:
    - `common/validation.py` = runtime/Home Assistant state validation.
    - `config/validation.py` = config dictionary validation.
  - Simplify `ExtrasConfigManager.validate_config()` to only perform minimal generic checks (e.g. `enabled` is boolean if present), and remove template/example-only checks (`min_value/max_value`).
  - Remove or deprecate `ExtrasConfigManager.get_*_validation()` helpers and have callers use `ConfigValidator` directly (or delegate to a shared `ConfigValidator` instance inside `ExtrasConfigManager`).

- Entity helper overlap findings (`entity/core.py` vs `entity/simple_entity_manager.py`):
  - `EntityHelpers` (core.py) owns entity-id parsing and generation logic (`detect_and_parse()`, `generate_entity_name_from_template()`), plus feature const introspection helpers (`_get_required_entities_from_feature()` / `_import_required_entities_sync()` and `_import_entity_mappings_sync()`).
  - `SimpleEntityManager` re-implements the same *feature const introspection* logic inside `_generate_entity_ids_for_combination()`:
    - Reads `FEATURE_DEFINITION`.
    - Derives `required_entities` from `sensor_configs`/`switch_configs`/etc and `optional` flags.
    - Builds templates and uses `EntityHelpers.generate_entity_name_from_template()`.
  - Net effect: the “what entities exist for a feature” rules are duplicated in two locations with slightly different surface area and error handling.
  - There is also a conceptual split that isn’t clean yet:
    - `EntityHelpers` mixes pure/string functions (parsing/generation) with integration-level concerns (importing feature const modules).
    - `SimpleEntityManager` is explicitly “config flow operations”, but currently performs both orchestration *and* feature inspection.

- Proposed consolidation direction (low-risk):
  - Keep `EntityHelpers` as the single authority for:
    - Entity-ID parsing/generation.
    - Reading feature const metadata (required entities + mapping resolution).
  - Make `SimpleEntityManager` call `EntityHelpers` helpers for required entities, instead of duplicating feature const parsing.
  - Consider extracting a narrow helper with a stable signature (e.g. `get_required_entities(feature_id) -> dict[platform, list[name]]` and `get_entity_templates(feature_id) -> ...`) and using it from both config-flow code and runtime startup validation.
  - Keep the current safety rule noted in `SimpleEntityManager.validate_entities_on_startup()` (do not create entity-registry-only entries that become permanently unavailable).

- Config schema consistency findings:
  - The integration options UI is built with `vol.Schema` + HA selectors in the central `config_flow.py` and `framework/helpers/config_flow.py`.
  - Feature-specific options steps (e.g. `features/default/config_flow.py`, `features/sensor_control/config_flow.py`) also build `vol.Schema` directly and delegate to the central flow.
  - `ExtrasConfigManager.get_config_schema()` returns a JSON-schema-like dict, but there are no call sites consuming `get_config_schema()` in the config flow/options flow.
  - Some feature config modules define additional schemas (e.g. `features/hello_world/config.py` has `FEATURE_CONFIG_SCHEMA` / `OPTIONS_SCHEMA`), but these are validated at runtime and are not integrated into the options flow UI.
  - Net effect: we currently have two schema representations (voluptuous vs JSON-schema-like dicts), but only voluptuous is used for the HA UI.

- Proposed consolidation direction (low-risk):
  - Treat `vol.Schema` (with selectors) as the single UI schema representation for Home Assistant flows.
  - Clarify whether `get_config_schema()` is intended for a non-HA UI consumer (cards or external tooling). If not, consider removing it or moving it behind an explicit “non-HA UI schema” API.
  - For feature runtime validation, prefer a consistent approach:
    - Either voluptuous validation (like `hello_world`) or `ConfigValidator` rules (like `humidity_control`), but avoid implying that `get_config_schema()` affects the HA UI.

- Error handling patterns findings:
  - Setup/orchestration paths generally aim to be resilient and continue operating with reduced functionality:
    - `services_integration.py` and `websocket_integration.py` catch `ImportError` for missing per-feature modules and continue.
    - Feature module setup/unload exceptions are caught and logged (tests expect these paths to not raise).
    - `config_flow.py` and feature config flow helpers use broad try/except for best-effort summaries and defensive UI logic.
  - “Core-ish” utilities tend to raise for programmer/config errors and return `None`/`False` for user/environmental absence:
    - `EntityHelpers.generate_entity_name_from_template()` raises `ValueError` for invalid templates.
    - `EntityHelpers.detect_and_parse()` returns `None` on malformed entity IDs.
    - `common/validation.py` raises `ValidationError` for invalid runtime inputs.
  - There is mixed usage of broad exception catches in runtime feature logic:
    - Automations and services often use `except Exception` to return `False`/no-op (e.g. humidity services and automation enablement checks).
    - Framework lifecycle code (`ExtrasBaseAutomation._on_homeassistant_started`) catches exceptions and marks feature as not ready.

- Recommended conventions (low-risk, align with current tests):
  - For integration orchestration (setup/unload/registration):
    - Catch errors per-feature, log, and continue with other features so one feature cannot break the whole integration.
    - Prefer specific exceptions where practical (e.g. `ImportError` for optional modules), otherwise use `except Exception as err`.
  - For pure/helpers validation: raise typed exceptions (`ValueError`, `ValidationError`) and keep functions side-effect free.
  - For “best-effort” UI/diagnostics paths (config flow overview texts, optional card cleanup): catch broadly but keep logging minimal and structured.
  - For logging: prefer `_LOGGER.exception(...)` when the traceback is actionable; otherwise `_LOGGER.error(..., %s)`.
