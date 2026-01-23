# Framework Foundation

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 5.

The framework provides reusable components, standardized patterns, and automated
lifecycle management so features can focus on domain logic.

## Framework architecture overview

The framework is layered:

- Base classes
- Helpers
- Services
- Card system + asset deployment

## Setup framework

The setup framework (in `framework/setup/`) orchestrates initialization phases
in a strict order and manages dependencies.

Key modules:

- `entry.py` (main entry + pipeline orchestrator)
- `features.py` (feature loading and instance creation)
- `devices.py` (device discovery/coordination + cleanup)
- `cards.py` (asset deployment and card registration)
- `utils.py`, `yaml.py` (helpers and YAML-to-config-flow bridge)

## Base classes

- `ExtrasBaseEntity` (`framework/base_classes/base_entity.py`)
  - Base for custom entities.
- `ExtrasBaseAutomation` (`framework/base_classes/base_automation.py`)
  - Base for Python automation classes.
- Platform entity classes (`framework/base_classes/platform_entities.py`)
  - `ExtrasSensorEntity`, `ExtrasSwitchEntity`, `ExtrasNumberEntity`, `ExtrasBinarySensorEntity`.
- `RamsesBaseCard` (`framework/www/ramses-base-card.js`)
  - Shared base for shipped Lovelace cards.

## Helper modules

Common helper areas:

- `framework/helpers/config/` configuration management patterns
- `framework/helpers/entity/` entity lifecycle helpers, including:
  - `SimpleEntityManager`
  - `DeviceFeatureMatrix`
- `framework/helpers/service/` service registration/validation
- `framework/helpers/commands/` command registry
- `framework/helpers/device/` device filtering + helpers

## Framework services

- Path management (`framework/helpers/paths.py` + `framework/www/paths.js`)
- Message system:
  - WebSocket command registration
  - ramses_cc message listeners + event patterns

## Usage examples

The architecture doc contains examples for:

- configuration management
- platform entities
- service framework

## Contents

- Framework architecture overview
- Setup framework
- Base classes
- Helper modules
- Framework services
- Usage examples

Back to: [Home](Home.md)
Prev: [Feature System](Feature-System.md)
Next: [Device Feature Management](Device-Feature-Management.md)
