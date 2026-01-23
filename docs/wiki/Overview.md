# Overview

## What is Ramses Extras?

Ramses Extras is a **feature-centric** Home Assistant integration that extends the `ramses_cc` integration with additional entities, automation, and UI components.

The overall goal is to keep functionality modular:

- Features are self-contained.
- The framework provides reusable building blocks.
- The Home Assistant integration layer stays thin.

## Core benefits

- Feature-centric design: each feature is self-contained with its own automation, services, entities, and UI.
- Framework foundation: reusable base classes/helpers used by all features.
- Clean HA integration: standard HA platforms and type-safe entities.
- Modular architecture: add new features using established patterns.
- Real-time updates: WebSocket APIs and message listeners for immediate UI updates.

## Key concepts

- Features: self-contained modules providing specific functionality.
- Framework: reusable base classes, helpers, and utilities.
- Platforms: Home Assistant integration layer for entities and services.
- Cards: JavaScript-based UI components for Lovelace.
- Config flow: Home Assistant configuration mechanism.

## Current features (high level)

- Default feature
  - Shared/common entities and WebSocket endpoints used by other features.
- HVAC Fan Card
  - Advanced Lovelace card for FAN monitoring/control.
- Humidity Control
  - Humidity-based automation and entities.
- Sensor Control
  - Central sensor mapping/override system for Humidity Control + HVAC Fan Card.
- Ramses Debugger
  - Debugging tools: traffic analyser, log explorer, packet log explorer.

## Next

- Users: [Getting Started (Users)](Getting-Started-Users.md)
- Developers: [Getting Started (Developers)](Getting-Started-Devs.md)
- Architecture: [System Architecture](System-Architecture.md)

Back to: [Home](Home.md)
