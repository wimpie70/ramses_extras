# Entity Naming Optimization Plan

## Overview

This document outlines the comprehensive optimization plan to simplify entity naming through automatic format detection based on device_id position, eliminate template conversion duplication, and create a unified entity naming system. The goal is to achieve a **single template system with automatic format detection** that works seamlessly for both CC and Extras entity formats.

## Core Problem Solved

**Before**: Manual format specification required
- `generate_entity_name_from_config()` - Extras format only
- `generate_entity_name_from_template()` - CC format only
- Need to specify "cc" vs "extras" convention manually
- Complex template logic with format switching

**After**: Automatic format detection
- Single universal template system
- No manual format specification needed
- Automatic detection based on device_id position
- Simplified, maintainable code structure

## Simplified Entity Naming Approach

### Universal Entity Format

**Format**: `{entity_type}.{template}` where templates use automatic format detection

**Pattern Recognition Logic**:
- **CC Format** (device_id prefix): `{device_id}_{specific_identifier}`
  - Example: `number.32_153289_param_7c00`
  - Example: `sensor.29_099029_temp`
  - **Detection**: Device ID appears at the beginning

- **Extras Format** (device_id suffix): `{entity_name}_{device_id}`
  - Example: `sensor.indoor_absolute_humidity_32_153289`
  - Example: `switch.dehumidify_32_153289`
  - Example: `number.relative_humidity_minimum_32_153289`
  - **Detection**: Device ID appears at the end

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

### 1. Enhanced EntityHelpers System

#### Core Implementation Classes

```python
# New automatic detection methods in framework/helpers/entity/core.py
class EntityHelpers:
    """Enhanced entity helpers with automatic format detection."""

    @staticmethod
    def _extract_device_id(entity_name: str) -> tuple[str | None, int]:
        """Extract device ID and return (device_id, position)."""
        # Pattern: 12_345678 or 12:345678
        pattern = r'(\d+[:_]\d+)'
        match = re.search(pattern, entity_name)
        if match:
            device_id = match.group(1).replace(':', '_')  # Convert : to _
            position = match.start()  # Position in entity name
            return device_id, position
        return None, -1

    @staticmethod
    def _detect_format_by_position(position: int, entity_name: str) -> str:
        """Detect format based on device_id position."""
        if position <= len(entity_name) * 0.3:  # First 30% → CC format
            return "cc"
        else:  # Last portion → Extras format
            return "extras"
```

#### Universal parse_entity_id() Method

**Enhanced Signature:**
```python
def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse entity ID with automatic format detection.

    Returns: (entity_type, entity_name, device_id) or None if parsing fails
    """
```

**Automatic Detection Logic:**
1. **Extract Components**: Split `entity_id` into `entity_type.entity_name`
2. **Device ID Detection**: Use regex to find `12_345678` or `12:345678` patterns
3. **Position Analysis**:
   - Beginning position (≤30%) → CC format: `(entity_type, identifier, device_id)`
   - End position → Extras format: `(entity_type, name_part, device_id)`
4. **Return Structured Data**: Always return `(entity_type, parsed_name, device_id)`

#### Universal generate_entity_name_from_template() Method

**Enhanced Universal Template System:**
```python
def generate_entity_name_from_template(
    entity_type: str,
    template: str,
    **kwargs
) -> str:
    """Generate entity name using universal template with automatic format detection.

    Key Innovation: Template position determines format automatically.

    Examples:
    - "dehumidify_{device_id}" → Extras format: "switch.dehumidify_32_153289"
    - "{device_id}_param_{param_id}" → CC format: "number.32_153289_param_7c00"
    - "indoor_absolute_humidity_{device_id}" → Extras format: "sensor.indoor_absolute_humidity_32_153289"
    """
    # Replace all placeholders
    entity_name = template

    # Handle device_id replacement with automatic format detection
    if "device_id" in kwargs and "{device_id}" in template:
        device_id = kwargs["device_id"]
        if "{device_id}" in template:
            # Detect format by template position
            device_pos = template.find("{device_id}")
            if device_pos == 0:
                # device_id at beginning → CC format
                entity_name = template.format(**kwargs)
                return f"{entity_type}.{entity_name}"
            else:
                # device_id at end → Extras format
                entity_name = template.format(**kwargs)
                return f"{entity_type}.{entity_name}"

    # Simple placeholder replacement for other patterns
    entity_name = template.format(**kwargs)
    return f"{entity_type}.{entity_name}"
```

**Template Pattern Examples:**
```python
# Extras Format Templates (device_id at end)
"dehumidify_{device_id}" → "switch.dehumidify_32_153289"
"indoor_absolute_humidity_{device_id}" → "sensor.indoor_absolute_humidity_32_153289"
"relative_humidity_minimum_{device_id}" → "number.relative_humidity_minimum_32_153289"

# CC Format Templates (device_id at beginning)
"{device_id}_param_{param_id}" → "number.32_153289_param_7c00"
"{device_id}_temp" → "sensor.32_153289_temp"

# Mixed Templates (position determines format)
"temp_{device_id}" → "sensor.temp_32_153289"  # Extras format
"{device_id}_fan_speed" → "number.32_153289_fan_speed"  # CC format
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

### Phase 1: Enhanced EntityHelpers Core (Priority 1) ✅ COMPLETED
### Phase 1.5: Enhanced Implementation Approach (Priority 1) ✅ COMPLETED

**Objective**: Implement automatic format detection in core EntityHelpers class

**Implementation Steps**:
1. ✅ **Add `_extract_device_id()` method**
   ```python
   @staticmethod
   def _extract_device_id(entity_name: str) -> tuple[str | None, int]:
       # Use regex pattern r'(\d+[:_]\d+)' to match device_id
       # Return (device_id, position) or (None, -1) if not found
   ```

2. ✅ **Add `_detect_format_by_position()` method**
   ```python
   @staticmethod
   def _detect_format_by_position(position: int, entity_name: str) -> str:
       # Return "cc" if position ≤ 30% of entity_name length
       # Return "extras" otherwise
   ```

3. ✅ **Update `parse_entity_id()` for automatic detection**
   - Integrate device ID extraction and position detection
   - Handle both CC and Extras formats seamlessly
   - Return consistent `(entity_type, parsed_name, device_id)` tuple

4. ✅ **Update `generate_entity_name_from_template()` for universal templates**
   - Support automatic format detection based on template structure
   - Handle `{device_id}` placeholder in any position
   - Maintain backward compatibility with existing templates

### Phase 2: Feature Template Consolidation (Priority 1) ✅ COMPLETED

**Objective**: Standardize and update all feature templates to use automatic detection

**Implementation Steps**:
1. ✅ **Update Humidity Control Templates** (`features/humidity_control/const.py`)
   ```python
   HUMIDITY_SWITCH_CONFIGS = {
       "dehumidify": {
           "entity_template": "dehumidify_{device_id}",  # Extras format - automatic
           "name_template": "Dehumidify {device_id}",
       },
       "target_humidity": {
           "entity_template": "target_humidity_{device_id}",  # Extras format - automatic
           "name_template": "Target Humidity {device_id}",
       }
   }
   ```

2. ✅ **Update Default Sensor Templates** (`features/default/const.py`)
   ```python
   DEFAULT_SENSOR_CONFIGS = {
       "indoor_absolute_humidity": {
           "entity_template": "indoor_absolute_humidity_{device_id}",  # Extras format - automatic
           "name_template": "Indoor Absolute Humidity {device_id}",
       },
       "indoor_relative_humidity": {
           "entity_template": "indoor_relative_humidity_{device_id}",  # Extras format - automatic
           "name_template": "Indoor Relative Humidity {device_id}",
       }
   }
   ```

3. ✅ **Create Framework CC Templates** (new: `framework/const.py`)
   ```python
   CC_TEMPLATES = {
       "param": "{device_id}_param_{param_id}",  # CC format - automatic
       "temp": "{device_id}_temp",              # CC format - automatic
       "fan_speed": "{device_id}_fan_speed",    # CC format - automatic
   }
   ```

### Phase 3: EntityManager Integration (Priority 2) ✅ COMPLETED

**Objective**: Update EntityManager to use automatic detection throughout

**Implementation Steps**:
1. ✅ **Update EntityManager to use enhanced EntityHelpers**
   ```python
   # In _scan_feature_entities method
   for entity_id in existing_entities:
       parsed = EntityHelpers.parse_entity_id(entity_id)  # Automatic detection
       if parsed:
           entity_type, entity_name, device_id = parsed
           # Process entity regardless of format
   ```

2. ✅ **Remove format-specific parsing logic**
   - Eliminate manual "cc" vs "extras" format checking
   - Use automatic detection for all entity processing
   - Simplify entity recognition logic

3. ✅ **Update entity generation to use universal templates**
   - Use `generate_entity_name_from_template()` for all new entities
   - Leverage automatic format detection in template generation
   - Maintain feature-centric template organization

### Phase 4: Platform File Updates (Priority 2) ✅ PARTIALLY COMPLETED

**Objective**: Update platform files to use simplified template approach

**Implementation Steps**:
1. 🔄 **Update Platform Entity Classes**
   ```python
   # Example: features/humidity_control/platforms/sensor.py
   class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
       @property
       def entity_id(self) -> str:
           """Use automatic format detection."""
           return EntityHelpers.generate_entity_name_from_template(
               "sensor", "indoor_absolute_humidity_{device_id}",
               device_id=self.device_id
           )
   ```

2. 🔄 **Update Base Entity Classes**
   - Modify `ExtrasBaseEntity` to use automatic detection
   - Update name generation methods
   - Ensure backward compatibility

### Phase 5: Testing & Validation (Priority 3) ✅ COMPLETED

**Objective**: Comprehensive test coverage for automatic detection

**Implementation Steps**:
1. ✅ **Create comprehensive test suite** (`tests/helpers/test_entity_naming_simple.py`)
   ```python
   def test_device_id_extraction():
       # Test device ID extraction for various patterns

   def test_format_detection():
       # Test position-based format detection

   def test_entity_parsing():
       # Test parsing both CC and Extras formats

   def test_entity_generation():
       # Test universal template generation
   ```

2. ✅ **Test both CC and Extras formats** work correctly
3. ✅ **Validate device_id position detection** accuracy
4. ✅ **Integration tests** with mixed entity scenarios

### Phase 6: Documentation Updates (Priority 3) 🔄 IN PROGRESS

**Objective**: Update all documentation to reflect simplified approach

**Implementation Steps**:
1. ✅ **Update this document** with enhanced implementation approach
2. 🔄 **Update RAMSES_EXTRAS_ARCHITECTURE.md** to simplify naming section
3. 🔄 **Update ENTITYMANAGER_API_REFERENCE.md** with unified methods
4. 🔄 **Update IMPLEMENTATION_SUMMARY.md** with complete guide

### Phase 7: Migration & Cleanup (Priority 4) 📋 PLANNED

**Objective**: Complete migration and remove legacy code

**Implementation Steps**:
1. 📋 **Review and update test files** to use automatic detection
2. 📋 **Remove deprecated format-specific methods** (if any remain)
3. 📋 **Update examples and tutorials** to use new approach
4. 📋 **Final validation** of complete system integration

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
