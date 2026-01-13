# Framework / Base Classes - Optimization TODO

Targets:

- `base_automation.py`
- `base_entity.py`
- `platform_entities.py`
- `base_card_manager.py`

## Tasks

- [x] Map responsibilities and dependencies of each base class (who calls what)
- [x] Identify duplication between `base_entity.py` and `platform_entities.py`
- [x] Check for over-complicated lifecycle flows in `base_automation.py` (simplify without behavior changes)
- [x] Verify type hints and reduce `Any` usage where safe
- [x] Confirm base classes have no feature-specific assumptions

## Notes / responsibilities

### `base_automation.py` (`ExtrasBaseAutomation`)

- Owns automation lifecycle:
  - `start()` / `stop()` manage registration/cleanup.
  - Startup is HA-event based:
    - If HA already running: initialize immediately.
    - Else: register a one-shot listener for `homeassistant_started`.
- Owns state-change subscriptions:
  - `_register_entity_listeners()` resolves entity patterns and registers listeners.
  - Uses `async_track_state_change_event` per concrete entity found.
- Owns debouncing and orchestration:
  - `_handle_state_change()` is the sync entrypoint from HA callback.
  - It schedules `_async_handle_state_change()` on the event loop.
  - Debounce timers are keyed by device.
- Delegates feature logic:
  - `_process_automation_logic(device_id, entity_states)` is abstract and implemented by the feature.
- Exposes a framework-safe way to update automation-owned binary sensors:
  - `set_binary_sensor_state(entity_id, is_on)` updates binary_sensor state following HA patterns.

### `base_entity.py` (`ExtrasBaseEntity`)

- Provides shared entity identity and device association:
  - Normalizes `device_id` variants (`id`, `device_id`, `_id`, etc.).
  - Creates `DeviceInfo` and attaches entities to the integration device.
  - Computes a `unique_id` fallback from `entity_id` or (`entity_type`, `device_id`).
- Serves as a mixin/base for platform entities:
  - Intended to be composed with HA `Entity` / `SensorEntity` / etc.
 - The legacy `RamsesSensorEntity` helper has been removed (Option A) since it was unused.

### `platform_entities.py` (generic platform entity classes + `generic_platform_setup`)

- Purpose: reduce duplication across platform implementations.
- `ExtrasPlatformEntity`:
  - Composes `ExtrasBaseEntity` + HA `Entity`.
  - Centralizes entity identity setup:
    - `_setup_entity_identity()` uses config `entity_template` + `EntityHelpers.generate_entity_name_from_template()`.
    - Sets `_attr_unique_id` derived from `entity_id`.
- Provides per-platform generic entity base classes:
  - `ExtrasSwitchEntity`, `ExtrasNumberEntity`, `ExtrasBinarySensorEntity`, `ExtrasSensorEntity`.
  - Each handles the minimal platform-specific attributes/state.
- `ExtrasNumberEntity` optionally persists value into `config_entry.options` via `_save_value_to_config()`.
- `generic_platform_setup(...)`:
  - Takes `platform_configs` (from `FEATURE_DEFINITION`) and an `entity_factory`.
  - Instantiates entities for a feature/platform and calls `async_add_entities`.
  - This is the intended “one place” for common setup flow.

### Duplication / overlap findings (`base_entity.py` vs `platform_entities.py`)

- Entity identity setup is currently split across two places:
  - `ExtrasBaseEntity` does device association (`DeviceInfo`) and `unique_id` fallbacks.
  - `ExtrasPlatformEntity._setup_entity_identity()` does entity_id + unique_id derivation + display name.
  - Net result: the “single source” for identity is not obvious; features may accidentally bypass one of the paths.

 - Previously, `RamsesSensorEntity` overlapped with `ExtrasSensorEntity` (two competing conventions for entity_id generation).
   That duplication is now removed by deleting the unused legacy class.

- Error handling/logging patterns for identity generation are duplicated:
  - Both modules wrap `EntityHelpers.generate_entity_name_from_template(...)` and log failures.
  - Failure messages are slightly different but semantically identical.

### Low-risk refactor options (behavior-preserving)

- Option A (implemented): remove unused `RamsesSensorEntity`
  - Confirmed via grep that it was not referenced by active features.
  - This removes the duplicate “generic sensor base” path in favor of template-driven platform entities.
  - Tests were updated to remove the obsolete test suite and add coverage for `ExtrasBaseEntity` branches.

- Option B: move identity setup helper into `ExtrasBaseEntity`
  - Introduce a protected helper on `ExtrasBaseEntity` to set `entity_id` / `_attr_unique_id` / `_attr_name`.
  - `ExtrasPlatformEntity` calls it, and `RamsesSensorEntity` (if kept) calls the same helper.
  - Benefits:
    - Centralizes identity behavior.
  - Risk:
    - Touches the base for all entities; must be done carefully and tested.

- Option C: keep as-is but document conventions
  - Explicitly document that platform entities should use `platform_entities.py` and that `RamsesSensorEntity` is legacy.
  - Lowest risk, but does not reduce duplication.

### Lifecycle simplification opportunities (`base_automation.py`)

- Listener registration is more complex than it needs to be:
  - `_register_entity_listeners()` expands patterns into a concrete list of current entities and registers a listener per entity.
  - When nothing matches, a periodic timer calls `_register_entity_listeners()` again.
  - This is workable but tends to create a “scan loop” pattern.
  - Low-risk improvement: add a guard so we never create multiple periodic timers.

- Thread-safe scheduling is likely redundant:
  - `_handle_state_change()` uses `loop.call_soon_threadsafe()` to schedule an async task.
  - HA state change event callbacks already run on the event loop.
  - Low-risk improvement: call `self.hass.async_create_task(...)` directly.

- Validation uses two different sources of truth:
  - `_validate_device_entities()` builds expected entity IDs via `f"{entity_type}.{entity_name}_{device_id}"`.
  - `_get_device_entity_states()` uses `get_feature_entity_mappings(...)`.
  - This can lead to mismatch if mappings/templates change.
  - Low-risk improvement: derive validation targets from `get_feature_entity_mappings(...)` too.

- Device-id extraction warnings are duplicated:
  - `_async_handle_state_change()` logs on failure to extract device_id.
  - `_extract_device_id()` also logs on failure.
  - Low-risk improvement: log only in `_extract_device_id()`.

- Periodic check stop condition may under/over-stop:
  - It compares `listeners_after > listeners_before` to decide to stop.
  - If listeners were already partially registered, this might keep the timer running longer than needed.
  - Low-risk improvement: stop when `len(self._specific_entity_ids) > 0`.

- Logging style consistency:
  - There are several f-string logs in `base_automation.py` that could be converted to lazy formatting.
  - Not urgent, but reduces noise in future diffs.

### Type-hints / Any reduction notes (safe)

- `base_automation.py`:
  - Tightened callback/timer surfaces (`_listeners`, `_change_timers`, periodic handle).
  - Added a minimal protocol for the optional binary sensor hook (`set_state(bool)`).
  - Clarified `entity_states` typing as `Mapping[str, float | bool]`.
- `platform_entities.py`:
  - Fixed an exception formatting bug in `_LOGGER.error(...)` (`%e` -> `%s`).
  - Removed an unused import.
- `base_entity.py`:
  - Removed unused imports and an unused module logger.

### Feature-specific assumptions check

- No feature-specific imports or runtime logic were found in base classes.
- Some docstrings/examples mention concrete feature names (e.g. "humidity_control", "hello_world") purely as illustrative examples.

### `base_card_manager.py` (`BaseCardManager`)

- Purpose: manage feature-owned frontend cards (discovery/registration/cleanup).
- `async_register_cards()`:
  - Reads feature-provided card config(s) via `_get_card_configurations()` (override point).
  - Validates expected JS files exist under the feature directory.
  - Returns a dict of registered card metadata.
- `async_cleanup()` clears internal registrations.
- This layer should remain feature-agnostic; it should not know card-specific semantics beyond:
  - ID/name/location/js file existence.
