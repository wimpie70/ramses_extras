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
- Indoor temperature + RH
- Outdoor temperature + RH
- CO2

Out of scope (now):
- Comfort temperature (already available in HVAC device data)

---

## Problem Statements (examples)

- Some HVAC devices are installed in thermally biased locations (attic/top floor), so internal `indoor_temp` is not representative for living spaces → bypass decisions become “wrong” from the user perspective.
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

### Central config location
- **Options flow** stores all selections in config entry options, e.g.:
  - `options["sensor_control"]["sources"][device_id][metric] = ...`

Cards may later offer *view-only* source information, and optionally a per-card override (not planned now).

---

## Data Model (proposal)

### Metrics
- `indoor_temp`
- `indoor_rh`
- `outdoor_temp`
- `outdoor_rh`
- `co2`

Derived (phase 2+):
- `indoor_abs_humidity` (derived from effective indoor temp + effective indoor RH)
- `outdoor_abs_humidity` (derived from effective outdoor temp + effective outdoor RH)

### Source descriptor

Each metric resolves to a `SourceDescriptor`:

```json
{
  "kind": "internal | external",
  "entity_id": "sensor.living_room_temperature",
  "label": "Living room temp",
  "origin": "ramses_cc | homeassistant",
  "notes": "optional"
}
```

### Rules

- **internal** means “use the standard ramses_extras mapping for this device/metric”.
- **external** means “use a specific HA `entity_id`”.
- Missing sensors are allowed; resolver returns `null` + reason.

### Validation rules (backend)

- For derived absolute humidity:
  - Must have both temp and RH sources available.
  - Mixing sources is allowed but should emit warnings (potentially misleading).
- For CO2:
  - If missing, allow `null`.
- If an internal sensor doesn’t exist (device model lacks it), show as unavailable in the UI.

---

## WebSocket / Mapping Contract (proposal)

Extend existing `ramses_extras/get_entity_mappings` to return:

- `mappings`: effective entity IDs (what the card/automation should use)
- `sources`: metadata per mapping (so the UI can show “external/internal” and label)
- `raw_internal` (optional): default internal mapping regardless of override, for UI comparison

### Example response

```json
{
  "mappings": {
    "indoor_temp": "sensor.living_room_temperature",
    "indoor_rh": "sensor.32_153289_indoor_humidity",
    "outdoor_temp": "sensor.32_153289_outdoor_temp",
    "outdoor_rh": "sensor.netatmo_outdoor_humidity",
    "co2": null
  },
  "sources": {
    "indoor_temp": {
      "kind": "external",
      "entity_id": "sensor.living_room_temperature",
      "label": "Living room temp"
    },
    "indoor_rh": {
      "kind": "internal",
      "entity_id": "sensor.32_153289_indoor_humidity",
      "label": "FAN indoor RH"
    },
    "outdoor_rh": {
      "kind": "external",
      "entity_id": "sensor.netatmo_outdoor_humidity",
      "label": "Netatmo outdoor RH"
    }
  },
  "raw_internal": {
    "indoor_temp": "sensor.32_153289_indoor_temp",
    "indoor_rh": "sensor.32_153289_indoor_humidity",
    "outdoor_temp": "sensor.32_153289_outdoor_temp",
    "outdoor_rh": "sensor.32_153289_outdoor_humidity",
    "co2": "sensor.32_153289_co2_level"
  }
}
```

**Notes**

- HVAC card can show “Indoor temp: 18 °C (external: Living room)” while also displaying “internal: 22 °C”.
- Humidity automation uses `mappings` only.

---

## Options Flow UX (proposal)

Per device (FAN), allow selection via dropdown/entity-picker for:

1. **Indoor temperature source**
   - Internal (default)
   - External entity picker
2. **Indoor RH source**
   - Internal (default)
   - External entity picker
3. **Outdoor temperature source**
   - Internal (default, if available)
   - External entity picker
4. **Outdoor RH source**
   - Internal (default, if available)
   - External entity picker
5. **CO2 source**
   - Internal (if available)
   - External entity picker
   - None

**Confirmation-step warnings:** e.g. “Abs humidity will mix temp from Living Room and RH from FAN; this may be physically inconsistent.”

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
- [ ] Decide metric keys + naming (indoor/outdoor/CO2)
- [ ] Decide WS response format (`mappings` + `sources` + optional `raw_internal`)
- [ ] Decide config-entry storage keys and defaults
- [ ] Decide initial UI constraints (entity pickers, device filter, allowed domains)

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

## Acceptance Criteria (initial milestone)

- A device can use an external living-room temperature sensor for `indoor_temp`.
- HVAC card shows the effective temperature and indicates it is external.
- Backend mapping WS returns both effective mapping + source metadata.
- Humidity automation can use external outdoor RH (or indoor RH) and still function, with warnings if pairing is mixed.
