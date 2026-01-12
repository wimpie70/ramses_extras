# HVAC Fan Card optimization TODO

## Progress

- [ ] Inspect existing hvac_fan_card implementation + tests
- [ ] Fix outstanding lint/test warnings (JS + Python)
- [ ] Align translations usage with framework translator (no hardcoded language strings)
- [ ] Simplify card templates to accept translated labels (keep template functions pure)
- [ ] Verify tests (hvac_fan_card) then run `make local-ci`

## Big-step workflow (each step should pass CI)

### 1) Card JS cleanup (safety-first)

- Goal: no behavior changes; clean up obvious issues:
  - remove unused variables / fix ESLint warnings
  - ensure inline handlers reference the correct card instance
  - keep device_id normalization consistent (`32:123456` vs `32_123456`)
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && npm test --silent"`
  - `bash -c "source ~/venvs/extras/bin/activate && pytest -q tests/features/hvac_fan_card/test_hvac_fan_card_init.py"`

### 2) Translations

- Goal: use the base card translation system (`this.t()`) everywhere:
  - remove ad-hoc language checks in templates
  - rely on `features/hvac_fan_card/www/hvac_fan_card/translations/*.json`
- Fast tests:
  - `bash -c "source ~/venvs/extras/bin/activate && npm test --silent"`

### 3) Template API consistency

- Goal: template functions accept explicit inputs (data + labels), not `hass`
  - avoid business logic in templates
  - keep formatting centralized

### 4) Full verification

- Full local CI:
  - `bash -c "source ~/venvs/extras/bin/activate && make local-ci"`
