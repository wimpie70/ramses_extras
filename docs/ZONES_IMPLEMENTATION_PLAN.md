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
- delayed validated import after migrations are proven

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

### Phase 1 - normalized read model

- introduce zone registry
- define the `zones` structured feature section
- support static config for ORCON and custom zones using that section
- add config flow support for editing that section inside the FAN-oriented configuration UX
- expose zone metadata to cards/diagnostics
- no automatic actuation required yet
- keep `zone_id` as the shared link to area-like sensor config

### Phase 2 - actuator adapters

- implement ORCON-native zone adapter
- implement generic custom valve adapter
- implement Shelly 2PM Gen3 adapter on top of the generic valve model
- add availability and position reporting
- support `min_position` / `max_position` safety limits for controllable valves
- add strict YAML export shape for support/debugging

### Phase 3 - FAN-level coordination

- create zone coordinator per FAN
- convert zone state into FAN-level demands
- feed arbiter through a single feature id
- add conflict rules with humidity / CO2 / manual override

### Phase 4 - richer editing and portability

- add optional validated YAML import for advanced users after migrations are proven
- add richer frontend editing if the structured model is stable enough

### Phase 5 - advanced behavior

- learned airflow weighting
- zone priorities
- occupancy-aware logic
- manual per-zone override handling

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
- Export should be strict YAML.
- Import should come later, after migrations are proven.
