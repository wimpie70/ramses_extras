# Framework / Frontend (www) - Optimization TODO

Targets:

- `ramses-base-card.js`
- `card-translations.js`
- `card-services.js`
- `logger.js`
- `paths.js`
- message broker utilities

## Tasks

- [x] Review `RamsesBaseCard` responsibilities and reduce any feature-specific coupling
- [x] Review translation loading/caching patterns for consistency and minimal duplication
- [x] Investigate `cards_enabled` latch timing TODO in `ramses-base-card.js`
- [x] Review websocket command wrapper helpers (consistency, error handling)
- [x] Confirm build/entity-id helpers are pure and accept explicit inputs

## Notes / findings

- `ramses-base-card.js` currently contains a TODO about `cards_enabled` latch timing.
