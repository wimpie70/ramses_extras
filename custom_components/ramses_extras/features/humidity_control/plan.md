# Humidity spike + zone support plan

## Goal

Extend the current humidity balancing design so a ventilation device can also react to fast local moisture spikes such as showers, while keeping feature boundaries aligned with the existing architecture.

This plan assumes:

- spike triggering uses **absolute humidity only**
- every `area_sensor` must provide both **temperature** and **relative humidity**
- direct absolute humidity input is **not** supported for `area_sensors`
- spike handling uses periodic re-evaluation instead of a fixed timeout
- when **Balance** is enabled, humidity spikes from additional configured sensors/zones should also participate in control decisions
- when **Balance** is disabled, manual override behaviour is intentionally left conservative for now
- visibility is important from the start, so **phase-2 observability is included immediately**
- some systems may later expose real ventilation zones, so the design must not block future zone-aware control

## Architecture guardrails

- [ ] Keep `sensor_control` as the **source-selection** feature
- [ ] Keep `humidity_control` as the **automation/decision** feature
- [ ] Keep derived absolute humidity entity creation in the **default feature**
- [ ] Avoid introducing parallel config registries outside existing feature config structures
- [ ] Keep the HVAC fan card consuming the same resolver/websocket data model as other features

## Desired end state

- [ ] A FAN device can monitor multiple humidity sources relevant to ventilation
- [ ] Extra room/area sources can trigger temporary high ventilation on sudden absolute humidity rises
- [ ] The trigger reason and active source are visible in entities and on the HVAC fan card
- [ ] The automation periodically re-evaluates active spike control and applies the then-current best action
- [ ] The design remains compatible with future true ventilation-zone support

## Feature split

### `sensor_control`

Owns:

- [ ] definition of additional `area_sensors` for a FAN device
- [ ] mapping of each additional source to:
  - [ ] temperature entity
  - [ ] humidity entity
  - [ ] or direct absolute humidity entity
- [ ] metadata for display, such as source label / area name / role
- [ ] future extension point for actual ventilation-zone metadata

Does **not** own:

- [ ] spike detection timing/state
- [ ] fan commands
- [ ] balancing decisions

### `default`

Owns:

- [ ] creation of derived absolute humidity sensors for configured extra sources
- [ ] a consistent naming model for extra absolute humidity entities
- [ ] shared absolute humidity calculation behaviour

### `humidity_control`

Owns:

- [ ] balancing logic using indoor/outdoor effective humidity values
- [ ] spike detection across additional configured sources
- [ ] temporary high-fan activation for spike events
- [ ] periodic re-evaluation handling for spike stop conditions
- [ ] status/diagnostic entities or attributes showing which source currently drives control

## Proposed configuration model

### `sensor_control`

Keep the existing primary indoor/outdoor absolute humidity replacement model
separate from the additional area-trigger model.

- [ ] existing `abs_humidity_inputs` continues to drive the primary indoor/outdoor
  effective absolute humidity sensors
- [ ] add a separate per-device list for additional area-trigger sources

Suggested working name:

- [ ] `area_sensors`

Per area sensor, store:

- [ ] `source_id`
- [ ] `label`
- [ ] optional `zone_id` for a future real ventilation zone link
- [ ] `enabled`
- [ ] `temperature_entity`
- [ ] `humidity_entity`
- [ ] `spike_rise_percent`
- [ ] `spike_window_minutes`
- [ ] `check_interval_minutes`

Rules:

- [ ] an area sensor is eligible for spike detection only when it can produce
  absolute humidity
- [ ] derived abs humidity requires both temp and RH inputs
- [ ] no RH-only fallback path
- [ ] no direct-abs input path for `area_sensors`
- [ ] invalid area sensors fail closed and do not participate in automation
- [ ] each area sensor must provide `temperature_entity` + `humidity_entity`

## Entity model

### Additional absolute humidity entities

Create visible entities from the start for each configured area sensor.

Suggested shape:

- [ ] `sensor.absolute_humidity_<source_id>_{device_id}`
- [ ] or another naming pattern consistent with current default-feature entity conventions

Each area sensor entity should expose:

- [ ] current absolute humidity value
- [ ] source label
- [ ] source device FAN id
- [ ] that it is derived from temp + RH
- [ ] raw input entities used for calculation
- [ ] optional future `zone_id`

### Humidity control diagnostics

Add enough visibility to understand behaviour without reading logs.

Potential additions:

- [ ] active trigger source attribute on `binary_sensor.dehumidifying_active_{device}`
- [ ] active control mode attribute (`balance`, `spike_boost`, `idle`)
- [ ] trigger abs humidity value
- [ ] trigger delta / rate-of-rise summary
- [ ] current stop-check interval / next re-evaluation
- [ ] optional future dedicated diagnostic sensor for active source

## Automation behaviour

### Balance mode

- [ ] Existing indoor/outdoor balancing remains the baseline decision path
- [ ] When Balance is enabled, additional configured `area_sensors` are also
  evaluated for spikes
- [ ] A spiking area sensor can escalate control to temporary `fan_high`

### Spike detection

Use absolute humidity only.

An area sensor can trigger when:

- [ ] current abs humidity rises by at least `delta_gm3`
- [ ] and/or relative humidity rises by at least configured `spike_rise_percent`
- [ ] within a configured time window
- [ ] area sensor is valid and enabled
- [ ] optional outdoor comparison increases confidence / influences duration

Questions to finalize during implementation:

- [ ] whether spike activation should use percent rise only or percent rise plus a minimum abs delta
- [ ] whether outdoor comparison is required or advisory for activation
- [ ] whether activation should require both RH rise and abs rise, or use RH rise as trigger and abs/outdoor as the decision gate

### Periodic re-evaluation / stop conditions

- [ ] Enter spike-boost state when an area sensor spike is detected
- [ ] Re-evaluate active spike control every configured interval
- [ ] Do not restore a cached previous fan state
- [ ] If the area remains too humid and outdoor air is still beneficial, remain on high
- [ ] If the area has recovered enough, or outdoor abs humidity is now worse, stop spike boost
- [ ] When spike boost stops, fall back to the current balance/manual logic outcome at that moment

### Manual mode assumptions for now

- [ ] If Balance is ON, spike sources participate in control decisions
- [ ] If Balance is OFF, do not add new aggressive override behaviour yet
- [ ] Future work may let real remotes explicitly overrule Extras control (`low`, `mid`, `high`, `auto`)

## Outdoor comparison

Use outdoor comparison as part of the decision model.

- [ ] compare local area-sensor abs humidity against outdoor abs humidity
- [ ] use this to refine confidence and stop conditions
- [ ] avoid overcomplicating the first implementation by requiring too many gates before a shower spike can trigger

## HVAC fan card

### Main card

- [ ] do not overload the main card with every area-sensor value by default
- [ ] show the currently active trigger area sensor when spike control is active
- [ ] show the relevant values for that active area sensor

### Settings / sensor sources panel

- [ ] list all configured `area_sensors` coming from `sensor_control`
- [ ] include their effective absolute humidity entities
- [ ] show whether each area sensor is direct-abs or derived
- [ ] keep the same resolver-driven source panel pattern already used for CO₂ and other metrics

## Zone-aware future support

Treat current `area_sensors` as compatible with future real zone support.

- [ ] avoid naming/config that assumes only one bathroom/shower area sensor exists
- [ ] allow a future mapping from `area_sensor` to a real ventilation `zone_id`
- [ ] keep automation evaluation able to work per-area-sensor now and per-zone later
- [ ] document which pieces are placeholders until real zone-capable systems are implemented

## Implementation milestones

### 1. Finalize data model

- [ ] choose exact config keys for `area_sensors`
- [ ] choose exact entity naming for area-sensor absolute humidity sensors
- [ ] define diagnostic attributes/entities for active trigger area-sensor visibility
- [ ] define re-evaluation settings for active spike control

### 2. Extend `sensor_control`

- [ ] keep existing primary `abs_humidity_inputs` behaviour intact
- [ ] add config schema / config flow support for `area_sensors`
- [ ] update resolver output to expose additional area-sensor metadata
- [ ] ensure websocket payloads include configured area-sensor summaries for the card
- [ ] fail closed on incomplete or invalid area-sensor definitions

### 3. Extend default-feature absolute humidity support

- [ ] create absolute humidity sensors for configured area sensors from temp+RH inputs
- [ ] reuse shared calculation helpers
- [ ] expose area-sensor metadata as attributes
- [ ] add tests for area-sensor temp+RH variants

### 4. Extend `humidity_control`

- [ ] add spike evaluation state machine
- [ ] evaluate all configured `area_sensors` on updates
- [ ] add periodic re-evaluation scheduling for active spike control
- [ ] expose active trigger area sensor and mode in entity attributes
- [ ] keep current balance behaviour intact when no source spikes

### 5. Extend HVAC fan card

- [ ] show active trigger area sensor + values during spike control
- [ ] show all configured `area_sensors` in the settings/source panel
- [ ] keep card data fully resolver/websocket driven
- [ ] add frontend tests for area-sensor listing / active trigger rendering

### 6. Verification and docs

- [ ] add targeted tests for resolver, abs humidity entities, automation timing, and card rendering
- [ ] update architecture docs if boundaries change materially
- [ ] add/update diagrams for balance + spike flow
- [ ] run `make local-ci`

## Open design questions

- [ ] exact config UX for managing multiple `area_sensors` in config flow
- [ ] whether area-sensor entities live under default feature or humidity_control namespaces
- [ ] exact stop condition thresholds for “humidity has recovered enough”
- [ ] how much outdoor comparison should gate immediate shower detection
- [ ] whether spike state needs a dedicated binary sensor separate from `dehumidifying_active`
- [ ] how to represent real ventilation zones once hardware support is added

## Definition of done

- [ ] multiple additional `area_sensors` can be configured for a FAN
- [ ] each usable area sensor has a visible derived absolute humidity entity
- [ ] spike detection uses absolute humidity only
- [ ] active spike control uses periodic re-evaluation instead of fixed timeout restore
- [ ] active trigger area sensor is visible in backend entities and on the HVAC fan card
- [ ] card settings/source panel shows all configured sensor-control `area_sensors`
- [ ] plan items are checked off during implementation
- [ ] local CI passes
