# Framework / Helpers - Optimization TODO

Major areas:

- `entity/` (entity ID generation, entity lookup, entity manager)
- `config/` + `config_flow.py` (option schemas, validation)
- `websocket_base.py` (WS command registration and dispatch)
- `ramses_commands.py` + `commands/registry.py` (command send/registry)
- `paths.py` (feature/module path helpers)
- `platform.py` (platform setup helpers)
- `brand_customization/` (brand detection/customizers)

## Tasks

- [ ] Identify duplicated validation helpers between `helpers/common/validation.py` and `helpers/config/validation.py`
- [ ] Review `helpers/entity/core.py` vs `helpers/entity/simple_entity_manager.py` for overlap and simplification opportunities
- [ ] Review `websocket_base.py` for feature-specific leakage and reduce surface area
- [ ] Review config schema patterns for consistency (feature config vs integration options)
- [ ] Review error handling patterns (what exceptions are caught vs allowed to bubble)

## Notes / findings

- `websocket_base.py` contains feature-specific behavior:
  - Applies `sensor_control` overrides (imports `features.sensor_control.resolver`).
  - Scrapes const module attributes using hardcoded prefixes (`HELLO_WORLD_`, `HUMIDITY_CONTROL_`, `HVAC_FAN_CARD_`, `SENSOR_CONTROL_`).
- `config/validation.py` contains feature-specific constants (`HUMIDITY_CONTROL_VALIDATION_RULES`, `TEMPERATURE_CONTROL_VALIDATION_RULES`).
