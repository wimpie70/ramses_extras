# Framework - Optimization TODO

This file tracks refactoring and cleanup for the framework layer.

## Parts

- Base classes: `./base_classes/todo.md`
- Helpers: `./helpers/todo.md`
- Frontend (cards): `./www/todo.md`

## Cross-cutting

- [ ] Define/confirm framework public APIs (what features are allowed to call)
- [ ] Reduce duplication across helpers (common patterns in entity/config/websocket)
- [ ] Ensure framework is feature-agnostic (no feature-specific naming, defaults, or logic)
- [ ] Review typing, error handling, and logging patterns for consistency
