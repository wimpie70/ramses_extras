# Humidity Control feature optimization TODO

## Progress

- [x] Inspect existing humidity_control implementation + tests
- [x] Fix outstanding lint/type/test warnings (Python)
- [x] Confirm service/websocket boundaries and entity creation rules
- [x] Improve docstrings/types across humidity_control modules
- [ ] Verify tests (humidity_control) then run `make local-ci`

## Big-step workflow (each step should pass CI)

### 1) Baseline inspection + quick cleanup

- Goal: no behavior changes; clean up obvious issues:
  - remove dead code / unused imports
  - ensure logs are actionable and not too noisy
  - ensure entity naming + unique_id patterns are consistent
  - ensure automations only subscribe to required events
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/humidity_control"`
  - `bash -c "source ~/venvs/extras/bin/activate && ruff check ."`

### 2) Docstrings + typing

- Goal: improve maintainability:
  - add module/class/function docstrings where helpful
  - clarify inputs/outputs and side-effects
  - ensure type hints are accurate (use built-in generics: `dict`, `list`, etc.)
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && mypy custom_components/ramses_extras"` (if configured locally)
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/humidity_control"`

### 3) Entity + service/websocket boundaries

- Goal: keep Humidity Control feature clean and modular:
  - entities created only when feature enabled + device eligible
  - services validate inputs and error clearly
  - websocket commands minimal + robust
  - avoid duplicated logic with Default feature (reuse helpers where possible)

### 4) Full verification

- Full local CI:
  - `bash -c "source ~/venvs/extras/bin/activate && make local-ci"`
