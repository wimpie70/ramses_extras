# Framework - Optimization TODO

This file tracks refactoring and cleanup for the framework layer.

## Parts

- Base classes: `./base_classes/todo.md`
- Helpers: `./helpers/todo.md`
- Frontend (cards): `./www/todo.md`

## Cross-cutting

- [x] Define/confirm framework public APIs (what features are allowed to call) — section 5.7 in `docs/RAMSES_EXTRAS_ARCHITECTURE.md` now covers all helpers features import, plus the upstream private-data compat shims
- [x] Reduce duplication across helpers (common patterns in entity/config/websocket)
- [x] Ensure framework is feature-agnostic (no feature-specific naming, defaults, or logic)
- [x] Review typing, error handling, and logging patterns for consistency — upstream private attrs now accessed via public-first getattr fallbacks; remaining shims documented in section 5.7
