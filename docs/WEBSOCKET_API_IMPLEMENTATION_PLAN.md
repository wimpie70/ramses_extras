# WebSocket API Implementation Plan

## Overview

This document outlines the implementation plan for creating a feature-centric WebSocket API architecture for Ramses Extras. The plan replaces the old monolithic `websocket_api.py` approach with a modular, feature-based system that integrates seamlessly with the existing framework.

## Architecture Overview

### Design Principles

1. **Feature-Centric Organization**: All WebSocket commands live within feature folders
2. **Reusable Framework Utilities**: Shared helpers only when multiple features need the same functionality
3. **Default Feature for Common Commands**: Commands used by >1 feature go to default feature
4. **Easy Feature Creation**: Simple pattern for adding WebSocket commands to new features
5. **Good Separation of Concerns**: Clear ownership and boundaries per feature
6. **Integration with Existing Systems**: Seamless integration with EntityManager and device handlers

### Core Components

#### 1. Feature-Based WebSocket Organization
- **Default Feature**: Common commands used by multiple features (device management, discovery)
- **Humidity Control Feature**: Feature-specific humidity management commands
- **HVAC Fan Card Feature**: Fan control and configuration commands
- **Future Features**: Easy pattern for adding WebSocket commands to new features

#### 2. Minimal Framework Utilities
- **WebSocket Base Classes**: Reusable base classes for command handling
- **Entity Integration Helpers**: EntityManager integration utilities
- **Device Integration Helpers**: Device handler integration utilities
- **Command Registration Utilities**: Simple registration and discovery helpers

#### 3. Command Discovery System
- **Feature Command Discovery**: Each feature exposes its WebSocket commands
- **Feature-Based Filtering**: Commands available only when feature is enabled
- **Integration with HA**: Seamless registration with Home Assistant WebSocket API

## Implementation Phases

### Phase 1: Foundation (High Priority)
**Goal**: Establish the core WebSocket framework infrastructure

#### 1.1 Framework WebSocket Infrastructure
```python
framework/websocket/
├── __init__.py              # WebSocketFramework class
├── commands.py              # Command registry and routing
├── handlers/                # Base command handlers
│   ├── __init__.py
│   ├── device_handler.py    # Base device command handler
│   └── entity_handler.py    # Base entity command handler
└── register.py              # Registration utilities
```

**Deliverables**:
- `WebSocketFramework` class with command registry
- `WS_COMMAND_REGISTRY` constant in `const.py`
- `register_ws_command()` and `get_ws_commands()` functions
- Command discovery and registration utilities

#### 1.2 WebSocket Command Base Classes
**Base Classes**:
- `FeatureWebSocketHandler`: Integration with feature instances
- `DeviceWebSocketHandler`: Device-specific operations
- `EntityWebSocketHandler`: Entity operations via EntityManager

**Features**:
- Standardized command execution pattern
- Integration with EntityManager for entity access
- Device handler integration for device operations
- Consistent error handling and validation
- Async/await support for all operations

#### 1.3 Integration with Home Assistant
**Requirements**:
- WebSocket command registration during integration startup
- Connection lifecycle management
- Proper error handling and logging
- Integration with existing feature system
- Connection to HA's WebSocket API infrastructure

### Phase 2: Core WebSocket Commands Implementation (High Priority)
**Goal**: Implement the WebSocket commands actually needed by existing frontend code

#### 2.1 Primary WebSocket Commands

| Command | Description | Parameters | Returns | Frontend Usage |
|---------|-------------|------------|---------|----------------|
| `get_bound_rem` | Get bound REM info for device | `device_id` | REM binding info | Replaces entity attribute fallback in HVAC fan card |
| `get_2411_schema` | Get device parameter schema | `device_id` | Schema object | Currently called by HVAC fan card via callWebSocket |

#### 2.2 Command Distribution

**Default Feature** (Device Management):
- `get_bound_rem` - Primary device discovery command
- `get_2411_schema` - Parameter schema for device configuration

**Feature-Specific Commands** (Future):
- No immediate needs identified - existing entities provide comprehensive get/set functionality
- Framework prepared for future feature-specific WebSocket commands when needed

### Phase 3: Enhancement (Low Priority)
**Goal**: Complete the WebSocket ecosystem

#### 3.1 Configuration and Security
- **WebSocket Feature Toggle**: Integrate with config flow options
- **CONF_ENABLED_WEB_SOCKETS**: Configuration option management
- **Authentication**: WebSocket endpoint security
- **Rate Limiting**: Command throttling and abuse prevention

#### 3.2 Documentation
- **API Reference**: Complete WebSocket command documentation
- **Integration Guide**: Developer guide for adding new commands
- **Examples**: Usage patterns and code examples

#### 3.3 Testing Framework
- **Unit Tests**: Framework and base class testing
- **Integration Tests**: Feature command testing
- **Mock Framework**: WebSocket connection mocking
- **Test Utilities**: Common testing utilities

## File Structure

### New Files to Create

```
custom_components/ramses_extras/
├── framework/helpers/
│   ├── websocket_base.py           # BaseWebSocketCommand class
│   ├── entity_websocket_helpers.py # EntityManager integration
│   └── device_websocket_helpers.py # Device handler integration
├── features/
│   ├── default/
│   │   └── websocket_commands.py   # Common commands (get_bound_rem, etc.)
│   ├── humidity_control/
│   │   └── websocket_commands.py   # Humidity-specific commands
│   └── hvac_fan_card/
│       └── websocket_commands.py   # Fan card specific commands
```

### Modified Files

```
custom_components/ramses_extras/
├── const.py                    # Add WebSocket command discovery
├── __init__.py                 # Add WebSocket registration
├── config_flow.py             # Add WebSocket config options
```

## Integration Points

### EntityManager Integration
- WebSocket commands can query entity states and configurations
- Commands can trigger entity creation/removal via EntityManager
- Integration with entity lifecycle management

### Device Handler Integration
- Commands leverage existing `DEVICE_TYPE_HANDLERS`
- Direct access to device objects via broker
- Integration with device discovery system

### Event System Integration
- WebSocket commands can fire custom events
- Subscription to device and entity events
- Real-time updates via event system

### Feature System Integration
- Commands access feature instances and their methods
- Integration with feature automation logic
- Feature-specific configuration access

## Command Registration Flow

1. **Feature Command Discovery**: System discovers WebSocket commands from each feature folder
2. **Feature-Based Filtering**: Commands filtered by enabled features (via AVAILABLE_FEATURES)
3. **Command Registration**: Each feature's `websocket_commands.py` exports its commands
4. **HA Registration**: Filtered commands registered with Home Assistant WebSocket API
5. **Runtime Execution**: Commands executed with feature context and framework utilities

## Error Handling Strategy

### Validation Errors
- Parameter validation using Voluptuous schemas
- Device existence validation
- Feature availability validation

### Runtime Errors
- Device communication failures
- Entity access errors
- Feature instance errors

### User Errors
- Invalid command parameters
- Insufficient permissions
- Feature not enabled

## Security Considerations

### Authentication
- WebSocket connection authentication
- Command-level authorization
- User permission validation

### Rate Limiting
- Command frequency limits
- Connection limits
- Abuse prevention

### Data Validation
- Input parameter validation
- Output data sanitization
- Type checking

## Performance Considerations

### Efficiency
- Command caching where appropriate
- Connection pooling
- Minimal data transfer

### Scalability
- Async command execution
- Non-blocking operations
- Resource cleanup

## Migration from Old Implementation

### Legacy Command Mapping
- `get_bound_rem` → Device Management command suite
- Single monolithic file → Feature-specific modules
- Direct ramses_rf access → Framework integration

### Compatibility
- No backward compatibility required
- Fresh implementation approach
- Clean slate for new architecture

## Testing Strategy

### Unit Tests
- Framework classes and methods
- Command registration and routing
- Base handler functionality

### Integration Tests
- Feature command execution
- EntityManager integration
- Device handler integration

### End-to-End Tests
- Full WebSocket command workflows
- Error handling scenarios
- Performance testing

## Success Criteria

### Functional Requirements
- [ ] All planned WebSocket commands implemented
- [ ] Feature integration working correctly
- [ ] EntityManager integration functional
- [ ] Device handler integration working
- [ ] Error handling comprehensive

### Quality Requirements
- [ ] Code follows existing patterns and standards
- [ ] Comprehensive test coverage
- [ ] Complete documentation
- [ ] Performance benchmarks met

### Architecture Requirements
- [ ] Clean separation of concerns
- [ ] Feature-centric organization
- [ ] Framework integration complete
- [ ] Extensibility demonstrated

## Implementation Notes

### Key Design Decisions
1. **No Backward Compatibility**: Fresh implementation without legacy constraints
2. **Feature Ownership**: Each feature owns its WebSocket commands
3. **Framework Integration**: Seamless integration with existing systems
4. **Async Everything**: All operations use async/await pattern
5. **Type Safety**: Full type annotation coverage

### Development Guidelines
1. **Consistent Patterns**: Follow existing code patterns
2. **Comprehensive Testing**: Test all command scenarios
3. **Documentation**: Document all commands and interfaces
4. **Error Handling**: Robust error handling for all scenarios
5. **Performance**: Optimize for efficiency and scalability

This implementation plan provides a comprehensive roadmap for creating a modern, feature-centric WebSocket API architecture that integrates seamlessly with the existing Ramses Extras framework.
