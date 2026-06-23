# Temperature Control (Bypass) Feature — Implementation Plan

> ## Progress tracker
>
> | Area | Status |
> | --- | --- |
> | §3 Feature identity (`temp_control`) | ✅ Done |
> | §5 Entities & data model (switch/select/binary_sensor/sensor) | ✅ Done |
> | §6 Configuration keys (config.py) | ✅ Done |
> | §7 Automation logic (state machine, manual override, speed gating) | ✅ Done (skeleton + logic; needs runtime validation) |
> | §8.1 Register in `AVAILABLE_FEATURES` | ✅ Done |
> | §8.2 Main options-menu entry + translations | ✅ Done |
> | §8.3 Feature-specific config flow | ✅ Done |
> | §9.1 Entity mappings in hvac_fan_card const | ✅ Done |
> | §9.2 UI: Temp control button (row 4) | ✅ Done |
> | §9.2 UI: Top-right indicator + highlight | ✅ Done |
> | §9.2 UI: Settings-mode entities | ✅ Done |
> | §9.2 UI: Manual actions disable temp_control | ✅ Done (action-based; state-based safety net pending) |
> | §9.2 Validation helper (`validateTempControlEntities`) | ✅ Done |
> | §9.2 Translations (en/nl) | ✅ Done |
> | §10 Framework touchpoints (select platform support) | ✅ Done |
> | §11 Backend tests | ✅ Done (43 tests: const, config, decision logic, hysteresis, interval, speed gating) |
> | §11 Frontend tests | ✅ Existing tests pass; new assertions TBD |
> | Phase 1 — Skeleton feature + config | ✅ Done |
> | Phase 2 — Automation MVP | ✅ Done (logic in place; needs runtime validation) |
> | Phase 3 — HVAC Fan Card integration | ✅ Done |
> | Phase 4 — Conflict handling / polish | 🟡 Partial (humidity/CO2 gates implemented in arbiter; state-based override net pending) |
> | Phase 5 — Documentation & release | ⏳ Pending |
>
> Legend: ✅ Done · 🟡 Partial · ⏳ Pending

## 1) Problem statement

Observed behavior:

- When the house is warm (inside temperature is higher than the *comfort temperature*) and the outside air is cooler than inside (conditions suitable for free cooling), the FAN unit does **not** reliably open the bypass when the unit is set to *automatic bypass*.

Goal:

- Add a Ramses Extras feature that can **actively control the FAN bypass** (open/close/auto) based on temperature conditions (“free cooling / night cooling”).
- Expose this feature in:
  - the integration options flow (feature enable + configuration)
  - the HVAC Fan Card (toggle + status indicator)

Non-goals (for the first iteration):

- Replacing the unit’s full internal ventilation logic.
- Rewriting ramses_cc bypass entities.
- Building a general-purpose “HVAC strategy engine” (keep it narrow: bypass control).


## 2) Architectural fit (feature-centric)

This feature should follow the existing **feature-centric architecture**:

- **Feature-owned intent/logic** lives in `custom_components/ramses_extras/features/<feature_id>/...`.
- **Shared infrastructure** (helpers, base classes, registries) lives in `custom_components/ramses_extras/framework/...`.
- `features/<feature_id>/const.py` is the **single source of truth** via `FEATURE_DEFINITION`.

Relevant existing patterns to copy:

- Automation pattern: `features/humidity_control/automation.py`, `features/co2_control/automation.py`
- Feature metadata & entity templates: `features/*/const.py` (`FEATURE_DEFINITION`)
- Options flow routing: global `custom_components/ramses_extras/config_flow.py` + feature-local `features/<feature_id>/config_flow.py`
- Card integration: `features/hvac_fan_card/www/...` + default feature WebSocket `ramses_extras/get_entity_mappings`


## 3) Proposed feature identity

### Feature ID

- **Feature ID**: `temp_control`
- Display name: “Temperature Control (Bypass)” (UI-friendly)

Why `temp_control`:

- Matches the button label requirement (“Temp control”).
- Keeps scope explicit: temperature-driven automation (even though the actuator is the bypass).


## 4) User-facing UX requirements

### 4.1 HVAC Fan Card changes

1) **New button**

- Add a new button to the last row (bypass related buttons):
  - Current: 3 buttons (`Bypass Auto`, `Bypass Close`, `Bypass Open`)
  - Target: 4 buttons, adding **`Temp control`**

2) **New indicator in top section**

- Add an indicator in the **top-right** section:
  - on the right side
  - **below “Comfort Temp”**
  - **above** the “Balance” and “CO2” status panels

Suggested text layout:

- `Temp control: Off` / `Temp control: On` / `Temp control: Cooling` (depending on state)

### 4.2 Options flow / configuration

- Provide a new feature configuration step in the Ramses Extras options flow.
- Allow configuring:
  - enabling the feature for selected FAN devices
  - core thresholds/hysteresis parameters
  - behavior around manual override and interaction with other automations


## 5) Entities & data model (backend)

Keep this minimal and consistent with other features:

### 5.1 Entities created by the feature (per FAN)

Recommended set:

1) `switch.temp_control_<device_id>`

- Acts as the **master enable** for the automation for a single FAN.
- This is what the HVAC Fan Card “Temp control” button toggles.

2) `select.temp_control_desired_speed_<device_id>`

- Config: desired ventilation speed during cooling: `low` | `medium` | `high`.
- Default: `high`.
- This is a *preference*, not a guarantee. The automation must still respect other active demands (humidity/CO2) and any “don’t increase moisture” constraints.

3) `binary_sensor.temp_control_active_<device_id>`

- Diagnostic: **true when the temperature-control automation is actively forcing bypass behavior** (i.e., in `cooling` or `heating_retention`).

4) `sensor.temp_control_status_<device_id>`

- Diagnostic/status string like: `idle`, `cooling`, `heating_retention`, `manual_override_off`, `disabled`, `blocked_transport`.
- Useful as the card indicator source.
- Attributes should include:
  - `desired_bypass_mode`: `auto` | `open` | `close`
  - `desired_speed`: `low` | `medium` | `high`
  - `effective_speed_note`: e.g. `"capped_due_to_humidity"`, `"co2_demand_higher"`, `"no_speed_change"`
  - `last_command`: `fan_bypass_open` | `fan_bypass_close` | `fan_bypass_auto`
  - `reason`: short summary for debugging (“supply cooler than indoor by X”, etc.)
  - `temperatures`: snapshot (indoor/outdoor/supply/comfort)

### 5.2 Entity templates in `const.py`

Define all entity templates and mappings in `features/temp_control/const.py` inside `FEATURE_DEFINITION`.

- `switch_configs`
- `boolean_configs`
- `sensor_configs`
- `device_entity_mapping`
- `required_entities`
- `entity_mappings` (important for frontend mapping via WebSocket)


## 6) Configuration controls (what we need)

### 6.1 Input signals

The automation needs these main temperature values:

- `indoor_temp`
- `comfort_temp`
- `outdoor_temp` (used for the cooling decision — is there cooling potential outside?)

Diagnostics (logged but not used for bypass decision):

- `supply_temp` (the temperature the unit actually supplies to the house; depends on bypass state and heat recovery)

Why `outdoor_temp` matters (not `supply_temp`):

- When bypass is **closed** (heat recovery), supply_temp ≈ indoor_temp because the heat exchanger warms the incoming air.
- This makes `supply_temp <= indoor_temp - delta` almost never true when bypass is closed — circular logic: the automation won’t open bypass because supply is warm, but supply will only cool when bypass is open.
- `outdoor_temp` represents the actual cooling potential of the outside air. Opening the bypass is what brings supply air closer to outdoor temp.
- `supply_temp` is still read and logged for diagnostics so users can see the effect of bypass actuation.

Proposed sourcing strategy:

- Prefer `sensor_control` mappings for indoor/outdoor temps (so users can point to external sensors if desired).
- Prefer 31DA message data for `supply_temp` when available (falls back to a mapped entity).
- Prefer FAN’s comfort temperature from existing parameter entities (if already available) but allow an override.

### 6.2 Proposed config keys (feature section)

Keep this **simple but safe** (mirrors the “few knobs” approach in humidity control).

At minimum:

- `enabled`: bool (feature section present)

Thermal logic (simple hysteresis):

- `comfort_delta_activate`: float (°C) — activate when indoor is outside comfort band:
  - Default: `1.0`
  - cooling entry condition uses `indoor_temp >= comfort_temp + X`
  - heating_retention entry condition uses `indoor_temp <= comfort_temp - X`
- `comfort_delta_deactivate`: float (°C) — deactivate when indoor returns toward comfort:
  - cooling exit uses `indoor_temp <= comfort_temp + Y` (Y < X)
  - heating_retention exit uses `indoor_temp >= comfort_temp - Y`
- `cooling_delta_activate`: float (°C) — cooling requires `outdoor_temp <= indoor_temp - X`
- `cooling_delta_deactivate`: float (°C) — cooling stops when `outdoor_temp >= indoor_temp - Y`

Safety:

- `min_outdoor_temp`: float (°C) — do not force bypass open if outdoor air is too cold

Stability (required because bypass actuation is slow):

- `min_bypass_mode_interval_seconds`: int — minimum time between `open/close/auto` changes

Manual override interaction:

- `manual_override_hold_minutes`: int — deprecated with current UX decision (manual action toggles temp_control off). Keep only if we later want a “pause then resume” mode.

Interaction with other features (keep as policy, not lots of knobs):

- If humidity control is actively dehumidifying/balancing, temp_control must **not** increase ventilation speed (avoid importing moist air). It may still manage bypass if it doesn’t worsen the humidity strategy.

Notes:

- We can add more knobs later if needed, but the first iteration should stay lean.


## 7) Automation logic (backend)

### 7.1 Core decision state machine

Implement a small state machine per FAN:

- `disabled` (switch off)
- `idle` (switch on, monitoring)
- `cooling` (actively forcing bypass open)
- `heating_retention` (actively forcing bypass closed)
- `manual_override_off` (automation was turned off due to manual user action)
- `blocked_transport` (device offline per transport monitor)

Notes:

- `manual_override_off` is essentially “disabled by user intent”; it is represented in HA simply by `switch.temp_control_*` turning off. The status sensor exists to make the reason visible in the UI.

### 7.2 Decision rule (first iteration)

Temp control is about keeping **indoor temperature near the comfort temperature** (both directions).

States:

- `cooling` → force bypass **open**
- `heating_retention` → force bypass **close** (maximize heat recovery)
- `idle` → bypass **auto**

Enter cooling (force bypass open) when all are true:

- `switch.temp_control_*` is on
- `indoor_temp >= comfort_temp + comfort_delta_activate`
- `outdoor_temp <= indoor_temp - cooling_delta_activate`
- `outdoor_temp >= min_outdoor_temp`

Enter heating_retention (force bypass close) when all are true:

- `switch.temp_control_*` is on
- `indoor_temp <= comfort_temp - comfort_delta_activate`

Exit cooling/heating_retention (return bypass to auto) when any are true:

- indoor returns into the comfort band:
  - cooling stops when `indoor_temp <= comfort_temp + comfort_delta_deactivate`
  - heating_retention stops when `indoor_temp >= comfort_temp - comfort_delta_deactivate`
- cooling stops when `outdoor_temp >= indoor_temp - cooling_delta_deactivate`
- safety violated (`outdoor_temp < min_outdoor_temp`)
- manual override happened (temp_control switch toggled off)

Command behavior:

- In `cooling`: send `fan_bypass_open`
- In `heating_retention`: send `fan_bypass_close`
- In `idle`: send `fan_bypass_auto`

Fan speed behavior (new):

- Temp control may *request* a fan speed during **cooling** via the **FanSpeedArbiter** using `select.temp_control_desired_speed_*`.
- Humidity control and CO2 control are boss:
  - if humidity control is active *or* indicates humidity is not OK, temp_control must not increase speed
  - if humidity/CO2 demand a higher speed, the arbiter will resolve higher (fine)
- In heating_retention, temp_control should not raise speed (default: no speed demand).

### 7.3 Triggering

- Use state-change listeners on the relevant temperature and status entities.
- No periodic timer needed; temperature signals are expected to change often enough.

Pattern: follow `HumidityAutomationManager` / `CO2AutomationManager` (subclass `ExtrasBaseAutomation`).

### 7.4 Command sending

Use existing command paths:

- `RamsesCommands` / command registry definitions from the default feature (`fan_bypass_open/close/auto` already exist)
- respect transport monitor checks

### 7.5 Manual actions: card buttons must disable temp_control

We want a very clear “user is boss” rule to avoid fighting the user:

- If the user clicks **any** of the manual bypass buttons (`Bypass Auto`, `Bypass Close`, `Bypass Open`) → **turn temp_control off** for that FAN (i.e. turn off `switch.temp_control_*`) and update the card top status immediately.
- If the user clicks any manual fan-speed button (`Low`, `Medium`, `High`, timer, away/auto cycling, etc.) → **also turn temp_control off**.
  - Rationale: if the user is making manual ventilation choices, they can also manually set bypass mode if needed.

What happens when the user clicks **Temp control** button:

- Toggle `switch.temp_control_*`.
- If toggling **on**, first push bypass to a known baseline by sending `fan_bypass_auto`, then allow the automation to take over (it may switch to open/close depending on comfort logic).

Backend behavior when temp_control is disabled:

- Clear any temp_control fan-speed arbiter demand.
- Return bypass to `auto` (optional; we can decide whether we restore auto immediately or leave the last manual state).

Detection mechanisms (for robustness):

1) **Action-based (primary):** HVAC Fan Card button handlers explicitly turn off `switch.temp_control_*` before sending a bypass command / applying a manual speed override.
2) **State-based (secondary safety net):** listen to ramses_cc bypass-mode entity changes; if bypass mode changes while temp_control is on and the change did not originate from temp_control, turn temp_control off.


## 8) Options flow / config flow implementation

### 8.0 WebSocket registration (feature-specific)

Make sure WebSocket commands are registered in the same way as other features:

- If temp_control needs **no** custom WebSocket commands (likely for MVP), rely on:
  - `ramses_extras/get_entity_mappings` (default feature)
  - HA entities (switch/select/sensor) for UI interaction

- If we later add custom WebSocket commands (e.g. richer diagnostics or batch actions):
  - implement handlers in `features/temp_control/websocket_commands.py`
  - declare metadata in `TEMP_CONTROL_WEBSOCKET_COMMANDS` in `features/temp_control/const.py`
  - register via `load_feature()` using `extras_registry.register_websocket_commands(...)`

Follow `features/co2_control/websocket_commands.py` and `features/*/const.py load_feature()` patterns.


### 8.1 Register the feature

- Add `temp_control` entry in `custom_components/ramses_extras/const.py` `AVAILABLE_FEATURES`.
  - allowed_device_slugs: `["FAN"]`
  - has_device_config: `True`

### 8.2 Add main options-menu entry

In `custom_components/ramses_extras/config_flow.py`:

- add `async_step_feature_temp_control()`
  - set `self._selected_feature = "temp_control"`
  - call `async_step_feature_config()`

Also ensure translations include:

- `options.step.main_menu.menu_options.feature_temp_control`

### 8.3 Feature-specific config flow

Create `custom_components/ramses_extras/features/temp_control/config_flow.py` implementing:

- `async_step_temp_control_config(flow, user_input)`

This function should:

1) show device selection (enabled devices for this feature)
2) show a config form for the defaults listed in §6.2
3) persist configuration using the canonical config structure (`set_feature_section`, per-device sections where needed)

Use sensor_control/config_flow.py as the “good example” for persistence helpers and canonical structure.


## 9) HVAC Fan Card integration plan

### 9.1 Entity mappings used by the card

The HVAC Fan Card uses `ramses_extras/get_entity_mappings` to populate config defaults.

To integrate cleanly:

- Add to `features/hvac_fan_card/const.py` → `FEATURE_DEFINITION["entity_mappings"]`:

  - `temp_control_entity`: `switch.temp_control_{device_id}`
  - `temp_control_desired_speed_entity`: `select.temp_control_desired_speed_{device_id}`
  - `temp_control_active_entity`: `binary_sensor.temp_control_active_{device_id}`
  - `temp_control_status_entity`: `sensor.temp_control_status_{device_id}`

This allows:

- card JS to access `config.temp_control_entity` (and fall back to naming convention if missing)

### 9.2 UI changes

1) **Controls row 4 (bypass row):**

- Update `features/hvac_fan_card/www/.../templates/controls-section.js`:
  - add a 4th button:

    - label: `Temp control`
    - action: toggle the per-device switch entity
    - data attribute (example): `data-action="toggle-temp-control" data-entity-id="..."`

  - update click behavior of *existing* controls:

    - when user clicks `Bypass Auto/Close/Open`: first turn off `switch.temp_control_*`, then send the bypass command
    - when user clicks manual speed buttons (Low/Medium/High/Timers/Away/etc): first turn off `switch.temp_control_*`, then apply manual override

2) **Top-right indicator (and highlight when automation controls bypass):**

- Update `features/hvac_fan_card/www/.../templates/top-section.js`:
  - insert a line under “Comfort Temp” in the `info-stack`
  - display state derived from:
    - `sensor.temp_control_status_*` (preferred; includes `cooling` vs `heating_retention`)
    - fallback to `binary_sensor.temp_control_active_*`
  - when temp_control is actively forcing bypass (cooling/heating_retention), visually highlight this status line (same style approach used for humidity/CO2 triggers).
  - optionally show a short suffix like `"(controlling bypass)"` so it’s obvious the bypass state is automation-driven.

3) **Settings mode: include temp_control entities**

In parameter/settings mode, the card should surface the temp_control-related entities so you can adjust behavior without leaving the card:

- `switch.temp_control_*`
- `select.temp_control_desired_speed_*`
- `sensor.temp_control_status_*` (read-only)

Also: comfort temperature is a FAN parameter and should remain the *leading* target. The card settings mode should keep exposing/editing that comfort parameter (as it already does via 2411 parameter editing).

4) **Validation helper:**

- Add `validateTempControlEntities()` to `framework/www/card-validation.js`.
- Wire it into the card similar to `validateCO2ControlEntities()`.

5) **Translations:**

- Add strings to `features/hvac_fan_card/www/.../translations/en.json` and `nl.json`:
  - `controls.temp_control`
  - `status.temp_control_*` (optional)


## 10) Framework touchpoints (what must be updated)

### 10.1 Feature registry

- `custom_components/ramses_extras/const.py` `AVAILABLE_FEATURES` must be updated.

### 10.2 Feature module structure

Create new folder:

- `custom_components/ramses_extras/features/temp_control/`

Suggested contents (start by copying `hello_world` or `humidity_control` and pruning):

- `__init__.py` — `create_temp_control_feature()` factory (returns `automation`, `config`, `platforms`, etc.)
- `const.py` — `FEATURE_DEFINITION` + defaults + websocket metadata if needed
- `automation.py` — `TempControlAutomationManager(ExtrasBaseAutomation)`
- `config.py` — config manager (prefer `ExtrasConfigManager` for consistent patterns)
- `platforms/` — switch, binary_sensor, sensor
- `services.py` — optional (not required for MVP)


## 11) Testing plan

### Backend tests

- Unit-test the decision function/state machine:
  - entering cooling
  - exiting cooling
  - hysteresis behavior
  - manual override (temp_control toggled off)
  - safety min_outdoor_temp

- Unit-test that the automation does not spam commands (min interval).

### Frontend tests

- Update existing `tests/frontend/test-hvac-fan-card.js` to expect the additional bypass row button and translations.


## 12) Implementation phases

### Phase 1 — Skeleton feature + config  ✅ Done

- Create `features/temp_control` module
- Register feature in `AVAILABLE_FEATURES`
- Add options-flow entrypoint + translations
- Create switch + status entities (even if logic is stubbed)

### Phase 2 — Automation MVP  ✅ Done (needs runtime validation)

- Implement temperature evaluation
- Command: open bypass in cooling, auto otherwise
- Manual actions toggle the automation off (no holdoff/resume in v1)

### Phase 3 — HVAC Fan Card integration  ✅ Done

- Add "Temp control" button
- Add top-right indicator
- Add validation + translations

### Phase 4 — Conflict handling / polish  🟡 Partial

- Interaction rules with humidity_control and co2_control  ✅ (arbiter gates implemented)
- Improved status reporting (reason strings, attributes)  ✅
- Add optional "force close" behavior if required  ✅ (heating_retention)
- State-based manual override safety net  ⏳ Pending

### Phase 5 — Documentation & release  ⏳ Pending

- Update wiki page(s) for the new feature
- Add release notes entry


## 13) Decisions captured from review (so implementation matches intent)

13.1 Temp control is not only cooling

- The comfort temperature (FAN parameter) is the target band.
- Temp control should manage bypass to support:
  - **cooling** (force bypass open when indoor above comfort and supply can cool)
  - **heating retention** (force bypass closed when indoor below comfort)

13.2 Humidity control and CO2 control are boss

- Temp control may request a fan speed while cooling, but only when it does not conflict.
- CO2 considerations are at least as important as humidity: temp_control must never fight CO2 control when air quality is bad.

Speed-increase gate (when temp_control is trying to *increase* ventilation during cooling):

- Only allow temp_control to request an increased speed up to `select.temp_control_desired_speed_*` when **both**:
  - humidity is OK (zones-aware), and
  - CO2 is OK (zones-aware)

Otherwise, temp_control must not request a higher speed (CO2/humidity control will win via the arbiter when they need to).

Definition: “humidity is OK” (zones-aware)

Baseline thresholds (from humidity_control):

- `min_rh` = `number.relative_humidity_minimum_<device_id>`
- `max_rh` = `number.relative_humidity_maximum_<device_id>`

Humidity signals (zones-aware):

- Always include the main indoor RH reading (`sensor.{device_id}_indoor_humidity` with fallbacks).
- If zones/areas are configured (sensor_control area sensors): also include each **enabled** area humidity entity as additional humidity inputs.

Rule:

- Humidity is OK when **all** considered RH readings are within `[min_rh, max_rh]`.
- Additionally, if humidity_control is currently active (e.g. `binary_sensor.dehumidifying_active_<device_id>` is `on`, or the zone-demand registry reports active `DemandSource.HUMIDITY` demands), treat humidity as **not OK** for the purposes of *increasing fan speed*.

Definition: “CO2 is OK” (zones-aware)

Primary signals (from co2_control when enabled):

- `binary_sensor.co2_active_<device_id>`
- `sensor.co2_zone_status_<device_id>` attributes (notably `internal_triggered`, and any per-zone trigger list)

Rule:

- CO2 is OK when co2_control is either disabled *or* it reports no active trigger:
  - `binary_sensor.co2_active_*` is `off`, and
  - `sensor.co2_zone_status_*`.attributes.`internal_triggered` is not `true`.

Zones/areas note:

- If sensor_control area sensors provide CO2 entities and thresholds, we should treat “CO2 OK” as: all enabled area CO2 readings are below their thresholds. Until that’s implemented, prefer the co2_control active/trigger status as the authoritative gate.

Policy:

- If humidity is OK **and** CO2 is OK, temp_control may increase fan speed up to `select.temp_control_desired_speed_*` (subject to arbiter resolution).
- If either is not OK, temp_control must not increase speed.

Implementation note:

- For v1, implement this with direct entity reads + area sensor list already returned by `ramses_extras/get_entity_mappings` (sensor_control overlay includes `area_sensors`).
- If this becomes too coupled, introduce explicit diagnostic entities later (e.g. `binary_sensor.humidity_ok_*`, `binary_sensor.co2_ok_*`, and/or `binary_sensor.all_zones_ok_*`) and consume those instead.

13.3 Comfort temperature source

- FAN comfort parameter is leading.
- It should remain editable from the HVAC Fan Card settings window (2411 parameter editor).

13.4 Manual override semantics

- Any manual bypass action (or manual fan-speed button press) toggles temp_control **off** for that FAN.
- The user can re-enable it using the Temp control button.

## 14) Future: areas/zones temperature targets (multi-zone comfort)

When using **areas/zones** (sensor_control area sensors), we may have scenarios like:

- One area too warm, another area OK/cool
- The global FAN comfort temperature is not a good proxy for all areas

In those cases, temp_control “cooling/heating_retention” decisions need a **per-area target** (desired/comfort temperature) in addition to per-area current temperature.

### 14.1 Proposed approach

1) Add optional per-area “comfort temperature” sources:

- Option A (simple): `number.temp_control_area_comfort_temp_<device_id>_<area_id>` entities (one per enabled area)
- Option B (integrated): reuse existing HA `climate`/`input_number`/`number` entities as configured per area (similar to how sensor_control lets users choose sensor sources)

2) Compute an aggregated “cooling demand” / “heating retention demand” across areas:

- For cooling: any(area_temp >= area_comfort + delta_activate) AND outdoor_temp can cool
- For heating retention: any(area_temp <= area_comfort - delta_activate)

3) Decide bypass mode using a simple priority:

- If any cooling-demand area exists → prefer `cooling`
- Else if any heating-demand area exists → prefer `heating_retention`
- Else → `idle`

(We can later refine this by weighting/majority or by selecting the “worst” area.)

4) Keep the current single-target logic as the default when no per-area comfort targets are configured.

### 14.2 Notes / risks

- Avoid fighting CO2/humidity strategies: per-area temperature demand must still be gated by the existing humidity/CO2 “boss” rules.
- UI: if per-area comfort targets exist, expose them in the HVAC Fan Card settings section similarly to humidity controls.
- Start minimal: implement per-area targets only for *cooling* first if needed; add heating retention later.

### 14.3 Centralized decision helper / zone coordinator integration (future)

When zones were introduced, we moved “what should the system do?” into one place so that:

- multiple signals (features + zone valves) are resolved consistently, and
- actuators are driven from a single computed plan.

In the current temp_control implementation **we are not using the zone coordinator decision path**:

- temp_control computes its own bypass decision (idle/cooling/heating_retention) and sends bypass commands.
- temp_control fan-speed requests are coordinated via the **FanSpeedArbiter** (this part *is* centralized).

For future multi-zone temperature targeting, we should align with the existing centralized decision flow by **combining** configuration + demand publishing:

- **Option A (inputs/config):** introduce per-area configuration:
  - a per-area comfort/target temperature entity (selected by the user, or user-created helper)
  - a per-area policy control like `select.temp_control_area_bypass_policy_*` (e.g. `off` / `cooling_only` / `heating_only` / `cooling_and_heating`)

- **Option B (coordination):** temp_control publishes a “temperature demand” into the existing demand registry using `DemandSource.OTHER` + `metadata`.
  - This pattern is already used to carry non-core demand types by attaching details in `metadata` (e.g. additional sensors such as air-quality-like signals).
  - Suggested metadata shape:
    - `kind: "temperature"`
    - `area_id`, `area_temp`, `area_target`, `delta`
    - `desired_bypass_mode: "open"|"close"`
    - `decision: "cooling"|"heating_retention"`
    - `reason: <short string>`

Resolution of potentially conflicting demands (multiple areas/zones) should be handled centrally:

- Introduce a **BypassModeArbiter** (parallel to FanSpeedArbiter).
- The zone coordinator (or a higher-level coordinator) should resolve **both**:
  - final fan speed (via FanSpeedArbiter), and
  - final bypass mode (via BypassModeArbiter)

Goal: **one place computes the final actuation plan** (fan speed + bypass mode), and features only contribute demand signals + reasons.
