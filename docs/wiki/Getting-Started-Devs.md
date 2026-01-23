# Getting Started (Developers)

## Goals of this page

- Explain the feature-centric architecture.
- Help you locate the correct place to implement changes.
- Provide the high-level development workflow.

## Understand the structure

High-level layers:

- Home Assistant integration wrapper (entry point, config flow, services)
- Features (self-contained modules)
- Framework (shared base classes/helpers)
- `ramses_cc` (device communication)

See: [System Architecture](System-Architecture.md)

## Quick start (developer workflow)

1. Understand the structure:
   - Features → Framework → HA platforms
2. Enable features:
   - Features are loaded dynamically; enable the ones you need in the integration options.
3. Implement components as needed:
   - automation
   - services
   - entities + HA platforms (sensor/switch/number/binary_sensor)
   - cards (frontend)
   - websocket commands (for cards and integrations)
   - feature-specific config flow step (optional)
4. Run tests locally.

See also:

- [Feature System](Feature-System.md)
- [Framework Foundation](Framework-Foundation.md)

## Adding a new feature

See: [Feature System](Feature-System.md)

Back to: [Home](Home.md)
