# Feature Catalog

This page provides a high-level catalog of Ramses Extras features, what they provide,
and how they are typically configured.

Note: configuration is generally done via the Home Assistant UI (options flow).

## Default feature

- Purpose:
  - Common/shared functionality used by other features.
- Provides:
  - Shared WebSocket endpoints.
  - Shared framework entities/utilities.
- Configuration:
  - Always enabled (not listed in the feature selection UI).

## HVAC Fan Card

- Purpose:
  - A Lovelace UI for monitoring and controlling FAN devices.
- Provides:
  - Lovelace card + editor.
  - Uses WebSocket entity mappings to avoid hardcoding entity IDs.
- Configuration:
  - Enable the feature in the Ramses Extras options flow.
  - Select the FAN devices you want to enable it for.
  - Add the card via the Lovelace UI.
- Prerequisites:
  - FAN-related features typically require a **bound REM** mapping (see
    [Getting Started (Users)](Getting-Started-Users.md)).

## Humidity Control

- Purpose:
  - Humidity-based ventilation control.
- Provides:
  - Entities (sensors/switches/etc. depending on device + configuration).
  - Python-based automation (no YAML automations).
- Configuration:
  - Enable the feature in the Ramses Extras options flow.
  - Select the devices to enable it for.

## Sensor Control

- Purpose:
  - Central place to resolve which entities provide sensor inputs per device
    (temperature/humidity/CO₂/absolute humidity).
- Provides:
  - Resolver logic used by other features.
- Configuration:
  - Enable the feature in the Ramses Extras options flow.
  - Select the devices to enable it for.

## Ramses Debugger

- Purpose:
  - Advanced debugging tools for protocol analysis and troubleshooting.
- Provides:
  - Lovelace cards (UI-only feature):
    - traffic analyser
    - log explorer
    - packet log explorer
  - WebSocket endpoints used by those cards.
- Configuration:
  - Enable the feature in the Ramses Extras options flow.
  - Create a dedicated Lovelace dashboard page and add the debugger cards.

## Hello World (developer example)

- Purpose:
  - Reference implementation for developers.
- Provides:
  - An example feature showing the typical structure (entities/services/automations/UI).
- Configuration:
  - Enable it in the options flow when you want to use it for development.

## Screenshots

For now, this page does not include screenshots.

Back to: [Home](Home.md)
Prev: [Overview](Overview.md)
Next: [System Architecture](System-Architecture.md)
