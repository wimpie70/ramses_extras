# Development Guide

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 10.

You are welcome to contribute to this integration. If you are missing support
for a device, or have a nice card that you like to share, please do.

Also see the repository "Contributing" information for environment setup.

## Coding standards and conventions

### File responsibilities

- Root platform files: thin Home Assistant integration wrappers that forward to
  feature implementations
- Feature files: feature-specific business logic and entity implementations
- Framework files: reusable utilities and base classes
- Frontend files: JavaScript/HTML assets for UI components

### Naming conventions

- Feature names: `snake_case` (e.g. `humidity_control`)
- Entity classes: `PascalCase` (often feature-prefixed)
- Helper functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Import patterns

```python
# Feature imports (relative)
from ...automation import HumidityAutomationManager

# Framework imports (absolute)
from custom_components.ramses_extras.framework.helpers.automation import ExtrasBaseAutomation
from custom_components.ramses_extras.framework.helpers.entity import EntityHelpers

# Root imports (absolute)
from custom_components.ramses_extras.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
```

Framework components should generally use absolute imports from features to
avoid module resolution edge cases.

## Development workflow

Recommended workflow is "framework-first":

1. Start with framework components for config, entities, and services.
2. Use platform entity base classes for HA integration.
3. Leverage brand customization and service frameworks.
4. Implement feature-specific logic last.

For a reference implementation, start from the `hello_world` feature (it
exercises entities, services, automations, and UI).

## Testing structure

Tests are grouped by type:

```text
tests/
├── managers/
├── helpers/
├── frontend/
├── config_flow/
├── startup/
└── test_registry.py
```

## Contents

- Coding standards and conventions
- Development workflow
- Testing structure

Back to: [Home](Home.md)
Prev: [Frontend Architecture](Frontend-Architecture.md)
Next: [Debugging and Troubleshooting](Debugging-and-Troubleshooting.md)
