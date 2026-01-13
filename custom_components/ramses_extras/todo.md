# Ramses Extras - Architecture / Optimization TODO

This file tracks *big picture* cleanup and refactoring work across the integration.

## Scope

- Framework: `./framework/todo.md`
- Features:
  - `./features/default/todo.md`
  - `./features/humidity_control/todo.md`
  - `./features/sensor_control/todo.md`
  - `./features/hvac_fan_card/todo.md`

## Big picture

- [ ] Review integration boundaries (framework vs features vs top-level integration)
- [ ] Identify feature-specific code currently living in the framework and propose moves
- [ ] Identify duplicate or over-complicated framework utilities and propose simplifications
- [ ] Confirm service/websocket/entity/automation responsibility boundaries are consistent across the codebase

## Notes / findings

- `hello_world` appears to be example code and still contains a TODO in its config schema.
- Framework feature-specific leakage found:
  - `framework/helpers/websocket_base.py` applies `sensor_control` overrides inside the framework (imports `features.sensor_control.resolver`).
  - `framework/helpers/websocket_base.py` hardcodes feature constant prefixes (`HELLO_WORLD_`, `HUMIDITY_CONTROL_`, `HVAC_FAN_CARD_`, `SENSOR_CONTROL_`) when scraping const modules.
  - `framework/helpers/config/validation.py` defines `HUMIDITY_CONTROL_VALIDATION_RULES` and `TEMPERATURE_CONTROL_VALIDATION_RULES` (likely should live in features).
