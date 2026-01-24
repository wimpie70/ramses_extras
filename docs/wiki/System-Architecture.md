# System Architecture

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 3.

## High-level architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Home Assistant                          │
├────────────────────────────────────────────────────────────┤
│  Ramses Extras Integration (Thin HA Wrapper)               │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │   Feature 1  │ │   Feature 2  │ │   Feature N  │        │
│  │ (Humidity)   │ │ (HVAC Card)  │ │   (Custom)   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
├────────────────────────────────────────────────────────────┤
│  Framework Foundation (Base Classes, Helpers, Managers)    │
├────────────────────────────────────────────────────────────┤
│  ramses_cc Integration (Device Communication)              │
└────────────────────────────────────────────────────────────┘
```

## Core design principles

### Feature-centric organization

- Each feature is self-contained (automation, services, entities, config, cards).
- Features are modular: enabling a feature does not require enabling all others.
- A **default** feature provides shared/common functionality.

### Framework foundation

- Shared base classes for entities and automations.
- Reusable helpers for setup, config flows, registry operations, etc.

### Python-based automations (not YAML)

- Automations are implemented as Python classes.
- They listen to ramses_cc events and device state changes.

### ramses_cc integration hooks

- Broker access for device communication.
- Event subscriptions (real-time message handling).
- Shared constants and schemas.

### Home Assistant integration

- Standard HA platforms (sensor/switch/binary_sensor/number).
- Type-safe entity implementations.

## Directory structure (overview)

At a high level, the repo is split into:

- `custom_components/ramses_extras/` integration entry points and platform files
- `custom_components/ramses_extras/features/` feature-centric modules
- `custom_components/ramses_extras/framework/` reusable foundation

## Integration flow (setup pipeline)

The main setup pipeline is orchestrated by the setup framework in
`custom_components/ramses_extras/framework/setup/`.

### Setup phases (summary)

- Early entry setup (async_setup_entry)
  - Initializes `hass.data` state
  - Watches the entity registry for new ramses_cc entities

- Main setup pipeline
  - Load feature definitions + import enabled feature platform modules
  - Discover devices and coordinate `async_setup_platforms` with ramses_cc
  - Setup WebSocket integration
  - Deploy Lovelace card assets (versioned) + expose frontend config
  - Register services
  - Validate entities + cleanup orphaned devices
  - Create and start feature instances (automation lifecycle)

## ramses_cc integration architecture

Ramses Extras depends on ramses_cc being available and ready.

- It will wait/retry if ramses_cc has not finished loading.
- Device discovery prefers direct broker access and falls back to registry-based
  extraction.

### Device binding requirement (FAN-related features)

For FAN-related features you typically need the Ramses RF **bound REM** mapping.
See:

- [Getting Started (Users)](Getting-Started-Users.md)

## Contents

- High-level architecture
- Core design principles
- Directory structure
- Integration flow
- `ramses_cc` integration architecture

Back to: [Home](Home.md)
Prev: [Getting Started (Developers)](Getting-Started-Devs.md)
Next: [Feature System](Feature-System.md)
