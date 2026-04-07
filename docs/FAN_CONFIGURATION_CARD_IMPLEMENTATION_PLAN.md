# FAN Configuration Card - Implementation Plan (Read-only)

## Goal

Add a **new custom Lovelace card** to `ramses_extras` that acts as a **test bench + observability console** for the fan configuration (FAN / zones / areas / REMs / valves / sensors).

This plan is explicitly scoped to:

- A **new custom card** (frontend JS + minimal Python feature/card registration).
- **Read-only** with respect to `sensor_control` configuration.
  - The card must **not** support editing `sensor_control` mappings/config like the HA “steps” UI.
- Optional “test bench” actions are allowed **only via existing services**, guarded by confirmations.

## Non-goals

- Editing `sensor_control` mappings/config from the card.
- Implementing a full replacement of `docs/zone_testing_package.yaml` in the first iteration (this can be addressed later; see M6).
- Large refactors of fan-control policy (arbiter/coordinator). This card should observe and exercise what exists.

## Canonical references

- `docs/RAMSES_EXTRAS_ARCHITECTURE.md`
- `docs/FAN_CONTROL_ARCHITECTURE.md`
- `docs/FAN_CONFIGURATION_SCHEMA_DRAFT.md`
- `docs/zone_testing_package.yaml` (reference behavior/UI only)

## Success criteria (Definition of Done)

- Card is loadable in HA with no console errors.
- Card can display, for a selected FAN (configured via card editor):
  - zones and areas topology
  - REM bindings + last activity (where available)
  - valve positions and calibration status (where available)
  - list of configured sensors + current values
- Card can trigger selected existing test actions (zone actuation/calibration/demand) with:
  - explicit enablement toggle
  - confirmation dialogs
  - clear error reporting
- Local CI passes.

---

## Progress tracking

### Checklist legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked (note blocker)

### Work log

Add entries as you go:

- **Date**:
- **Milestone**:
- **Notes**:
- **Next**:

---

## Milestones

### M1 - Card scaffolding and registration

- [x] Decide final card ID/name
  - `ramses-fan-map` (card `type: custom:ramses-fan-map`)
- [x] Add a new card definition under the `sensor_control` feature
- [x] Implement a Python feature/card manager similar to `features/hvac_fan_card/`
- [x] Add frontend JS bundle under a `www/` folder and ensure it is served/registered
- [x] Implement a card editor that selects the FAN via `device_id` (same pattern as `hvac-fan-card-editor`)
- [x] Render a minimal shell UI:
  - header + selected FAN
  - “Loading…” state
  - “Error” state

**Done when**: card renders reliably with stub data and correctly wires lifecycle/hooks.

### M2 - Backend data sources and WebSocket contract (read-only)

- [x] Inventory existing websocket commands to reuse (expected in `features/default/websocket_commands.py`):
  - enabled features/cards
  - entity mappings
  - fan config associations
  - remote bindings
  - zones
  - zone positions
  - diagnostics
- [x] Define a card-level “data contract” (JSON shapes) for:
  - configured FAN (`device_id`) and device metadata for display
  - zones/areas
  - valves/positions
  - sensors list + readings
  - REM bindings + activity
- [~] Define “initial payload” fetch sequence
  - aim: minimal round-trips, avoid polling when push/events exist
- [x] Identify missing read-only data
  - if missing data cannot be composed client-side:
    - [x] add **minimal** new websocket endpoint(s)
    - [ ] add tests for those endpoints

**Done when**: card can fetch real data for at least one FAN and show it.

### M3 - UI: FAN overview + topology

- [~] FAN overview panel
  - FAN id
  - coordinator/arbiter summary where available
- [x] Zones table
  - zone id
  - associated area(s)
  - associated valve(s)
  - current “demand” summary (read-only)
- [~] Areas table
  - area id
  - associated sensor entities (if available)
- [x] REM bindings table
  - rem id
  - bound fan id
  - last activity timestamp (if available)
  - conflict / unmatched traffic warnings (if available)

**Done when**: topology is visible, stable, and handles empty states cleanly.

### M4 - UI: Observability (valves, sensors, diagnostics)

- [~] Valve positions panel
  - per valve: current position, age, last update
  - calibration status (if available)
  - safety bounds (min/max) if present in model
- [x] Sensors panel
  - list of configured sensors (resolved) and current values
  - show “source” (mapping/entity) where available
  - stale indicator and basic validation
- [~] Diagnostics panel
  - zone demand breakdown (read-only)
  - any arbiter/coordinator diagnostics already exposed

**Done when**: the card is meaningfully useful for observability.

### M5 - Test bench actions (existing services only)

All actions must be guarded:

- require explicit “Test bench enabled” toggle
- confirmations (and ideally “hold to confirm” pattern)
- explicit “this will change your system” warning

Actions (expected existing services):

- [x] “Run zone actuation cycle”
  - service: `ramses_extras.run_zone_actuation`
- [x] “Set/clear zone demand”
  - service: `ramses_extras.set_zone_demand`
- [x] “Calibrate all valves”
  - service: `ramses_extras.calibrate_all_valves`

Also:

- [x] Render results and errors inline per action
- [x] Don’t auto-run actions (no background automations in the card)

**Done when**: actions run, failures are visible, and UI prevents accidental use.

### M6 - Optional: reduce reliance on `zone_testing_package.yaml`

This milestone is intentionally optional and can be deferred.

- [ ] Identify what the YAML package currently provides that the card covers
- [ ] Decide what remains YAML-only vs moves into integration
- [ ] If integration changes are needed:
  - keep them small and additive
  - avoid changing fan policy/arbiter unless required

**Done when**: you can use the card as the primary observability tool.

### M7 - Tests, lint, documentation

- [ ] Backend tests for any new websocket endpoint(s)
- [ ] Manual frontend verification checklist completed
- [ ] Run local CI
- [ ] Add user docs snippet for adding the card

**Done when**: CI passes and docs exist.

---

## Implementation details (what to change)

### Likely files (frontend)

- Create:
  - `custom_components/ramses_extras/features/sensor_control/www/ramses-fan-map.js`
- Potentially create:
  - `custom_components/ramses_extras/features/sensor_control/www/ramses-fan-map-editor.js`

Frontend should follow existing patterns from:

- `custom_components/ramses_extras/framework/www/ramses-base-card.js`
- `custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js`

### Likely files (backend)

- `custom_components/ramses_extras/features/sensor_control/const.py`
  - add card metadata/registration constants
- `custom_components/ramses_extras/features/sensor_control/__init__.py`
  - create feature manager / card manager hook (pattern after hvac fan card)

If new websocket data is required (prefer not), expect to extend:

- `custom_components/ramses_extras/features/default/websocket_commands.py`

### WebSocket usage guidelines

- Prefer **existing websocket commands**.
- Prefer **one-time fetch + event-driven updates**.
- Avoid tight polling loops.

### UI structure (suggested)

- **Header**
  - FAN summary + refresh button
  - status badges (connected / last update)
- **Topology**
  - Zones
  - Areas
  - REM bindings
- **Observability**
  - Valves/positions
  - Sensors
  - Diagnostics
- **Test bench (danger zone)**
  - gated actions

---

## Manual verification checklist (frontend)

- [ ] Card appears in “Add card” UI (or via manual YAML type)
- [ ] Card renders with no runtime errors
- [ ] Switching FAN updates all sections
- [ ] Empty states do not throw (no zones, no rems, no sensors)
- [ ] WebSocket failures show readable error
- [ ] Service call failures show readable error
- [ ] “Test bench enabled” gating works and is sticky only for the session (preferred)

---

## Test commands

Use the project venv (per repo convention):

- [ ] Local targeted tests (fast signal):
  - `bash -c "source ~/venvs/extras/bin/activate && pytest ."`
- [ ] Full local CI (authoritative):
  - `make local-ci`

Note: small/targeted runs may fail coverage, but full runs must pass.

---

## Risks / open questions

- [x] Exact placement: should this be under `sensor_control` feature or a dedicated `fan_configuration` feature?
  - current implementation: **under `sensor_control`**.
- [x] Data completeness: can the desired observability be composed from existing websocket commands?
- [~] REM activity: ensure we expose “last activity” in a stable, privacy-safe way.
- [ ] Multi-FAN setups: confirm expected UX (current assumption: one card instance per FAN, selected via the card editor).
