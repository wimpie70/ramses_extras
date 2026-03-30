# Remote Binding - Implementation Plan

## Purpose

Define how Ramses Extras should associate real REM devices with FAN devices so that:

- observed remote button presses can be attributed to the correct FAN
- HA cards can reflect real remote actions consistently
- the fan-speed arbiter remains the single authority for effective HA-side control state
- the design still behaves safely when Home Assistant is offline

## Scope

This plan covers:

- binding a REM to a FAN inside Extras
- using that binding to interpret live remote traffic
- feeding shared HA/arbiter state from remote commands
- exposing binding state to diagnostics and cards where useful

This plan does not try to move the source of truth into `ramses_rf`. The binding is intentionally maintained in Extras for now.

## Goals

- Support one physical REM controlling one FAN device.
- Detect and attribute `Auto`, speed, `Away`, and timer button presses.
- Keep HA state aligned with real-world remote actions.
- Avoid duplicate command loops when a remote press is observed after HA already sent a command.
- Allow future extension to multiple remotes, zone remotes, or richer role models.

## Non-goals for phase 1

- Automatic discovery of bindings from `ramses_rf`.
- Multi-remote arbitration for one FAN.
- Bidirectional provisioning of bindings into devices.
- Full historical binding audit trail.

## Current state

Today Extras already has pieces of this:

- `RamsesCommands._get_bound_rem_device()` can ask the underlying system for a bound REM when available.
- the default service layer can observe remote-originated fan commands and update arbiter state
- the fan-speed arbiter tracks manual override and `extras_control_enabled`
- the HVAC card already reflects arbiter-driven control mode

The missing part is a stable Extras-owned binding model that does not depend on `ramses_rf` having first-class REM-to-FAN registration.

## Configuration strategy alignment

This plan should follow the shared strategy in:

- `docs/CONFIGURATION_STRATEGY.md`

That means the remote-binding implementation should not grow as an isolated set of loose config-entry keys.

Instead:

- remote binding should own a dedicated feature section inside the shared structured config model
- config flow should become an editor for that section, not the definition of the data model
- the editing UX should live under a FAN-oriented configuration area, likely evolving the current `sensor_control` UX toward a broader `FAN Configuration` concept
- strict YAML export should use the same validated feature section shape
- validated YAML import should come later, after migrations are proven
- discovered REM/FAN devices from `ramses_cc` should be used for prefilling and suggestions, not silently treated as persisted policy or persisted as hints

Suggested placement inside the shared config model:

```text
features:
  remote_binding:
    FANs:
      32:153289:
        REMs:
          - rem_id: 37:169161
            role: primary
            enabled: true
            source: manual_config
```

This keeps remote-binding ownership explicit while still letting other features refer to the same FAN identities.

## Proposed architecture

### 1. Binding registry in Extras

Create an Extras-owned binding registry keyed by FAN device id.

Suggested logical shape:

```text
fan_remote_bindings:
  32:153289:
    remotes:
      - device_id: 37:169161
        role: primary
        source: manual_config
        enabled: true
```

Suggested storage location:

- a structured `remote_binding` feature section in persisted config
- mirrored into `hass.data[DOMAIN]` at runtime for fast lookup

### 2. Binding resolution order

When Extras needs to determine whether a remote belongs to a FAN:

1. explicit Extras binding
2. live lookup via `_get_bound_rem_device()`
3. no match -> ignore as unrelated traffic

This gives a stable user-configured path while still benefiting from device-reported information if present.

### 3. Runtime service API

Add a small binding helper/service layer with operations like:

- list bindings for a FAN
- set/replace primary REM for a FAN
- remove binding
- validate whether a REM is already assigned elsewhere

This can stay internal at first, then be surfaced through config flow / WebSocket later.

### 4. Config flow UX

Add a dedicated binding step under FAN-oriented configuration.

Near-term direction:

- keep config flow as the main editor
- edit the structured `remote_binding` feature section rather than loose options keys
- expose it through a FAN-oriented configuration editor rather than a separate top-level feature UI
- prefill candidate FAN and REM devices from discovery
- still allow external/manual device selection when discovery candidates are incomplete

Initial UX can be simple:

- select FAN
- select REM from known REM-capable devices
- save one primary binding

Future UX can support:

- multiple remotes
- remote roles
- binding health indicators
- observed last-seen timestamp
- strict YAML export against the same feature section shape
- later validated YAML import against the same feature section shape

### 4a. Framework/config dependencies

This plan depends on framework work described in `docs/CONFIGURATION_STRATEGY.md`.

Required support includes:

- shared structured config storage for feature-owned sections
- nested validation for binding entries via `register_config_validator()`
- cross-reference validation against known FAN and REM device references
- uniqueness validation (one REM not assigned to multiple FANs)
- strict YAML export helpers for support and debugging
- **validated import via framework validation registry**

### 5. Message attribution pipeline

Observed remote messages should flow like this:

1. live message arrives from event bus or direct client listener
2. Extras resolves the target FAN using the binding registry
3. remote command is normalized into a canonical fan command
4. arbiter state is updated without echo-sending the command
5. diagnostics/card state refreshes from the arbiter

### 6. Debounce and duplicate protection

Real remotes may emit repeated packets. Keep and extend the current protections:

- per-device/per-command debounce window
- ignore `RQ` polling traffic
- optionally correlate by `(src, dst, code, payload)` for a short TTL

## Offline behavior

When Home Assistant is offline, the real remote must still directly control the FAN.

Therefore Extras must treat live remote observation as a state-synchronization layer, not as the mechanism that makes the remote work.

Design rule:

- the physical FAN/REM interaction works without HA
- when HA comes back, Extras should reconcile toward the observed real-world state instead of assuming HA remained authoritative

## Phased implementation

### Phase 1 - explicit FAN -> REM binding ✅ COMPLETE

- [x] add runtime binding registry
- [x] define the `remote_binding` structured feature section
- [x] add config flow support for one REM per FAN as an editor for that section inside the FAN-oriented configuration UX
- [x] use registry in remote command attribution
- [x] expose binding in diagnostics/debug state

### Phase 2 - reconciliation and observability ✅ COMPLETE

- [x] add last-seen remote timestamp
- [x] add diagnostics for unmatched remote traffic
- [x] add binding conflict detection
- [x] add WebSocket/debugger endpoint for reading bindings
- [x] add strict YAML export shape for support/debugging

### Phase 3 - richer remote model ✅ COMPLETE

- [x] multiple remotes per FAN
- [x] role support (`primary`, `secondary`, `boost_only`)
- [x] optional learned binding suggestions from observed traffic
- [x] validated YAML import via framework validation registry (`register_config_validator()`)

### Phase 4 - integration completion ✅ COMPLETE

- [x] import validation registered in `features/sensor_control/remote_binding_yaml.py`
- [x] export support via `export_config_to_yaml()`
- [x] documentation with examples in `docs/REMOTE_BINDING_EXAMPLES.md`
- [ ] final integration testing with live REM devices (deferred to hardware validation)

#### Phase 4a - live REM integration test plan (detailed)

This phase is intentionally focused on validating the end-to-end behavior with **real REM hardware**.

**Live Test Results (March 30, 2026):**
- **REM Device**: `37:168270` (physical REM actively sending commands)
- **DIS Device**: `37:169161` (physical display unit)
- **FAN Device**: `32:153289` (ventilation unit)
- **Observed Traffic**: REM sending `22F1` fan mode commands (high/low) to FAN
- **Status**: Real devices detected and traffic flowing correctly

The primary design rule remains:

- REM -> FAN control must work without Home Assistant
- Extras acts as a **state synchronization layer** when HA is online

**Live Testing Checklist:**

- [x] Detect real REM devices on RF network (`37:168270`)
- [x] Detect real DIS devices (`37:169161`)
- [x] Verify `22F1` command traffic from REM to FAN
- [ ] Configure binding for `37:168270` → `32:153289`
- [ ] Verify binding matches traffic (not showing as unmatched)
- [ ] Test binding suggestion from observed traffic
- [ ] Verify arbiter updates when REM buttons pressed
- [ ] Confirm state reconciliation after HA restart

##### Test prerequisites

- A known FAN device id (canonical `xx:xxxxxx` format)
- At least one REM device to bind
- Remote binding configured via the FAN-oriented config flow (or strict YAML import)
- Logging enabled for troubleshooting

##### What to validate (ordered)

1. **Binding resolution order**
   - Confirm explicit Extras binding is used when present.
   - Confirm `_get_bound_rem_device()` is only used as fallback.
   - Confirm unmatched REM traffic is correctly surfaced as diagnostics (but does not mutate persisted config).

2. **Command attribution correctness**
   - Press REM buttons for:
     - `Auto`
     - speed changes
     - `Away`
     - timer actions
   - Confirm the observed command is attributed to the correct FAN.

3. **Debounce / duplicate protection**
   - Confirm repeated packets do not create repeated state transitions.
   - Confirm `RQ` polling traffic is ignored.

4. **Arbiter synchronization (no command echo loops)**
   - Confirm a REM-originated action updates arbiter state.
   - Confirm Extras does not "echo" the same command back to the FAN.

5. **Conflict detection**
   - Validate that one REM cannot be assigned to multiple FANs.
   - Validate diagnostics/error handling when conflicts are present.

6. **Offline/online behavior**
   - With HA offline, confirm the physical REM still controls the FAN.
   - After HA comes online, confirm arbiter state converges toward the real-world observed state.

##### Observability checklist

During tests, capture:

- the effective binding map (per FAN)
- last-seen timestamps
- unmatched REM traffic counters
- arbiter effective mode/speed and any manual override state

##### Documentation updates (examples)

Update documentation with:

- a minimal example config snippet for one FAN / one REM
- an example for multiple REMs with roles (`primary`, `secondary`, `boost_only`)
- a short troubleshooting section:
  - "REM presses not reflected in HA"
  - "REM traffic unmatched"
  - "binding conflict detected"

## Status

**Last Updated:** March 2026

- **Implementation:** Phases 1-4 complete. Live hardware testing deferred.
- **Schema definition:** ✅ Complete in `docs/FAN_CONFIGURATION_SCHEMA_DRAFT.md`
- **Feature section:** ✅ Defined and persisted via `features.sensor_control.remote_binding`
- **Config flow integration:** ✅ Available under FAN-oriented configuration
- **YAML export:** ✅ Supported via `export_config_to_yaml()`
- **YAML import validation:** ✅ Registered validator in `remote_binding_yaml.py`
- **Documentation examples:** ✅ Complete in `docs/REMOTE_BINDING_EXAMPLES.md`

## Risks

- duplicate handling if both event-bus and direct-client messages are seen
- stale bindings if users replace hardware without updating config
- accidental cross-binding of one REM to multiple FAN devices
- future conflict with eventual native `ramses_rf` REM registration if the models differ

## Safeguards

- store bindings explicitly and validate uniqueness
- prefer direct-client live data when available
- keep one canonical command normalization path
- keep arbiter as the only HA-side policy authority

## Open questions for review

- Should phase 1 allow exactly one REM per FAN, or one primary plus optional extras?
- Should explicit Extras bindings override device-reported bindings unconditionally?
- Do you want unmatched observed REM traffic surfaced in the debugger UI immediately, or later?

## Decisions applied

- Remote binding should keep its own structured config section.
- Remote binding should be edited under a FAN-oriented configuration area, not as a separate top-level feature UX.
- Discovery from `ramses_cc` should be used as a hint source only, and not persisted unless explicitly accepted into config.
- Discovery candidates are not the only valid option, because external/manual devices must also remain possible.
- REM-aware naming such as `rem_id` is preferred over more generic field names where practical.
- Export uses strict YAML via `export_config_to_yaml()`.
- Import uses the framework validation registry (`register_config_validator()`) with per-feature validation.
