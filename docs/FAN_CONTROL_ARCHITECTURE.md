# Fan Control Architecture

## Purpose

This document is the single source of truth for fan control behavior in `ramses_extras`.

It replaces the separate transport-monitoring and fan-speed-arbitration design notes with one consolidated architecture and implementation plan.

It covers:

- the current implementation
- the problems observed in current behavior
- the target architecture
- intended future behavior
- migration phases
- decisions that still need user input later

## Scope

This document covers fan-related control behavior for HVAC/FAN devices in `ramses_extras`, including:

- transport monitoring
- command dispatch
- fan speed arbitration
- card-initiated manual actions
- automation demands from features such as humidity and CO2 control
- future physical remote integration
- future zone and valve-aware control

It does not define unrelated feature logic.

## Architectural fit

This follows the `ramses_extras` architecture principles:

- features are feature-centric and compute their own intent
- shared control policy belongs in the framework
- the default feature may expose shared entities/services, but should not own shared control policy
- `ramses_cc` remains the communication and device-integration layer

Therefore:

- the arbiter belongs in `framework/helpers`
- transport/device liveness monitoring belongs in `framework/helpers`
- features publish demands/intents, not final device policy
- cards should not bypass the framework control model for normal fan actions

## Current implementation snapshot

### Transport monitor

Current implementation: `custom_components/ramses_extras/framework/helpers/transport_monitor.py`

Current behavior:

- per-device command-based liveness tracking
- when a command is sent, a timeout starts for that device
- when a reply is seen from that device, the timeout is cancelled and the device is marked online
- if no reply is seen before timeout, the device is marked offline
- a transport-state binary sensor exposes online/offline state to Home Assistant and cards

Recent correction:

- the monitor must listen to the live `ramses_cc` message stream via `coordinator.client.add_msg_handler(...)`
- HA bus `ramses_cc_message` may still exist as a fallback, but it is not the authoritative current path

### Fan speed arbiter

Current implementation: `custom_components/ramses_extras/framework/helpers/fan_speed_arbiter.py`

Current behavior:

- humidity and CO2 features can publish fan speed demands
- arbiter resolves one command from multiple demands
- current policy is simple highest-speed-wins with priority and update time tie-breaking
- when no demands remain, arbiter resolves to `fan_auto`
- arbiter checks transport availability before sending

### Command dispatch

Current implementation: `custom_components/ramses_extras/framework/helpers/ramses_commands.py`

Current behavior:

- direct packet sending goes through `ramses_cc`
- transport monitor is notified when commands are sent
- commands are blocked when transport monitoring is active and the device is marked unavailable
- command delivery and reply observation are not yet modeled as distinct state layers

### Current problem observed

Current user-facing behavior shows an architectural gap:

- card button presses can still send direct fan commands successfully
- feature automations continue to use the arbiter to resolve their desired state
- therefore a manual fan command can be quickly overwritten by automation re-evaluation

Example consequence:

- user presses `fan_low`
- command is sent successfully
- humidity control clears its demand or reevaluates
- arbiter resolves back to `fan_auto`
- device appears to ignore the button even though the command was transmitted

This is not a `ramses_cc` send-path failure. It is a control-model mismatch.

## Core architecture decision

The arbiter must become the single authority for effective fan-control state.

That means:

- all actors submit intent or demand to the arbiter
- only the arbiter resolves effective device behavior
- only one command application path should exist for effective fan mode changes
- manual card actions must become arbiter-managed manual override demands, not bypass commands
- future remote actions must also become arbiter inputs
- future zone/valve behavior must be resolved by the same control model

## Target control model

### Principle

There are three layers that must stay separate:

- desired state
- sent state
- confirmed state

This separation is necessary to support:

- offline handling
- retries or delayed application
- transport uncertainty
- physical remote changes
- future zone-aware coordination

### Actors that produce intent

The following should be modeled as control inputs:

- humidity control
- CO2 control
- HVAC fan card manual actions
- future physical remote actions
- future zone/valve coordination
- future features such as occupancy, VOC, PM, temperature strategy, schedules

These actors should not independently decide final device state.

### Control responsibilities

#### Features

Features are responsible for:

- sensing and computing feature-specific conditions
- publishing or clearing demand
- describing why they want a specific outcome
- reacting to resolved state when needed

Features are not responsible for:

- directly owning final device fan mode
- overriding other features ad hoc
- deciding global control policy

#### Arbiter

The arbiter is responsible for:

- storing active demands/intents
- storing manual override state
- resolving effective fan-control outcome
- later resolving zone/valve side effects
- deduplicating command application
- exposing diagnostics for why a result won

#### Transport monitor

The transport monitor is responsible for:

- observing whether the device appears responsive
- tracking global transport activity and per-device liveness
- informing the arbiter/sender whether a send is safe or unconfirmed
- helping distinguish offline devices from temporarily unconfirmed commands

The monitor should not own control policy.

#### Command sender

The command sender is responsible for:

- translating resolved outcome into `ramses_cc` commands
- sending commands
- updating sent-state bookkeeping
- reporting success/failure/timeout back into control state

## Demand and intent model

The demand model should evolve from simple speed requests toward a richer intent model.

### Current minimum fields

The current arbiter demand already contains:

- `feature_id`
- `source_id`
- `requested_speed`
- `priority`
- `reason`
- `metadata`
- `updated_at`

### Target fields

The target model should support:

- `device_id`
- `feature_id`
- `source_id`
- `intent_kind`
- `requested_speed` or future richer requested outcome
- `priority`
- `reason`
- `metadata`
- `scope`
- `zone_id`
- `area_id`
- `severity`
- `hold_until`
- `expires_at`
- `manual`
- `sticky`
- `origin` (`automation`, `card`, `remote`, `system`)

Not all of these fields need to be implemented immediately.

## Manual override model

### Decision

Manual actions should be represented as arbiter-managed override demands.

Manual override should not be implemented as:

- direct fan command bypassing the arbiter
- a global hidden switch sprinkled across features
- feature-specific ad hoc suppression logic

### Intended behavior

When a user presses a fan button on the card:

- the card submits a manual intent to the backend
- the backend creates or updates a manual override demand for that device
- the arbiter resolves the new effective state
- the command sender applies the resolved state if transport policy allows
- cards and diagnostics expose that the device is in manual mode

### Manual override semantics

Manual override should be:

- high priority
- explicit in diagnostics
- sticky for the current implementation when the user presses `low`, `medium`, or `high`
- configurable later so installations can choose sticky manual mode or a more passive mode that keeps automation calculations alive but ignored
- visible to all automations via arbiter state

### Effect on automations

When manual override is active:

- current implementation direction: automations should front-check control mode and stop applying control logic for that device
- this effectively disables the fan-control part of humidity and CO2 automations while sticky manual mode is active
- later this should become configurable so automations can optionally keep evaluating and publishing lower-priority background state without displacing manual override
- some automation classes may later support explicit exceptions, for example a CO2-related overrule or safety condition

This means the first implementation is intentionally strict and simple, while the long-term design remains more flexible.

### Exit from manual mode

Manual mode should end by one of the following strategies:

- explicit user action such as pressing `auto`
- expiry of a hold timer
- future remote action that changes effective mode
- future policy decision if a critical safety/control demand must supersede manual mode

Current implementation decision:

- pressing `auto` exits sticky manual mode and returns control to the arbiter's normal automatic resolution (`auto_by_extras` when features have demands, otherwise `auto_by_fan`)

Later this should become configurable.

## Control mode representation

The system should expose a coarse control-mode state per device so users, automations, and cards can see how control is currently being resolved.

### Initial control mode taxonomy

The first coarse states are:

- `manual_override`
- `auto_by_extras`
- `auto_by_fan`

These are intentionally coarse and stable enough for diagnostics and UI.

### Entity plan

The backend should expose a dedicated diagnostic entity for this state.

This entity is intended to:

- show `manual` clearly in Home Assistant and cards
- give automations a simple front-check input
- explain whether current control comes from the device itself or from `ramses_extras`

This should later become configurable in how it is used by automations and UI, but the existence of the entity itself is useful immediately.

### Why an entity matters

Debug-state dictionaries are helpful for development, but they are not enough for the real product behavior.

An actual entity gives:

- visibility in HA dashboards
- easier condition checks for automation logic
- a future frontend integration point
- better observability when troubleshooting conflicting control behavior

## Remote-device integration model

Future physical remote actions should be treated as first-class control inputs.

### Intended behavior

When a real remote device changes mode or speed:

- detect the remote-originating change from the `ramses_cc` message stream
- for the near-term design, treat it the same as manual override
- map it into an arbiter intent
- update resolved state and diagnostics
- reflect the new state in cards/entities
- avoid split-brain between physical and virtual control paths

### Current limitation

For multi-fan installations, mapping a remote to the correct fan is not yet fully defined.

Near-term expectation:

- support the behavior model in the architecture
- defer the full implementation until fan-to-remote association is defined clearly enough

Long-term direction:

- remote behavior may eventually be defined primarily in `ramses_extras`, not only through FAN binding

### Why this matters

If physical remotes are not modeled as arbiter inputs, the system can diverge:

- device state changes physically
- cards still believe a different state is authoritative
- automations may immediately fight the remote action

Using the arbiter as the shared authority prevents this.

## Zone and valve-aware future model

The current arbiter only resolves a final fan command.

In the future, it should become the control point for combined fan and airflow-distribution behavior.

### Intended future behavior

A manual or automated intent may imply more than fan speed. For example:

- zone airflow preference
- valve opening/closing
- weighted contribution from multiple spaces
- protection against over-ventilating or under-ventilating inactive areas

Therefore future button actions should eventually express high-level intent, not only raw fan speed.

Examples:

- manual boost
- manual low ventilation
- away mode
- auto mode
- zone priority mode

The arbiter should later translate these into:

- fan speed
- valve positions
- zone distribution decisions
- any required suppression or coordination logic

## Monitoring and offline behavior

### Current role of monitoring

The transport monitor tells us whether:

- the global transport appears active
- a specific device recently replied after commands
- a send should be skipped because the device is currently considered unavailable

### Target role of monitoring

The monitoring layer should inform policy, not replace it.

The arbiter/sender should be able to reason about:

- desired state
- pending desired state while device is offline
- last sent state
- last confirmed state
- whether a command is blocked, queued, retried, or awaiting confirmation

### Intended behavior when device is offline

When a user or automation requests a change while the device is offline:

- do not silently discard the intent
- store the desired state if policy says it should survive
- expose that the request is pending or unconfirmed
- re-evaluate when the device becomes available again

The exact retry/queueing policy can evolve later, but the state model should allow it.

## Resolved-state model

The arbiter should eventually expose, per device:

- active demands
- active manual override, if any
- resolved desired outcome
- last sent command
- last confirmed state
- whether current state is pending/unconfirmed
- winning source and reason
- transport availability snapshot

This is valuable for:

- card UI
- diagnostics
- future debugger tooling
- understanding why a device is in a given mode

## Intended user-visible behavior

### Card button behavior

Target behavior:

- pressing a card button should change the device state via arbiter-managed manual mode
- that state should persist according to manual-mode policy
- it should not be immediately overwritten by humidity or CO2 automation
- the card should show whether the state is manual, automatic, pending, or offline

### Automation behavior

Target behavior:

- humidity and CO2 features compute demands independently
- they do not directly fight one another
- they do not overwrite manual mode unless explicitly permitted by policy
- when manual mode ends, automatic control resumes from the active demands already known to the arbiter

Current implementation direction:

- sticky manual mode disables the fan-control side of automations for that device
- later this behavior should be configurable
- later specific override exceptions may be allowed

### Offline behavior

Target behavior:

- offline status is accurate
- commands are not treated as confirmed only because they were attempted
- user can distinguish between desired and confirmed state
- reconnecting can allow re-evaluation or reapplication of desired state

## Migration plan

### Phase 1: Documentation consolidation

- create this canonical document
- reduce old monitor/arbiter docs to pointers to this document
- use this document for future implementation decisions

### Phase 2: Close the current control-model gap

- route HVAC card manual fan actions through the arbiter instead of direct command bypass
- add a first manual override concept in the arbiter
- make humidity and CO2 features respect manual override
- add an initial control-mode entity for diagnostics and UI visibility
- preserve current transport safety checks

Expected outcome:

- button presses no longer appear to fail because they are not immediately overwritten by automation

### Phase 3: Improve arbiter state model

- add explicit manual-override state
- add desired vs sent vs confirmed tracking
- add diagnostics for winning source, pending state, and transport-aware reasoning

### Phase 4: Remote integration

- listen for physical remote actions from the live `ramses_cc` message stream
- map remote actions into arbiter intents
- keep cards and backend synchronized

### Phase 5: Zone and valve-aware control

- extend the demand model for area/zone scope
- introduce valve-aware and zone-aware resolution
- let manual actions express higher-level intent, not only raw speed

## What should not happen

The following should be avoided:

- card buttons sending normal fan-mode changes outside the arbiter
- separate features owning final fan mode independently
- transport monitor directly deciding control policy
- implicit hidden disabling of automations without shared state
- assuming sent command equals confirmed state

## Near-term implementation recommendation

The best next implementation step is:

- add arbiter-managed manual override for HVAC card fan actions
- update automations to respect manual override
- keep transport monitoring as the send-safety and confirmation input

This addresses the current user-visible problem while preserving the architecture needed for future zones, valves, and remotes.

## Open decisions that will need user input later

These do not block the documentation and initial manual-override slice, but they will need explicit decisions later:

- how manual mode should become configurable after the first sticky implementation
- whether some automation classes may override manual mode under defined conditions
- exact representation of desired/sent/confirmed state in entities or diagnostics
- retry policy for pending commands after reconnect
- how physical remote actions should interact with existing manual override state
- exact zone/valve weighting model

## Related implementation files

- `custom_components/ramses_extras/framework/helpers/fan_speed_arbiter.py`
- `custom_components/ramses_extras/framework/helpers/transport_monitor.py`
- `custom_components/ramses_extras/framework/helpers/ramses_commands.py`
- `custom_components/ramses_extras/features/humidity_control/automation.py`
- `custom_components/ramses_extras/features/co2_control/automation.py`
- `custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js`
- `custom_components/ramses_extras/features/default/platforms/binary_sensor.py`

## Status

Current status:

- transport monitoring is implemented and recently corrected to use the live `ramses_cc` message stream
- basic fan arbitration is implemented
- manual card actions are being moved toward arbiter-managed sticky manual override
- a control-mode entity is part of the near-term implementation direction
- future remote and zone support are intentionally planned, not yet implemented
