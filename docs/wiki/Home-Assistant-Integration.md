# Home Assistant Integration

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 8.

## Platform integration architecture

Ramses Extras uses a **thin wrapper** approach in the root platform files.

- Root platform modules (`sensor.py`, `switch.py`, `number.py`, `binary_sensor.py`)
  act as dispatchers.
- Feature platform modules implement the real business logic.

High level:

- Root platform loops through registered feature setup functions.
- Default feature always loads.
- Other features load only if enabled.

## Entity naming system

Entity IDs appear in two main formats:

- CC format: device id at the beginning (e.g. `number.32_153289_param_3f`).
- Extras format: device id at the end (e.g. `sensor.indoor_absolute_humidity_32_153289`).

The framework uses detection patterns to interpret the device id position.

## Configuration flow integration

The config flow includes a generic matrix-style feature/device selection.
Features can also provide their own config step(s) via feature-specific
`config_flow.py` helpers.

High-level flow:

- Select a feature.
- Choose devices for that feature.
- Optionally route to feature-specific config steps.
- Confirm entity changes; entities are created/removed via `SimpleEntityManager`.
- Reload entry to apply.

## Service integration

- Integration-level services are defined in `services.yaml`.
- Feature services live in each feature’s `services.py`.
- Services are registered dynamically based on enabled features.
- WebSocket APIs are used for real-time UI components.

## Contents

- Platform integration architecture
- Entity naming system
- Configuration flow integration
- Service integration

Back to: [Home](Home.md)
Prev: [Entity Management](Entity-Management.md)
Next: [Frontend Architecture](Frontend-Architecture.md)
