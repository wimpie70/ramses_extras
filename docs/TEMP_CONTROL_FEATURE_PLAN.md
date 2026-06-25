# Temperature Control (Bypass) Feature

> ## Progress tracker
>
> | Area | Status |
> | --- | --- |
> | §3 Feature identity (`temp_control`) | ✅ Done |
> | §5 Entities & data model (switch/select/binary_sensor/sensor) | ✅ Done |
> | §6 Configuration keys (config.py) | ✅ Done |
> | §7 Automation logic (state machine, manual override, speed gating) | ✅ Done (runtime validated) |
> | §7.7 Dewpoint guard (condensation protection) | ✅ Done (optional, opt-in) |
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
> | §11 Backend tests | ✅ Done (58 tests) |
> | §11 Frontend tests | ✅ Existing tests pass |
> | §14 Multi-zone per-area comfort | ✅ Done (per-area evaluation + zone demand publishing) |
> | Phase 1 — Skeleton feature + config | ✅ Done |
> | Phase 2 — Automation MVP | ✅ Done (runtime validated) |
> | Phase 3 — HVAC Fan Card integration | ✅ Done |
> | Phase 4 — Conflict handling / polish | ✅ Done |
> | Phase 5 — Documentation & release | ⏳ Pending |
>
> Legend: ✅ Done · 🟡 Partial · ⏳ Pending


## 1) Problem statement

Observed behavior:

- When the house is warm (inside temperature is higher than the *comfort temperature*) and the outside air is cooler than inside (conditions suitable for free cooling), the FAN unit does **not** reliably open the bypass when the unit is set to *automatic bypass*.

Goal:

- Add a Ramses Extras feature that can **actively control the FAN bypass** (open/close/auto) based on temperature conditions ("free cooling / night cooling").
- Expose this feature in:
  - the integration options flow (feature enable + configuration)
  - the HVAC Fan Card (toggle + status indicator)

Non-goals:

- Replacing the unit's full internal ventilation logic.
- Rewriting ramses_cc bypass entities.
- Building a general-purpose "HVAC strategy engine" (keep it narrow: bypass control).


## 2) Architectural fit (feature-centric)

This feature follows the existing **feature-centric architecture**:

- **Feature-owned intent/logic** lives in `custom_components/ramses_extras/features/temp_control/...`.
- **Shared infrastructure** (helpers, base classes, registries) lives in `custom_components/ramses_extras/framework/...`.
- `features/temp_control/const.py` is the **single source of truth** via `FEATURE_DEFINITION`.

Relevant patterns used:

- Automation pattern: `features/humidity_control/automation.py`, `features/co2_control/automation.py`
- Feature metadata & entity templates: `features/*/const.py` (`FEATURE_DEFINITION`)
- Options flow routing: global `config_flow.py` + feature-local `features/temp_control/config_flow.py`
- Card integration: `features/hvac_fan_card/www/...` + default feature WebSocket `ramses_extras/get_entity_mappings`


## 3) Feature identity

- **Feature ID**: `temp_control`
- Display name: "Temperature Control (Bypass)"


## 4) User-facing UX

### 4.1 HVAC Fan Card

1) **Temp control button** — added to the bypass row (row 4), next to `Bypass Auto`, `Bypass Close`, `Bypass Open`.

2) **Top-right indicator** — below "Comfort Temp", above "Balance" and "CO2" panels:
   - `Temp control: Off` / `Temp control: On` / `Temp control: Cooling` / `Temp control: Heating retention`
   - Visually highlighted when actively controlling bypass.

### 4.2 Options flow

- Feature configuration step in the Ramses Extras options flow.
- Configure: enabling per FAN device, thresholds/hysteresis, default fan speed.


## 5) Entities & data model

### 5.1 Entities created per FAN

1) `switch.temp_control_<device_id>` — master enable for the automation.

2) `select.temp_control_desired_speed_<device_id>` — desired ventilation speed during cooling: `low` | `medium` | `high`. Default: `high`. This is a *preference*; the FanSpeedArbiter resolves conflicts.

3) `binary_sensor.temp_control_active_<device_id>` — diagnostic: true when temp_control is actively forcing bypass (cooling or heating_retention).

4) `sensor.temp_control_status_<device_id>` — diagnostic status string: `idle`, `cooling`, `heating_retention`, `disabled`.
   - Attributes:
     - `desired_bypass_mode`: `auto` | `open` | `close`
     - `desired_speed`: `low` | `medium` | `high`
     - `effective_speed_note`: `requested` | `no_speed_change`
     - `last_command`: `fan_bypass_open` | `fan_bypass_close` | `fan_bypass_auto`
     - `temperatures`: snapshot (indoor/outdoor/supply/comfort)
     - `settings`: active settings snapshot


## 6) Configuration

### 6.1 Input signals

The automation needs:

- `indoor_temp` — indoor temperature
- `comfort_temp` — FAN comfort temperature (parameter 75)
- `outdoor_temp` — outdoor temperature (used for cooling decision)

Diagnostics (logged but not used for bypass decision):

- `supply_temp` — the temperature the unit supplies to the house

Why `outdoor_temp` (not `supply_temp`) for the cooling decision:

- When bypass is **closed** (heat recovery), supply_temp ≈ indoor_temp because the heat exchanger warms the incoming air.
- This makes `supply_temp <= indoor_temp - delta` almost never true when bypass is closed — circular logic.
- `outdoor_temp` represents the actual cooling potential of the outside air. Opening the bypass is what brings supply air closer to outdoor temp.

Sourcing strategy:

- `sensor_control` mappings for indoor/outdoor temps (users can point to external sensors).
- 31DA message data for `supply_temp` when available.
- FAN's comfort temperature from parameter entity (param 75), with per-area override (see §14).

### 6.2 Config keys

Thermal logic (hysteresis):

- `comfort_delta_activate`: float (°C) — default `1.0`
  - cooling entry: `indoor_temp >= comfort_temp + X`
  - heating_retention entry: `indoor_temp <= comfort_temp - X`
  - cooling exit: `indoor_temp <= comfort_temp + Y` (Y < X)
  - heating_retention exit: `indoor_temp >= comfort_temp - Y`
- `cooling_delta_activate`: float (°C) — default `1.0` — cooling requires `outdoor_temp <= indoor_temp - X`
- `cooling_delta_deactivate`: float (°C) — default `0.5` — cooling stops when `outdoor_temp >= indoor_temp - Y`

Safety:

- `min_outdoor_temp`: float (°C) — default `10.0` — do not force bypass open if outdoor air is too cold
- `dewpoint_guard_enabled`: bool — default `False` — when enabled, blocks cooling if condensation risk is high (see §7.7)
- `dewpoint_margin_c`: float (°C) — default `1.0` — safety margin added to the indoor dew point for the condensation guard

Stability:

- `min_bypass_mode_interval_seconds`: int — default `180` — minimum time between bypass mode changes

Fan speed:

- `default_desired_speed`: str (`low` | `medium` | `high`) — default `high` — used when the per-device select entity has no state yet

Interaction with other features:

- Temp control always sets its fan speed demand during cooling. The **FanSpeedArbiter** resolves conflicts with humidity_control and co2_control — if those features demand a higher speed, the arbiter picks the highest. Temp control does not need to second-guess humidity/CO2 thresholds.


## 7) Automation logic

### 7.1 State machine (per FAN)

- `disabled` — switch off
- `idle` — switch on, monitoring, bypass auto
- `cooling` — actively forcing bypass open
- `heating_retention` — actively forcing bypass closed

### 7.2 Decision rules

**Single-target mode** (no areas configured):

Enter cooling when all are true:
- `switch.temp_control_*` is on
- `indoor_temp >= comfort_temp + comfort_delta_activate`
- `outdoor_temp <= indoor_temp - cooling_delta_activate`
- `outdoor_temp >= min_outdoor_temp`

Enter heating_retention when all are true:
- `switch.temp_control_*` is on
- `indoor_temp <= comfort_temp - comfort_delta_activate`

Exit conditions (return to idle / bypass auto):
- indoor returns into comfort band (using `comfort_delta_deactivate`)
- cooling: `outdoor_temp >= indoor_temp - cooling_delta_deactivate`
- safety: `outdoor_temp < min_outdoor_temp`
- manual override (switch toggled off)

**Per-area mode** (when sensor_control areas with temperature entities are configured):

See §14.

### 7.3 Command behavior

- `cooling` → send `fan_bypass_open`
- `heating_retention` → send `fan_bypass_close`
- `idle` → send `fan_bypass_auto`

### 7.4 Fan speed behavior

- During **cooling**: temp_control sets a fan speed demand via the **FanSpeedArbiter** using `select.temp_control_desired_speed_*`.
- The arbiter resolves conflicts between features (highest speed wins).
- During **heating_retention** and **idle**: temp_control clears its speed demand.

### 7.5 Triggering

- State-change listeners on temperature and status entities.
- No periodic timer; temperature signals change often enough.
- Pattern: subclass `ExtrasBaseAutomation` (same as humidity_control / co2_control).

### 7.6 Manual override handling

Three layers of protection ensure the user is always in control:

1) **Action-based (primary):** HVAC Fan Card button handlers turn off `switch.temp_control_*` before sending a manual bypass or speed command.

2) **Arbiter-based:** When a user presses a remote or card speed button, the service handler sets `is_manual_override_active` in the FanSpeedArbiter. Temp_control checks this and skips processing. When the user presses **Auto**, the manual override is cleared and `_async_resume_feature_control()` re-evaluates temp_control (along with humidity_control and co2_control).

3) **State-based safety net:** Listens to `binary_sensor.*_bypass_position` entity changes. If the bypass position changes while temp_control is on and the change was not caused by a recent temp_control command (within 10s), temp_control is turned off automatically.

Backend behavior when temp_control is disabled:
- Clear fan-speed arbiter demand.
- Clear all zone demands (DemandSource.OTHER).
- Return bypass to `auto`.

### 7.7 Dewpoint guard (condensation protection)

When `dewpoint_guard_enabled` is `True`, temp_control adds a condensation safety check before forcing bypass open for cooling.

**Physical rationale:**

- Bypass open → cold outdoor air flows through the supply ducts.
- Ducts and internal surfaces cool down towards the supply air temperature.
- Warm, humid indoor air contacts those cold surfaces.
- If `supply_temp < indoor_dewpoint + margin`, condensation forms on cold ducts/surfaces.

**Computation:**

- Indoor dew point is calculated from `indoor_temp` + `indoor_rh` using the Magnus formula:

  ```
  a = 17.62, b = 243.12
  gamma = (a * T) / (b + T) + ln(RH / 100)
  dewpoint = (b * gamma) / (a - gamma)
  ```

- If `supply_temp < indoor_dewpoint + dewpoint_margin_c`, the desired mode is forced back to `idle` (bypass auto) and zone demands are cleared.

**Why indoor (not outdoor) dewpoint:**

- The condensation risk is indoor moisture condensing on cold supply surfaces.
- Outdoor air at 6°C/100% RH has dewpoint 6°C, but when it enters a 22°C house it warms up and RH drops to ~30% — that air itself won't cause condensation.
- The relevant comparison is: how cold do surfaces get (`supply_temp`) vs. how much moisture is already in the house (`indoor_dewpoint`).

**Important note on `supply_temp`:**

- The guard relies on `supply_temp` reflecting the actual supply air temperature after bypass open.
- When bypass is open (no heat recovery), supply_temp should approach outdoor_temp.
- If `supply_temp` is not available or not updating (e.g. sensor unavailable), the guard may not trigger as expected. Ensure `sensor.<device>_supply_temp` is populated.

**Configuration:**

- `dewpoint_guard_enabled`: bool (default `False`) — opt-in.
- `dewpoint_margin_c`: float °C (default `1.0`) — conservative starting point. Increase if the guard blocks cooling too often; decrease if condensation still occurs.


## 8) Options flow / config flow

### 8.1 Feature registration

- `temp_control` entry in `const.py` `AVAILABLE_FEATURES`.
  - `allowed_device_slugs: ["FAN"]`
  - `has_device_config: True`

### 8.2 Main options-menu entry

- `async_step_feature_temp_control()` in `config_flow.py`.
- Translations: `options.step.main_menu.menu_options.feature_temp_control`.

### 8.3 Feature-specific config flow

`features/temp_control/config_flow.py`:
- Device selection (enabled FAN devices)
- Config form for the settings in §6.2
- `default_desired_speed` selector (low/medium/high)
- Persists using canonical config structure (`set_feature_section`)


## 9) HVAC Fan Card integration

### 9.1 Entity mappings

Added to `features/hvac_fan_card/const.py` → `FEATURE_DEFINITION["entity_mappings"]`:

- `temp_control_entity`: `switch.temp_control_{device_id}`
- `temp_control_desired_speed_entity`: `select.temp_control_desired_speed_{device_id}`
- `temp_control_active_entity`: `binary_sensor.temp_control_active_{device_id}`
- `temp_control_status_entity`: `sensor.temp_control_status_{device_id}`

### 9.2 UI changes

1) **Bypass row (row 4):** "Temp control" button toggles the per-device switch entity. Existing bypass buttons turn off temp_control before sending their command.

2) **Top-right indicator:** Status line under "Comfort Temp", derived from `sensor.temp_control_status_*`. Highlighted when actively controlling bypass.

3) **Settings mode:** Surfaces `switch.temp_control_*`, `select.temp_control_desired_speed_*`, and `sensor.temp_control_status_*`.

4) **Validation helper:** `validateTempControlEntities()` in `card-validation.js`.

5) **Translations:** `controls.temp_control` and status strings in en.json / nl.json.


## 10) Framework touchpoints

### 10.1 Feature module structure

`custom_components/ramses_extras/features/temp_control/`:

- `__init__.py` — `create_temp_control_feature()` factory
- `const.py` — `FEATURE_DEFINITION` + defaults
- `automation.py` — `TempControlAutomationManager(ExtrasBaseAutomation)`
- `config.py` — `TempControlConfig` / `TempControlSettings`
- `config_flow.py` — feature-specific options flow step
- `platforms/` — switch, select, binary_sensor, sensor

### 10.2 Service handler integration

`features/default/services.py` — `_async_resume_feature_control()` calls `temp_control._reconcile_startup_states(device_id)` when the user presses Auto or a remote override timeout expires.


## 11) Testing

### Backend tests (58 tests)

- **Decision logic:** entering/exiting cooling, heating_retention, hysteresis
- **Safety:** min_outdoor_temp blocks cooling, dewpoint guard blocks cooling on condensation risk
- **Stability:** min bypass mode interval prevents command spam
- **Speed demand:** set during cooling, cleared in idle/heating_retention/disabled
- **Manual override:** skipped when `is_manual_override_active`, skipped when extras control disabled
- **Bypass safety net:** external bypass change turns off temp_control; own command within 10s window is ignored; non-bypass entities pass through
- **Per-area evaluation:** cooling demand, heating_retention demand, idle areas skipped, fallback to global comfort, disabled areas skipped, min_outdoor_temp blocks cooling
- **Zone demands:** set for areas with zone_id, cleared when stale, skipped for areas without zone_id, all cleared on disable
- **Aggregate decision:** cooling has priority over heating_retention


## 12) Implementation phases

### Phase 1 — Skeleton feature + config ✅ Done

### Phase 2 — Automation MVP ✅ Done (runtime validated)

### Phase 3 — HVAC Fan Card integration ✅ Done

### Phase 4 — Conflict handling / polish ✅ Done

- FanSpeedArbiter resolves all speed conflicts
- Manual override: action-based + arbiter-based + state-based safety net
- Resume on Auto via `_async_resume_feature_control`

### Phase 5 — Documentation & release ⏳ Pending


## 13) Design decisions

### 13.1 Temp control is not only cooling

- The comfort temperature (FAN parameter) is the target band.
- Temp control manages bypass for both:
  - **cooling** (force bypass open when indoor above comfort and outdoor can cool)
  - **heating retention** (force bypass closed when indoor below comfort)

### 13.2 FanSpeedArbiter resolves conflicts

- Temp control always sets a fan speed demand during cooling.
- The FanSpeedArbiter resolves competing demands from humidity_control, co2_control, and temp_control by picking the highest speed.
- Temp control does not implement its own humidity/CO2 gating — that would duplicate logic owned by those features.
- If humidity_control is dehumidifying, it sets its own demand; the arbiter resolves.

### 13.3 Comfort temperature source

- FAN comfort parameter (param 75) is the global default.
- Per-area comfort temperature can be set via `comfort_temperature_entity` in sensor_control area config (see §14).
- The comfort parameter remains editable from the HVAC Fan Card settings window (2411 parameter editor).

### 13.4 Manual override semantics

- Any manual bypass action (or manual fan-speed button press) toggles temp_control **off** for that FAN.
- Remote/card speed button presses set `is_manual_override_active` — temp_control skips processing.
- Pressing **Auto** clears the manual override and resumes temp_control.
- The user can re-enable temp_control using the Temp control button.


## 14) Multi-zone temperature targets (per-area comfort)

### 14.1 Per-area comfort temperature

Each area sensor in sensor_control can optionally have a `comfort_temperature_entity` field. Comfort temp is resolved with this priority:

1. **Area sensor `comfort_temperature_entity`** — if set, use that entity's value (e.g. an `input_number` helper the user created in HA).
2. **FAN global comfort temperature** (param 75) — fallback when no per-area comfort entity is configured.

Users can:
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

### 14.4 Actuation chain

When per-area evaluation produces a non-idle decision, three actuators are driven:

| Actuator | Mechanism | How |
|----------|-----------|-----|
| **Bypass** | Direct command | temp_control sends `fan_bypass_open`/`close`/`auto` |
| **Fan speed** | FanSpeedArbiter | temp_control sets demand → arbiter resolves → applies |
| **Zone valves** | ZoneDemandRegistry → ZoneCoordinator | temp_control publishes `DemandSource.OTHER` → ZoneDemandRegistry schedules actuation cycle (1s debounce) → ZoneCoordinator opens valves for demanding zones, closes others |

Zone demand metadata:
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
- The zone coordinator resolves **both** fan speed (via FanSpeedArbiter) and bypass mode (via BypassModeArbiter)

Goal: **one place computes the final actuation plan** (fan speed + bypass mode), and features only contribute demand signals + reasons.


## 15) Runtime issues found & fixed during validation

### 15.1 sensor_control overlay not applied to backend automation

- The automation read internal ramses_cc sensors instead of the user-configured external helper entities.
- Fix: added `_get_sensor_control_context()` to the automation, calling `SensorControlResolver` directly to get external entity mappings for `indoor_temp`, `outdoor_temp`, and `indoor_rh`.

### 15.2 Transport monitor could not parse PacketDTO messages

- The `_handle_msg` callback expected `Message` objects (with `src.id` / `dst.id`), but ramses_rf now passes `PacketDTO` objects (with `addr1` / `addr2` / `addr3` string fields).
- Result: `src=None dst=None` for every message → devices never marked online → all commands skipped with "transport unavailable".
- Fix: updated `_handle_msg` to read `addr1` from `PacketDTO`, with fallback to `src.id` for backward compatibility.

### 15.3 Python 2 syntax errors in automation.py

- `except TypeError, ValueError:` (Python 2 syntax) appeared in two places, preventing the module from importing.
- Fix: corrected to `except (TypeError, ValueError):`.

### 15.4 Per-feature speed gating removed in favor of arbiter

- The original `_allow_speed_increase` method checked indoor RH against min/max thresholds and blocked speed increases when humidity was out of range.
- Problem: if humidity_control is not enabled, the min/max RH values have no meaning, and the gate blocked cooling speed increases unnecessarily.
- Fix: removed per-feature gating entirely. Temp control now always sets its demand during cooling, and the FanSpeedArbiter resolves conflicts.

### 15.5 Dewpoint guard added (condensation protection)

- Added optional `dewpoint_guard_enabled` + `dewpoint_margin_c` settings.
- When enabled, cooling (bypass open) is blocked if `supply_temp < indoor_dewpoint + margin`.
- Indoor dewpoint is computed from `indoor_temp` + `indoor_rh` via the Magnus formula.
- Defaults to off (opt-in) to preserve existing behavior for users who don't need it.
- Note: the guard depends on `supply_temp` being accurate. If the supply temp sensor is unavailable or not updating, the guard may not trigger correctly.

### 15.6 Select platform not unloaded on integration reload

- `async_unload_entry` was unloading only 4 of 5 platforms (sensor, switch, binary_sensor, number) — `Platform.SELECT` was missing.
- On reload (options change, manual reload), the select platform was never torn down, causing `ValueError: Config entry ... for ramses_extras.select has already been setup!`.
- Fix: added `Platform.SELECT` to the `async_unload_platforms` call so unload and setup are symmetric.
