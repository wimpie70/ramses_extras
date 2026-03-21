# Fan Speed Arbitration - Implementation Plan

## Objective

Create a central framework-level fan speed arbitration layer so feature automations no longer send competing fan commands directly. Features should publish demand, and one arbiter should resolve the final device fan command.

## Why

Current CO2 and humidity automations both send commands directly. This causes command conflicts and makes future expansion harder for:

- CO2 severity-based boosts
- humidity balance and spike handling
- future temperature / VOC / PM / occupancy features
- future zone and valve-aware airflow calculation

## Architecture Decision

The arbitration engine belongs in the framework, not in `default`.

- `framework`: owns shared control policy and command dispatch
- `default`: may later expose shared diagnostic entities or services
- features: compute demand only, not final actuator policy

## Phase 1: Initial Framework Slice

### Deliverables

- Add a framework helper: `fan_speed_arbiter.py`
- Support shared singleton access via `hass.data`
- Support demand registration, clearing, resolution, and command dedupe
- Migrate current humidity and CO2 automations to use the arbiter
- Add focused unit tests for the helper and first integration points

### Initial policy

Use a simple highest-speed-wins policy:

- `fan_high` beats `fan_medium`
- `fan_medium` beats `fan_low`
- `fan_low` beats `fan_auto`
- If there are no active demands, resolve to `fan_auto`

This policy is intentionally simple and replaces fragile feature-to-feature override behavior.

## Demand Model

Each feature submits a demand with at least:

- `device_id`
- `feature_id`
- `source_id`
- `requested_speed`
- `priority`
- `reason`
- `metadata`

The model should be extensible for future fields like:

- `scope` (`device`, `indoor`, `outdoor`, `area`, `zone`)
- `severity`
- `zone_id`
- `area_id`
- `hold_until`
- valve openness / weighted airflow metadata

## Current Feature Mapping

### Humidity control

- dehumidify active -> request `fan_high`
- balance idle while enabled -> request `fan_low`
- paused for CO2 -> clear humidity demand
- switch off / inactive -> clear humidity demand

### CO2 control

- triggered without zones -> request `fan_medium`
- triggered with higher calculated level -> request `fan_medium` / `fan_high`
- inactive -> clear CO2 demand

## Phase 2: Better Policy Model

After the first slice is stable, move to a richer demand model:

- normalized severity per source
- tie-breaking by priority only where needed
- area/zone-aware aggregation
- valve-aware weighting
- per-device final score mapped to speed commands

## Diagnostics

The arbiter should expose enough state for future diagnostics:

- active demands per device
- resolved command per device
- winning feature/source
- last applied command
- last command reason

## Testing Strategy

### Unit tests

- speed normalization
- highest-speed resolution
- priority tie-breaking
- clearing one feature demand while preserving another
- command dedupe
- no-demand -> `fan_auto`

### Integration-oriented tests

- humidity stop no longer overrides CO2 medium demand
- humidity pause-for-CO2 clears humidity demand instead of forcing low
- CO2 demand resolution updates correctly when zones/sources change

## Coverage Target

Final implementation should keep total coverage above 85%.

Targeted tests are fine while iterating, but the final validation should include the broader project coverage gate.

## Migration Steps

1. Add framework arbiter helper
2. Route humidity automation through arbiter
3. Route CO2 automation through arbiter
4. Add unit tests and feature integration tests
5. Validate locally
6. Later extend demand model for zones and valves

## Open Decisions For Later

These do not block phase 1:

- exact weighting for multiple zones
- valve openness contribution formula
- hold-time / anti-flap behavior per source
- whether low-speed idle balance should eventually become `auto` for some devices
- diagnostic entities exposed through `default`
