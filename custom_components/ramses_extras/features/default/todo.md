# Default feature optimization TODO

## Progress

- [x] Inspect existing default feature implementation + tests
- [x] Fix outstanding lint/type/test warnings (Python)
- [x] Confirm integration services/websocket contracts for default feature are correct
- [x] Improve docstrings/types across default feature modules
- [ ] Verify tests (default) then run `make local-ci`

## Big-step workflow (each step should pass CI)

### 1) Baseline inspection + quick cleanup

- Goal: no behavior changes; clean up obvious issues:
  - remove dead code / unused imports
  - ensure logs are actionable and not too noisy
  - ensure entity naming + unique_id patterns are consistent
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/default"`
  - `bash -c "source ~/venvs/extras/bin/activate && ruff check ."`

### 2) Docstrings + typing

- Goal: improve maintainability:
  - add module/class/function docstrings where helpful
  - clarify inputs/outputs and side-effects
  - ensure type hints are accurate (use built-in generics: `dict`, `list`, etc.)
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && mypy custom_components/ramses_extras"` (if configured locally)
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q --no-cov tests/features/default"`

### 3) Entity + service/websocket boundaries

- Goal: confirm Default feature is cleanly separated and acts as the common base:
  - entities created only when needed
  - service calls validate inputs and error clearly
  - websocket commands are minimal + robust

### 4) Full verification

- Full local CI:
  - `bash -c "source ~/venvs/extras/bin/activate && make local-ci"`
