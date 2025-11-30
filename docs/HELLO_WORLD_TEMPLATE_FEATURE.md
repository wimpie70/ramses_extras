# Template Feature Plan: Hello World Switch Card

## Overview
Create a simple "Hello World" feature that demonstrates the complete Ramses Extras feature architecture. The feature provides:
- **1 Switch Entity**: Controls a virtual device state
- **1 Binary Sensor**: Mirrors the switch state for status indication
- **WebSocket Command**: Remote control of the switch
- **Lovelace Card**: UI for monitoring and controlling the switch

This serves as a minimal but complete template for new features.

## Feature Architecture

### Core Design Principles
- **Feature-Centric**: Self-contained module with all components
- **Framework Integration**: Uses existing base classes and helpers
- **Simple State Management**: In-memory state (no persistence needed)
- **WebSocket Integration**: Real-time control via HA WebSocket API
- **UI Components**: Lovelace card with reactive updates

### Feature Components

#### 1. **Feature Factory** (`__init__.py`)
```python
def create_hello_world_feature(hass, config_entry):
    return {
        "entities": HelloWorldEntities(hass, config_entry),
        "services": HelloWorldServices(hass, config_entry),
        "config": HelloWorldConfig(hass, config_entry),
        "card_manager": HelloWorldCardManager(hass, config_entry),
        "platforms": {
            "switch": create_hello_world_switch,
            "binary_sensor": create_hello_world_binary_sensor,
            "sensor": create_hello_world_sensor,  # Placeholder
            "number": create_hello_world_number,  # Placeholder
        },
    }
```

#### 2. **Entity Management** (`entities.py`)
- **State Storage**: Simple dict-based state management
- **Device Linking**: Links entities to ramses_cc devices
- **Event Handling**: Responds to device discovery events

#### 3. **Platform Implementations** (`platforms/`)
- **Switch Platform**: `switch.py` - Toggle control entity
- **Binary Sensor Platform**: `binary_sensor.py` - Status indicator entity
- **Sensor Platform**: `sensor.py` - Optional sensor readings (placeholder)
- **Number Platform**: `number.py` - Optional numeric controls (placeholder)
- **Base Classes**: Inherit from `ExtrasSwitchEntity`, `ExtrasBinarySensorEntity`, `ExtrasSensorEntity`, `ExtrasNumberEntity`

#### 4. **WebSocket Commands** (`websocket_commands.py`)
- **Command Handler**: `@websocket_api.websocket_command` decorated function
- **State Updates**: Real-time switch control via WebSocket
- **Response Format**: Standard HA WebSocket response pattern

#### 5. **Configuration** (`config.py`)
- **Feature Settings**: Enable/disable, naming, device selection
- **Validation**: Input validation and defaults
- **UI Schema**: Configuration flow options

#### 6. **Services** (`services.py`)
- **Switch Control**: Service calls for programmatic control
- **State Queries**: Get current switch state
- **Bulk Operations**: Control multiple switches

#### 7. **Lovelace Card** (`www/hello_world_card/`)
- **Card Component**: `hello-world-card.js` - Main card logic
- **Editor**: `hello-world-card-editor.js` - Configuration UI
- **Templates**: HTML templates for card layout
- **Translations**: Multi-language support
- **Styles**: Card-specific CSS styling

## File Structure

```
features/hello_world_card/
├── __init__.py              # Feature factory function
├── const.py                 # Feature constants and configurations
├── entities.py              # Entity management and state handling
├── services.py              # Service definitions and handlers
├── config.py                # Configuration management
├── websocket_commands.py    # WebSocket command handlers
├── platforms/               # HA platform implementations
│   ├── __init__.py
│   ├── switch.py           # Switch entity platform
│   ├── binary_sensor.py    # Binary sensor entity platform
│   ├── sensor.py           # Sensor entity platform (placeholder)
│   └── number.py           # Number entity platform (placeholder)
└── www/                    # Frontend assets
    └── hello_world_card/
        ├── hello-world-card.js           # Main card component
        ├── hello-world-card-editor.js    # Configuration editor with device selection
        ├── card-styles.js                # Card styling
        ├── templates/
        │   ├── card.html
        │   └── editor.html
        └── translations/
            ├── en.json
            └── nl.json
```

## Entity Implementation Plan

### Switch Entity
- **Entity ID**: `switch.hello_world_{device_id}`
- **Name**: "Hello World Switch {device_id}"
- **Icon**: `mdi:lightbulb`
- **State**: Boolean on/off state
- **Control**: `async_turn_on()` / `async_turn_off()`
- **Attributes**: Device info, last changed timestamp

### Binary Sensor Entity
- **Entity ID**: `binary_sensor.hello_world_status_{device_id}`
- **Name**: "Hello World Status {device_id}"
- **Device Class**: `connectivity`
- **State**: Mirrors switch state (on/off)
- **Attributes**: Switch entity reference, sync status

### State Management
- **Storage**: Feature-level state dictionary
- **Persistence**: None (resets on restart)
- **Synchronization**: Binary sensor auto-syncs with switch
- **Events**: State change events for UI updates

### Placeholder Platforms (Sensor & Number)
The template includes empty placeholder implementations for sensor and number platforms. These are not functional by default but provide a starting point for extending the feature:

#### Sensor Platform Placeholder
- **Purpose**: For reading device values (temperature, humidity, etc.)
- **Entity ID**: `sensor.hello_world_reading_{device_id}`
- **Implementation**: Extend `ExtrasSensorEntity` when adding sensor functionality

#### Number Platform Placeholder
- **Purpose**: For adjustable numeric settings (setpoints, timers, etc.)
- **Entity ID**: `number.hello_world_setting_{device_id}`
- **Implementation**: Extend `ExtrasNumberEntity` when adding numeric controls

## WebSocket Integration Plan

### Command Definition
```javascript
// WebSocket command
{
  "type": "ramses_extras/hello_world/toggle_switch",
  "device_id": "32:153289",
  "state": true  // or false
}
```

### Handler Implementation
- **Decorator**: `@websocket_api.websocket_command`
- **Validation**: Device ID and state parameter validation
- **State Update**: Update feature state and trigger entity updates
- **Response**: Success/failure with current state
- **Error Handling**: Invalid device ID, permission errors

### Real-time Updates
- **Event System**: HA events for state changes
- **Card Updates**: Automatic UI refresh on state changes
- **WebSocket Events**: Push updates to connected clients

### Device Discovery Command
For card editors to populate device selection dropdowns, a centralized WebSocket command should be implemented:

```javascript
// Command to get available Ramses RF devices
{
  "type": "ramses_extras/get_available_devices"
}

// Response format
{
  "devices": [
    {
      "device_id": "32:153289",
      "device_type": "HvacVentilator",
      "model": "Orcon HRV400",
      "capabilities": ["fan_control", "humidity_sensor"]
    }
  ]
}
```

**Implementation Strategy:**
- Add this command to the `default` feature's WebSocket commands (shared utility)
- Refactor existing `hvac_fan_card` editor to use this centralized approach
- Use ramses_cc broker to get accurate device information
- Include device capabilities for better filtering

**Default Feature WebSocket Command Implementation:**
```python
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/get_available_devices",
})
@websocket_api.async_response
async def ws_get_available_devices(hass, connection, msg):
    """Get list of all discovered Ramses RF devices for card editors."""
    try:
        # Get ramses_cc broker
        broker = await _get_broker_for_entry(hass)

        devices = []
        for device in broker.devices:
            devices.append({
                "device_id": device.id,
                "device_type": device.__class__.__name__,
                "model": getattr(device, "model", "Unknown"),
                "capabilities": _get_device_capabilities(device),
            })

        connection.send_result(msg["id"], {"devices": devices})

    except Exception as error:
        connection.send_error(msg["id"], "device_discovery_error", str(error))
```

**Benefits over current hvac_fan_card approach:**
- More reliable device detection using backend data
- Consistent device listing across all card editors
- Richer device metadata (model, capabilities)
- Easier maintenance and debugging

## Lovelace Card Implementation Plan

### Card Features
- **Visual Design**: Clean, modern card layout with device information display
- **Interactive Elements**: Toggle switch, status indicator
- **Device Information**: Shows device ID, name, or both using JavaScript templates
- **Real-time Updates**: Live state synchronization
- **Configuration**: Device selection, display options
- **Responsive**: Mobile-friendly design

### Card Architecture
- **Base Class**: Extends Lovelace card base
- **State Management**: Subscribes to entity state changes
- **WebSocket Integration**: Direct command sending
- **Template System**: Configurable layouts
- **Translation Support**: Multi-language UI

### Editor Features
- **Device Selection**: Dynamic dropdown populated with all discovered Ramses RF devices
- **Device Discovery**: Automatically fetches available devices via WebSocket API
- **Device Validation**: Ensures selected device exists and is compatible
- **Display Options**: Custom name, device ID display modes (ID only, name only, or both)
- **Layout Customization**: Compact view, status display options
- **Real-time Validation**: Immediate feedback on configuration changes
- **Live Preview**: Card preview updates as configuration changes

### Editor Implementation Details

#### Device Discovery Integration
The card editor should use a centralized WebSocket command for device discovery (to be implemented). This approach is better than the current hvac_fan_card method because:

- **Centralized Logic**: Device discovery happens on the backend, not client-side heuristics
- **Reliable Data**: Uses actual ramses_cc device registry instead of HA device registry
- **Rich Metadata**: Includes device type, model, and capabilities
- **Reusable**: Multiple card editors can use the same command

```javascript
// Fetch available Ramses RF devices for selection
async getDeviceOptions() {
    try {
        const response = await this.callWebSocket({
            type: 'ramses_extras/get_available_devices'
        });
        return response.devices.map(device => ({
            value: device.device_id,
            label: `${device.device_id} (${device.device_type})`
        }));
    } catch (error) {
        console.warn('Failed to fetch devices, falling back to HA registry');
        return this._getDevicesFromHARegistry(); // Fallback method
    }
}
```

**Note**: The existing `hvac_fan_card` currently uses client-side device discovery via HA registry. For consistency and better reliability, both cards should be refactored to use the new centralized WebSocket command.

#### Configuration Schema
```javascript
getConfigElement() {
    return {
        type: 'custom:hello-world-card',
        device_id: '',  // Selected from device dropdown
        name: 'Hello World Switch',
        show_status: true,
        compact_view: false
    };
}
```

#### Dynamic Device Selection
- **WebSocket Call**: `ramses_extras/get_available_devices` to fetch device list
- **Dropdown Population**: Device IDs with type information (e.g., "32:153289 (HvacVentilator)")
- **Validation**: Ensures selected device exists before saving
- **Auto-refresh**: Updates device list when new devices are discovered

### JavaScript Template Usage Example

#### Device Information Display
The card demonstrates practical JavaScript template usage for displaying device information:

```javascript
// Template function to format device display
getDeviceDisplayName() {
    const deviceId = this._config.device_id;
    const deviceName = this._config.name || 'Hello World Switch';

    // Option 1: Show device ID only
    if (this._config.show_device_id_only) {
        return deviceId;
    }

    // Option 2: Show custom name only
    if (this._config.show_name_only) {
        return deviceName;
    }

    // Option 3: Show both (default)
    return `${deviceName} (${deviceId})`;
}

// HTML template with dynamic device info
render() {
    const deviceDisplay = this.getDeviceDisplayName();
    const switchState = this.getSwitchState();

    return html`
        <ha-card>
            <div class="card-header">
                <div class="device-info">${deviceDisplay}</div>
            </div>
            <div class="card-content">
                <div class="switch-container">
                    <ha-switch
                        .checked=${switchState}
                        @change=${this._handleSwitchChange}>
                    </ha-switch>
                    <div class="status">
                        Status: ${switchState ? 'ON' : 'OFF'}
                    </div>
                </div>
            </div>
        </ha-card>
    `;
}
```

#### Template Configuration Options
```javascript
// Card configuration options for display customization
getConfigElement() {
    return {
        type: 'custom:hello-world-card',
        device_id: '',
        name: 'Hello World Switch',
        show_device_id_only: false,    // Show only device ID
        show_name_only: false,         // Show only custom name
        show_both: true               // Show "Name (Device ID)" format
    };
}
```

This demonstrates how to use JavaScript templates for dynamic content rendering, conditional display logic, and configuration-driven customization.

## Configuration Options

### Feature Configuration
```yaml
hello_world_card:
  enabled: true
  default_name: "Hello World"
  icon: "mdi:lightbulb"
  auto_discovery: true
```

### Card Configuration
```yaml
type: custom:hello-world-card
device_id: "32:153289"
name: "My Hello World Switch"
show_device_id_only: false    # Show only device ID
show_name_only: false         # Show only custom name
show_both: true              # Show "Name (Device ID)" format
show_status: true
compact_view: false
```

### Validation Rules
- **Device ID**: Must be valid ramses_cc device
- **Name**: Optional custom name
- **Icon**: Valid MDI icon name
- **Permissions**: User access control

## Testing Strategy

### Unit Tests
- **Entity Creation**: Switch and binary sensor instantiation
- **State Management**: State changes and synchronization
- **WebSocket Commands**: Command validation and execution
- **Service Calls**: Service method functionality

### Integration Tests
- **HA Integration**: Entity registration and discovery
- **WebSocket API**: End-to-end command flow
- **Card Rendering**: Lovelace card display and interaction
- **Configuration Flow**: Feature enable/disable

### Manual Testing
- **UI Interaction**: Card controls and state updates
- **Device Discovery**: Automatic entity creation
- **Multi-device**: Multiple switches on different devices
- **Error Scenarios**: Invalid commands, missing devices

## Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1)
1. Create feature directory structure with all platform placeholders
2. Implement basic `__init__.py` factory with all platform registrations
3. Add feature to `AVAILABLE_FEATURES` registry
4. Create `const.py` with basic configurations
5. Implement simple state management
6. Create empty placeholder implementations for sensor and number platforms

### Phase 2: Entity Implementation (Week 2)
1. Create switch platform with `ExtrasSwitchEntity`
2. Create binary sensor platform with `ExtrasBinarySensorEntity`
3. Implement entity state synchronization
4. Add device discovery integration
5. Test entity creation and basic functionality

### Phase 3: WebSocket Integration (Week 3)
1. Implement WebSocket command handler for hello world feature
2. Add command validation and error handling
3. Integrate with entity state updates
4. Test WebSocket API functionality
5. Add real-time event broadcasting
6. **Bonus**: Implement centralized device discovery command in default feature
7. **Bonus**: Refactor existing hvac_fan_card editor to use centralized device discovery

### Phase 4: Lovelace Card (Week 4)
1. Create card JavaScript component
2. Implement card editor interface
3. Add template and styling system
4. Integrate WebSocket commands in card
5. Test card rendering and interaction

### Phase 5: Configuration & Polish (Week 5)
1. Implement configuration management
2. Add service definitions
3. Create comprehensive tests
4. Add documentation and examples
5. Final integration testing

### Success Criteria
- ✅ Feature appears in HA configuration flow
- ✅ Switch and binary sensor entities auto-create
- ✅ WebSocket commands control switch state
- ✅ Lovelace card displays and controls switch
- ✅ Real-time state synchronization
- ✅ Comprehensive test coverage
- ✅ Clean, documented code following patterns

## Future Enhancement Opportunities

### Framework Integration Improvements (Investigate Later)
- **Brand Customization Hooks**: Placeholder for device-specific customizations
- **Service Framework Usage**: Leverage ExtrasServiceManager for consistency
- **Entity Lifecycle Management**: Use EntityLifecycleManager for proper cleanup
- **Configuration Validation**: Use ConfigValidator for robust settings

*Note: These framework improvements should be investigated in a separate planning session to determine which ones to include in the base template vs. as optional extensions.*

### Testing & Documentation Enhancements (Investigate Later)
- **Comprehensive Test Coverage**: Unit, integration, and error scenario tests
- **Inline Documentation**: Clear code comments and API docs
- **Usage Examples**: Practical implementation examples
- **Troubleshooting Guide**: Common issues and solutions

*Note: Enhanced testing and documentation should be planned separately to ensure the template remains focused on core functionality while providing guidance for comprehensive testing strategies.*

### Advanced Features & Performance (Investigate Later)
- **Device Grouping**: Support for controlling multiple devices as a group
- **Scheduling**: Time-based automation for device control
- **Energy Monitoring**: Power consumption tracking and reporting
- **Performance Optimizations**: Caching, lazy loading, connection pooling
- **Enhanced UX**: Loading states, animations, keyboard navigation
- **Integration Options**: Third-party APIs, cloud services, mobile apps

*Note: These advanced features represent future enhancement opportunities. A separate architectural planning session should evaluate which features to prioritize and how they integrate with the core template.*

This template feature provides a complete, working example that new developers can use as a starting point for their own features while demonstrating all key Ramses Extras architectural patterns and best practices. The modular design allows for easy extension with additional capabilities as needed.

## Guidelines

- all projects (ramses_extras, -_cc, -rf) have their own venv, eg: ~/venvs/_cc
- usage: source ~/venvs/extras/bin/activate
- tests should pass local (make local-ci) and also on github
- log files: /home/willem/docker_files/hass/config/home-assistant.log /home/willem/docker_files/hass/config/ramses_log
- run tests like: cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && python3 tests/managers/test_humidity_automation.py"
- Python: don't import/use old Dict, List, Optional, etc... just use dict, list, optional, etc..
- Python: make sure the lines are not exceeding the linelenghts (ruff/mypy)
- Backward compatible: we don't need that for now.

- ramses_extras: always read RAMSES_EXTRAS_ARCHITECTURE.md
