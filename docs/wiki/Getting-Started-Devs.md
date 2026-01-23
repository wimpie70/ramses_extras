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

- Identify the feature you want to change (or create a new one).
- Implement components as needed:
  - automation
  - services
  - platforms (entities)
  - cards (frontend)
  - websocket commands
  - feature-specific config flow step (optional)
- Run tests locally.

## Adding a new feature

See: [Feature System](Feature-System.md)

Back to: [Home](Home.md)
