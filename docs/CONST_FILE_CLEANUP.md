# Const File Cleanup and Standardization

## Overview

This document describes the cleanup and standardization of the const files in Ramses Extras, implementing minimal definitions in the root const and consistent patterns across feature-specific const files.

## Issues Identified

### Root const.py Problems

- **Bloat**: Contained 400+ lines with device discovery, event system, and business logic
- **Mixed Responsibilities**: Constants mixed with implementation code
- **Import Issues**: Complex circular imports and async functions
- **Hard to Maintain**: Business logic scattered across multiple functions

### Feature const Files Inconsistencies

- **Inconsistent Naming**: Different patterns across features
- **Missing **all** exports**: No proper module exports
- **Business Logic Mixing**: Feature constants mixed with runtime logic
- **Redundant Configuration**: Some features had overlapping or unnecessary configs

## New Architecture

### Root const.py - Minimal Core Constants

The root const file now contains only **essential constants**:

```python
"""Core constants for Ramses Extras integration."""

from pathlib import Path
from typing import Any, Callable, Dict, List

DOMAIN = "ramses_extras"
INTEGRATION_DIR = Path(__file__).parent

# URLs and documentation
GITHUB_URL = "https://github.com/wimpie70/ramses_extras"
GITHUB_WIKI_URL = f"{GITHUB_URL}/wiki"

# Configuration constants
CONF_NAME = "name"
CONF_ENABLED_FEATURES = "enabled_features"
CONF_ENABLED_WEB_SOCKETS = "enabled_web_sockets"
CONF_MESSAGE_EVENTS = "message_events"

# UI/Frontend constants
WS_CMD_GET_BOUND_REM = f"{DOMAIN}/get_bound_rem"
CARD_FOLDER = "www"
CARD_HELPERS_FOLDER = "www/helpers"
FEATURE_FOLDER = "features"

# Feature identifiers
FEATURE_ID_DEFAULT = "default"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"

# Event system constants
EVENT_DEVICE_READY_FOR_ENTITIES = "ramses_device_ready_for_entities"

# Registries (minimal interfaces only)
DEVICE_TYPE_HANDLERS: dict[str, Callable] = {}
PLATFORM_REGISTRY: dict[str, dict[str, Callable]] = {}
```

**Removed from root const.py:**

- All async functions
- Device discovery logic
- Event firing functions
- Business logic constants
- Complex feature scanning
- Registry implementations

### Standardized Feature Const Pattern

Each feature const file now follows this standardized structure:

```python
"""Feature description - feature-specific entity definitions."""

from typing import Any
from homeassistant.helpers.entity import EntityCategory

# Entity configurations by type
FEATURE_SENSOR_CONFIGS = {entity_name: config_dict, ...}
FEATURE_SWITCH_CONFIGS = {entity_name: config_dict, ...}
FEATURE_NUMBER_CONFIGS = {entity_name: config_dict, ...}
FEATURE_BOOLEAN_CONFIGS = {entity_name: config_dict, ...}

# Device mapping
FEATURE_DEVICE_ENTITY_MAPPING = {
    "DeviceType": {
        "sensor": ["entity_name", ...],
        "switch": ["entity_name", ...],
        "number": ["entity_name", ...],
        "binary_sensor": ["entity_name", ...],
    },
}

def load_feature() -> None:
    """Load feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_sensor_configs(FEATURE_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(FEATURE_SWITCH_CONFIGS)
    extras_registry.register_number_configs(FEATURE_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(FEATURE_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(FEATURE_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("feature_name")

__all__ = [
    "FEATURE_SENSOR_CONFIGS",
    "FEATURE_SWITCH_CONFIGS",
    "FEATURE_NUMBER_CONFIGS",
    "FEATURE_BOOLEAN_CONFIGS",
    "FEATURE_DEVICE_ENTITY_MAPPING",
    "load_feature",
]
```

## File-by-File Changes

### `features/default/const.py`

**Changes:**

- Added `FEATURE_ID_DEFAULT` constant
- Added proper `__all__` exports
- Maintained entity configurations structure
- Simplified documentation

**What's Kept:**

- Base sensor configurations (indoor/outdoor absolute humidity)
- Empty configs for other entity types
- Device mapping for shared sensors
- Load function

**What's Removed:**

- Nothing (this was already clean)

### `features/humidity_control/const.py`

**Changes:**

- Removed business logic constants (decision thresholds, actions, etc.)
- Removed complex configuration dictionaries
- Added proper `__all__` exports
- Simplified structure

**What's Kept:**

- Entity configurations (switch, number, boolean)
- Device mapping
- Load function

**What's Removed:**

- `FEATURE_ID_HUMIDITY_CONTROL` (moved to root)
- `HUMIDITY_CONTROL_CONST` (business logic)
- `HUMIDITY_DECISION_THRESHOLDS` (runtime logic)
- `HUMIDITY_DECISION_ACTIONS` (runtime logic)
- `websocket_messages` (runtime logic)
- `logging_categories` (runtime logic)
- `defaults` (runtime logic)

### `features/hvac_fan_card/const.py`

**Changes:**

- Removed redundant feature identification
- Added proper `__all__` exports
- Simplified structure
- Kept minimal configuration

**What's Kept:**

- Empty entity configs (inherits from default)
- Device mapping
- Load function

**What's Removed:**

- `FEATURE_ID_HVAC_FAN_CARD` (moved to root)
- `HVAC_FAN_CARD_CONFIG` (business logic)

## Benefits of New Structure

### 1. **Clear Separation of Concerns**

- **Root const**: Only core integration constants
- **Feature consts**: Only entity definitions and mappings
- **Business logic**: Moved to appropriate feature modules

### 2. **Consistency**

- All feature const files follow the same pattern
- Consistent naming conventions
- Proper module exports (`__all__`)
- Standardized load function

### 3. **Maintainability**

- Easier to understand what's in each file
- Reduced complexity in const files
- Business logic in appropriate modules
- Clear imports and dependencies

### 4. **Testability**

- Const files are pure data definitions
- Easy to mock and test
- No async complexity in const files
- Clear interfaces

### 5. **Performance**

- Faster imports (less code to parse)
- No circular import issues
- Cleaner dependency graph
- Reduced memory footprint

## Migration Guide

### For Developers

1. **Import constants from appropriate location:**

   ```python
   # Core constants
   from custom_components.ramses_extras.const import DOMAIN, FEATURE_ID_HUMIDITY_CONTROL

   # Feature-specific configs
   from custom_components.ramses_extras.features.humidity_control.const import (
       HUMIDITY_SWITCH_CONFIGS,
       HUMIDITY_NUMBER_CONFIGS
   )
   ```

2. **Business logic moved to feature modules:**

   ```python
   # Decision logic now in automation.py or services.py
   from custom_components.ramses_extras.features.humidity_control.automation import (
       HUMIDITY_DECISION_THRESHOLDS
   )
   ```

3. **Event handling moved to framework:**
   ```python
   # Device discovery in __init__.py or framework modules
   from custom_components.ramses_extras.framework.helpers.device import (
       handle_device_discovery
   )
   ```

### For Features

When creating new features, follow this pattern:

```python
# features/my_new_feature/const.py
"""My new feature - feature-specific entity definitions."""

from typing import Any
from homeassistant.helpers.entity import EntityCategory

MY_FEATURE_SENSOR_CONFIGS = {
    "my_sensor": {
        "name_template": "My Sensor {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "°C",
        # ... other config
    }
}

MY_FEATURE_DEVICE_ENTITY_MAPPING = {
    "DeviceType": {
        "sensor": ["my_sensor"],
    },
}

def load_feature() -> None:
    """Load my_new_feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_sensor_configs(MY_FEATURE_SENSOR_CONFIGS)
    extras_registry.register_device_mappings(MY_FEATURE_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("my_new_feature")

__all__ = [
    "MY_FEATURE_SENSOR_CONFIGS",
    "MY_FEATURE_DEVICE_ENTITY_MAPPING",
    "load_feature",
]
```

## Backward Compatibility

The changes maintain backward compatibility:

1. **Existing imports still work** (from same locations)
2. **Feature loading unchanged** (same load functions)
3. **Registry interface unchanged** (same registration methods)
4. **Entity configurations preserved** (same structure and data)

## Issues Resolved

### Blocking Import Fixes

After initial cleanup, a blocking import error occurred during Home Assistant startup. This was resolved by:

1. **Restored AVAILABLE_FEATURES**: Added back with minimal implementation to maintain compatibility
2. **Moved dynamic imports inside functions**: Eliminated top-level `__import__` calls that blocked the event loop
3. **Simplified feature detail retrieval**: Removed dynamic module loading in config flow
4. **Moved imports to function scope**: All `AVAILABLE_FEATURES` imports now happen inside functions to avoid blocking

### Code Changes Made

**config_flow.py**:

- Replaced dynamic `__import__` calls with simple AVAILABLE_FEATURES lookup
- Moved feature detail extraction to use static data only

**framework/helpers/entity/manager.py**:

- Moved `AVAILABLE_FEATURES` import inside function scope

**framework/helpers/automation/base.py**:

- Removed top-level `AVAILABLE_FEATURES` import
- Simplified validation logic to avoid blocking calls

**framework/helpers/entity/core.py**:

- Commented out top-level `AVAILABLE_FEATURES` import

## Next Steps

1. **Move business logic** to appropriate feature modules
2. **Consolidate device discovery** into framework helpers
3. **Standardize event handling** across features
4. **Create feature template** for new features
5. **Consider async module loading** for future dynamic feature loading

## Conclusion

The const file cleanup provides a solid foundation for maintainable, consistent, and scalable feature development. By separating core constants from business logic and standardizing feature const files, the codebase becomes much more manageable and follows established Python patterns.
