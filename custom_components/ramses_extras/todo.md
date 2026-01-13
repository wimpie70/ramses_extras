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
- [x] Identify feature-specific code currently living in the framework and propose moves
- [ ] Identify duplicate or over-complicated framework utilities and propose simplifications
- [ ] Confirm service/websocket/entity/automation responsibility boundaries are consistent across the codebase

## Notes / findings

- `hello_world` is example/template code.
- Resolved framework feature-specific leakage:
  - `framework/helpers/websocket_base.py` no longer applies `sensor_control` overrides inside the framework.
  - `framework/helpers/websocket_base.py` no longer hardcodes feature constant prefixes when scraping const modules.
  - `framework/helpers/config/validation.py` no longer defines feature-specific validation rule constants.
