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

The setup framework (in `custom_components/ramses_extras/framework/setup/`) orchestrates initialization phases
in a strict order and manages dependencies.

Key modules:

- `entry.py` (main entry + pipeline orchestrator)
- `features.py` (feature loading and instance creation)
- `devices.py` (device discovery/coordination + cleanup)
- `cards.py` (asset deployment and card registration)
- `utils.py`, `yaml.py` (helpers and YAML-to-config-flow bridge)

## Base classes

- `ExtrasBaseEntity` (`custom_components/ramses_extras/framework/base_classes/base_entity.py`)
  - Base for custom entities.
- `ExtrasBaseAutomation` (`custom_components/ramses_extras/framework/base_classes/base_automation.py`)
  - Base for Python automation classes.
- Platform entity classes (`custom_components/ramses_extras/framework/base_classes/platform_entities.py`)
  - `ExtrasSensorEntity`, `ExtrasSwitchEntity`, `ExtrasNumberEntity`, `ExtrasBinarySensorEntity`.
- `RamsesBaseCard` (`custom_components/ramses_extras/framework/www/ramses-base-card.js`)
  - Shared base for shipped Lovelace cards.

## Helper modules

Common helper areas:

- `custom_components/ramses_extras/framework/helpers/config/` configuration management patterns
- `custom_components/ramses_extras/framework/helpers/entity/` entity lifecycle helpers, including:
  - `SimpleEntityManager`
  - `DeviceFeatureMatrix`
- `custom_components/ramses_extras/framework/helpers/service/` service registration/validation
- `custom_components/ramses_extras/framework/helpers/commands/` command registry
- `custom_components/ramses_extras/framework/helpers/device/` device filtering + helpers

## Framework services

- Path management (`custom_components/ramses_extras/framework/helpers/paths.py` + `custom_components/ramses_extras/framework/www/paths.js`)
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
