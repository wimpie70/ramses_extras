# Temperature Control (Bypass) Feature — Implementation Plan

> ## Progress tracker
>
> | Area | Status |
> | --- | --- |
> | §3 Feature identity (`temp_control`) | ✅ Done |
> | §5 Entities & data model (switch/select/binary_sensor/sensor) | ✅ Done |
> | §6 Configuration keys (config.py) | ✅ Done |
> | §7 Automation logic (state machine, manual override, speed gating) | ✅ Done (runtime validated) |
> | §8.1 Register in `AVAILABLE_FEATURES` | ✅ Done |
> | §8.2 Main options-menu entry + translations | ✅ Done |
> | §8.3 Feature-specific config flow | ✅ Done (includes default_desired_speed selector) |
> | §9.1 Entity mappings in hvac_fan_card const | ✅ Done |
> | §9.2 UI: Temp control button (row 4) | ✅ Done |
> | §9.2 UI: Top-right indicator + highlight | ✅ Done |
> | §9.2 UI: Settings-mode entities | ✅ Done |
> | §9.2 UI: Manual actions disable temp_control | ✅ Done (action-based + state-based safety net) |
> | §9.2 Validation helper (`validateTempControlEntities`) | ✅ Done |
> | §9.2 Translations (en/nl) | ✅ Done |
> | §10 Framework touchpoints (select platform support) | ✅ Done |
> | §11 Backend tests | ✅ Done (58 tests: const, config, decision logic, hysteresis, interval, speed demand, manual override, bypass safety net, per-area evaluation, zone demands) |
> | §11 Frontend tests | ✅ Existing tests pass; new assertions TBD |
> | Phase 1 — Skeleton feature + config | ✅ Done |
> | Phase 2 — Automation MVP | ✅ Done (runtime validated) |
> | Phase 3 — HVAC Fan Card integration | ✅ Done |
> | Phase 4 — Conflict handling / polish | ✅ Done (arbiter resolves speed conflicts; no per-feature gating) |
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
  - `effective_speed_note`: e.g. `"requested"`, `"no_speed_change"`
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

Fan speed:

- `default_desired_speed`: str (`low` | `medium` | `high`) — default speed used when the per-device `select.temp_control_desired_speed_*` entity has no state yet. Default: `high`.

Manual override interaction:

- `manual_override_hold_minutes`: int — deprecated with current UX decision (manual action toggles temp_control off). Keep only if we later want a “pause then resume” mode.

Interaction with other features (keep as policy, not lots of knobs):

- Temp control always sets its fan speed demand during cooling. The **FanSpeedArbiter** resolves conflicts with humidity_control and co2_control — if those features demand a higher speed, the arbiter picks the highest. Temp control does not need to second-guess humidity/CO2 thresholds.

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

- Temp control *always sets* a fan speed demand during **cooling** via the **FanSpeedArbiter** using `select.temp_control_desired_speed_*`.
- The **FanSpeedArbiter** resolves conflicts between features:
  - if humidity_control or co2_control demand a higher speed, the arbiter picks the highest (fine)
  - if humidity_control is dehumidifying, it sets its own demand; the arbiter resolves — temp_control does not need to second-guess it
- In heating_retention, temp_control does not set a speed demand (cleared).

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

### Phase 4 — Conflict handling / polish  ✅ Done

- Interaction rules with humidity_control and co2_control  ✅ (FanSpeedArbiter resolves all speed conflicts)
- Improved status reporting (reason strings, attributes)  ✅
- Add optional "force close" behavior if required  ✅ (heating_retention)
- State-based manual override safety net  ✅ (listens to bypass position entity changes; turns temp_control off if bypass changes externally without a recent temp_control command)

### Phase 5 — Documentation & release  ⏳ Pending

- Update wiki page(s) for the new feature
- Add release notes entry


## 15) Runtime issues found & fixed during validation

15.1 sensor_control overlay not applied to backend automation

- The automation read internal ramses_cc sensors (e.g. `outdoor_temp=25°C`) instead of the user-configured external helper entities (e.g. `outdoor_temp=18°C`).
- Fix: added `_get_sensor_control_context()` to the automation, calling `SensorControlResolver` directly to get external entity mappings for `indoor_temp`, `outdoor_temp`, and `indoor_rh`.

15.2 Transport monitor could not parse PacketDTO messages

- The `_handle_msg` callback expected `Message` objects (with `src.id` / `dst.id`), but ramses_rf now passes `PacketDTO` objects (with `addr1` / `addr2` / `addr3` string fields).
- Result: `src=None dst=None` for every message → devices never marked online → all commands skipped with "transport unavailable".
- Fix: updated `_handle_msg` to read `addr1` from `PacketDTO`, with fallback to `src.id` for backward compatibility.

15.3 Python 2 syntax errors in automation.py

- `except TypeError, ValueError:` (Python 2 syntax) appeared in two places, preventing the module from importing and crashing `_allow_speed_increase` at runtime.
- Fix: corrected to `except (TypeError, ValueError):`.

15.4 Per-feature speed gating removed in favor of arbiter

- The original `_allow_speed_increase` method checked indoor RH against min/max thresholds and blocked speed increases when humidity was out of range.
- Problem: if humidity_control is not enabled, the min/max RH values have no meaning, and the gate blocked cooling speed increases unnecessarily.
- Fix: removed per-feature gating entirely. Temp control now always sets its demand during cooling, and the FanSpeedArbiter resolves conflicts with humidity_control and co2_control.


## 13) Decisions captured from review (so implementation matches intent)

13.1 Temp control is not only cooling

- The comfort temperature (FAN parameter) is the target band.
- Temp control should manage bypass to support:
  - **cooling** (force bypass open when indoor above comfort and outdoor can cool)
  - **heating retention** (force bypass closed when indoor below comfort)

13.2 FanSpeedArbiter resolves conflicts

- Temp control always sets a fan speed demand during cooling.
- The FanSpeedArbiter resolves competing demands from humidity_control, co2_control, and temp_control by picking the highest speed.
- Temp control does not implement its own humidity/CO2 gating — that would duplicate logic owned by those features.
- If humidity_control is dehumidifying, it sets its own demand; the arbiter resolves.

13.3 Comfort temperature source

- FAN comfort parameter is leading.
- It should remain editable from the HVAC Fan Card settings window (2411 parameter editor).

13.4 Manual override semantics

- Any manual bypass action (or manual fan-speed button press) toggles temp_control **off** for that FAN.
- The user can re-enable it using the Temp control button.

## 14) Multi-zone temperature targets (per-area comfort)

### 14.1 Implementation

Per-area comfort temperature is resolved with this priority:

1. **Area sensor `comfort_temperature_entity`** — if set in sensor_control config, use that entity's value (e.g. an `input_number` helper the user created in HA).
2. **FAN global comfort temperature** (param 75) — fallback when no per-area comfort entity is configured.

This means users can:
- Point `comfort_temperature_entity` to any HA entity (`input_number`, `number`, `sensor`, `climate`) for per-area targets.
- Leave it unset to use the FAN's global comfort temperature for all areas.

### 14.2 Per-area evaluation

For each enabled area with a `temperature_entity`:

- **Cooling demand** when: `area_temp >= area_comfort + comfort_delta_activate` AND `outdoor_temp >= min_outdoor_temp` AND `outdoor_temp <= area_temp - cooling_delta_activate`
- **Heating retention demand** when: `area_temp <= area_comfort - comfort_delta_activate`
- **Idle** when neither condition is met (area is within comfort band)

### 14.3 Aggregate bypass decision

- If **any** area has a cooling demand → bypass mode = `cooling` (cooling has priority)
- Else if **any** area has a heating retention demand → bypass mode = `heating_retention`
- Else → bypass mode = `idle`

When no areas are configured (or no area has a temperature entity), the original single-target logic is used (indoor_temp vs global comfort_temp).

### 14.4 Zone demand publishing

When per-area evaluation produces a non-idle decision, temp_control publishes demands into the `ZoneDemandRegistry`:

- `DemandSource.OTHER` with metadata:
  - `kind: "temperature"`
  - `area_id`, `area_temp`, `area_target`
  - `decision: "cooling"|"heating_retention"`
  - `reason: <short string>`

Only areas with a `zone_id` get zone demands (so zone valves open for the area that needs cooling/heating). Areas without a `zone_id` still influence the bypass decision but don't trigger zone valve actuation.

When the bypass mode returns to idle, or temp_control is disabled, all temp_control zone demands are cleared.

### 14.5 Future: BypassModeArbiter

The current implementation has temp_control directly sending bypass commands. For future multi-feature bypass coordination (e.g. if humidity_control also wants to manage bypass), a **BypassModeArbiter** (parallel to FanSpeedArbiter) should be introduced so that:

- Features publish bypass mode demands (open/close/auto + reason)
- The arbiter resolves conflicts and sends the final bypass command
- The zone coordinator (or a higher-level coordinator) resolves **both** fan speed (via FanSpeedArbiter) and bypass mode (via BypassModeArbiter)

Goal: **one place computes the final actuation plan** (fan speed + bypass mode), and features only contribute demand signals + reasons.
