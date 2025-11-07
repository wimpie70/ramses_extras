# Entity Naming System Improvements

## Summary

Successfully resolved entity naming issues in the Ramses Extras integration by implementing a comprehensive naming system with proper device ID templates and helper methods.

## Problems Resolved

### 1. Missing Device ID in Templates

**Before:**

- `name_template`: "Indoor Absolute Humidity" (no device ID)
- Entities had inconsistent names like "sensor.indoor_abs_humid" without device identification

**After:**

- `entity_template`: "indoor*absolute_humidity*{device_id}" (includes device ID)
- Consistent format: "sensor.indoor_absolute_humidity_32_153289"

### 2. Inconsistent Naming Convention

**Before:**

- Hardcoded mappings between const names and entity names
- Complex regex patterns for device ID extraction
- Multiple naming patterns causing confusion

**After:**

- Semantic entity names: `indoor_absolute_humidity`, `relative_humidity_maximum`
- Helper methods for consistent generation
- Clean entity ID parsing

### 3. Configuration Structure Issues

**Before:**

- `ENTITY_CONFIGS` contained only sensor configs (misleading name)
- Missing template information for entity generation

**After:**

- `SENSOR_CONFIGS`, `SWITCH_CONFIGS`, `BOOLEAN_CONFIGS`, `NUMBER_CONFIGS`
- Each config includes `entity_template` with `{device_id}` placeholder

## New Entity Naming Convention

**Format:** `{entity_type}.{entity_name}_{device_id}`

**Examples:**

```
sensor.indoor_absolute_humidity_32_153289
sensor.outdoor_absolute_humidity_32_153289
number.relative_humidity_minimum_32_153289
number.relative_humidity_maximum_32_153289
number.absolute_humidity_offset_32_153289
switch.dehumidify_32_153289
binary_sensor.dehumidifying_active_32_153289
```

## Helper Methods Added

### 1. `generate_entity_name_from_template(entity_type, entity_name, device_id)`

Generates consistent entity IDs using configured templates.

```python
entity_id = generate_entity_name_from_template("sensor", "indoor_absolute_humidity", "32_153289")
# Returns: "sensor.indoor_absolute_humidity_32_153289"
```

### 2. `parse_entity_id(entity_id)`

Parses entity IDs to extract components.

```python
result = parse_entity_id("sensor.indoor_absolute_humidity_32_153289")
# Returns: ("sensor", "indoor_absolute_humidity", "32_153289")
```

### 3. `get_all_required_entity_ids_for_device(device_id)`

Gets all entity IDs required for a device.

```python
entities = get_all_required_entity_ids_for_device("32_153289")
# Returns list of all entity IDs for device "32_153289"
```

### 4. `get_entity_template(entity_type, entity_name)`

Retrieves the entity template for generation.

## Files Modified

### 1. `const.py`

- Renamed `ENTITY_CONFIGS` to `SENSOR_CONFIGS`
- Added `entity_template` field to all entity configurations
- Updated entity names to be more semantic
- Fixed `ENTITY_TYPE_CONFIGS` reference

### 2. `helpers/device.py`

- Added entity name helper methods
- Imported configuration constants
- Implemented robust entity ID parsing logic

### 3. `automations/humidity_automation.py`

- Updated to use new helper methods
- Removed complex regex patterns
- Simplified entity validation logic
- Replaced hardcoded name mappings

### 4. Test Files

- Created comprehensive test suite: `test_entity_naming_simple.py`
- All tests passing, validating the new naming system

## Benefits

1. **Consistency**: All entities follow the same naming pattern
2. **Reliability**: Helper methods ensure correct entity generation
3. **Maintainability**: Centralized configuration and logic
4. **Scalability**: Easy to add new entity types and devices
5. **Debugging**: Clear entity names make troubleshooting easier
6. **Backward Compatibility**: Maintained for existing functionality

## Testing Results

✅ All entity generation tests passed
✅ All entity parsing tests passed
✅ All entity validation tests passed
✅ All name template tests passed
✅ All naming consistency tests passed

The improved entity naming system is now working correctly and provides a solid foundation for future development.
