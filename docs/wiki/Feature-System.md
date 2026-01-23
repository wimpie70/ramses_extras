# Feature System

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 4.

## How features work

Each feature is a **self-contained module** that provides specific functionality.
Features follow a consistent structure and can be enabled/disabled independently.

The `hello_world` feature is intended as a template for new development.

## Feature lifecycle

1. Registration: feature is listed in `AVAILABLE_FEATURES` in the root `const.py`.
2. Discovery: config flow discovers available features.
3. Activation: user enables/disables features via the integration options.
4. Creation: the framework imports the feature module and creates a feature instance.
5. Registration: feature platforms are registered with Home Assistant.
6. Operation: the feature runs independently (entities, services, automations, cards).

## Current features (summary)

### Default

- Purpose: shared/common functionality used by other features.
- Provides: base entities and common WebSocket commands.

### Humidity Control

- Purpose: humidity-based ventilation control.
- Automations: Python-based (no YAML automation rules).

### Sensor Control

- Purpose: central place to decide which entities provide sensor inputs per device.
- Scope: indoor/outdoor temperature, humidity, CO₂, and derived absolute humidity.

#### Resolver boundaries and precedence (high level)

Sensor Control is intentionally limited to selecting which existing entities provide
sensor inputs. It does not create new entities and it does not contain device-specific
automation logic.

The resolver applies precedence per device and per metric:

1. Compute internal baseline entity ID from internal templates.
2. Apply user overrides.
3. Missing/invalid external entities fail closed (treated as unavailable).

Absolute humidity is handled as a hybrid:

- Sensor Control stores inputs (temperature + RH, or direct abs humidity entity).
- The default feature provides resolver-aware absolute humidity sensors.

### HVAC Fan Card

- Purpose: advanced Lovelace card for FAN monitoring/control.
- Uses `ramses_extras/get_entity_mappings` to resolve entity IDs.

### Ramses Debugger

- Purpose: debugging tools for protocol analysis.
- Provides: traffic analyser, log explorer, packet log explorer.

## Contents

- How features work
- Feature lifecycle
- Current features
- Feature structure pattern
- Feature components
- Adding new features

Back to: [Home](Home.md)
Prev: [System Architecture](System-Architecture.md)
Next: [Framework Foundation](Framework-Foundation.md)
