# Enhanced Device Discovery Architecture

## Overview

This document outlines the planned enhancement to the Ramses Extras device discovery and entity management system. The new architecture will provide better separation of concerns, enable brand-specific entity management, and improve extensibility for future device types.

## Current Architecture Analysis

### Current Flow

1. **Device Discovery**: Loop through `AVAILABLE_FEATURES` to find matching device type
2. **Feature Handler**: Call handler from feature configuration (currently all features use same handler)
3. **Entity Check**: Use EntityRegistry to determine if device should have entities
4. **Entity Creation**: Store device IDs, create entities during platform setup

### Current Limitations

- Handler duplication across features supporting same device type
- No post-discovery entity modification capabilities
- No brand-specific logic or customization
- Complex feature dependency on handler configuration

## Enhanced Architecture

### 1. Device Type Handler Mapping

**Framework Level**: Create central mapping from device types to handlers

```python
# Framework mapping (const.py)
DEVICE_TYPE_HANDLERS = {
    "HvacVentilator": "handle_hvac_ventilator",
    "HvacController": "handle_hvac_controller",  # Future device type
    "Thermostat": "handle_thermostat",           # Future device type
}
```

**Benefits:**

- Single source of truth for device handling
- Easy to add new device types
- No handler duplication
- Clear separation between device handling and feature logic

### 2. Event System

**Event Name**: `ramses_device_ready_for_entities`

**Timing**: After device handler completes but BEFORE entity creation

**Event Data**:

```python
{
    "device_id": "32:153289",
    "device_type": "HvacVentilator",
    "device_object": device,  # Full device object for inspection
    "entity_ids": ["sensor.indoor_absolute_humidity_32_153289", ...],  # Entities that will be created
    "handled_by": "humidity_control"  # Which feature called the handler
}
```

**Benefits:**

- Features can respond to device discovery
- Access to full device object for brand/model inspection
- Timing allows entity list modification before creation
- Event-based extensibility

### 3. Double Evaluation System

**Phase 1 - Discovery**:

- Discover devices that should have entities
- Fire event for each discovered device
- Listeners can modify EntityRegistry or set flags

**Phase 2 - Creation**:

- Platform setup creates entities
- Check entity-specific flags before creation
- Apply any modifications from event listeners

### 4. Entity Configuration Enhancement

**New Flag**: `default_enabled` in all entity configurations

**Example**:

```python
# Feature const.py files
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify {device_id}",
        "default_enabled": True,  # NEW: defaults to True for existing entities
        "entity_template": "dehumidify_{device_id}",
        # ... other config
    }
}
```

**Benefits**:

- Runtime entity filtering
- Brand-specific entity enable/disable
- Safe default behavior (True maintains current behavior)

### 5. Event Listener Pattern

**Example Implementation**:

```python
# Feature event listener
async def on_device_ready_for_entities(event_data):
    """Handle device discovery for brand-specific logic."""
    device = event_data["device_object"]

    # Log device discovery (proof of concept)
    _LOGGER.info(f"Device {device.id} ({device.model}) ready for entity creation")

    # Brand-specific logic (future implementation)
    if "orcon" in device.model.lower():
        # Enable brand-specific features
        # Modify entity configurations
        # Set default values
        pass
```

## Implementation Plan

### Phase 1: Framework Changes

1. Add `DEVICE_TYPE_HANDLERS` mapping in `const.py`
2. Update `_handle_device` to use device type mapping
3. Add event firing after successful device handling
4. Test framework changes

### Phase 2: Entity Configuration Updates

1. Add `default_enabled: True` to all existing entity configurations
2. Update EntityRegistry to include flag in configuration data
3. Verify existing entities maintain current behavior

### Phase 3: Platform Integration

1. Update platform entity creation to check `default_enabled` flag
2. Ensure entities respect configuration flags
3. Test entity filtering functionality

### Phase 4: Event Listeners

1. Create proof-of-concept event listener in humidity_control feature
2. Log device discovery information
3. Test brand-specific logic framework

### Phase 5: Testing & Validation

1. Test single event per device discovery
2. Verify entity filtering with disabled flags
3. Validate performance impact
4. Test brand-specific entity modification

## Benefits Summary

### Technical Benefits

- **Cleaner Architecture**: Separation of device handling and feature logic
- **Reduced Duplication**: Single handler per device type
- **Runtime Flexibility**: Entity list modification before creation
- **Extensibility**: Easy addition of new device types and brands

### Feature Benefits

- **Brand-Specific Logic**: Device model detection and customization
- **Configurable Entities**: Runtime enable/disable based on device capabilities
- **Enhanced Automation**: Brand-specific automation patterns
- **Better User Experience**: Optimized entity sets per device brand

### Maintenance Benefits

- **Single Source of Truth**: Device type mappings in one place
- **Event-Based Notifications**: Easy debugging and monitoring
- **Safe Defaults**: Backward compatibility maintained
- **Gradual Migration**: Can implement incrementally

## Technical Considerations

### Performance

- Single event per device discovery (not per feature)
- Efficient flag checking during entity creation
- No impact on existing device discovery performance

### Compatibility

- `default_enabled: True` maintains current behavior
- Existing features work without modification
- Optional event listeners (features can ignore events)

### Future Extensibility

- Easy addition of new device types
- Plugin pattern for brand-specific logic
- Event system can support multiple listeners
- EntityRegistry modification API (planned for later)

## Migration Strategy

1. **Start with Framework**: Implement device type mapping and events
2. **Maintain Compatibility**: All existing entities default to enabled
3. **Gradual Enhancement**: Add event listeners incrementally
4. **Brand Logic**: Implement brand-specific features over time

## Conclusion

This enhanced architecture provides a robust foundation for device discovery and entity management while maintaining backward compatibility and enabling powerful new capabilities for brand-specific customization and runtime entity management.

The design emphasizes simplicity, extensibility, and clear separation of concerns, making it easier to maintain and enhance the Ramses Extras integration over time.
