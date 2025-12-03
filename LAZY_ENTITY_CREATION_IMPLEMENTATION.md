# Lazy Entity Creation Implementation Plan

## Overview

This document outlines the implementation of **Option 1: Lazy Entity Creation** with **Menu-Based Options Flow Architecture** to solve the entity creation timing issue in Ramses Extras.

## Problem Statement

**Current Issue**: When enabling features, entities are created for all compatible devices, but users don't know which devices they actually need until they add cards to the dashboard and make selections.

**Solution**: Entities are created only when users explicitly select devices through:

- **Card-based features**: Entity creation triggered by card configuration
- **Automation-only features**: Entity creation triggered by feature-specific config flow
- **Menu-based configuration**: Clean separation through options flow menu

## Architecture Overview

### New Menu-Based Configuration Flow Structure

```
🏠 Main Options Flow Menu                     🔧 Feature Config Submenu
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ Ramses Extras Configuration         │     │ Feature Configuration               │
│                                     │     │                                     │
│ 1. Features Management              │────>│ Feature Name: Humidity Control      │
│ 2. Humidity Control Settings        │     │ Device Selection:                   │
│ 3. HVAC Fan Card Settings           │     │ ☑️ Device A (HvacVentilator)       │
│ 4. Hello World Card Settings        │     │ ☑️ Device B (HvacVentilator)       │
│ 5. General Settings                 │     │ ☐ Device C (HvacVentilator)       │
│                                     │     │                                     │
│ [< Back] [Save Configuration]       │     │ [< Back] [Save] [Apply & Return]   │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

### Entity Creation Flow

| Feature Type        | Trigger                                   | Entity Creation |
| ------------------- | ----------------------------------------- | --------------- |
| **Card-based**      | User adds card + selects device           | Immediate       |
| **Automation-only** | User configures feature + selects devices | On save         |
| **Menu-driven**     | Options flow → Feature config → Devices   | On save         |

## Implementation Architecture

### Phase 1: Menu-Based Options Flow

**✅ IMPLEMENTED - Dynamic menu generation with menu_visible property**, implement a clean menu-based approach:

```python
# Dynamic menu-based options flow structure
async def async_step_init(self, user_input=None):
    """Show main configuration menu with dynamic feature loading."""
    # Generate menu options dynamically from AVAILABLE_FEATURES
    menu_options = ["features_management"]  # Always include features management

    # Add features that have menu_visible=True
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("menu_visible", False):
            menu_options.append(feature_key)

    menu_options.append("general_settings")  # Always include general settings

    return self.async_show_menu(
        step_id="init",
        menu_options=menu_options,
    )

# Individual feature steps
async def async_step_features_management(self, user_input=None):
    """Enable/disable features - selectbox with multi-select."""

async def async_step_humidity_control(self, user_input=None):
    """Humidity Control configuration - device selection with selectboxes."""

async def async_step_hvac_fan_card(self, user_input=None):
    """HVAC Fan Card configuration - card settings."""

async def async_step_hello_world_card(self, user_input=None):
    """Hello World Card configuration - optional device selection."""

async def async_step_general_settings(self, user_input=None):
    """General integration settings."""
```

**Key Improvements Implemented:**

- ✅ Uses `async_show_menu()` instead of boolean selectors (ramses_cc pattern)
- ✅ Clean menu navigation with proper step separation
- ✅ Device selection with selectboxes and proper form submission
- ✅ Each step has `last_step=True` for proper navigation
- ✅ Follows ramses_cc config flow patterns exactly

### Phase 2: Feature-Specific Configuration Classes

Each feature gets its own configuration class inheriting from `ConfigFlow`:

```python
# Feature configuration classes
class HumidityControlConfigFlow(FeatureConfigFlowBase):
    """Humidity Control device selection and configuration."""
    async def async_step_device_selection(self, user_input=None):
        """Select devices for humidity control."""

class HvacFanCardConfigFlow(FeatureConfigFlowBase):
    """HVAC Fan Card configuration - card-only feature."""
    async def async_step_card_settings(self, user_input=None):
        """Configure card settings."""

class HelloWorldCardConfigFlow(FeatureConfigFlowBase):
    """Hello World Card configuration with optional device selection."""
    async def async_step_device_selection(self, user_input=None):
        """Optional device selection for entities."""
```

### Phase 3: Navigation and State Management

**Clean Navigation Pattern** (based on ramses_cc):

- Each step handles ONE specific configuration area
- Easy navigation back to main menu
- Clean separation of concerns
- State preservation across steps

**Data Storage Strategy**:

- Use HA's built-in `options` storage
- Per-feature configuration stored in `options["features"][feature_name]`
- No more `hass.data` storage or `pending_data` complexity

## Key Benefits of Menu-Based Architecture

✅ **Clean Separation**: Each configuration area is completely separate
✅ **Easy Navigation**: Users can easily jump between different settings
✅ **Scalable**: Adding new features automatically adds menu options via menu_visible property
✅ **User-Friendly**: Clear, focused steps instead of overwhelming forms
✅ **Maintainable**: Clean separation of configuration concerns
✅ **State Preservation**: Configuration state properly maintained across steps
✅ **ramses_cc Compatible**: Follows established patterns from parent integration

## Implementation Phases

### Phase 1: Core Framework Updates [COMPLETED ✅]

- [x] Enhanced Feature Registry with config flow support
- [x] Generic Device Selection Framework (feature-agnostic)
- [x] Lazy Entity Creation Manager (reusable patterns only)

**Key Components Created:**

- `DeviceSelectionManager`: Feature-agnostic device discovery and selection
- `LazyEntityCreationManager`: Framework for selective entity creation
- `FeatureConfigFlowBase`: Base class for feature-specific config flows
- `_show_feature_device_selection_menu_based()`: Reusable device selection UI with selectboxes and confirmation

### Phase 2: Config Flow System [COMPLETED ✅]

**OLD APPROACH (Previous Implementation):**

- ❌ Single monolithic step with embedded configure buttons
- ❌ Complex state management with pending_data and hass.data
- ❌ Inline device selection forms
- ❌ Navigation complexity

**NEW APPROACH (Menu-Based - IMPLEMENTED):**

- ✅ Menu-based options flow with clean separation (ramses_cc pattern)
- ✅ Feature-specific config flow classes
- ✅ Proper navigation between configuration areas using `async_show_menu()`
- ✅ Clean state management using HA options storage
- ✅ Each step handles one specific configuration aspect
- ✅ Selectboxes and submit buttons for device selection
- ✅ Clean form submission following ramses_cc patterns
- ✅ Reusable `_show_feature_device_selection_menu_based()` method for any feature requiring device selection

#### Reusable Device Selection Framework

The `_show_feature_device_selection_menu_based()` method provides a standardized way to handle device selection for any feature:

```python
async def _show_feature_device_selection_menu_based(
    self, feature_key: str, feature_config: dict[str, Any],
    user_input: dict[str, Any] | None = None, optional: bool = False
) -> config_entries.FlowResult:
    """Reusable device selection UI for any feature requiring device selection.

    Features: humidity_control, hello_world_card, etc.
    - Discovers compatible devices based on feature_config["supported_device_types"]
    - Shows selectboxes with device names, IDs, and types
    - Handles optional vs required device selection
    - Provides confirmation step before saving
    - Stores selected devices in options["features"][feature_key]["selected_devices"]
    """
```

**Usage Pattern:**

```python
# In feature-specific step methods
async def async_step_humidity_control(self, user_input=None):
    return await self._show_feature_device_selection_menu_based(
        "humidity_control", AVAILABLE_FEATURES["humidity_control"], user_input
    )

async def async_step_hello_world_card(self, user_input=None):
    return await self._show_feature_device_selection_menu_based(
        "hello_world_card", AVAILABLE_FEATURES["hello_world_card"], user_input, optional=True
    )
```

**Entity Management Integration:**
When device selections are confirmed, the system automatically:

- **Creates entities** for newly selected devices based on feature's `required_entities`
- **Removes entities** for deselected devices from the entity registry
- **Triggers integration reload** to create new entities through normal platform setup

This ensures that entity creation/removal happens immediately when users change device selections, providing proper lazy entity creation behavior.

**Feature Enabling with Device Selection Integration:**
When features are enabled/disabled through the features management menu, the system now:

- **Checks for existing device selections** in the feature configuration
- **Only creates entities for selected devices** when a feature is enabled (not all compatible devices)
- **Respects user device selections** made in individual feature config flows
- **Falls back to all compatible devices** if no specific device selections exist

This ensures that feature enabling respects the lazy entity creation principle by only creating entities for devices that have been explicitly selected by the user.

## Current Implementation Status

### ✅ Completed Features

- **Device selection integration**: Features now respect device selections when being enabled
- **Entity creation filtering**: Only creates entities for explicitly selected devices
- **Default feature handling**: Default feature doesn't conflict with specific feature selections
- **Entity override logic**: Specific features can override default feature entities for selected devices

### 🔄 Partially Implemented Features

- **Basic cleanup**: Entity removal when features are disabled (existing functionality)
- **Device-level cleanup**: Partial support for removing entities when devices are deselected

### 🚧 Future Enhancements Needed

#### 1. Comprehensive Cleanup for Disabled Features

When a feature is disabled, the system should:

- **Remove all entities** created by that feature for all devices
- **Clean up entity registry** entries
- **Update entity catalog** to reflect the disabled state
- **Trigger integration reload** to remove entities from Home Assistant

#### 2. Device-Level Cleanup for Deselected Devices

When devices are deselected within a feature, the system should:

- **Identify entities** that were created for the deselected devices
- **Remove only those specific entities** while keeping entities for still-selected devices
- **Maintain feature state** for other devices
- **Update device selection tracking** in the entity catalog

#### 3. Enhanced Entity Lifecycle Management

- **Automatic cleanup triggers** when device selections change
- **Entity state tracking** to know which entities were created by which feature/device combinations
- **Bulk cleanup operations** for efficiency
- **Error handling and recovery** for cleanup failures

## Implementation Roadmap

### Phase 1: Current Implementation (✅ Completed)

- Device selection integration for feature enabling
- Entity creation filtering based on device selections
- Basic entity override logic

### Phase 2: Cleanup Enhancements (🚧 In Progress)

- Feature disable cleanup implementation
- Device deselection cleanup implementation
- Entity lifecycle state tracking

### Phase 3: Advanced Features (🔮 Future)

- Automated cleanup triggers on configuration changes
- Performance optimization for large-scale cleanup operations
- Comprehensive error handling and recovery mechanisms
- User notification and confirmation for cleanup operations

## Technical Implementation Notes

The current implementation focuses on the "creation" side of lazy entity management. The cleanup functionality exists in basic form but needs enhancement to fully support the device-level granularity that the creation side now provides.

Key areas for future development:

1. **Entity tracking enhancement**: Need to track which entities were created by which specific device selections
2. **Cleanup granularity**: Currently removes all entities for a feature when disabled, needs device-level granularity
3. **State management**: Need to maintain proper state when devices are added/removed from selections
4. **Performance**: Bulk operations needed for efficient cleanup of many entities

### Phase 3: Feature Migration [PENDING]

- Update humidity control with menu-based config
- Keep HVAC fan card as card-only with dedicated settings
- Add optional config flow to hello world card via menu
- Migrate all feature configurations to separate menu options

### Phase 4: Entity Lifecycle Updates [COMPLETED ✅]

- [x] Platform Setup for lazy creation
- [x] Selective Entity Factory
- [x] Cleanup for unselected devices

**Platform Enhancement:**

- ✅ Enhanced `PlatformSetup` class with lazy creation support
- ✅ Added `async_setup_platform_lazy()` method
- ✅ Implemented device selection lookup from config flows
- ✅ Added entity cleanup for unselected devices
- ✅ Created selective entity factory pattern

### Phase 5: Clean Implementation [PENDING]

- Direct migration to new menu-based system
- Remove legacy config flow complexity
- Full implementation of clean navigation
- Remove pending_data and hass.data storage patterns

## Implementation Steps

1. **✅ Plan approved** - Menu-based architecture design reviewed and approved
2. **✅ Phase 1 completed** - Framework foundation with device selection and lazy entity creation
3. **✅ Phase 2 completed** - Menu-based config flow system implemented (ramses_cc pattern)
4. **🔄 Phase 3 pending** - Feature migration to menu-based configuration
5. **✅ Phase 4 completed** - Entity lifecycle updates with selective creation and cleanup
6. **⏳ Phase 5 pending** - Clean menu-based implementation without legacy concerns

## Architecture Benefits Achieved

✅ **Clean Separation**: Features clearly configured through dedicated menu options
✅ **Menu-Based Navigation**: Easy navigation between configuration areas
✅ **Feature-Specific Classes**: Each feature has its own configuration flow
✅ **Scalable Framework**: Adding new features means adding new menu options via menu_visible property
✅ **Device-Level Entity Management**: Device selection changes immediately create/remove entities without full integration reload
✅ **User Control**: Clear device selection for automation features
✅ **ramses_cc Compatible**: Follows established patterns from parent integration
✅ **State Management**: Clean separation using HA's options storage
✅ **Timing Solution**: Entities created only when needed

## Migration Strategy

### Current → New Architecture Mapping

| Current Implementation         | New Architecture                                |
| ------------------------------ | ----------------------------------------------- |
| Single `async_step_features()` | Menu with separate steps per configuration area |
| Embedded configure buttons     | Dedicated feature config classes                |
| Complex pending_data storage   | Clean options storage per feature               |
| Inline device selection        | Proper sub-flows for device selection           |
| hass.data feature_configs      | Standard HA options storage                     |

### Step-by-Step Migration

1. **Implement new menu-based options flow**
   - Replace `RamsesExtrasOptionsFlowHandler.async_step_init()` with menu-based approach
   - Add separate step methods for each configuration area
   - Remove complex `async_step_features()` logic

2. **Create feature-specific config flow classes**
   - Create `HumidityControlConfigFlow` class in `features/humidity_control/config_flow.py`
   - Create `HvacFanCardConfigFlow` class in `features/hvac_fan_card/config_flow.py`
   - Create `HelloWorldCardConfigFlow` class in `features/hello_world_card/config_flow.py`
   - Update `async_get_options_flow()` to return appropriate flow handlers

3. **Migrate humidity control to new pattern**
   - Remove inline device selection from main config flow
   - Move device selection logic to `HumidityControlConfigFlow`
   - Update device storage to use clean options structure

4. **Migrate HVAC fan card to new pattern**
   - Remove configure button from main flow
   - Move card settings to `HvacFanCardConfigFlow`
   - Update card management to use new configuration

5. **Migrate hello world card to new pattern**
   - Remove configure button from main flow
   - Move optional device selection to `HelloWorldCardConfigFlow`
   - Update entity creation logic

6. **Remove old monolithic config flow**
   - Delete complex `pending_data` and `hass.data` storage
   - Remove inline device selection forms
   - Clean up navigation complexity

7. **Update framework and helpers**
   - Update `FeatureConfigFlowBase` for new menu pattern
   - Modify device selection managers for new flow
   - Update entity creation for clean options storage

8. **Update documentation and tests**
   - Update architecture documentation
   - Modify integration tests for new flow
   - Update user-facing documentation

## Technical Implementation Details

### Menu Structure

```
Main Menu (async_step_init)
├── Features Management (async_step_features_management)
│   └── Simple enable/disable checkboxes
├── Humidity Control (async_step_humidity_control)
│   └── Device selection sub-flow
├── HVAC Fan Card (async_step_hvac_fan_card)
│   └── Card configuration settings
├── Hello World Card (async_step_hello_world_card)
│   └── Optional device selection
└── General Settings (async_step_general_settings)
    └── Integration-wide settings
```

### Data Storage Pattern

```python
# Clean option storage structure
options = {
    "features": {
        "humidity_control": {
            "enabled": True,
            "selected_devices": ["32:153289", "32:153290"]
        },
        "hvac_fan_card": {
            "enabled": True,
            "card_settings": {"refresh_rate": 1}
        }
    }
}
```

## Detailed Implementation Guide

### Files That Need Changes

**Primary Files to Modify:**

1. **`custom_components/ramses_extras/config_flow.py`**
   - Replace `RamsesExtrasOptionsFlowHandler.async_step_init()` with menu-based approach
   - Remove complex `async_step_features()` method
   - Add new step methods for each configuration area
   - Update `async_get_options_flow()` method

2. **`custom_components/ramses_extras/framework/helpers/config/feature_config_flow.py`**
   - Update base class for new menu-based navigation pattern
   - Modify device selection flow integration

3. **New feature config flow files:**
   - `custom_components/ramses_extras/features/humidity_control/config_flow.py`
   - `custom_components/ramses_extras/features/hvac_fan_card/config_flow.py`
   - `custom_components/ramses_extras/features/hello_world_card/config_flow.py`

### Code Structure Changes

**Before (Current Implementation):**

```python
class RamsesExtrasOptionsFlowHandler:
    async def async_step_features(self, user_input=None):
        # Single monolithic step handling everything
        # Complex state management with pending_data
        # Embedded configure buttons
        # Inline device selection forms
```

**After (New Menu-Based Implementation):**

```python
class RamsesExtrasOptionsFlowHandler:
    async def async_step_init(self, user_input=None):
        # Clean menu-based navigation
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "features_management",
                "humidity_control",
                "hvac_fan_card",
                "hello_world_card",
                "general_settings",
            ]
        )

    async def async_step_features_management(self, user_input=None):
        # Simple enable/disable checkboxes only

    async def async_step_humidity_control(self, user_input=None):
        # Device selection via sub-flow
        return await self.async_step_device_selection_humidity()

    async def async_step_device_selection_humidity(self, user_input=None):
        # Clean device selection for humidity control
```

### FAN Device Filtering Implementation

**Key Improvement**: The humidity control feature now implements proper FAN device filtering to ensure only actual fan devices are listed, not all HVAC devices.

````python
def _is_fan_device(self, device: dict[str, Any]) -> bool:
    """Check if a device is a FAN device (not just any HVAC device).

    Args:
        device: Device information dictionary with device_id, device_type, etc.

    Returns:
        True if the device is a FAN device, False otherwise
    """
    # Use the same device identification method as ramses_cc
    # Ramses_cc uses the _SLUG attribute to identify device types
    # FAN devices have _SLUG == "FAN"

    # Check if device has _SLUG attribute (ramses_cc device object)
    if hasattr(device, "_SLUG") and device._SLUG == "FAN":
        return True

    # For device info dictionaries, check if it's a FAN device
    # Look for fan-specific attributes or device_type
    device_type = device.get("device_type", "")
    device_id = device.get("device_id", "")

    # Check for fan-specific attributes that indicate this is a fan device
    has_fan_attributes = any(
        attr in device.get("attributes", {})
        for attr in ["fan_speed", "fan_mode", "fan_control", "fan_speed_levels"]
    )

    # Check if device has fan-related capabilities
    has_fan_capabilities = any(
        cap in device.get("capabilities", [])
        for cap in ["fan_control", "fan_speed_control", "ventilation_control"]
    )

    # Device is considered a FAN device if:
    # 1. It's an HvacVentilator type, AND
    # 2. It has fan-related attributes or capabilities
    return device_type == "HvacVentilator" and (has_fan_attributes or has_fan_capabilities)

  451 |
  452 | **Ramses_cc SLUG-Based Device Identification:**
  453 |
  454 | The filtering now uses the same device identification method as ramses_cc, which uses the `_SLUG` attribute to identify device types. This is the same approach used in `ramses_cc/broker.py`:
  455 |
  456 | ```python
  457 | # From ramses_cc/broker.py line 491:
  458 | if hasattr(device, "_SLUG") and device._SLUG == "FAN":
  459 |     await self._setup_fan_bound_devices(device)
  460 | ```
  461 |
  462 | This ensures compatibility with the ramses_cc device identification system and properly identifies FAN devices that have the necessary control capabilities.
````

**Usage in Device Selection Flow:**

```python
# Filter to only FAN devices for humidity control
fan_devices = []
for device in discovered_devices:
    # Check if this is a FAN device (not just any HvacVentilator)
    if self._is_fan_device(device):
        fan_devices.append(device)

discovered_devices = fan_devices
```

This ensures that humidity control only works with actual fan devices that have the necessary control capabilities, providing a more accurate and user-friendly device selection experience.

### Hello World Card Device Discovery Implementation

**Key Improvement**: The hello world card feature now implements comprehensive device discovery to show ALL ramses_cc devices, not just specific device types.

```python
# Special handling for hello_world_card - show ALL ramses_cc devices
if feature_key == "hello_world_card":
    _LOGGER.info(
        f"🌍 Hello World Card - using comprehensive device discovery for ALL ramses_cc devices"
    )
    # Use a comprehensive list of all possible device types for hello world
    supported_device_types = [
        "HvacVentilator",
        "HvacCarbonDioxideSensor",
        "HvacTemperatureSensor",
        "HvacHumiditySensor",
        "HvacController",
        "Climate",
        "Fan",
        "Sensor",
        "Switch",
        "Number",
        "BinarySensor",
        # ... comprehensive list of all device types
    ]

# For hello_world_card, if no devices found, try broader discovery
if feature_key == "hello_world_card" and not discovered_devices:
    _LOGGER.info(
        f"🔍 No devices found for hello_world_card, trying broader discovery"
    )
    # Try to discover all ramses_cc devices from entity registry
    try:
        from homeassistant.helpers import entity_registry

        entity_registry_instance = entity_registry.async_get(self.hass)

        # Look for all ramses_cc entities to find devices
        ramses_devices = set()
        for entity in entity_registry_instance.entities.values():
            if (
                entity.platform == "ramses_cc"
                and hasattr(entity, "device_id")
                and entity.device_id
            ):
                ramses_devices.add(entity.device_id)

        if ramses_devices:
            _LOGGER.info(
                f"🔍 Found {len(ramses_devices)} ramses_cc devices from entity registry: {ramses_devices}"
            )

            # Create device info for each found device
            for device_id in ramses_devices:
                discovered_devices.append(
                    {
                        "device_id": device_id,
                        "device_type": "HvacVentilator",  # Default type
                        "name": f"Ramses Device {device_id}",
                        "manufacturer": "Ramses",
                        "model": "Unknown",
                        "compatible": True,
                        "zone": "Unknown",
                    }
                )
    except Exception as e:
        _LOGGER.error(
            f"❌ Failed to discover ramses_cc devices from entity registry: {e}"
        )
```

This implementation ensures that the hello world card feature serves as a comprehensive template that can work with any ramses_cc device, making it a true "hello world" starting point for other features to build upon.

**Key Technical Details:**

- The wildcard method `discover_all_ramses_cc_devices()` bypasses device type filtering entirely
- It uses `_get_device_info_wildcard()` which doesn't filter by device types
- Falls back to entity registry discovery if broker discovery fails
- Returns ALL ramses_cc devices regardless of their SLUG or device type

### Migration Priority

**Phase 1: Core Infrastructure**

1. Implement new menu-based `async_step_init()`
2. Create simple `async_step_features_management()`
3. Remove complex `async_step_features()` logic

**Phase 2: Feature Migration** 4. Create `HumidityControlConfigFlow` class 5. Create `HvacFanCardConfigFlow` class 6. Create `HelloWorldCardConfigFlow` class

**Phase 3: Cleanup** 7. Remove old monolithic config flow code 8. Clean up `pending_data` and `hass.data` usage 9. Update tests and documentation

This architecture provides a clean, scalable solution that maintains the feature-centric design while solving the entity creation timing challenge through proper menu-based configuration management.
