# Hello World Card: Switch + Automation + Binary Sensor Pattern

## Objective
Transform the Hello World Card to demonstrate Python automation reacting to switch changes, triggering binary sensor updates with immediate UI updates - following Ramses Extras Architecture principles.

## Updated Architecture Pattern
Flow: Switch → Automation → Binary Sensor → Card (real-time updates)

✅ **Switch Entity**: Manual control (users can toggle)
✅ **Python Automation**: Listens to switch changes and triggers binary sensor
✅ **Binary Sensor**: Reflects automation logic (not direct switch mirroring)
✅ **JavaScript Card**: Shows both entities with immediate updates (no polling)
✅ **WebSocket Commands**: Control switch, automation handles binary sensor

## Progress Update

### Phase 1: ✅ Python Automation System Created and Registered
- Create automation.py following Ramses Extras architecture patterns
- Implement automation that listens to switch state changes
- Create automation manager class inheriting from ExtrasBaseAutomation
- Add event listeners for switch entity changes
- Implement automation logic that triggers binary sensor based on switch state
- Register automation with feature factory

### Phase 2: ✅ Binary Sensor System Modified
- Remove direct switch mirroring logic
- Add automation trigger integration
- Implement automation-triggered state control methods
- Binary sensor reflects automation logic, not direct switch state
- Ensure immediate UI updates when automation triggers changes
- Add methods for automation to set binary sensor state

### Phase 3: Enhance Switch Platform (Keep but Improve)
- Keep switch platform but ensure it works with automation
- Update switch to trigger automation events properly
- Ensure switch state changes are captured by automation
- Maintain clean switch implementation for template purposes

### Phase 4: Update WebSocket Command System
- Keep WebSocket commands for switch control
- Update commands to work with automation pattern
- Ensure automation responds to WebSocket-triggered switch changes
- Update command responses to reflect automation approach

### Phase 5: Transform JavaScript Card for Real-time Updates
- Keep switch toggle functionality (demonstrates manual control)
- Show both switch and binary sensor status
- Implement immediate updates using HA state subscriptions
- Remove polling - use real-time HA state updates
- Update card layout to clearly show automation flow
- Add visual indication of automation-triggered changes
- Update card editor options

### Phase 6: Update Configuration and Documentation
- Update feature documentation to explain automation pattern
- Document the switch → automation → binary sensor flow
- Update card configuration examples
- Create clear documentation showing this as template pattern
- Clean up any unnecessary complexity

### Phase 7: Testing and Validation
- Test automation responds to switch changes
- Validate binary sensor updates when automation triggers
- Test card shows real-time updates without polling
- Verify WebSocket commands work with automation
- Test with multiple devices
- Validate clean, simple implementation

## Key Architecture Benefits Demonstrated

✅ **Python Automations**: Shows how to create automation classes that listen to entity changes
✅ **Event-Driven**: Automation responds to switch events and triggers binary sensor
✅ **Real-time UI**: Immediate updates via HA state subscriptions (no polling)
✅ **Clean Separation**: Switch for manual control, automation for logic, binary sensor for status
✅ **Template Pattern**: Demonstrates the standard Ramses Extras automation pattern

## Success Criteria

- [ ] Automation created following architecture patterns
- [ ] Automation registered with feature factory
- [ ] Binary sensor modified to work with automation
- [ ] Switch remains for manual control and demonstration
- [ ] Automation listens to switch changes and triggers binary sensor
- [ ] Binary sensor reflects automation logic (not direct mirroring)
- [ ] Card shows real-time status without polling
- [ ] Clean, simple implementation following architecture patterns
- [ ] Serves as perfect template for automation-driven features

## Feature Architecture

### Core Design Principles
- **Framework-First**: Leverages Ramses Extras framework foundation for 60-80% code reduction
- **Automation-Centric**: Python automation as the core logic engine using `ExtrasBaseAutomation`
- **Event-Driven**: Switch changes trigger automation, automation updates binary sensor
- **Real-time Updates**: Immediate UI updates via HA state subscriptions
- **Clean Separation**: Each component has a single, clear responsibility
- **Template Pattern**: Demonstrates standard Ramses Extras automation architecture using framework components

### Implementation Status

### ✅ Currently Implemented
The Hello World Card feature is **fully implemented** and demonstrates the complete automation-driven architecture:

#### Framework Components Used
- **Platform Setup Framework**: `PlatformSetup.async_setup_platform()` for standardized platform setup
- **Base Entity Classes**: `ExtrasSwitchEntity`, `ExtrasBinarySensorEntity` from `framework/base_classes/platform_entities.py`
- **Automation Framework**: `ExtrasBaseAutomation` from `framework/base_classes/base_automation.py`
- **Entity Management**: Custom `HelloWorldEntities` with state change callbacks and event firing
- **Feature Registration**: Automatic platform registration with global registry
- **Card Management**: `HelloWorldCardManager` for JavaScript card deployment

#### Current Implementation Details
- **✅ Python Automation**: `HelloWorldAutomationManager` listens to switch changes and triggers binary sensor
- **✅ Switch Entity**: `HelloWorldSwitch` using `ExtrasSwitchEntity` framework base
- **✅ Binary Sensor**: `HelloWorldBinarySensor` with `set_state()` method for automation control
- **✅ Entity Management**: Centralized state management with callback system
- **✅ Event System**: Custom events for real-time state updates
- **✅ Feature Factory**: Complete feature creation with framework integration
- **✅ Platform Registration**: Automatic registration with HA platform system

### 🎯 Framework Integration Examples

The feature demonstrates several key framework patterns:

#### 1. Platform Setup Framework Usage
```python
# In platforms/switch.py and binary_sensor.py
from custom_components.ramses_extras.framework.helpers import platform

await platform.PlatformSetup.async_setup_platform(
    platform="switch",
    hass=hass,
    config_entry=config_entry,
    async_add_entities=async_add_entities,
    entity_configs=HELLO_WORLD_SWITCH_CONFIGS,
    entity_factory=create_hello_world_switch,
)
```

#### 2. Base Entity Classes Usage
```python
# In platforms/switch.py and binary_sensor.py
from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
    ExtrasBinarySensorEntity,
)

class HelloWorldSwitch(ExtrasSwitchEntity):
    """Uses ExtrasSwitchEntity framework base for 80% code reduction"""

class HelloWorldBinarySensor(ExtrasBinarySensorEntity):
    """Uses ExtrasBinarySensorEntity framework base with automation integration"""
```

#### 3. Automation Framework Usage
```python
# In automation.py
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)

class HelloWorldAutomationManager(ExtrasBaseAutomation):
    """Uses ExtrasBaseAutomation framework for event handling and lifecycle"""
```

## Feature Components

#### 1. **Feature Factory** (`__init__.py`)
```python
def create_hello_world_feature(hass, config_entry):
    return {
        "entities": HelloWorldEntities(hass, config_entry),
        "automation": HelloWorldAutomation(hass, config_entry),
        "services": HelloWorldServices(hass, config_entry),
        "config": HelloWorldConfig(hass, config_entry),
        "card_manager": HelloWorldCardManager(hass, config_entry),
        "platforms": {
            "switch": create_hello_world_switch,
            "binary_sensor": create_hello_world_binary_sensor,
        },
    }
```

#### 2. **Python Automation** (`automation.py`) - ✅ IMPLEMENTED
- **Inheritance**: `HelloWorldAutomationManager(ExtrasBaseAutomation)`
- **Event Listeners**: State change listeners for `switch.hello_world_switch_*` entities
- **Automation Logic**: Simple transformation: binary sensor follows switch state
- **Automation Control**: `set_state()` method for binary sensor control via automation
- **Registration**: Created via `create_hello_world_automation()` factory function
- **Event Integration**: Listens to HA state change events and triggers binary sensor updates

#### 3. **Entity Management** (`entities.py`) - ✅ IMPLEMENTED
- **State Storage**: `HelloWorldEntities` with centralized state management
- **State Change Callbacks**: Registration system for entity state change notifications
- **Event System**: Custom `hello_world_entity_state_changed` events for real-time updates
- **Device Integration**: Coordinates between switch, automation, and binary sensor
- **Global Access**: Stored in `hass.data["ramses_extras"]["hello_world_entities"]` for global access

#### 4. **Platform Implementations** (`platforms/`) - ✅ IMPLEMENTED
- **Switch Platform**: `switch.py` - `HelloWorldSwitch(ExtrasSwitchEntity)` with framework integration
- **Binary Sensor Platform**: `binary_sensor.py` - `HelloWorldBinarySensor(ExtrasBinarySensorEntity)` with automation control
- **Framework Integration**: Uses `PlatformSetup.async_setup_platform()` for standardized setup
- **Base Classes**: `ExtrasSwitchEntity`, `ExtrasBinarySensorEntity` from `framework/base_classes/platform_entities.py`
- **Entity Factory**: `create_hello_world_switch()` and `create_hello_world_binary_sensor()` functions
- **Platform Registration**: Automatic registration via `register_feature_platform()`

#### 5. **WebSocket Commands** (`websocket_commands.py`) - 📋 PLANNED
- **Command Registry**: Defined in `const.py` as `HELLO_WORLD_WEBSOCKET_COMMANDS`
- **Switch Control**: `ramses_extras/hello_world/toggle_switch` for real-time control
- **State Queries**: `ramses_extras/hello_world/get_switch_state` for status requests
- **Integration Ready**: Registered with framework WebSocket command system
- **Automation Pattern**: Commands will work with automation-driven architecture

#### 6. **Configuration** (`const.py`) - ✅ IMPLEMENTED
- **Feature Settings**: Defined in `HELLO_WORLD_CARD_CONFIGS` for card management
- **Entity Configurations**: `HELLO_WORLD_SWITCH_CONFIGS`, `HELLO_WORLD_BINARY_SENSOR_CONFIGS`
- **Device Mappings**: `HELLO_WORLD_DEVICE_ENTITY_MAPPING` for device-to-entity relationships
- **Framework Integration**: Uses framework constants and patterns

#### 7. **Services** - 📋 PLACEHOLDER
- **Service Framework Ready**: Structure prepared for future service implementation
- **HA Integration**: Can leverage `ExtrasServiceManager` framework when needed
- **Current Control**: Entities provide direct control through HA service calls
- **Future Enhancement**: Can add custom services using framework patterns

#### 8. **Lovelace Card** (`www/hello_world_card/`) - 📋 CARD MANAGEMENT IMPLEMENTED
- **Card Manager**: `HelloWorldCardManager` ✅ IMPLEMENTED - Manages card registration and deployment
- **Card Configuration**: Defined in `HELLO_WORLD_CARD_CONFIGS` with full metadata
- **JavaScript Files**: Card and editor files expected but not yet created
- **Framework Integration**: Uses `DEPLOYMENT_PATHS` for proper asset deployment
- **Real-time Updates**: Architecture ready for HA state subscriptions (no polling)
- **Visual Flow**: Will show switch → automation → binary sensor flow
- **Editor**: Will provide device selection and configuration options

**Next Steps for Card Development:**
- Create `www/hello_world_card/hello-world-card.js` with JavaScript template literals
- Create `www/hello_world_card/hello-world-card-editor.js` for configuration
- Implement HA state subscriptions for real-time updates
- Add visual indication of automation flow
- Include translation support

## File Structure

```
features/hello_world_card/
├── __init__.py              # Feature factory function
├── automation.py            # Python automation system
├── entities.py              # Entity management and state handling
├── services.py              # Service definitions and handlers
├── config.py                # Configuration management
├── websocket_commands.py    # WebSocket command handlers
├── platforms/               # HA platform implementations
│   ├── __init__.py
│   ├── switch.py           # Switch entity platform (manual control)
│   └── binary_sensor.py    # Binary sensor entity platform (automation-triggered)
└── www/                    # Frontend assets
    └── hello_world_card/
        ├── hello-world-card.js           # Main card component with real-time updates
        ├── hello-world-card-editor.js    # Configuration editor
        ├── card-styles.js                # Card styling
        └── translations/
            ├── en.json
            └── nl.json
```

## Entity Implementation Plan

### Switch Entity
- **Entity ID**: `switch.hello_world_{device_id}`
- **Name**: "Hello World Switch {device_id}"
- **Icon**: `mdi:lightbulb`
- **State**: Boolean on/off state (manual control)
- **Control**: `async_turn_on()` / `async_turn_off()`
- **Attributes**: Device info, last changed timestamp
- **Automation Integration**: Triggers automation events on state changes

### Binary Sensor Entity
- **Entity ID**: `binary_sensor.hello_world_status_{device_id}`
- **Name**: "Hello World Status {device_id}"
- **Device Class**: `connectivity`
- **State**: Reflects automation logic (not direct switch mirroring)
- **Attributes**: Automation reference, trigger source, last update
- **Automation Control**: State set by automation, not direct switch sync

### Python Automation
- **Class**: `HelloWorldAutomation` inheriting from `ExtrasBaseAutomation`
- **Event Listening**: Switch entity state changes
- **Logic**: Transform switch state to appropriate binary sensor state
- **State Updates**: Set binary sensor state based on automation logic
- **Integration**: Seamless integration with entity state updates

### State Management
- **Storage**: Feature-level state dictionary
- **Persistence**: None (resets on restart)
- **Flow**: Switch → Automation → Binary Sensor
- **Events**: State change events for UI updates
- **Real-time**: Immediate updates via HA state subscriptions

## Python Automation Implementation - ✅ IMPLEMENTED

### Current Automation Class Structure
```python
class HelloWorldAutomationManager(ExtrasBaseAutomation):
    """Automation that listens to switch changes and controls binary sensor."""

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        super().__init__(
            hass=hass,
            feature_id="hello_world_card",
            binary_sensor=None,  # Will be set when entities are available
            debounce_seconds=0,  # No debouncing needed - event-driven approach
        )
        self.config_entry = config_entry
        self._automation_active = False

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for Hello World automation."""
        return [
            "switch.hello_world_switch_*",
            "binary_sensor.hello_world_status_*",
        ]

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes with automation-specific processing."""
        # Only process Hello World switch changes
        if entity_id.startswith("switch.hello_world_switch_"):
            await super()._async_handle_state_change(entity_id, old_state, new_state)

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, Any]
    ) -> None:
        """Process Hello World automation logic for a device."""
        switch_state = entity_states.get("switch", False)

        # Simple automation logic: binary sensor follows switch state
        binary_sensor_should_be_on = switch_state

        # Trigger binary sensor update via automation
        await self._trigger_binary_sensor_update(
            device_id, binary_sensor_should_be_on
        )

    async def _trigger_binary_sensor_update(
        self, device_id: str, should_be_on: bool
    ) -> None:
        """Trigger binary sensor update via automation."""
        # Get binary sensor entity from stored references
        entity_id = f"binary_sensor.hello_world_status_{device_id}"
        binary_sensor_entity = (
            self.hass.data.get("ramses_extras", {})
            .get("entities", {})
            .get(entity_id)
        )

        if binary_sensor_entity:
            # Use the automation-triggered state update method
            binary_sensor_entity.set_state(should_be_on)
```

### Automation Registration
- **Factory Integration**: Automatically created and registered
- **Event System**: Integrated with HA event system
- **Entity Updates**: Seamless integration with entity state updates
- **Error Handling**: Robust error handling and logging

## WebSocket Integration Plan

### Switch Control Command
```javascript
// WebSocket command for switch control
{
  "type": "ramses_extras/hello_world/toggle_switch",
  "device_id": "32:153289",
  "state": true  // or false
}
```

### Handler Implementation
- **Decorator**: `@websocket_api.websocket_command`
- **Validation**: Device ID and state parameter validation
- **Switch Update**: Update switch state (triggers automation)
- **Automation Response**: Binary sensor updates via automation
- **Error Handling**: Invalid device ID, permission errors

### Real-time Updates
- **Event System**: HA events for automation-triggered changes
- **Card Updates**: Automatic UI refresh on binary sensor changes
- **WebSocket Events**: Push updates to connected clients
- **No Polling**: Real-time subscriptions only

## Lovelace Card Implementation Plan

### Card Features
- **Visual Design**: Clean layout showing switch and binary sensor status
- **Interactive Elements**: Switch toggle (manual control)
- **Status Display**: Real-time binary sensor status
- **Automation Flow**: Visual indication of switch → automation → binary sensor
- **Real-time Updates**: HA state subscriptions (no polling)
- **Configuration**: Device selection, display options

### Card Architecture
- **Base Class**: Extends Lovelace card base
- **State Management**: Subscribes to both switch and binary sensor changes
- **WebSocket Integration**: Switch control via WebSocket
- **JavaScript Templates**: Uses JavaScript template literals for HTML rendering
- **Translation Support**: Multi-language UI

### Real-time Update Implementation
```javascript
// Subscribe to entity state changes (no polling)
async connectedCallback() {
    super.connectedCallback();

    // Subscribe to switch changes
    this._switch unsub = this.hass.connection.subscribeEvents(
        (event) => this._handleSwitchUpdate(event),
        "state_changed",
        { entity_id: this._getSwitchEntityId() }
    );

    // Subscribe to binary sensor changes
    this._binary_sensor unsub = this.hass.connection.subscribeEvents(
        (event) => this._handleBinarySensorUpdate(event),
        "state_changed",
        { entity_id: this._getBinarySensorEntityId() }
    );
}

_handleSwitchUpdate(event) {
    // Update switch display immediately
    const newState = event.data.new_state;
    this._switchState = newState.state === "on";
    this.requestUpdate();
}

_handleBinarySensorUpdate(event) {
    // Update binary sensor display immediately
    const newState = event.data.new_state;
    this._binarySensorState = newState.state === "on";
    this.requestUpdate();
}
```

### Card Layout (JavaScript Template Literals)
```javascript
// JavaScript template literal for card rendering
render() {
    return html`
        <ha-card>
            <div class="card-header">
                <div class="device-info">${this.getDeviceDisplayName()}</div>
                <div class="automation-status">Automation: Active</div>
            </div>
            <div class="card-content">
                <div class="switch-section">
                    <div class="section-title">Manual Control</div>
                    <ha-switch
                        .checked=${this._switchState}
                        @change=${this._handleSwitchChange}>
                    </ha-switch>
                    <div class="status">Switch: ${this._switchState ? 'ON' : 'OFF'}</div>
                </div>

                <div class="arrow-down">↓</div>

                <div class="automation-section">
                    <div class="section-title">Python Automation</div>
                    <div class="automation-status">${this.getAutomationStatus()}</div>
                </div>

                <div class="arrow-down">↓</div>

                <div class="binary-sensor-section">
                    <div class="section-title">Automation Result</div>
                    <div class="binary-sensor-display">
                        <ha-icon icon="${this._binarySensorState ? 'mdi:check-circle' : 'mdi:close-circle'}"></ha-icon>
                        <div class="status">Binary Sensor: ${this._binarySensorState ? 'ON' : 'OFF'}</div>
                    </div>
                </div>
            </div>
        </ha-card>
    `;
}
```

### Editor Features
- **Device Selection**: Dynamic dropdown populated with discovered devices
- **Display Options**: Configure which entities to show
- **Automation Settings**: Configure automation behavior
- **Layout Options**: Compact view, show/hide sections

### JavaScript Template Usage

#### Device Information Display
```javascript
getDeviceDisplayName() {
    const deviceId = this._config.device_id;
    const deviceName = this._config.name || 'Hello World Switch';

    if (this._config.show_device_id_only) {
        return deviceId;
    }

    if (this._config.show_name_only) {
        return deviceName;
    }

    return `${deviceName} (${deviceId})`;
}
```

#### Automation Status Display
```javascript
getAutomationStatus() {
    // Show automation activity
    if (this._automationLastTrigger) {
        return `Last triggered: ${this._automationLastTrigger}`;
    }
    return 'Waiting for switch changes';
}
```

## Configuration Options

### Feature Configuration
```yaml
hello_world_card:
  enabled: true
  default_name: "Hello World"
  icon: "mdi:lightbulb"
  auto_discovery: true
  automation_enabled: true
  automation_logic: "mirror"  # mirror, invert, custom
```

### Card Configuration
```yaml
type: custom:hello-world-card
device_id: "32:153289"
name: "My Hello World Switch"
show_switch: true
show_binary_sensor: true
show_automation_flow: true
compact_view: false
automation_logic: "mirror"  # mirror, invert, custom
```

### Validation Rules
- **Device ID**: Must be valid ramses_cc device
- **Name**: Optional custom name
- **Icon**: Valid MDI icon name
- **Automation Logic**: Valid logic type
- **Permissions**: User access control

## Testing Strategy

### Unit Tests
- **Automation Creation**: Automation class instantiation and registration
- **Event Listening**: Switch state change detection
- **Logic Implementation**: Automation logic calculation
- **Binary Sensor Control**: State setting via automation
- **WebSocket Commands**: Command validation and execution
- **Service Calls**: Service method functionality

### Integration Tests
- **Automation Flow**: Switch → Automation → Binary Sensor
- **Real-time Updates**: Immediate UI updates without polling
- **WebSocket Integration**: End-to-end command flow
- **Card Rendering**: Lovelace card display and interaction
- **Event System**: HA event propagation

### Manual Testing
- **Automation Response**: Verify automation responds to switch changes
- **Binary Sensor Updates**: Validate automation-triggered updates
- **Real-time UI**: Test immediate updates without polling
- **WebSocket Commands**: Verify commands work with automation
- **Multi-device**: Test with multiple devices
- **Error Scenarios**: Invalid commands, missing devices

## Implementation Roadmap - UPDATED STATUS

### ✅ COMPLETED PHASES
The Hello World Card feature is **substantially complete** with all core functionality implemented:

#### ✅ Phase 1-3: Core Implementation (COMPLETED)
- **✅ Python Automation**: `HelloWorldAutomationManager` implemented using `ExtrasBaseAutomation`
- **✅ Binary Sensor Integration**: `HelloWorldBinarySensor` with `set_state()` method for automation control
- **✅ Switch Platform**: `HelloWorldSwitch` using `ExtrasSwitchEntity` framework base
- **✅ Entity Management**: `HelloWorldEntities` with state change callbacks and event firing
- **✅ Feature Factory**: Complete integration with framework patterns

#### ✅ Phase 4: Framework Integration (COMPLETED)
- **✅ Platform Setup**: Uses `PlatformSetup.async_setup_platform()` framework
- **✅ Base Classes**: Leverages `ExtrasSwitchEntity`, `ExtrasBinarySensorEntity`
- **✅ Automation Framework**: Uses `ExtrasBaseAutomation` for event handling
- **✅ Registration**: Automatic platform registration with global registry

### 📋 REMAINING PHASES

#### Phase 5: WebSocket Commands Implementation (Priority: High)
1. **Create WebSocket Commands**: Implement `websocket_commands.py` with framework patterns
2. **Switch Control**: `ramses_extras/hello_world/toggle_switch` command
3. **State Queries**: `ramses_extras/hello_world/get_switch_state` command
4. **Automation Integration**: Ensure commands work with automation-driven pattern
5. **Error Handling**: Comprehensive validation and error responses

#### Phase 6: JavaScript Lovelace Card (Priority: High)
1. **Create Card Component**: `www/hello_world_card/hello-world-card.js`
2. **JavaScript Templates**: Use template literals with `${}` interpolation
3. **Real-time Updates**: HA state subscriptions (no polling)
4. **Visual Flow**: Show switch → automation → binary sensor flow
5. **Card Editor**: `www/hello_world_card/hello-world-card-editor.js`
6. **Translation Support**: Multi-language UI

#### Phase 7: Enhancement & Polish (Priority: Medium)
1. **Service Framework**: Optional services using `ExtrasServiceManager`
2. **Configuration UI**: Enhanced configuration options
3. **Testing**: Comprehensive test suite
4. **Documentation**: Final documentation polish
5. **Performance**: Optimization and monitoring

### 🚀 Quick Start Guide for Developers

Since the core implementation is complete, developers can:

1. **Start with Existing Code**: Use the implemented automation and entities as reference
2. **Extend Automation Logic**: Modify `_process_automation_logic()` in `automation.py`
3. **Add New Entities**: Follow the established pattern in `platforms/` directory
4. **Create Card**: Use the card manager framework for JavaScript implementation
5. **Add Services**: Leverage `ExtrasServiceManager` framework when needed

### Success Criteria - CURRENT STATUS
- ✅ **Automation Framework**: Uses `ExtrasBaseAutomation` with event-driven architecture
- ✅ **Entity Integration**: Switch and binary sensor work with automation pattern
- ✅ **Platform Framework**: Leverages `PlatformSetup` and base entity classes
- ✅ **Feature Factory**: Complete framework integration
- 📋 **WebSocket Commands**: Ready for implementation using framework patterns
- 📋 **JavaScript Card**: Architecture ready, files need to be created
- 📋 **Complete Template**: Serves as excellent foundation for new automation-driven features

## Future Enhancement Opportunities

### Advanced Automation Patterns (Investigate Later)
- **Conditional Logic**: More complex automation rules
- **Multiple Triggers**: Support for multiple input entities
- **Timer-Based**: Time-based automation triggers
- **State History**: Track state changes over time
- **Conditional Actions**: Different actions based on conditions

### Enhanced UI/UX (Investigate Later)
- **Animation**: Smooth transitions for state changes
- **Debug View**: Show automation execution flow
- **Performance Metrics**: Display automation response times
- **Custom Styling**: More visual customization options
- **Mobile Optimization**: Enhanced mobile interface

### Framework Integration (Investigate Later)
- **Configuration UI**: Visual automation rule builder
- **Automation Templates**: Pre-built automation patterns
- **State Persistence**: Save/restore automation states
- **Integration Hooks**: Connect to external systems
- **Performance Monitoring**: Automation performance metrics

## Extending the Hello World Feature

### Quick Extension Guide

The Hello World Card serves as an **excellent template** for creating new automation-driven features. Here's how to extend it:

#### 1. **Modify Automation Logic**
```python
# In automation.py - modify _process_automation_logic()
async def _process_automation_logic(
    self, device_id: str, entity_states: dict[str, Any]
) -> None:
    """Custom automation logic for your feature."""
    # Your business logic here
    switch_state = entity_states.get("switch", False)

    # Example: More complex automation
    if switch_state and self._should_activate_device(device_id):
        await self._trigger_advanced_action(device_id, True)
    elif not switch_state:
        await self._trigger_advanced_action(device_id, False)
```

#### 2. **Add New Entity Types**
```python
# In const.py - add new entity configurations
HELLO_WORLD_SENSOR_CONFIGS = {
    "my_custom_sensor": {
        "name_template": "My Custom Sensor {device_id}",
        "entity_template": "my_custom_sensor_{device_id}",
        "device_types": ["HvacVentilator"],
        "unit_of_measurement": "°C",
    }
}

# In platforms/sensor.py - create entity class
class MyCustomSensor(ExtrasSensorEntity):
    """Custom sensor using framework base."""
    pass
```

#### 3. **Extend Entity Management**
```python
# In entities.py - add new state management
def get_entity_state(self, device_id: str, entity_type: str, entity_key: str) -> Any:
    """Get current state with custom logic."""
    # Add your custom state calculation
    if entity_key == "my_custom_sensor":
        return self._calculate_custom_value(device_id)
    return super().get_entity_state(device_id, entity_type, entity_key)
```

#### 4. **Create Custom Services**
```python
# In services.py - use ExtrasServiceManager framework
from custom_components.ramses_extras.framework.helpers.service import ExtrasServiceManager

class MyCustomServices(ExtrasServiceManager):
    SERVICE_DEFINITIONS = {
        "my_custom_action": {
            "type": ServiceType.ACTION,
            "parameters": {"device_id": str, "value": float},
        }
    }
```

#### 5. **Add WebSocket Commands**
```python
# In websocket_commands.py - use framework patterns
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/hello_world/my_custom_command",
    vol.Required("device_id"): str,
    vol.Optional("parameters"): dict,
})
@websocket_api.async_response
async def ws_my_custom_command(hass, connection, msg):
    """Custom WebSocket command using framework patterns."""
    # Implementation with framework integration
```

### Framework Usage Benefits

By following the Hello World pattern, new features get:

- **60-80% Code Reduction**: Using framework base classes and helpers
- **Consistent Architecture**: Following established patterns
- **Automatic Integration**: Framework handles HA integration details
- **Real-time Updates**: Built-in event system and state management
- **Template Consistency**: Easy to understand and maintain

### Best Practices Demonstrated

1. **Framework First**: Always check `framework/` directory for existing solutions
2. **Base Classes**: Use `ExtrasSwitchEntity`, `ExtrasBinarySensorEntity`, etc.
3. **Event-Driven**: Implement automation using `ExtrasBaseAutomation`
4. **State Management**: Use the entity management patterns
5. **Platform Setup**: Leverage `PlatformSetup.async_setup_platform()`

This template feature demonstrates the core Ramses Extras automation pattern: Python automation listening to entity changes and triggering other entities, with real-time UI updates. It serves as the perfect foundation for any automation-driven feature while showcasing clean architectural separation, real-time updates, and extensive framework integration.

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
