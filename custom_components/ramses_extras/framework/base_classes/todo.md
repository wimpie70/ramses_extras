# Framework / Base Classes - Optimization TODO

Targets:

- `base_automation.py`
- `base_entity.py`
- `platform_entities.py`
- `base_card_manager.py`

## Tasks

- [ ] Map responsibilities and dependencies of each base class (who calls what)
- [ ] Identify duplication between `base_entity.py` and `platform_entities.py`
- [ ] Check for over-complicated lifecycle flows in `base_automation.py` (simplify without behavior changes)
- [ ] Verify type hints and reduce `Any` usage where safe
- [ ] Confirm base classes have no feature-specific assumptions
