# Hello World optimization TODO

## Progress

- [x] Inspect existing hello_world implementation + tests
- [x] Simplify hello_world platforms (use framework patterns, reduce duplication)
- [x] Simplify hello_world services + websocket commands (use framework helpers where sensible)
- [ ] Ensure docstrings/comments are consistent (Sphinx `:param` for public Python APIs; JS file comments where needed)
- [ ] Update `docs/RAMSES_EXTRAS_ARCHITECTURE.md` to reflect the optimized hello_world pattern
- [ ] Verify tests (hello_world) then run `make local-ci`

## Big-step workflow (each step should pass CI)

### 1) Platform cleanup + refactor

- Goal: reduce feature-specific boilerplate in `platforms/*.py`, relying on:
  - `framework.helpers.platform.PlatformSetup`
  - `framework.base_classes.platform_entities.*`
- Fast test:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world/test_hello_world_platforms.py --cov=custom_components.ramses_extras.features.hello_world --cov-fail-under=0"`

### 2) Services + WebSocket cleanup

- Goal: keep Hello World logic thin; use `EntityHelpers` templates from `const.py` (single source of truth)
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world/test_hello_world_services.py --cov=custom_components.ramses_extras.features.hello_world --cov-fail-under=0"`
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world/test_hello_world_websocket_commands.py --cov=custom_components.ramses_extras.features.hello_world --cov-fail-under=0"`

### 3) Automation + feature factory sanity

- Goal: remove unnecessary state duplication; keep feature factory lightweight
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world/test_hello_world_automation.py --cov=custom_components.ramses_extras.features.hello_world --cov-fail-under=0"`
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world/test_hello_world_init.py --cov=custom_components.ramses_extras.features.hello_world --cov-fail-under=0"`

### 4) Docs update

- Update `docs/RAMSES_EXTRAS_ARCHITECTURE.md`:
  - Document Hello World as the reference minimal-feature pattern
  - Emphasize `FEATURE_DEFINITION` as single source of truth
  - Point to `PlatformSetup` usage to keep feature code small

### 5) Full verification

- Feature test suite:
- Feature test suite:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hello_world"`
- Full local CI:
  - `bash -c "source ~/venvs/extras/bin/activate && make local-ci"`
