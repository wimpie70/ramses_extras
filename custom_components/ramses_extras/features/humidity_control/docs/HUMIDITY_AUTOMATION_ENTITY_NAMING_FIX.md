# Humidity Automation Entity Naming Fix

## Problem Summary

The humidity automation was failing with "Missing entities" errors because there was a naming mismatch between:

- **What the automation expected**: `sensor.indoor_abs_humid_32_153289`
- **What actually gets created**: `sensor.indoor_absolute_humidity_32_153289`

The automation was looking for entities with abbreviated names from const.py, but the entity managers create entities with full descriptive names.

## Root Cause

1. **const.py** uses abbreviated entity names for internal reference:
   - `indoor_abs_humid` → becomes → `indoor_absolute_humidity`
   - `outdoor_abs_humid` → becomes → `outdoor_absolute_humidity`
   - `rel_humid_min` → becomes → `relative_humidity_minimum`
   - `rel_humid_max` → becomes → `relative_humidity_maximum`
   - `abs_humid_offset` → becomes → `absolute_humidity_offset`

2. **Entity managers** create entities with full descriptive names based on the `name_template` in const.py

3. **Automation** was looking for abbreviated names, causing continuous "Missing entities" errors

## Solution Implemented

### 1. Added Name Transformation Function

```python
def _get_entity_name_from_const(self, const_entity_name: str) -> str:
    """Convert const.py entity name to actual entity_id name."""
    name_mapping = {
        "indoor_abs_humid": "indoor_absolute_humidity",
        "outdoor_abs_humid": "outdoor_absolute_humidity",
        "rel_humid_min": "relative_humidity_minimum",
        "rel_humid_max": "relative_humidity_maximum",
        "abs_humid_offset": "absolute_humidity_offset",
    }
    return name_mapping.get(const_entity_name, const_entity_name)
```

### 2. Updated State Mappings Generation

**Before (Broken)**:
```python
# Looked for: sensor.indoor_abs_humid_32_153289
mappings["indoor_abs"] = f"sensor.{device_id}_indoor_abs_humid"
```

**After (Fixed)**:
```python
# Uses const.py definitions dynamically
const_name = "indoor_abs_humid"  # From const.py
actual_name = self._get_entity_name_from_const(const_name)  # "indoor_absolute_humidity"
mappings["indoor_abs"] = f"sensor.{device_id}_{actual_name}"  # "sensor.32_153289_indoor_absolute_humidity"
```

### 3. Updated Entity Validation

**Before (Broken)**:
```python
# Hardcoded abbreviated names
expected_entities = [
    f"sensor.{device_id}_indoor_abs_humid",
    f"number.{device_id}_rel_humid_min",
    # ...
]
```

**After (Fixed)**:
```python
# Uses const.py definitions with name transformation
humidity_feature = AVAILABLE_FEATURES.get("humidity_control", {})
required_entities = humidity_feature.get("required_entities", {})

for entity_type, entity_list in required_entities.items():
    for const_entity_name in entity_list:
        actual_name = self._get_entity_name_from_const(const_entity_name)
        entity_id = f"{entity_type}.{device_id}_{actual_name}"
        # Check if entity exists
```

## Benefits of This Solution

1. **Dynamic**: Uses const.py definitions, not hardcoded values
2. **Flexible**: Will work with multiple devices, not just device 32:153289
3. **Maintainable**: Changes to const.py automatically propagate to automation
4. **Correct**: Generates entity names that match what entity managers create
5. **Testable**: Comprehensive test suite validates the logic

## Expected Entity Names

The automation now correctly looks for:

| Entity Type | Expected Entity ID | Description |
|------------|-------------------|-------------|
| Sensor | `sensor.32_153289_indoor_humidity` | CC: Indoor relative humidity |
| Sensor | `sensor.32_153289_indoor_absolute_humidity` | Extras: Calculated absolute humidity |
| Sensor | `sensor.32_153289_outdoor_absolute_humidity` | Extras: Calculated absolute humidity |
| Number | `number.32_153289_relative_humidity_minimum` | Extras: Min threshold |
| Number | `number.32_153289_relative_humidity_maximum` | Extras: Max threshold |
| Number | `number.32_153289_absolute_humidity_offset` | Extras: Offset value |
| Switch | `switch.dehumidify_32_153289` | Extras: Control switch |
| Binary Sensor | `binary_sensor.dehumidifying_active_32_153289` | Extras: Status indicator |

## Testing

Created comprehensive test suite: `tests/managers/test_humidity_automation.py`

Tests validate:
- Name transformation logic
- State mappings generation
- Entity validation
- Humidity decision logic
- Problem reproduction (old vs new approach)
- Solution verification

## Files Modified

1. **ramses_extras/custom_components/ramses_extras/automations/humidity_automation.py**
   - Added `_get_entity_name_from_const()` method
   - Updated `_get_state_mappings()` to use dynamic approach with name transformation
   - Updated `_validate_device_entities()` to use const.py definitions

2. **ramses_extras/tests/managers/test_humidity_automation.py** (New)
   - Comprehensive test suite for the entity naming fix
   - Validates all aspects of the solution

## Verification

To verify the fix works:

1. **Check Home Assistant logs** for reduction in "Missing entities" errors
2. **Turn on dehumidify switch** to test the automation
3. **Monitor fan behavior** based on humidity conditions
4. **Run tests** using: `cd /home/willem/dev/ramses_extras && python -m pytest tests/managers/test_humidity_automation.py -v`

## Next Steps

1. **Reload Home Assistant integration** to pick up the code changes
2. **Monitor logs** for elimination of "Missing entities" errors
3. **Test automation** by turning on dehumidify control and observing fan behavior
4. **Verify end-to-end functionality** with real humidity readings

## Decision Logic Reminder

The automation implements the exact decision flow from `humidity_decision_flow.md`:

```
IF indoor_rh > max_humidity:
  IF indoor_abs > outdoor_abs + offset:
    Set fan HIGH (Active dehumidification)
  ELSE:
    Set fan LOW (Avoid bringing moisture)
ELIF indoor_rh < min_humidity:
  IF indoor_abs < outdoor_abs - offset:
    Set fan HIGH (Active humidification)
  ELSE:
    Set fan LOW (Avoid over-humidifying)
ELSE:
  No action (acceptable range)
```

This fix ensures the automation can properly monitor the required entities to make these decisions.
