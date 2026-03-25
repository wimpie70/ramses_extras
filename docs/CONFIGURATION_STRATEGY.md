# Ramses Extras Configuration Strategy

## Purpose

This document defines the intended long-term configuration strategy for `ramses_extras`.

It is meant to keep the growing feature set maintainable while still being:

- usable for normal Home Assistant users
- debuggable for advanced users and maintainers
- consistent with the feature-centric architecture
- suitable for future features such as remote binding and zones

This document also records the concrete framework and feature work that is needed so the idea does not get lost while implementation happens in slices.

## Why this is needed

`ramses_extras` is growing from simple feature toggles toward a richer model with:

- feature/device enablement
- per-device feature settings
- future REM -> FAN bindings
- future FAN zone definitions
- future custom hardware mappings
- future richer debugging and support needs

The current config model works for basic feature selection, but it will become hard to maintain if every new feature grows its own ad hoc options flow structure.

## Core decision

The target direction is a hybrid model:

- frontend/config flow is the main way users create and edit config
- the backend keeps one structured internal config model
- config should be exportable as strict YAML generated from the structured model
- import should come later, after schema versioning and migrations are proven
- each feature owns its own config section within the shared model

This means YAML should not be the only primary configuration path, but it should become a first-class debugging and sharing format.

## Design goals

- Keep Home Assistant UX approachable.
- Keep feature boundaries clear.
- Allow one installation to describe its full setup in one structured snapshot.
- Make user feedback easier by allowing a complete setup to be shared.
- Support discovery-based prefilling from `ramses_cc` without silently treating discovery as policy.
- Reuse one validation/migration pipeline regardless of whether config came from UI or import.

## Non-goals for the first implementation

- Replacing Home Assistant config flows with raw YAML files.
- Allowing arbitrary manual file edits to become the only supported path.
- Building a full visual config editor for every feature before the shared model exists.
- Solving all migrations before the first typed model exists.

## Recommended model

## 1. One internal shared config model

The backend should hold a single structured integration config model.

That model should contain:

- integration-wide metadata
- discovered device references
- feature/device enablement
- per-feature config sections
- future export/import metadata such as schema version

Suggested high-level shape:

```yaml
ramses_extras:
  schema_version: 1
  devices:
    fans:
      - device_id: 32:153289
        label: Main Ventilation
    remotes:
      - device_id: 37:169161
        label: Kitchen Remote
  features:
    default:
      enabled_devices:
        - 32:153289
    humidity_control:
      devices:
        32:153289:
          enabled: true
    remote_binding:
      FANs:
        32:153289:
          REMs:
            - rem_id: 37:169161
              role: primary
    zones:
      FANs:
        32:153289:
          - zone_id: bathroom
            source_type: orcon_native
```

This is a conceptual shape, not yet the final schema.

## 2. Feature-owned sections

Each feature should own its own section under the shared config model.

This keeps feature separation intact:

- the framework owns structure and persistence
- each feature owns validation and semantics for its section
- features can reference shared device identities without duplicating all device metadata

This should avoid a giant flat dictionary of unrelated keys.

## 3. Multiple editors for the same model

There should be one canonical model but multiple ways to interact with it:

- config flow / options flow
- future frontend config screens
- strict YAML export generated from the canonical model
- later validated YAML import
- future debugger/config inspection tools

The editor should not define the model. The model should define the editor behavior.

## FAN-oriented configuration grouping

Remote binding and zones should not become isolated top-level user concepts disconnected from existing FAN-related configuration.

The preferred direction is:

- keep feature-owned config sections in the shared model
- group FAN-related editing under a FAN-oriented configuration area in the UI
- evolve the current `sensor_control` UX toward a broader FAN-configuration concept if that gives a clearer user experience

That means there are two separate concerns:

- storage ownership, which stays feature-specific
- editor grouping, which can be FAN-oriented

Near-term guidance:

- keep `sensor_control` as the existing anchor in the codebase for FAN-related configuration flows
- allow the UI/documentation name to evolve toward something like `FAN Configuration`
- avoid forcing remote binding and zones to become independent `AVAILABLE_FEATURES` entries unless the runtime architecture truly requires that later
- prefer FAN/REM-aware naming in the model where it improves clarity, such as `rem_id` instead of a more generic `remote_id`

## Why not YAML-only

YAML-only has real benefits:

- easy to share
- easy to inspect
- good for debugging
- good for reproducing setups

But it also has important costs:

- custom parsing and migration burden
- more fragile user input
- poorer UX for most Home Assistant users
- more risk of partial invalid state after edits
- more support burden for hand-edited mistakes

Because of that, YAML should be a support/debug format first, not the initial primary authoring path.

## Why not config-flow-only

Config-flow-only also has limits once configuration becomes richer:

- hard to inspect the full setup at once
- hard to share complete config in bug reports
- hard to bulk-edit repeated structures like zones
- hard to compare one setup with another

That is why the hybrid model is preferred.

## Discovery and prefilling

Discovery from `ramses_cc` should be used as input for config creation, not as silent persisted policy.

Discovery can help with:

- known FAN devices
- known REM-capable devices
- known sensors/entities
- labels and friendly defaults
- suggested bindings and candidate zone devices

But explicit Extras configuration should remain the source of policy for:

- which REM belongs to which FAN
- which zones exist in Extras
- which actuator mapping is used
- which optional features are enabled

Discovery guidance:

- discovered devices/entities should normally be recomputed from `ramses_cc` and Home Assistant at runtime
- discovery results should be treated as hints until the user explicitly accepts them into config
- discovered candidates are not the only valid option, because users may intentionally configure external/manual devices or entities that are not discovered automatically
- once the user accepts a mapping or creates feature config based on a discovered item, that explicit config should be persisted

## Current framework state

## What already exists

The current framework already provides useful pieces:

- `AVAILABLE_FEATURES` registry in `custom_components/ramses_extras/const.py`
- feature/device enablement matrix support in config flow helpers
- basic per-feature config helper patterns in `framework/helpers/config/core.py`
- validation utilities in `framework/helpers/config/validation.py`
- dynamic discovery of feature-specific config flow implementations in `framework/helpers/config_flow.py`
- central options flow structure in `custom_components/ramses_extras/config_flow.py`

These give a solid starting point.

## What is missing

The current framework still lacks the main pieces needed for the hybrid model:

- a typed shared config model
- a stable storage layout for feature-owned structured sections
- config schema versioning and migrations for structured feature sections
- a unified import/export layer
- shared device-reference helpers for feature config sections
- framework-level section validation and merge logic
- debugger/config inspection support for the full structured config

## Framework work needed

## 1. Define a canonical config data model

Needed work:

- define integration-level config objects
- define shared device reference objects
- define feature section container rules
- add `schema_version`
- define how config entry data/options map into this model

This should become the backbone for all future config work.

## 2. Add structured persistence helpers

The current config helpers mainly work like generic key/value dictionaries.

Needed work:

- shared structured config storage for feature-owned sections
- section-level merge/update helpers
- immutable or copy-safe update patterns
- clear distinction between persisted config and runtime cached state
- helper lookups for relationships such as `find_areas_for_zone()` and `find_entities_for_zone()`

## 3. Add section-aware validation

The current validator is useful for simple scalar checks, but remote binding and zones need more structure.

Needed work:

- nested object validation
- cross-reference validation between sections and shared device references
- uniqueness constraints such as one REM not being primary for multiple FANs
- per-FAN zone uniqueness rules
- zone actuator safety validation such as `min_position` and `max_position`
- better surfaced validation errors for config flow and future import

## 4. Add schema migration support

Needed work:

- config schema version storage
- migration functions for structured sections
- one centralized migration helper module/file for legacy normalization and section reshaping
- feature-owned migration hooks when a section evolves

This matters early so the model can grow safely.

## 5. Add import/export services or WebSocket support

Needed work:

- export current structured config as strict YAML generated from the canonical model
- redact security-sensitive and runtime-only fields from export
- later allow validated import of YAML payloads after migrations are proven
- expose these through debugger or WebSocket tooling

This is one of the main benefits of the hybrid strategy.

## 6. Add config inspection/debugger support

Needed work:

- expose effective structured config in diagnostics/debugger
- optionally show discovered-vs-explicit data
- show validation or migration warnings

This will make support much easier.

## Feature work needed

## Remote binding feature

Needed work:

- define the `remote_binding` config section schema
- store FAN -> REM bindings in structured feature config, not ad hoc keys
- use shared discovered device references for candidate selection
- support future YAML export/import for bindings
- surface unmatched observed REM traffic and binding health in diagnostics

## Zones feature

Needed work:

- define the `zones` config section schema
- support multiple zone entries per FAN
- support source-specific nested structures for ORCON and custom actuators
- make `zone_id` the shared source-of-truth link between zones and area-like sensor config
- use shared device/entity references instead of free-form duplication where possible
- support actuator safety limits such as `min_position` and `max_position`
- support frontend editing first, export later

## Sensor-oriented features

Needed work:

- align sensor selection features with the shared config model
- avoid every feature inventing its own device/entity storage conventions
- make zones reusable as structured sources for humidity/CO2 and future logic

## Debugger feature

Needed work:

- expose config export or config snapshot views
- expose structured config diagnostics separately from live runtime state
- optionally show discovery suggestions and unresolved mappings

## Config flow and frontend direction

## Near-term UI direction

The near-term editor should remain config-flow/options-flow based, because it is the fastest path that fits Home Assistant conventions.

But the flows should evolve toward editing structured feature sections instead of pushing many unrelated loose keys into config entry data/options.

## Longer-term frontend direction

Once the shared model is stable, a richer frontend editor becomes much more realistic.

A future frontend editor could:

- show the complete setup in a more navigable way
- edit per-feature sections with better UX for repeated structures
- prefill from discovered devices/entities
- export the structured config for support

This should come after the model is stable, not before.

## Proposed phased plan

### Phase 1 - establish the model

- define the shared structured config shape
- define per-feature section boundaries
- decide where the persisted canonical form lives in config entry data/options
- add schema versioning scaffolding

### Phase 2 - framework enablement

- extend config helpers for structured sections
- add nested validation and migration support
- add runtime access helpers for feature sections
- add shared device-reference helpers

### Phase 3 - first consumers

- completed for `sensor_control`: runtime readers and config-flow summaries now read the canonical shared model with legacy compatibility
- completed for `sensor_control`: config-flow persistence now writes canonical `ramses_extras.features.sensor_control` while temporarily mirroring legacy top-level `sensor_control`
- completed for `sensor_control`: focused tests cover canonical-read compatibility and dual-write persistence for config-flow edits
- migrate remote binding plan to the shared model
- migrate zones plan to the shared model
- align sensor-related feature config where needed

### Phase 4 - support/debug tooling

- add strict YAML config export
- add debugger visibility for structured config
- add diagnostics for explicit vs discovered mappings

### Phase 5 - optional advanced editing

- add validated YAML import
- add richer frontend editing if justified

## Tracking checklist

## Framework

- define canonical structured config shape
- define section ownership rules
- define shared device reference rules
- add schema versioning
- add migration hooks
- extend validation for nested/cross-section data
- add import/export helpers
- add debugger config visibility

## Export rules

- export the effective canonical config shape as strict YAML
- exclude security-sensitive values such as passwords
- exclude transient runtime-only data such as caches, last-seen timestamps, transport snapshots, and inferred discovery hints that were never explicitly accepted into config
- keep the export stable enough for support, diffing, and future import

## Remote binding

- define `remote_binding` section schema
- add structured storage helpers
- align config flow with shared model
- add diagnostics/export shape

## Zones
- define `zones` section schema
- define adapter-specific nested config shapes
- align config flow with shared model
- add diagnostics/export shape

## Decisions made

- The first export format should be strict YAML generated from the structured model.
- Import should come later, after migrations are proven.
- Remote binding and zones should be edited under a FAN-oriented configuration area, likely by evolving the current `sensor_control` UX toward a broader `FAN Configuration` concept.
- During the transition, `sensor_control` should follow Option C: config flows persist canonical `ramses_extras.features.sensor_control` while mirroring legacy top-level `sensor_control` until legacy storage is retired.
- Shared discovery results from `ramses_cc` should be treated as hints and not persisted unless explicitly accepted into config.
- Security-sensitive values such as passwords must be excluded from export, along with other runtime-only/transient state.
- Discovery candidates are not the only valid source of configuration, because external/manual devices and entities must also remain possible.
- `zone_id` should be a shared source-of-truth link so areas/entities can be found from a zone consistently.
- Zone valves should support safety limits such as minimum and maximum position to help protect the FAN.

## Relationship to other docs

This document should inform:

- `docs/REMOTE_BINDING_IMPLEMENTATION_PLAN.md`
- `docs/FAN_CONFIGURATION_SCHEMA_DRAFT.md`
- `docs/ZONES_IMPLEMENTATION_PLAN.md`
- `docs/FAN_CONTROL_ARCHITECTURE.md`

The fan-control architecture remains the source of truth for control policy.
This document is the source of truth for how richer configuration should be modeled and maintained.
