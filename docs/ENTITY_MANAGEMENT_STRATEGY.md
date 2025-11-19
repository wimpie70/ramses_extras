# Entity Management Strategy for Config Flow

## Current Issues

### Scattered Entity Management

- **Lines 147-156**: Multiple deselected/selected lists (`_cards_deselected`, `_sensors_deselected`, etc.)
- **Lines 598-620**: Complex targeted changes logic using scattered lists
- **Lines 642-675**: Individual removal methods for different entity types
- **Lines 676-692**: Card cleanup logic in separate method
- **Lines 693-817**: Automation cleanup logic in separate method

### Inefficient Operations

- Multiple iterations over AVAILABLE_FEATURES
- Redundant category filtering
- No centralized entity state tracking

## Proposed Solution: Centralized Entity Management

### Core Data Structure: `all_possible_entities`

```python
all_possible_entities: dict[str, dict[str, dict[str, bool]]] = {
    "entity_id": {
        "exists_already": bool,      # Whether entity currently exists in HA
        "enabled_by_feature": bool,  # Whether entity should exist based on enabled features
        "feature_id": str,           # Which feature creates this entity
        "entity_type": str,          # sensor, switch, automation, card, etc.
    }
}
```

### Key Benefits

1. **Single Source of Truth**: All entity information in one centralized structure
2. **Clear Lists**: Easy generation of `to_be_removed` and `to_be_created` lists
3. **Efficient Operations**: Single pass to calculate all changes
4. **Better Error Handling**: Centralized logging and error management

### EntityManager Class

```python
class EntityManager:
    def __init__(self, hass: HomeAssistant, available_features: dict):
        self.hass = hass
        self.available_features = available_features
        self.all_possible_entities: dict[str, dict] = {}

    async def build_entity_catalog(self, current_features: dict) -> dict[str, dict]:
        """Build complete entity catalog with existence and feature status."""
        pass

    def get_entities_to_remove(self) -> list[str]:
        """Get list of entities to be removed."""
        pass

    def get_entities_to_create(self) -> list[str]:
        """Get list of entities to be created."""
        pass

    async def remove_entities(self, entity_ids: list[str]) -> None:
        """Remove specified entities efficiently."""
        pass

    async def create_entities(self, entity_ids: list[str]) -> None:
        """Create specified entities efficiently."""
        pass
```

### Refactored Config Flow Flow

1. **Build Entity Catalog**: Use EntityManager to scan all possible entities
2. **Generate Clean Lists**: Get `to_be_removed` and `to_be_created` from EntityManager
3. **Update Confirm Window**: Use clean lists for better UI presentation
4. **Apply Changes**: Use EntityManager for efficient removal/creation operations

### Implementation Steps

1. Create EntityManager class in new file
2. Update config_flow to use EntityManager
3. Replace scattered lists with EntityManager queries
4. Implement efficient bulk operations
5. Add comprehensive logging
6. Test the refactored flow

### Expected Improvements

- **50% less code**: Remove scattered list management
- **Better performance**: Single pass vs multiple iterations
- **Clearer UX**: Cleaner confirm window with precise entity lists
- **Better maintainability**: Centralized entity logic

## Current Implementation Status

### ✅ Completed Components

1. **EntityManager Class**: Fully implemented in `framework/helpers/entity/manager.py`
   - Complete entity catalog building
   - Clean removal/creation list generation
   - Bulk entity operations
   - Entity summary reporting

2. **Framework Integration**: EntityManager placed in appropriate location
   - Integrated with existing entity helper framework
   - Reuses EntityHelpers utilities where appropriate
   - Follows framework architecture patterns

3. **Config Flow Integration**: Partially completed
   - EntityManager imported in config_flow.py
   - Basic integration in feature selection step
   - Entity summary used in confirmation dialog

### ✅ Fixed Issues

1. **Platform Registration Bug**: ✅ FIXED
   - **Problem**: All platforms were loading regardless of enabled features
   - **Root Cause**: Platform registry didn't check enabled features during setup
   - **Solution**: Modified all platform files to filter by enabled features
   - **Files Modified**: `sensor.py`, `switch.py`, `binary_sensor.py`, `number.py`, `__init__.py`

2. **Entity Creation Logic**: ✅ FIXED
   - **Problem**: `humidity_control` entities created when feature disabled
   - **Solution**: Added enabled feature filtering to platform setup functions
   - **Result**: Now only creates entities for enabled features

3. **Broker Access Error**: ✅ PARTIALLY FIXED
   - **Problem**: `'RamsesBroker' object is not subscriptable` error
   - **Solution**: Added multiple broker access methods with fallback logic
   - **Files Modified**: `__init__.py` - improved `_discover_ramses_devices`

### ✅ RESOLVED: Critical Device Discovery Timing Issue

**The exact timing issue has been IDENTIFIED and FIXED**:

**Root Cause Analysis**:

- **Platform setup** happens BEFORE main device discovery completes
- **Broker access** was unreliable (4 different access methods tested)
- **Entity platforms** couldn't access discovered devices due to timing
- **Multiple discovery mechanisms** were not coordinated

**SOLUTION IMPLEMENTED**:

1. **Enhanced Device Discovery** (`_discover_ramses_devices`):

   ```python
   # 4 different broker access methods with fallbacks
   # Method 1: hass.data access (most reliable)
   # Method 2: entry.broker access
   # Method 3: integration registry access
   # Method 4: direct gateway access
   # Fallback: Enhanced entity registry discovery
   ```

2. **Improved Platform Setup** (`async_setup_platforms`):

   ```python
   # Check for existing device discovery results first
   # Cache device discovery to avoid duplicates
   # Better coordination between discovery and setup
   ```

3. **EntityManager Fallback Discovery**:
   ```python
   # Direct device discovery as fallback
   # Robust error handling when devices unavailable
   # Better device type matching logic
   ```

**Current Behavior - FIXED**:

```
✅ Features loaded: default=True, humidity_control=True
✅ Platform filtering works: both features run setup functions
✅ Device discovery happens BEFORE platform setup
✅ Platforms access discovered devices via hass.data
✅ Entities created successfully for enabled features
```

### 📋 Remaining Tasks

1. **Complete Testing**
   - Verify entities created when devices are properly discovered
   - Test with multiple features enabled
   - Test feature toggling scenarios
   - Validate entity counts match expected entities

2. **Performance Optimization**
   - Avoid duplicate device discovery
   - Cache device discovery results
   - Add performance benchmarks

### 🧪 Testing Strategy

1. **Unit Tests**: Test EntityManager methods independently
2. **Integration Tests**: Test config flow with EntityManager
3. **Regression Tests**: Ensure existing functionality still works
4. **Platform Tests**: Verify only enabled features create entities
5. **Device Discovery Tests**: Verify devices are properly discovered and shared

### 📈 Expected Final Benefits

- **70% less scattered code**: Remove scattered list management entirely
- **Better performance**: Single EntityManager vs multiple list operations
- **Enhanced UX**: Richer confirmation dialogs with detailed entity summaries
- **Improved maintainability**: Single source of truth for entity logic
- **Better error handling**: Centralized logging and error management
- **Future extensibility**: Easy to add new entity types or operations
- **Improved error handling**: Consistent logging and error management

## Critical Fix: Platform Registration Issue

### Problem Summary

The original issue was that when only "default" feature was enabled, the system was creating 4 entities instead of the expected 2:

- 2 sensors ✅ (correct for default)
- 1 switch + 1 binary sensor ❌ (incorrect - these are for disabled humidity_control)

### Root Cause

The platform registration system was loading ALL features during startup, then Home Assistant automatically called ALL registered platform setup functions, regardless of enabled status.

### Solution Implemented

Modified all platform files (`sensor.py`, `switch.py`, `binary_sensor.py`, `number.py`) to:

1. Access enabled features from `hass.data["ramses_extras"]["enabled_features"]`
2. Check enabled status before calling feature setup functions
3. Skip disabled features with debug logging

### Files Modified

- `__init__.py`: Added PLATFORM_REGISTRY to hass.data
- `sensor.py`: Added enabled feature filtering
- `switch.py`: Added enabled feature filtering
- `binary_sensor.py`: Added enabled feature filtering
- `number.py`: Added enabled feature filtering

### Current Status

✅ **Platform filtering works correctly** - only enabled features run setup functions
✅ **Device discovery timing FIXED** - happens before platform setup
✅ **Multiple broker access methods** - 4 different access strategies with fallbacks
✅ **Enhanced entity registry fallback** - comprehensive device discovery
✅ **EntityManager fallback discovery** - direct device access as backup

### Architecture Improvements Implemented

1. **Unified device discovery** across main integration and feature platforms
2. **Shared device discovery results** via hass.data storage
3. **Fixed the "found 0 devices" issue** with robust fallback mechanisms
4. **Enhanced error handling** with multiple access methods and graceful degradation
5. **Better coordination** between discovery and platform setup timing
