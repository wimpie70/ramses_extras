# AI Agent Instructions and Guidelines for ramses_extras

Project-specific rules for the `ramses_extras` codebase. Cross-repo rules
(venvs, test invocation, typing, PR/commit conventions) live in the global
rules file.

## Architecture

- **Feature-centric architecture**: The framework provides base classes,
  helpers, and reusable code. The default feature is always enabled and is a
  good place for common entities, servicecalls, etc.
- **Architecture changes**: Before making architecture changes, first read
  `docs/RAMSES_EXTRAS_ARCHITECTURE.md`.

## Test Environments (Home Assistant instances)

- **`hass` (port 8123)**: the normal dev HA instance, used for day-to-day
  development and debugging.
- **`ha-sim` (port 8124)**: a dedicated simulation HA instance running in
  Docker. The `tools/ha_sim_test` tool makes use of the device simulator
  feature and runs against this instance.
- **Production HA**: runs on a separate server. Do not point dev tools or
  tests at it.

## Backward Compatibility

- Backward compatibility is not required for now, **except** for the
  `get`/`set`/`update` `fan_param` methods/functions/servicecalls, since this
  is WIP on `ramses_cc`.
