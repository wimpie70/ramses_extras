# FAN Configuration Schema Draft

## Purpose

This document is the first concrete schema draft following:

- `docs/CONFIGURATION_STRATEGY.md`
- `docs/REMOTE_BINDING_IMPLEMENTATION_PLAN.md`
- `docs/ZONES_IMPLEMENTATION_PLAN.md`
- `docs/FAN_CONTROL_ARCHITECTURE.md`

It turns the configuration strategy into an actionable direction for implementation.

The goal is to define:

- the first structured config shape for FAN-oriented configuration
- how feature-owned sections fit inside that shape
- how the current `sensor_control` implementation maps into it
- what framework changes are needed to support it

## Core direction

There are two separate concerns that must not be conflated:

- storage ownership
- editor grouping

Storage ownership should remain feature-specific.
Editor grouping should become FAN-oriented.

That means:

- `sensor_control` keeps owning sensor-source related config
- `remote_binding` keeps owning remote-binding config
- `zones` keeps owning zone config
- the user-facing editor can present these under one FAN-oriented area such as `FAN Configuration`

## First schema direction

The first structured model should look like one canonical config document with feature-owned sections.

Suggested shape:

```yaml
ramses_extras:
  schema_version: 1

  features:
    sensor_control:
      devices:
        32:153289:
          sources:
            indoor_temperature:
              kind: internal
            indoor_humidity:
              kind: external
              entity_id: sensor.bathroom_humidity
          abs_humidity_inputs:
            indoor_abs_humidity:
              temperature:
                kind: external
                entity_id: sensor.bathroom_temperature
              humidity:
                kind: external
                entity_id: sensor.bathroom_humidity
          area_sensors:
            - source_id: bathroom
              label: Bathroom
              enabled: true
              zone_id: bathroom
              temperature_entity: sensor.bathroom_temperature
              humidity_entity: sensor.bathroom_humidity
              area_co2_enabled: true
              co2_entity: sensor.bathroom_co2
              co2_threshold: 1000

    remote_binding:
      FANs:
        32:153289:
          REMs:
            - rem_id: 37:169161
              role: primary
              enabled: true
              source: manual_config

    zones:
      FANs:
        32:153289:
          - zone_id: bathroom
            label: Bathroom
            source_type: orcon_native
            enabled: true
            sensors:
              area_sensor_ids:
                - bathroom
            actuator:
              kind: native
            capabilities:
              controllable: false
              reports_position: true
          - zone_id: office
            label: Office
            source_type: custom_valve
            enabled: true
            sensors:
              area_sensor_ids:
                - office
            actuator:
              kind: shelly_2pm_gen3
              open_entity: button.office_valve_open
              close_entity: button.office_valve_close
              position_entity: sensor.office_valve_position
              min_position: 15
              max_position: 90
            capabilities:
              controllable: true
              reports_position: true
```

This is a schema draft, not the final implementation contract.

## Why this shape

This shape keeps several things clear:

- each feature owns its own persisted section
- devices are referenced by real FAN device ids
- RAMSES role-aware naming can be preserved in the schema where it improves clarity, especially for FAN and REM relationships
- shared concepts such as `zone_id` and `area_sensor_ids` can be reused across features
- the UI can still show everything under one FAN-oriented editor
- strict YAML export can serialize the same structure without inventing a second format

## FAN-oriented editor view

The editor does not need to mirror the storage layout one-to-one.

The UI can be grouped per FAN, for example:

```text
FAN Configuration
  -> Select FAN 32:153289
     -> Sensor sources
     -> Area sensors
     -> Remote binding
     -> Zones
```

Under the hood, each submenu still writes to its own feature-owned section.

This matches the current user preference:

- keep remote binding and zones under a FAN-oriented config area
- do not force them into separate top-level user concepts

## Relationship to current sensor_control storage

Today `sensor_control` is already the closest thing to a FAN-oriented configuration area.

Current persisted shape is effectively:

```text
options["sensor_control"] = {
  "sources": {
    "32_153289": {
      ... per-metric overrides ...
    }
  },
  "abs_humidity_inputs": {
    "32_153289": {
      ... abs humidity inputs ...
    }
  },
  "area_sensors": {
    "32_153289": [
      ... area sensor entries ...
    ]
  }
}
```

That tells us a few useful things:

- there is already a per-device structured subtree
- `sensor_control` already acts as a multi-step FAN-oriented editor
- device-key normalization currently uses underscore keys like `32_153289`
- area sensors already contain `zone_id`, which is a useful bridge to future zones

## Recommended normalization changes

The next schema direction should improve a few things from the current shape.

### 1. Prefer canonical device ids in the model

Current storage often uses underscore-normalized device keys.

Recommended direction:

- use canonical `32:153289` style device ids in the internal model
- only normalize to underscore where Home Assistant entity naming or legacy compatibility requires it

This makes exported YAML and debugging clearer.

### 2. Keep feature sections, but align their internal shape

Recommended section patterns:

- `sensor_control.devices[device_id]`
- `zones.FANs[device_id]`
- `remote_binding.FANs[device_id].REMs[]`

This keeps feature ownership while making FAN-scoped lookups consistent.

### 3. Make `zone_id` the shared source of truth between zones and area-like sensors

The current `sensor_control.area_sensors` model is already useful.

Recommended direction:

- `zones` should define the canonical list of configured zones per FAN
- `sensor_control.area_sensors` should reference those zones via `zone_id`
- it should be easy to find all areas for a zone and all relevant entities for a zone from one normalized lookup path

This reduces duplication and makes the zone relationship explicit.

### 4. Reuse area sensors instead of duplicating sensor mapping in zones when possible

The current `sensor_control.area_sensors` model is already useful once `zone_id` becomes the shared link.

Recommended direction:

- zones should be allowed to reference `area_sensor_ids`
- zones should not be forced to duplicate temperature/humidity/CO2 entity mappings if those are already modeled as area sensors
- direct inline sensor config can remain possible where no reusable area sensor exists or where an external device is intentionally used

This reduces config duplication and makes humidity/CO2/zones align better.

### 5. Add explicit actuator safety limits

Custom zone valves should support minimum and maximum allowed positions.

Recommended direction:

- add `min_position` and `max_position` to controllable actuator config
- validate that `0 <= min_position <= max_position <= 100`
- use these limits to prevent a configuration that can fully starve airflow and protect the FAN
- keep room for a later FAN-level safeguard that ensures not all controllable zones can close below the configured safe threshold at the same time

## Discovery rules

Discovery from `ramses_cc` and Home Assistant should be treated as hint-only unless the user explicitly accepts a configuration item.

That means:

- discovered FAN devices are shown as candidates
- discovered REM devices are shown as candidates
- discovered entities are shown as candidates
- manual or external devices/entities must still be allowed even if they are not discovered as candidates
- these discovery results should not be exported as persisted config unless accepted into a feature section

Exported YAML should reflect explicit configuration, not every transient discovery observation.

## Export rules

The first export format should be strict YAML generated from the canonical model.

Export should:

- include the effective persisted structured config
- exclude passwords and other security-sensitive values
- exclude transient runtime-only fields
- exclude discovery hints that were never explicitly accepted into config

Runtime-only fields that should stay out of export include examples such as:

- last-seen timestamps
- transport snapshots
- binding health cache
- unresolved discovery suggestions
- temporary UI state

## Framework implications

## 1. Canonical config model layer

The framework needs a canonical config model layer that can:

- read from config entry data/options
- normalize legacy shapes
- expose typed feature sections
- produce strict YAML export from the same model

This does not need to be a full rewrite on day one, but the shape should be defined early.

## 2. Section access helpers

The framework should add helpers like:

- `get_feature_section(feature_id)`
- `set_feature_section(feature_id, section_data)`
- `get_fan_section(feature_id, device_id)`
- `list_configured_fans(feature_id)`
- `find_areas_for_zone(device_id, zone_id)`
- `find_entities_for_zone(device_id, zone_id)`

The current generic config helpers are too scalar/key-value oriented for this next phase.

## 3. Nested validation

The framework validator needs to evolve beyond simple scalar checks.

Needed validation types include:

- nested object validation
- device-id normalization/validation
- entity existence validation where appropriate
- uniqueness rules such as primary remote conflicts
- per-FAN `zone_id` uniqueness
- references from zones to known `area_sensor_ids`
- actuator safety validation for `min_position` and `max_position`

## 4. Migration support

The framework needs schema migration scaffolding before import is added.

Near-term migration needs already exist:

- current `sensor_control` config uses underscore keys
- future canonical export should prefer colon device ids
- future FAN-oriented editor grouping should not break existing stored `sensor_control` trees

Recommended direction:

- keep legacy normalization and section reshaping in one migration helper module/file
- do not spread migration rules across unrelated feature editors
- make it possible to migrate underscore device keys, renamed fields, and section reshapes through one audited path

## 5. Editor grouping support

The current options flow already routes feature-specific editors and already has a dedicated `sensor_control` path.

That suggests a practical near-term path:

- keep current feature-owned config storage
- extend the FAN-oriented UI around the existing `sensor_control` editor path
- add remote-binding and zones submenus under that FAN-oriented area
- avoid prematurely turning them into independent top-level feature UX entries

## Suggested first implementation slice

The first implementation slice should stay small and structural.

### Slice 1

- define the canonical schema draft in code constants or typed models
- define canonical device-id handling
- add a structured read/write helper for feature sections
- keep existing `sensor_control` storage readable
- do not add YAML import yet

### Slice 2

- add strict YAML export from the canonical model
- export only explicit persisted config
- redact security-sensitive values

### Slice 3

- add FAN-oriented editor grouping in the options flow
- keep `sensor_control` as the initial anchor
- add placeholders or submenu hooks for `remote_binding` and `zones`

### Slice 4

- migrate remote binding to the canonical section shape
- migrate zones to the canonical section shape
- connect these sections to the FAN-oriented editor

## Concrete repo implications

Based on the current codebase, the likely impact areas are:

- `custom_components/ramses_extras/config_flow.py`
- `custom_components/ramses_extras/framework/helpers/config/core.py`
- `custom_components/ramses_extras/framework/helpers/config/validation.py`
- `custom_components/ramses_extras/framework/helpers/config_flow.py`
- `custom_components/ramses_extras/features/sensor_control/config_flow.py`
- future feature modules for `remote_binding` and `zones`

## Near-term recommendation

The next implementation step should not be full feature coding yet.

It should be:

- define the canonical structured config contract in code
- decide the exact section names and device-key rules
- define the `zone_id` source-of-truth relationship between `zones` and `area_sensors`
- keep `sensor_control` as the short-term FAN-oriented editor anchor
- add strict YAML export only after the canonical model exists

## Open design items still worth deciding later

- whether zones may inline sensor entities in addition to `area_sensor_ids`
- how much of the current `sensor_control.area_sensors` model should be reused directly versus reshaped during migration
- whether the UI label should remain `Sensor Control` for now or start moving toward `FAN Configuration`

## Status

This document is the first concrete schema draft for the hybrid configuration strategy.
It is intended to guide the next implementation slices and reduce the risk of ad hoc config growth.
