# Sensor Sources / Mapping Roadmap (Ramses Extras)

## Goal

Allow per-device selection of which sensor entities are used by:
- HVAC card UI
- Humidity automation/control
- Future automations (e.g. CO2-driven ventilation)
while keeping configuration **centralized in the integration Options Flow** and exposing both:
- **effective entity IDs** (what to use)
- **source metadata** (where it came from, and optionally the raw/internal values too)

Scope (now):
- Indoor temperature
- Indoor humidity
- CO2
- Outdoor temperature
- Outdoor humidity
- Indoor absolute humidity (derived from a selected temp + humidity pair)
- Outdoor absolute humidity (derived from a selected temp + humidity pair)

Out of scope (now):
- Comfort temperature (already available in HVAC device data)

---

## Problem Statements (examples)

- Some HVAC devices are installed in thermally biased locations (attic/top floor), so internal `indoor_temperature` is not representative for living spaces → bypass decisions become “wrong” from the user perspective.
- Some devices may have missing sensors or only 1 humidity sensor; sometimes we still want to compute absolute humidity using a *different* RH/temp pair (possibly external).
- We want “effective” values for logic, but also want to **see what the sources are** in the card (and optionally show raw internal readings too).

---

## Proposed Architecture (high level)

### New feature: `sensor_control` (recommended)
A feature that:
- Stores per-device source selection for each metric
- Optionally creates derived entities (absolute humidity)
- Provides a resolver used by:
  - `ramses_extras/get_entity_mappings` (so cards keep using existing pattern)
  - humidity-control automation logic
- Can be bootstrapped by copying the existing `hello_world` feature as a template to inherit the full framework wiring (config, entities, services, UI scaffolding) before customizing sensor-specific logic.

### Central config location
- **Options flow** stores all selections in config entry options, e.g.:
  - `options["sensor_control"]["sources"][device_id][metric] = ...`

Cards may later offer *view-only* source information, and optionally a per-card override (not planned now).

---

## Data Model (proposal)

### Metrics
- `indoor_temperature`
- `indoor_humidity`
- `co2`
- `outdoor_temperature`
- `outdoor_humidity`
- `indoor_abs_humidity` (derived)
- `outdoor_abs_humidity` (derived)

### Source descriptor

Each metric resolves to a `SourceDescriptor`:

```json
{
  "kind": "internal | external | derived",
  "entity_id": "sensor.living_room_temperature",
  "label": "Living room temp",
  "origin": "ramses_cc | homeassistant",
  "notes": "optional"
}
```

### Rules

- **internal** means “use the standard ramses_extras mapping for this device/metric”.
- **external** means “use a specific HA `entity_id`”.
- If an override is set but invalid/missing, **fail closed**: resolver returns `null` + reason (no fallback).
- If internal is not available for a device model, resolver returns `null` + reason.

### Validation rules (backend)

- For derived absolute humidity:
  - Must have both a temperature source and a humidity source configured for the derived metric.
  - If either source is missing/invalid, the derived metric resolves to `null`.
- For CO2:
  - If missing, allow `null`.
- If an internal sensor doesn’t exist (device model lacks it), show as unavailable in the UI.

---

## WebSocket / Mapping Contract (proposal)

Extend existing `ramses_extras/get_entity_mappings` to return:

- `mappings`: effective entity IDs (what the card/automation should use)
- `sources`: metadata per mapping (so the UI can show “external/internal” and label) (**always included**)
- `raw_internal` (optional): default internal mapping regardless of override, for UI comparison

### Example response

```json
{
  "mappings": {
    "indoor_temperature": "sensor.living_room_temperature",
    "indoor_humidity": "sensor.32_153289_indoor_humidity",
    "co2": null,
    "outdoor_temperature": "sensor.32_153289_outdoor_temp",
    "outdoor_humidity": "sensor.netatmo_outdoor_humidity",
    "indoor_abs_humidity": "sensor.32_153289_indoor_abs_humidity",
    "outdoor_abs_humidity": null
  },
  "abs_humidity_inputs": {
    "indoor_abs_humidity": {
      "temperature": "sensor.living_room_temperature",
      "humidity": "sensor.32_153289_indoor_humidity"
    },
    "outdoor_abs_humidity": {
      "temperature": null,
      "humidity": null
    }
  },
  "sources": {
    "indoor_temperature": {
      "kind": "external",
      "entity_id": "sensor.living_room_temperature",
      "label": "Living room temp"
    },
    "indoor_humidity": {
      "kind": "internal",
      "entity_id": "sensor.32_153289_indoor_humidity",
      "label": "FAN indoor RH"
    },
    "outdoor_humidity": {
      "kind": "external",
      "entity_id": "sensor.netatmo_outdoor_humidity",
      "label": "Netatmo outdoor RH"
    },
    "indoor_abs_humidity": {
      "kind": "derived",
      "entity_id": "sensor.32_153289_indoor_abs_humidity",
      "label": "FAN indoor abs humidity"
    }
  },
  "raw_internal": {
    "indoor_temperature": "sensor.32_153289_indoor_temp",
    "indoor_humidity": "sensor.32_153289_indoor_humidity",
    "co2": "sensor.32_153289_co2_level",
    "outdoor_temperature": "sensor.32_153289_outdoor_temp",
    "outdoor_humidity": "sensor.32_153289_outdoor_humidity"
  }
}
```

**Notes**

- HVAC card can show “Indoor temp: 18 °C (external: Living room)” while also displaying “internal: 22 °C”.
- Humidity automation uses `mappings` only.

---

## Options Flow UX (proposal)

Per device (initially FAN + CO2-capable devices), show a **single combined form** with dropdown/entity-picker fields for:

1. **Indoor temperature**
   - Internal (default)
   - External entity picker
2. **Indoor humidity**
   - Internal (default)
   - External entity picker
3. **CO2**
   - Internal (default, if available)
   - External entity picker
   - None
4. **Outdoor temperature**
   - Internal (default, if available)
   - External entity picker
5. **Outdoor humidity**
   - Internal (default, if available)
   - External entity picker
6. **Indoor absolute humidity (derived)**
   - Temperature source (Internal / External entity)
   - Humidity source (Internal / External entity)
7. **Outdoor absolute humidity (derived)**
   - Temperature source (Internal / External entity)
   - Humidity source (Internal / External entity)

**Confirmation-step warnings:** derived metrics will be missing if either paired source is missing/invalid.

---

## Card UX (HVAC)

Per metric, show:

- Value (from effective mapping)
- Source indicator badge (`INT` / `EXT`)
- Tooltip or secondary line with source label + entity_id
- Optional “Show internal readings” toggle, which uses `raw_internal` to display comparative values

---

## Phases & Progress

### Phase 0 — Design & contracts
- [x] Decide metric keys + naming (indoor/outdoor/CO2 + abs humidity)
- [x] Decide WS response format (`mappings` + `sources` + optional `raw_internal` + abs humidity inputs)
- [x] Decide config-entry storage keys and defaults
- [x] Decide initial UI constraints (entity pickers, device filter, allowed domains)

### Phase 1 — Backend: `sensor_control` config + resolver
- [ ] Add new feature folder `features/sensor_control/`
- [ ] Add options-flow step for `sensor_control` per device
- [ ] Implement resolver that:
  - [ ] Returns effective entity IDs for each metric
  - [ ] Returns source metadata
  - [ ] Handles missing internal sensors gracefully
  - [ ] Persists config in config-entry options

### Phase 2 — Integrate with `get_entity_mappings`
- [ ] Update WS `ramses_extras/get_entity_mappings` so it:
  - [ ] Builds internal baseline mappings (existing behavior)
  - [ ] Applies `sensor_control` overrides
  - [ ] Returns `sources` (+ optional `raw_internal`)
- [ ] Add debug logs that show effective mapping + source kind

### Phase 3 — HVAC card UI: display source info
- [ ] Update HVAC card to render:
  - [ ] Source badges (INT/EXT)
  - [ ] Tooltips / secondary lines with label + entity_id
  - [ ] Optional “internal vs effective” comparison in debug mode

### Phase 4 — Humidity automation: consume effective mappings
- [ ] Update `humidity_control` so it uses effective:
  - [ ] Indoor temp + RH
  - [ ] Outdoor temp + RH
  - [ ] CO2 (if/when needed)
- [ ] Add validation: if required metrics missing, disable automation per device with clear log + UI message

### Phase 5 — Derived/advanced sensors (abs humidity + aggregation)
- Derived:
  - [ ] Indoor abs humidity from chosen indoor temp + RH
  - [ ] Outdoor abs humidity from chosen outdoor temp + RH
- Aggregations:
  - [ ] Bathroom max RH triggers boost
  - [ ] Average RH reference for “return-to-normal”
- Advanced UI:
  - [ ] Selecting multiple entities for aggregation

---

## Status Snapshot

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0 — Design & contracts | Completed | Metric keys + WS payload + UX decided |
| Phase 1 — Backend: `sensor_control` config + resolver | Not started | Requires feature scaffolding + options flow work |
| Phase 2 — Integrate with `get_entity_mappings` | Not started | Blocked on Phase 1 resolver outputs |
| Phase 3 — HVAC card UI | Not started | Depends on WS payload changes |
| Phase 4 — Humidity automation | Not started | Requires effective mappings + validation logic |
| Phase 5 — Derived/advanced sensors | Not started | Optional stretch once earlier phases land |

---

## Acceptance Criteria (initial milestone)

- A device can use an external living-room temperature sensor for `indoor_temperature`.
- HVAC card shows the effective temperature and indicates it is external.
- Backend mapping WS returns both effective mapping + source metadata.
- Humidity automation can use external outdoor humidity (or indoor humidity) and still function.
