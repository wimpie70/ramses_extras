# Framework Reorganization Plan

## Overview

The framework currently has an architectural inconsistency where automation base classes are mixed with helpers, while entity base classes are properly separated. This reorganization plan addresses this by splitting `automation/base.py` to achieve consistency.

## Current Structure (Inconsistent)

```
framework/
├── base_classes/
│   ├── base_entity.py       # ✅ Entity base classes properly separated
│   └── __init__.py
├── helpers/
│   ├── entity/
│   │   ├── core.py          # ✅ Entity helpers properly separated
│   │   ├── manager.py       # ✅ Entity manager properly separated
│   │   └── __init__.py
│   ├── automation/
│   │   ├── base.py          # ❌ Mixed: base class + helpers
│   │   └── __init__.py
```

## Target Structure (Consistent)

```
framework/
├── base_classes/
│   ├── base_entity.py       # Entity base classes
│   ├── base_automation.py   # Automation base class (NEW)
│   └── __init__.py          # Updated exports
├── helpers/
│   ├── entity/
│   │   ├── core.py          # Entity utilities
│   │   ├── manager.py       # Entity orchestration
│   │   └── __init__.py
│   ├── automation/
│   │   ├── core.py          # Automation utilities (NEW)
│   │   └── __init__.py      # Updated exports
```

## File Changes Required

### 1. Create `framework/base_classes/base_automation.py`

**Content to move from `helpers/automation/base.py`:**
- `ExtrasBaseAutomation` class (abstract base class)
- All abstract methods and base class functionality
- Remove helper functions (move to `core.py`)

**Key changes:**
- Update imports to reference new helper location
- Keep all base class functionality intact

### 2. Create `framework/helpers/automation/core.py`

**Content to move from `helpers/automation/base.py`:**
- `_get_required_entities_from_feature()` function
- `_singularize_entity_type()` function
- Any other utility functions not part of the base class

**Key changes:**
- Make functions available for import by base_automation.py
- Update any internal imports as needed

### 3. Update `framework/base_classes/__init__.py`

**Current:**
```python
from .base_entity import ExtrasBaseEntity
__all__ = ["ExtrasBaseEntity"]
```

**Updated:**
```python
from .base_entity import ExtrasBaseEntity
from .base_automation import ExtrasBaseAutomation

__all__ = ["ExtrasBaseEntity", "ExtrasBaseAutomation"]
```

### 4. Update `framework/helpers/automation/__init__.py`

**Current:**
```python
from .base import ExtrasBaseAutomation
__all__ = ["ExtrasBaseAutomation"]
```

**Updated:**
```python
from .core import _get_required_entities_from_feature, _singularize_entity_type
__all__ = ["_get_required_entities_from_feature", "_singularize_entity_type"]
```

### 5. Update Import in `features/humidity_control/automation.py`

**Current:**
```python
from custom_components.ramses_extras.framework.helpers.automation.base import (
    ExtrasBaseAutomation,
)
```

**Updated:**
```python
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)
```

### 6. Update Internal Imports in `base_automation.py`

**Add imports for helper functions:**
```python
from ..automation.core import _get_required_entities_from_feature, _singularize_entity_type
```

## Implementation Steps

### Phase 1: File Creation
1. Create `framework/base_classes/base_automation.py` with `ExtrasBaseAutomation` class
2. Create `framework/helpers/automation/core.py` with helper functions
3. Update `__init__.py` files as specified

### Phase 2: Import Updates
1. Update `humidity_control/automation.py` import
2. Update internal imports in `base_automation.py`
3. Verify all imports work correctly

### Phase 3: Testing
1. Run existing tests to ensure functionality preserved
2. Test humidity control automation specifically
3. Verify no import errors or missing dependencies

### Phase 4: Documentation Updates
1. Update `RAMSES_EXTRAS_ARCHITECTURE.md` to reflect new directory structure
2. Update any other documentation references
3. Remove old `framework/helpers/automation/base.py` file
4. Commit changes with clear description

## Benefits

✅ **Architectural Consistency**: All base classes in `base_classes/`, all helpers in `helpers/`
✅ **Clear Separation**: Base classes vs. utility functions properly separated
✅ **Better Organization**: Related functionality grouped logically
✅ **Maintainability**: Easier to find and modify components
✅ **Future-Proof**: Consistent pattern for adding new base classes

## Risk Assessment

**Low Risk**: This is primarily a file reorganization with import updates. The functionality remains identical.

**Testing Required**:
- Import validation across all affected files
- Humidity control automation functionality
- Any other automations that might be added in the future

## Files to Create

1. `custom_components/ramses_extras/framework/base_classes/base_automation.py`
2. `custom_components/ramses_extras/framework/helpers/automation/core.py`

## Files to Modify

1. `custom_components/ramses_extras/framework/base_classes/__init__.py`
2. `custom_components/ramses_extras/framework/helpers/automation/__init__.py`
3. `custom_components/ramses_extras/features/humidity_control/automation.py`
4. `ramses_extras/docs/RAMSES_EXTRAS_ARCHITECTURE.md`

## Files to Delete

1. `custom_components/ramses_extras/framework/helpers/automation/base.py`
