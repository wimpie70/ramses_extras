# Entity Management

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 7.

## SimpleEntityManager

`SimpleEntityManager` encapsulates:

- `DeviceFeatureMatrix`
- entity diffing (what to add/remove)
- direct registry operations

It is responsible for ensuring the entity set in Home Assistant matches the
current device/feature configuration.

## Entity creation logic

Required entities are calculated from the device/feature matrix. At a high
level:

- The enabled combinations are enumerated.
- For each combination, entity IDs are generated from feature definitions.

## Entity validation

On startup, the manager validates consistency:

- Current entities (what exists now)
- Required entities (what should exist)

Then it computes:

- Extra entities: exist but shouldn’t
- Missing entities: should exist but don’t

And it performs cleanup + creation to reconcile.

## Entity registration

When entities are created/removed, operations happen directly in the Home
Assistant entity registry.

Entity creation uses:

- the domain from the `entity_id` prefix
- `unique_id` derived from the `entity_id`
- platform `ramses_extras`

## Contents

- SimpleEntityManager
- Entity creation logic
- Entity validation
- Entity registration

Back to: [Home](Home.md)
Prev: [Device Feature Management](Device-Feature-Management.md)
Next: [Home Assistant Integration](Home-Assistant-Integration.md)
