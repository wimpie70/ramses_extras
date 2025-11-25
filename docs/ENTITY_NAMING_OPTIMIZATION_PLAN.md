# Entity Naming Optimization Plan

## Overview

This document outlines the optimization plan to simplify entity naming through automatic format detection based on device_id position, eliminate template conversion duplication, and create a unified entity naming system.

## Simplified Entity Naming Approach

### Universal Entity Format

**Format**: `{entity_type}.{template}` where template can contain:

**Pattern Detection**:
- **CC Format** (device_id prefix): `{device_id}_{specific_identifier}`
  - Example: `number.32_153289_param_7c00`
  - Example: `sensor.29_099029_temp`

- **Extras Format** (device_id suffix): `{entity_name}_{device_id}`
  - Example: `sensor.indoor_absolute_humidity_32_153289`
  - Example: `switch.dehumidify_32_153289`
  - Example: `number.relative_humidity_minimum_32_153289`

### Automatic Format Detection

**Detection Logic**:
1. **Device ID Recognition**: Match patterns like `12_345678` or `12:345678`
2. **Position Analysis**:
   - If device_id appears at the beginning → CC format
   - If device_id appears at the end → Extras format
3. **Context Parsing**: Use surrounding pattern to determine intent

### Issues Resolved

1. **Simplified Template Logic**: Single template system with automatic format detection
2. **Consistent Entity Recognition**: All entities parsed using same logic
3. **No Manual Specification**: System determines format automatically
4. **Reduced Complexity**: No need to specify cc or extras conventions

## Solution Architecture

### 1. Simplified EntityHelpers System

#### Universal parse_entity_id() Method

**Signature:**
```python
def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    # Returns: (entity_type, entity_name, device_id)
```

**Automatic Detection Logic:**
1. **Extract Device ID**: Match `12_345678` or `12:345678` patterns
2. **Determine Position**:
   - Device ID at beginning → CC format: `(entity_type, specific_identifier, device_id)`
   - Device ID at end → Extras format: `(entity_type, entity_name, device_id)`
3. **Parse Accordingly**: Return structured components based on detected format

#### Simplified generate_entity_name_from_template() Method

**Universal Template System:**
```python
def generate_entity_name_from_template(
    entity_type: str,
    template: str,
    **kwargs
) -> str:
    """Generate entity name using template with automatic format detection.

    Template can contain device_id in any position - format is detected automatically.
    """
    # Simple placeholder replacement
    entity_name = template.format(**kwargs)
    return f"{entity_type}.{entity_name}"
```

**Template Examples:**
```python
# Extras format template
"dehumidify_{device_id}" → "switch.dehumidify_32_153289"

# CC format template
"{device_id}_param_{param_id}" → "number.32_153289_param_7c00"

# Universal template - position doesn't matter
"indoor_absolute_humidity_{device_id}" → "sensor.indoor_absolute_humidity_32_153289"
```

### 2. Feature-Centric Template Strategy

#### Leverage Existing Feature Templates
```python
# features/humidity_control/const.py - ALREADY EXISTS
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "entity_template": "dehumidify_{device_id}",
        # ... other config
    }
}

# features/default/const.py - ALREADY EXISTS
DEFAULT_SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "entity_template": "indoor_absolute_humidity_{device_id}",
        # ... other config
    }
}

# Framework CC templates (for dynamic entities) - TO BE CREATED
CC_TEMPLATES = {
    "param": "{device_id}_param_{param_id}",
    # ... other cc patterns
}
```

**Key Points:**
- Use existing feature const templates (no new ENTITY_TEMPLATES needed)
- Maintain feature-centric design
- Templates use `{device_id}` placeholders for automatic format detection

### 3. EntityManager Integration

Update EntityManager to use simplified helpers:

```python
class EntityManager:
    async def _scan_feature_entities(self, feature_id, feature_config, existing_entities):
        # Use universal EntityHelpers.parse_entity_id for all entities
        # Use simple feature templates for entity generation
        # No distinction needed between CC/Extras - handled automatically
```

## Implementation Plan

### Phase 1: Simplified EntityHelpers (Priority 1)

1. **Update parse_entity_id()** with automatic format detection
   - Detect device_id position (prefix vs suffix)
   - Parse entity based on detected format
   - Return structured components regardless of format

2. **Simplify generate_entity_name_from_template()**
   - Universal template system
   - Automatic placeholder replacement
   - No manual format specification needed

3. **Add device_id recognition utility**
   - Match patterns: `12_345678` or `12:345678`
   - Determine position within entity name
   - Extract components accordingly

### Phase 2: Update Template System (Priority 1)

1. **Standardize feature templates**
   - Use simple placeholders: `{device_id}`, `{param_id}`, etc.
   - Position determines format automatically
   - No complex convention switching

2. **Consolidate template definitions**
   - Single source of truth for entity templates
   - Easy to understand and maintain
   - Automatic format detection on use

### Phase 3: EntityManager Updates (Priority 2)

1. **Update EntityManager** to use simplified helpers
2. **Remove format-specific logic** - handled automatically
3. **Use unified template system** for all entity generation
4. **Simplify entity recognition** - no owner distinction needed

### Phase 4: Documentation Updates (Priority 2)

1. **Update RAMSES_EXTRAS_ARCHITECTURE.md** with simplified naming approach
2. **Update ENTITYMANAGER_API_REFERENCE.md** with unified methods
3. **Document automatic detection** logic

### Phase 5: Testing & Validation (Priority 3)

1. **Create comprehensive tests** for automatic detection
2. **Test both CC and Extras formats** work correctly
3. **Validate device_id position** detection
4. **Integration tests** with mixed entity scenarios

## Feature-Centric Architecture Preservation

**Key Principle**: Maintain feature-specific code within feature folders

- **Feature const files**: Keep feature-specific entity templates and configurations
- **Framework helpers**: Centralized naming logic with automatic format detection
- **EntityManager**: Uses simplified helpers, respects feature boundaries
- **Test files**: Updated to reflect automatic detection approach

## Benefits

1. **Simplified Logic**: Single template system with automatic format detection
2. **No Manual Specification**: System determines format based on device_id position
3. **Reduced Complexity**: No need to distinguish between CC/Extras conventions
4. **Maintainability**: Single source of truth for entity naming logic
5. **Error Prevention**: Automatic detection prevents format mismatches
6. **Future-Proof**: Easy to add new templates without convention complexity

## Files Referencing Entity Naming (Scattered Code Inventory)

### Feature Files (Feature-Centric Design)
**Template Definitions:**
- `features/humidity_control/const.py` - HUMIDITY_SWITCH_CONFIGS with entity_template
- `features/default/const.py` - DEFAULT_SENSOR_CONFIGS with entity_template
- `features/humidity_control/automation.py` - References state_mappings and entity templates

**Platform Implementations:**
- `features/humidity_control/platforms/sensor.py` - Uses name_template and entity_template
- `features/humidity_control/platforms/switch.py` - Uses name_template for entity naming
- `features/humidity_control/platforms/number.py` - Uses name_template for entity naming
- `features/humidity_control/platforms/binary_sensor.py` - Uses name_template for entity naming
- `features/default/platforms/sensor.py` - Uses name_template for entity naming

### Framework Files
- `framework/helpers/entity/core.py` - EntityHelpers with get_entity_template methods
- `framework/base_classes/base_entity.py` - Base entity class using name_template
- `framework/helpers/common/validation.py` - validate_entity_template method

### Test Files
- `tests/helpers/test_entity_naming_simple.py` - Has both CC and Extras template patterns
- `tests/managers/test_humidity_automation.py` - References entity naming for testing

### Documentation Files (Updated)
- `docs/ENTITY_NAMING_OPTIMIZATION_PLAN.md` - This document (simplified approach)
- `docs/RAMSES_EXTRAS_ARCHITECTURE.md` - Updated entity naming section
- `docs/ENTITYMANAGER_API_REFERENCE.md` - Updated EntityManager integration

## Update Priority

### Phase 1: Framework Helpers (High Priority)
- `framework/helpers/entity/core.py` - Add automatic format detection
- `framework/base_classes/base_entity.py` - Update to use automatic detection

### Phase 2: Feature Files (High Priority)
- Feature automation files - Update to use automatic detection
- Feature platform files - Simplify template usage

### Phase 3: Test Files (Medium Priority)
- `tests/helpers/test_entity_naming_simple.py` - Update test patterns
- `tests/managers/test_humidity_automation.py` - Update entity references

### Phase 4: CC Templates (Low Priority)
- Create framework CC templates for dynamic entities
- Integrate with existing feature templates

## Migration Strategy

1. **Fresh Start**: No backward compatibility needed - new system from ground up
2. **Automatic Detection**: System recognizes existing entity patterns automatically
3. **Template Simplification**: Move to simple placeholder-based templates
4. **Validation**: Entity naming validation prevents format errors

This plan simplifies the entity naming system while preserving the feature-centric architecture through automatic format detection based on device_id position.
