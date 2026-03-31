# FAN Zones - Implementation Plan

## Purpose

Define how Ramses Extras should model and use zones attached to FAN systems, covering both:

- native/real zones associated with ORCON fan systems
- user-defined zones implemented with custom hardware such as valves and Shelly 2PM Gen3

The goal is to create a zone model that can later drive fan control, diagnostics, and UI without tying the architecture to one specific hardware source.

## Scope

This plan covers:

- zone data model
- hardware abstraction for ORCON and custom zones
- integration points with fan control, cards, and future automations
- phased rollout strategy

This plan does not require full closed-loop zone control in phase 1.

## Goals

- Represent zones in a common Extras model regardless of source hardware.
- Allow one FAN device to own multiple zones.
- Support both read-only and controllable zones.
- Prepare for future fan demand generation from zone state.
- Keep the architecture extensible for non-Shelly actuators later.

## Non-goals for phase 1

- Full automatic zone discovery for every hardware family.
- Complex airflow balancing logic.
- Predictive control.
- Deep coupling to one actuator vendor.

## Configuration strategy alignment

This plan should follow the shared strategy in:

- `docs/CONFIGURATION_STRATEGY.md`

That means zones should not be added as a collection of loose per-feature keys.

Instead:

- zones should own a dedicated structured feature section inside the shared config model
- config flow should act as an editor for that section
- the editing UX should live under a FAN-oriented configuration area, likely evolving the current `sensor_control` UX toward a broader `FAN Configuration` concept
- strict YAML export should use the same validated section shape
- validated YAML import should come later, after migrations are proven
- discovered devices and entities from `ramses_cc` and Home Assistant should be used to prefill choices, not silently become policy or persisted hints

Suggested placement inside the shared config model:

```text
features:
  zones:
    FANs:
      32:153289:
        - zone_id: bathroom
          source_type: orcon_native
          enabled: true
        - zone_id: office
          source_type: shelly_2pm_gen3
          enabled: true
```

This keeps zone ownership explicit while letting other features reuse the same FAN identities and shared device references.

## Proposed domain model

### FAN zone

A zone belongs to exactly one FAN device and exposes a normalized structure.

Suggested logical shape:

```text
FAN_zones:
  32:153289:
    - zone_id: bathroom
      label: Bathroom
      source_type: orcon_native
      enabled: true
      sensors:
        humidity_entity: sensor.bathroom_humidity
        temperature_entity: sensor.bathroom_temperature
        co2_entity: sensor.bathroom_co2
      actuator:
        kind: native
        entity_id: null
      capabilities:
        reports_position: true
        controllable: false
```

For custom hardware:

```text
FAN_zones:
  32:153289:
    - zone_id: office
      label: Office
      source_type: custom_valve
      enabled: true
      sensors:
        humidity_entity: sensor.office_humidity
        temperature_entity: sensor.office_temperature
        co2_entity: sensor.office_co2
      actuator:
        kind: shelly_2pm_gen3
        open_entity: button.office_valve_open
        close_entity: button.office_valve_close
        position_entity: sensor.office_valve_position
        min_position: 15
        max_position: 90
      capabilities:
        reports_position: true
        controllable: true
```

## Architecture

### 1. Zone registry

Create a FAN-zone registry in Extras, stored per config entry and cached at runtime.

Responsibilities:

- list zones per FAN
- validate unique `zone_id` within a FAN
- expose normalized zone metadata
- provide a stable source for cards, debugger, and future automations

Suggested storage location:

- a structured `zones` feature section in persisted config
- mirrored into runtime registry objects for fast access

### 2. Hardware adapters

Use adapter classes per zone source family.

Initial adapter families:

- `orcon_native`
- `custom_valve`
- `shelly_2pm_gen3`

Each adapter should translate between hardware-specific entities and the normalized zone model.

### 3. Sensor integration

Zones should reuse existing sensor-control concepts where possible.

Recommended alignment:

- `zones` becomes the canonical source of truth for configured zones per FAN
- area-like sensors should reference zones via `zone_id`
- zone sensors become structured area-like sources for FAN features
- humidity / CO2 card sections can reference zone metadata instead of loose entity lists
- future automations can ask for `enabled zones for FAN X` rather than re-reading ad hoc config blobs
- framework helpers should make it easy to answer questions such as `find_areas_for_zone()` and `find_entities_for_zone()`

### 4. Actuator abstraction

Zone actuation should be abstracted behind a small interface.

Suggested capabilities:

- `open`
- `close`
- `set_position` if supported
- `get_position`
- `is_available`
- enforce `min_position` / `max_position` safety limits

This keeps ORCON native dampers and custom valves on the same architectural path.

### 5. Framework/config dependencies

This plan depends on framework work described in `docs/CONFIGURATION_STRATEGY.md`.

Required support includes:

- shared structured config storage for feature-owned sections
- nested validation for zone entries and actuator mappings
- cross-reference validation against known FAN devices and Home Assistant entities
- helper lookups such as `find_areas_for_zone()` and `find_entities_for_zone()`
- actuator safety validation for `min_position` and `max_position`
- section-aware migrations as the zone schema evolves
- strict YAML export helpers for support and debugging
- **feature-level validated import via the framework validation registry**
- `import_validation.py` with `register_config_validator()` for per-feature validation
- `validate_full_config_import_detailed()` with per-feature error reporting

## Integration with fan control

Zones should not bypass the fan-speed arbiter.

Instead:

- zone logic computes zone-level demand or state
- a zone coordinator derives a FAN-level ventilation demand
- that FAN-level demand is submitted to the arbiter
- the arbiter remains the single authority for the effective command

This preserves the same control boundary already used for humidity control and CO2 control.

## Integration with cards and diagnostics

### HVAC card

Near-term:

- show configured zones and active contributors
- highlight which zone triggered humidity/CO2 demand
- show zone availability and optional valve position

Later:

- manual zone controls where safe
- zone override indicators

### Debugger

- show zone registry for each FAN
- show adapter health
- show last actuator command / last observed position

## Phased implementation

### Phase 1 - normalized read model ✅ COMPLETE

- [x] introduce zone registry
- [x] define the `zones` structured feature section
- [x] support static config for ORCON and custom zones using that section
- [x] add config flow support for editing that section inside the FAN-oriented configuration UX
- [x] expose zone metadata to cards/diagnostics
- [ ] no automatic actuation required yet
- [x] keep `zone_id` as the shared link to area-like sensor config

### Phase 2 - actuator adapters ✅ COMPLETE

- [x] implement ORCON-native zone adapter
- [x] implement generic custom valve adapter
- [x] implement Shelly 2PM Gen3 adapter on top of the generic valve model
- [x] add availability and position reporting
- [x] support `min_position` / `max_position` safety limits for controllable valves
- [x] add strict YAML export shape for support/debugging

### Phase 3 - FAN-level coordination ✅ COMPLETE

- [x] create zone coordinator per FAN
- [x] convert zone state into FAN-level demands
- [x] feed arbiter through a single feature id
- [x] add conflict rules with humidity / CO2 / manual override

### Phase 4 - richer editing and portability ✅ COMPLETE

- [x] add optional validated YAML import for advanced users after migrations are proven
- [x] add richer frontend editing if the structured model is stable enough

### Phase 5 - advanced behavior 🔄 PENDING

- [ ] learned airflow weighting
- [ ] zone priorities
- [ ] occupancy-aware logic
- [ ] manual per-zone override handling

#### Phase 5a - demand-driven min/max actuation ✅ COMPLETE

This slice is **testable with real hardware**, even when:

- actual airflow per "% open" is not known/measurable yet
- valves may only support open/close and/or coarse positioning

The key behavior for this slice is:

- determine which FAN zones have **active demand** (humidity / CO2 / future area sensors)
- drive zone actuators to either:
  - a configured `max_position` (open)
  - or a configured `min_position` (safe minimum open)

This gives an actionable end-to-end workflow for 4 physical valves without requiring a flow model.

##### Goals

- Provide a deterministic and safe zone-actuation policy that responds to demand sources.
- Keep the **fan-speed arbiter** as the single authority for FAN-level speed; this slice only controls zone actuators.
- Make behavior observable and debuggable by comparing:
  - which zones were deemed "demanding"
  - which zones were driven to min/max
  - internal FAN sensors (e.g., flow/speed/pressure if available) before/after actuation

##### Non-goals (deferred)

- Estimating airflow contribution per zone position.
- Continuous proportional control.
- Occupancy-aware behavior.
- Manual per-zone override UI.

##### Proposed control rule (initial)

For each FAN:

1. Compute a per-zone boolean `has_demand`.
2. If `has_demand` is true for a controllable zone, request actuator position `max_position`.
3. Otherwise, request actuator position `min_position`.
4. If a zone is not controllable, do not attempt actuation.
5. If actuator availability is false, do not attempt actuation and surface a diagnostic.

Notes:

- This policy does not require weighting. It only requires a reliable `has_demand` signal.
- When multiple zones have demand, multiple zones will be driven to `max_position`.

##### Where demand comes from

The initial implementation should treat demand as a union of known signals, per zone:

- **Humidity demand**: zone contributes if it is the active humidity contributor for that FAN.
- **CO2 demand**: zone contributes if it is the active CO2 contributor for that FAN.
- **Future**: any additional area-sensor derived demand should expose the same `zone_id`.

The precise wiring should prefer **existing feature outputs** over duplicating logic in zones:

- zones consumes “zone_id is demanding” signals
- the producing feature remains owner of its own thresholds and logic

##### Data model additions (minimal)

To support Phase 5a without introducing flow weighting, add optional config fields:

- `zones.FANs[device_id][*].policy`
  - `mode`: `demand_minmax` (default for controllable zones)
  - `min_position`: already exists (safety)
  - `max_position`: already exists (safety)

No new persisted fields are required for demand itself (it is runtime-derived).

##### Implementation steps (ordered)

1. **Define a single runtime representation** for zone demand, keyed by `(fan_id, zone_id)`.
   - Implemented in `framework/helpers/zone_demand.py`
   - With comprehensive unit tests
2. **Expose demand signals** from humidity/CO2 (and future sources) via `ZoneDemandRegistry`.
   - Read-only runtime API, not persisted config
3. **Extend zone coordinator** to compute:
   - `has_demand` per zone via `_demand_registry.has_demand()`
   - Target actuator position (`min_position` vs `max_position`)
4. **Call the actuator adapter** with target position via `async_run_zone_actuation_cycle()`.
   - Only commands if position differs by >= 5%
   - Skips non-controllable zones
5. **Add observability:**
   - `has_zone_demand()`, `get_zone_demand_breakdown()` methods
   - Diagnostics include demand registry state and actuator commands
6. **Add tests:**
   - 19 tests for `zone_demand.py` registry
   - 7 tests for coordinator demand/actuation methods
7. **Live hardware integration test** (4 valves):
   - WebSocket command `ramses_extras/run_zone_actuation` ready

##### Live hardware test checklist

For each FAN:

1. Confirm each zone’s actuator entities are available.
2. Confirm each controllable zone has `min_position` and `max_position` set.
3. Force a single-zone demand (e.g., raise humidity/CO2 in one zone).
4. Observe:
   - zone coordinator marks exactly that `zone_id` as demanding
   - that zone drives to max, all other controllable zones drive to min
   - FAN internal sensors respond plausibly (directional validation, not calibration)
5. Repeat for each zone.

#### Phase 5b - priorities ✅ COMPLETE

Add per-zone `priority` (integer) to resolve cases where not all demanding zones should open to max.

Initial policy option:

- allow a per-FAN cap like `max_open_zones` (optional)
- if more zones demand than the cap, open the highest priority ones

**Implementation:** `actuation_priority` in `ZoneConfig`, `_max_open_zones` in `ZoneCoordinator`, priority sorting in `async_run_zone_actuation_cycle()`

#### Phase 5c - learned weighting (future)

Once real flow measurement is possible, introduce `weight` per zone (learned or configured) to support:

- selecting the best subset of zones to open
- distributing opening across zones
- producing a stable FAN-level demand estimate

**Preparation without hardware:** We can prepare a theoretical lookup table based on:
- Pipe diameter (e.g., 150mm round)
- Fan speed settings (low/medium/high with known flow rates)
- Valve position vs. estimated flow curves

This gives a starting weight model that can be refined once real flow sensors are available.

## Status

**Last Updated:** March 2026

- **Implementation:** Phases 1-5b complete. Phase 5c pending (requires flow measurement hardware).
- **Zone demand registry:** ✅ Implemented in `framework/helpers/zone_demand.py`
- **Zone registry:** ✅ Implemented in `framework/helpers/zones.py`
- **Hardware adapters:** ✅ Implemented in `framework/helpers/zone_adapters.py` (ORCON native, generic valve, Shelly 2PM Gen3)
- **Zone coordinator:** ✅ Implemented in `framework/helpers/zone_coordinator.py` with demand-driven actuation and priority-based selection
- **Safety limits:** ✅ `min_position`/`max_position` validated in config flow
- **Phase 5b priorities:** ✅ `actuation_priority` and `max_open_zones` implemented with tests
- **YAML export:** ✅ Supported via `export_config_to_yaml()`
- **YAML import validation:** ✅ Registered validator in `features/sensor_control/zones_yaml.py`
- **Integration:** Zones feed FAN-level demand to the arbiter (same boundary as humidity/CO2 control)

## Configuration UX proposal

For each FAN:

1. open Zones config
2. choose `Add ORCON zone` or `Add custom zone`
3. supply label and `zone_id`
4. map sensors
5. map optional actuator entities
6. validate and save

Near-term direction:

- keep config flow as the first editor
- edit the structured `zones` section rather than loose options keys
- expose it through a FAN-oriented configuration editor rather than a separate top-level feature UI
- prefill FAN devices and likely entities from discovery where possible
- still allow external/manual devices and entities when discovery candidates are incomplete

For Shelly 2PM Gen3 specifically:

- use a dedicated preset/helper in the flow so users do not need to understand the generic adapter model first

## Risks

- overfitting the first version to Shelly-specific assumptions
- mixing zone state and fan policy in the same abstraction
- making UI/config too complex before the normalized data model is stable
- inconsistent availability across zone adapters

## Safeguards

- define one normalized zone contract first
- keep hardware adapters thin
- keep FAN demand generation separate from raw hardware IO
- keep manual override above zone-generated demands

## Open questions for review

- Do you want ORCON zones to be modeled as read-only first, or controllable from phase 1 if data is already available?
- For custom valves, do you want position-based control first or just open/close?
- Should Shelly 2PM Gen3 be the first custom actuator implemented, or only the reference adapter shape?

## Decisions applied

- Zones should keep their own structured config section.
- Zones should be edited under a FAN-oriented configuration area, not as a separate top-level feature UX.
- Discovery from `ramses_cc` and Home Assistant should be used as a hint source only, and not persisted unless explicitly accepted into config.
- Discovery candidates are not the only valid option, because external/manual devices and entities must also be supported.
- `zone_id` should be the shared source-of-truth link between zones and area-like sensor config.
- Controllable zone valves should support `min_position` and `max_position` safety limits.
- Export uses strict YAML via `export_config_to_yaml()`.
- Import uses the **framework validation registry** with per-feature validators registered via `register_config_validator()`.
- Import validates against schema, cross-references entities, checks constraints before saving.
- Config flow shows per-feature validation errors: `[zones]`, `[remote_binding]`, `[sensor_control]`.
