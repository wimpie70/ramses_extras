# Sensor Control feature optimization TODO

## Progress

- [x] Inspect existing sensor_control implementation + tests
- [x] Fix outstanding lint/type/test warnings (Python)
- [ ] Confirm resolver behavior and mapping precedence is well-defined
- [ ] Improve docstrings/types across sensor_control modules
- [ ] Verify tests (sensor_control) then run `make local-ci`

## Big-step workflow (each step should pass CI)

### 1) Baseline inspection + quick cleanup

- Goal: no behavior changes; clean up obvious issues:
  - remove dead code / unused imports
  - ensure logs are actionable and not too noisy
  - ensure resolver output is stable and predictable
  - ensure mapping keys are consistent across device types
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/sensor_control"`
  - `bash -c "source ~/venvs/extras/bin/activate && ruff check ."`

### 2) Docstrings + typing

- Goal: improve maintainability:
  - add module/class/function docstrings where helpful
  - clarify inputs/outputs and side-effects
  - ensure type hints are accurate (use built-in generics: `dict`, `list`, etc.)
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && mypy custom_components/ramses_extras"` (if configured locally)
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/sensor_control"`

### 3) Resolver + boundaries

- Goal: keep Sensor Control focused on resolving sensor sources:
  - clear precedence order (explicit config overrides > derived > internal)
  - deterministic mapping output for cards/features
  - avoid duplicating Default/Humidity Control logic

### 4) Full verification

- Full local CI:
  - `bash -c "source ~/venvs/extras/bin/activate && make local-ci"`
