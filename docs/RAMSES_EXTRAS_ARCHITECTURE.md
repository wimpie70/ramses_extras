# Ramses Extras Architecture Guide

## 1. Table of Contents
- [1. Table of Contents](#1-table-of-contents)
- [2. Overview \& Quick Start](#2-overview--quick-start)
- [3. System Architecture](#3-system-architecture)
- [4. Feature System](#4-feature-system)
- [5. Framework Foundation](#5-framework-foundation)
- [6. Device Feature Management](#6-device-feature-management)
- [7. Entity Management](#7-entity-management)
- [8. Home Assistant Integration](#8-home-assistant-integration)
- [9. Frontend Architecture](#9-frontend-architecture)
- [10. Development Guide](#10-development-guide)
- [11. Debugging and Troubleshooting Guide](#11-debugging-and-troubleshooting-guide)
- [12. API Reference](#12-api-reference)
- [13. Implementation Details](#13-implementation-details)

---

## 2. Overview & Quick Start

### What is Ramses Extras?

Ramses Extras is a **feature-centric** Home Assistant integration that extends the ramses_cc integration with additional entities, automation, and UI components. It provides a clean, modular architecture that allows for easy extension and customization.

### Core Benefits

- **Feature-Centric Design**: Each feature is self-contained with its own automation, services, entities, and UI
- **Framework Foundation**: Reusable components that all features can use
- **Clean HA Integration**: Standard Home Assistant platform integration with type-safe entities
- **Modular Architecture**: Easy to add new features using established patterns
- **Real-time Updates**: WebSocket APIs and message listeners for immediate UI updates

### Key Concepts

- **Features**: Self-contained modules that provide specific functionality
- **Framework**: Reusable base classes, helpers, and utilities
- **Platforms**: Home Assistant integration layer for entities and services
- **Cards**: JavaScript-based UI components for the Lovelace interface
- **Config_flow**: HA way to configure integrations

### Quick Start for Developers

1. **Understand the Structure**: Features → Framework → HA Platforms
2. **Enable Features**: Add features to `AVAILABLE_FEATURES` in `const.py`
3. **Implement Components**: Each feature can have card, automation, services, entities, and platforms
4. **Register Platforms**: Features register their platforms with Home Assistant
5. **Deploy Assets**: JavaScript cards and helpers are deployed to HA config directory
6. - **Config_flow**: Each feature can have it's own HA configuration step


---

## 3. System Architecture

### High-Level Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Home Assistant                          │
├────────────────────────────────────────────────────────────┤
│  Ramses Extras Integration (Thin HA Wrapper)               │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │   Feature 1  │ │   Feature 2  │ │   Feature N  │        │
│  │ (Humidity)   │ │ (HVAC Card)  │ │   (Custom)   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
├────────────────────────────────────────────────────────────┤
│  Framework Foundation (Base Classes, Helpers, Managers)    │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │   Base       │ │   Entity     │ │   Device     │        │
│  │   Classes    │ │   Helpers    │ │   Handlers   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
├────────────────────────────────────────────────────────────┤
│  ramses_cc Integration (Device Communication)              │
└────────────────────────────────────────────────────────────┘
```

### Core Design Principles

#### Feature-Centric Organization
- Each feature is **self-contained** with its own automation, services, entities, and config
- Features are **modular** - only need a small addition to the framework root const.py to be loaded dynamically
- Clear **separation of concerns** within each feature
- A **default feature** provides common/shared functionality

#### Framework Foundation
- **Reusable helpers** that all features can use
- **Base classes** for common functionality
- **Common utilities** for logging, validation, etc.

#### Python-Based Automations (Not YAML)
- **Hardcoded Python Logic**: All automations are implemented as Python classes, not YAML automation rules
- **Event-Driven Architecture**: Automations listen to ramses_cc events and device state changes
- **Full Python Control**: Complete programmatic control over automation logic, conditions, and actions
- **Framework Integration**: Automations use framework base classes for consistent patterns and lifecycle management

#### ramses_cc Integration Hooks
- **Broker Access**: Direct integration with ramses_cc broker for device communication
- **ramses_rf Layer**: Access to underlying ramses_rf protocol layer for low-level device operations
- **Event Subscriptions**: Listen to ramses_cc events for real-time device updates
- **Device Enumeration**: Enhanced device enumeration building on ramses_cc foundation
- **Shared Constants**: Use ramses_cc constants and schemas for device communication
- **Message Handling**: Direct access to ramses_cc message parsing and generation

#### Home Assistant Integration
- Standard HA platform integration (sensor, switch, binary_sensor, number)
- Type-safe entity implementations
- Full compatibility with HA ecosystem

### Directory Structure

```
custom_components/ramses_extras/
├── 🔑 Core Integration (HA Requirements)
│   ├── __init__.py              # Integration entry point
│   ├── config_flow.py           # HA config flow
│   ├── const.py                 # Core constants with AVAILABLE_FEATURES
│   ├── manifest.json            # HA integration manifest
│   └── services.yaml            # HA service definitions
│
├── 🎯 Features (Feature-Centric)
│   ├── humidity_control/        # Humidity control feature
│   │   ├── automation.py        # Feature automation logic
│   │   ├── services.py          # Feature services
│   │   ├── entities.py          # Entity management
│   │   ├── config.py            # Feature configuration
│   │   ├── const.py             # Feature constants
│   │   ├── __init__.py          # Feature factory
│   │   └── platforms/           # HA platform implementations
│   │       ├── sensor.py        # Feature sensor entities
│   │       ├── switch.py        # Feature switch entities
│   │       ├── number.py        # Feature number entities
│   │       └── binary_sensor.py # Feature binary sensor entities
│   │
│   ├── hvac_fan_card/           # HVAC fan card feature
│   │   ├── __init__.py
│   │   ├── const.py
│   │   └── www/                 # Feature-specific web assets
│   │       └── hvac_fan_card/
│   │           ├── hvac-fan-card.js
│   │           ├── hvac-fan-card-editor.js
│   │           ├── message-handlers.js
│   │           └── translations/
│   │
│   ├── hello_world/         # Hello World template feature
│   │   ├── __init__.py
│   │   ├── automation.py
│   │   ├── config.py
│   │   ├── const.py
│   │   ├── entities.py
│   │   ├── services.py
│   │   ├── websocket_commands.py
│   │   ├── platforms/
│   │   │   ├── __init__.py
│   │   │   ├── binary_sensor.py
│   │   │   ├── number.py
│   │   │   ├── sensor.py
│   │   │   └── switch.py
│   │   └── www/
│   │       └── hello_world/
│   │           ├── card-styles.js
│   │           ├── hello-world-editor.js
│   │           ├── hello-world.js
│   │           ├── templates/
│   │           └── translations/
│   │               ├── en.json
│   │               └── nl.json
│   │
│   └── default/                 # Default feature scaffold
│       ├── __init__.py
│       ├── const.py
│       ├── commands.py
│       ├── config_flow.py
│       ├── websocket_commands.py
│       └── platforms/
│           └── sensor.py
│
├── 🏛️ Framework (Reusable Foundation)
│   ├── base_classes/            # Base classes for inheritance
│   │   ├── __init__.py
│   │   ├── base_automation.py          # Automation base
│   │   ├── base_entity.py              # Entity base
│   │   └── platform_entities.py        # Generic platform entities
│   │
│   ├── helpers/                 # Reusable Python utilities
│   │   ├── __init__.py
│   │   ├── config/                     # Configuration management
│   │   │   ├── __init__.py
│   │   │   ├── core.py                 # ExtrasConfigManager
│   │   │   ├── validation.py           # ConfigValidator
│   │   │   ├── schema.py               # ConfigSchema
│   │   │   └── templates.py            # ConfigTemplates
│   │   ├── config_flow.py              # Config flow extension helpers
│   │   ├── platform.py                 # Enhanced with setup framework
│   │   ├── brand_customization/        # Brand customization
│   │   │   ├── __init__.py
│   │   │   ├── core.py                 # ExtrasBrandCustomizer
│   │   │   ├── detection.py            # BrandPatterns
│   │   │   ├── models.py               # ModelConfigManager
│   │   │   └── entities.py             # EntityGenerationManager
│   │   ├── entity/                     # Entity management
│   │   │   ├── __init__.py
│   │   │   ├── core.py                 # EntityHelpers
│   │   │   ├── simple_entity_manager.py # SimpleEntityManager
│   │   │   ├── device_feature_matrix.py # DeviceFeatureMatrix
│   │   │   └── device_feature_mapping.py # Legacy mapping
│   │   ├── service/                    # Service framework
│   │   │   ├── __init__.py
│   │   │   ├── core.py                 # ExtrasServiceManager
│   │   │   ├── registration.py         # ServiceRegistry
│   │   │   └── validation.py           # ServiceValidator
│   │   ├── automation/                 # Automation helpers
│   │   ├── device/                     # Device helpers
│   │   │   ├── __init__.py
│   │   │   ├── core.py                 # Device helpers
│   │   │   └── filter.py              # Device filtering
│   │   ├── commands/                   # Command framework
│   │   │   ├── __init__.py
│   │   │   └── registry.py             # CommandRegistry
│   │   ├── common/                     # Common utilities
│   │   │   ├── __init__.py
│   │   │   └── validation.py           # Validation utilities
│   │   └── paths.py                    # Path management
│   │
│   ├── www/                     # Reusable JavaScript utilities
│   │   ├── paths.js             # Environment-aware path constants
│   │   ├── card-commands.js
│   │   ├── card-services.js
│   │   ├── card-translations.js
│   │   ├── card-validation.js
│   │   └── ramses-message-broker.js
│   │
│   └── managers/                # Framework managers
│       └── __init__.py
│
├── 🌐 Platform (HA Integration)
│   ├── sensor.py                # Root sensor platform
│   ├── switch.py                # Root switch platform
│   ├── binary_sensor.py         # Root binary sensor platform
│   ├── number.py                # Root number platform
│   └── __init__.py
│
├── extras_registry.py           # Feature registry system
├── websocket_integration.py     # WebSocket command registry
└── translations/                # Integration-level translations
    ├── en.json                  # English integration strings
    └── nl.json                  # Dutch integration strings
```

### Integration Flow

**Step 1:** **HA Integration Loads** - `__init__.py` handles integration setup
**Step 2:** **ramses_cc Readiness Check** - Integration waits for ramses_cc to be loaded
**Step 3:** **Device Enumeration** - Access devices already discovered by ramses_cc broker
**Step 4:** **Feature Creation** - Feature factories create feature instances
**Step 5:** **Platform Forwarding** - Root platforms forward to feature platforms
**Step 6:** **Entity Registration** - Entities register with HA via feature platforms
**Step 7:** **Asset Deployment** - JavaScript cards deployed to HA config directory

#### ramses_cc Readiness and Dependency Management

Ramses Extras **waits for ramses_cc to be ready** before initializing. The integration checks if ramses_cc is loaded and waits with retry if necessary:

```python
# Check ramses_cc readiness during platform setup
ramses_cc_loaded = "ramses_cc" in hass.config.components

if ramses_cc_loaded:
    # Proceed with device enumeration and integration setup
    device_ids = await _discover_ramses_devices(hass)
else:
    # Retry in 60 seconds if ramses_cc not ready
    hass.call_later(60.0, hass.async_create_task(delayed_retry))
```

**Why This Matters:**
1. **Dependency Management** - Ramses Extras cannot function without ramses_cc
2. **Robust Initialization** - Handles cases where ramses_cc loads after Ramses Extras
3. **Device Enumeration** - Requires ramses_cc broker access for device enumeration
4. **Event Integration** - Needs ramses_cc event system for real-time updates

### ramses_cc Integration Architecture

Ramses Extras builds upon the ramses_cc integration by providing direct hooks into the underlying communication layer:

#### Broker Access and Device Communication
```python
# Direct broker access for device operations
async def _get_broker_for_entry(hass):
    """Get ramses_cc broker instance for device communication."""
    # Access ramses_cc broker through HA data
    return hass.data["ramses_cc"]["broker"]

# Device discovery and communication
async def _find_device_by_id(broker, device_id):
    """Find device by ID in ramses_cc broker."""
    for device in broker.devices:
        if device.id == device_id:
            return device
    return None
```

#### ramses_rf Layer Integration
- **Protocol Access**: Direct access to ramses_rf protocol layer for low-level operations
- **Message Handling**: Integration with ramses_rf message parsing and generation
- **Device State**: Real-time access to device state through ramses_rf layer
- **Command Sending**: Send commands directly through ramses_rf communication stack

#### Event System Integration
```python
# Listen to ramses_cc events for real-time device updates
self.hass.bus.async_listen("ramses_cc_message", self._on_ramses_message)

# Enhanced device discovery events
self.hass.bus.async_listen("ramses_device_ready_for_entities", self._on_device_ready)
```

#### Shared Constants and Schemas
- **Device Types**: Use ramses_cc device type definitions
- **Parameter Schemas**: Leverage ramses_cc parameter schemas for device configuration
- **Message Codes**: Integrate with ramses_cc message code definitions
- **Error Handling**: Use ramses_cc error patterns and handling

#### Initialization Dependencies

**ramses_cc Readiness Requirement**: Ramses Extras **requires ramses_cc to be loaded and ready** before initialization:

```python
# Check ramses_cc readiness in async_setup_platforms()
ramses_cc_loaded = "ramses_cc" in hass.config.components

if ramses_cc_loaded:
    # Proceed with device discovery and integration setup
    broker = await _get_broker_for_entry(hass)
    device_ids = await _discover_ramses_devices(hass)
else:
    # Retry in 60 seconds if ramses_cc not ready
    hass.call_later(60.0, hass.async_create_task(delayed_retry))
```

#### Integration Points
1. **Device Enumeration**: Building on ramses_cc device discovery with enhanced capabilities
2. **Message Processing**: Intercepting and processing ramses_cc messages for feature logic
3. **State Synchronization**: Real-time state updates from ramses_cc to feature entities
4. **Command Execution**: Direct command execution through ramses_rf layer
5. **Error Handling**: Coordinated error handling between ramses_cc and features
6. **Initialization Coordination**: Waiting for ramses_cc readiness before feature startup

---

## 4. Feature System

### How Features Work

Each feature is a self-contained module that provides specific functionality. Features follow a consistent pattern and can be enabled/disabled independently.

The `Hello World Card` feature can be used as a template to develop new functionality.

### Feature Lifecycle

1. **Registration**: Feature added to `AVAILABLE_FEATURES` in main `const.py`
2. **Discovery**: Config flow discovers available features
3. **Activation**: User enables/disables features via HA config
4. **Creation**: Feature factory creates feature instance
5. **Registration**: Feature registers its platforms with Home Assistant
6. **Operation**: Feature operates independently with its own entities and automations

### Current Features

#### ✅ Default Feature
- **Purpose**: Base functionality available for all devices
- **Entities**: Basic sensor entities for device monitoring
- **Commands**: Standard device commands and utilities
- **WebSocket**: Basic command APIs for device interaction
- **Platforms**: sensor

#### ✅ Humidity Control
- **Purpose**: Advanced humidity-based ventilation control
- **Entities**: Humidity sensors, control switches, number inputs
- **Automation**: Python-based automatic fan speed adjustment (no YAML automation rules)
- **Services**: Manual humidity control and configuration
- **Platforms**: sensor, switch, number, binary_sensor

#### ✅ HVAC Fan Card
- **Purpose**: Real-time HVAC system monitoring and control card
- **UI Components**: JavaScript Lovelace card with real-time updates
- **Data Source**: WebSocket APIs and message listeners
- **Features**: Temperature display, fan speed control, mode selection
- **Platforms**: No direct entities (UI-focused feature)

#### ✅ Hello World Card
- **Purpose**: Template feature demonstrating complete Ramses Extras architecture
- **Components**: Includes all standard feature components (automation, config, entities, services, platforms, www)
- **Usage**: Can be copied and modified to create new features following established patterns
- **Platforms**: sensor, switch, number, binary_sensor

### Feature Structure Pattern

```python
# features/humidity_control/__init__.py
def create_humidity_control_feature(hass, config_entry):
    return {
        "automation": HumidityAutomationManager(hass, config_entry),
        "entities": HumidityEntities(hass, config_entry),
        "services": HumidityServices(hass, config_entry),
        "config": HumidityConfig(hass, config_entry),
        "platforms": {
            "sensor": HumidityAbsoluteSensor,
            "switch": create_humidity_switch,
            "number": create_humidity_number,
            "binary_sensor": create_humidity_binary_sensor,
        },
    }
```

### Feature Components

Each feature contains these core components. **Some components are optional** depending on the feature's functionality:

#### Required Components
- **__init__.py**: Feature factory functions (always required)
- **const.py**: Feature-specific constants and mappings (always required)

#### Optional Components (choose as needed)
- **automation.py**: Feature-specific automation logic in Python code (e.g., `HumidityAutomationManager`) - **Not YAML automation rules** - Optional, only if feature needs automation
- **services.py**: Feature-specific service methods (e.g., `HumidityServices`) - Optional, only if feature needs services
- **entities.py**: Feature-specific entity management (e.g., `HumidityEntities`) - Optional, only if feature needs entity management
- **config.py**: Feature-specific configuration (e.g., `HumidityConfig`) - Optional, only if feature needs configuration
- **platforms/**: HA platform implementations with feature-specific entity classes - Optional, only if feature needs Home Assistant entities
- **www/**: JavaScript UI components for Lovelace cards - Optional, only if feature needs UI components
- **websocket_commands.py**: WebSocket API commands - Optional, only if feature needs WebSocket APIs

### Adding New Features

The `Hello World Card` feature serves as a template. Instead of following the next recipe, you can just copy this folder and refactor it for your own needs. You will still need to `register feature` by adding it to the main `const.py`

1. **Create Feature Structure**
   ```bash
   mkdir -p custom_components/ramses_extras/features/my_new_feature
   mkdir -p custom_components/ramses_extras/features/my_new_feature/platforms
   touch custom_components/ramses_extras/features/my_new_feature/__init__.py
   touch custom_components/ramses_extras/features/my_new_feature/automation.py
   touch custom_components/ramses_extras/features/my_new_feature/services.py
   touch custom_components/ramses_extras/features/my_new_feature/entities.py
   touch custom_components/ramses_extras/features/my_new_feature/config.py
   touch custom_components/ramses_extras/features/my_new_feature/const.py
   ```

2. **Implement Core Components**
   - Follow the established patterns in existing features
   - Implement automation logic, services, entities, and configuration
   - Create platform files for HA entity integration

3. **Register Feature**
   - Add feature to `AVAILABLE_FEATURES` in main `const.py`
   - Feature will be automatically discovered and enabled via config flow

---

## 5. Framework Foundation

The Ramses Extras framework provides a comprehensive foundation for building features with reusable components, standardized patterns, and automated lifecycle management. The framework has been designed to accelerate feature development.

### 🏗️ Framework Architecture Overview

The framework follows a **layered architecture** approach:

```
┌────────────────────────────────────────────────────────────┐
│                    Framework Foundation                    │
├────────────────────────────────────────────────────────────┤
│  📦 Base Classes      🧩 Helpers       🌐 Services         │
│  - Entity Bases       - Config         - Platform Setup    │
│  - Automation         - Entity         - Service Mgmt      │
│  - Platform Entity    - Brand Custom   - Validation        │
│                       - Service                            │
├────────────────────────────────────────────────────────────┤
│  🔧 Platform Layer    📋 Entity Mgmt   🎯 Brand Support    │
│  - Setup Framework    - Simple Mgr     - Detection         │
│  - Integration        - Device Matrix  - Customization     │
│  - Forwarding         - Management     - Model Config      │
└────────────────────────────────────────────────────────────┘
```

### 📚 Base Classes

The framework provides reusable base classes that all features can inherit from:

#### ExtrasBaseEntity
- **Purpose**: Base class for all custom entities
- **Location**: `framework/base_classes/base_entity.py`
- **Features**: Common entity functionality, device linking, state management

#### ExtrasBaseAutomation
- **Purpose**: Base class for automation logic
- **Location**: `framework/base_classes/base_automation.py`
- **Features**: Automation patterns, lifecycle management, event handling

#### Platform Entity Classes
- **Purpose**: Generic platform entity base classes for all HA platforms
- **Location**: `framework/base_classes/platform_entities.py`
- **Classes**:
  - `ExtrasSwitchEntity` - Generic switch entity for all features
  - `ExtrasNumberEntity` - Generic number entity for all features
  - `ExtrasBinarySensorEntity` - Generic binary sensor entity for all features
  - `ExtrasSensorEntity` - Generic sensor entity for all features

### 🧩 Helper Modules

#### Configuration Management (`framework/helpers/config/`)
- **Purpose**: Reusable configuration management patterns
- **Components**:
  - `core.py` - `ExtrasConfigManager` base class for configuration management
  - `validation.py` - `ConfigValidator` utility class with common patterns
  - `schema.py` - `ConfigSchema` UI schema generation utilities
  - `templates.py` - `ConfigTemplates` with pre-built default configurations
- **Usage**: All features can use the same configuration patterns

#### Entity Management (`framework/helpers/entity/`)
- **Purpose**: Comprehensive entity lifecycle and registry management
- **Components**:
  - `core.py` - `EntityHelpers` class with comprehensive entity utilities
  - `simple_entity_manager.py` - `SimpleEntityManager` class for simplified entity management
  - `device_feature_matrix.py` - `DeviceFeatureMatrix` for per-device feature tracking

#### Brand Customization (`framework/helpers/brand_customization/`)
Note: Framework exists but limited implementation
- **Purpose**: Centralized brand detection and customization patterns
- **Components**:
  - `core.py` - `ExtrasBrandCustomizer` base class and `BrandCustomizerManager`
  - `detection.py` - `BrandPatterns` for brand detection pattern management
  - `models.py` - `ModelConfigManager` for model-specific configuration handling
  - `entities.py` - `EntityGenerationManager` for brand-specific entity generation
- **Usage**: Supports multiple brands (Orcon, Zehnder, etc.) through framework

#### Service Framework (`framework/helpers/service/`)
- **Purpose**: Comprehensive service registration, execution, and validation
- **Components**:
  - `core.py` - `ExtrasServiceManager` base class for service execution
  - `registration.py` - `ServiceRegistry` for centralized service management
  - `validation.py` - `ServiceValidator` for comprehensive service validation
- **Benefits**: Unified service management, comprehensive validation, performance monitoring
- **Service Types**: ACTION, STATUS, CONFIGURATION, DIAGNOSTIC, CONTROL
- **Service Scopes**: DEVICE, FEATURE, GLOBAL

#### Command Framework (`framework/helpers/commands/`)
- **Purpose**: Command registration and management system
- **Components**:
  - `registry.py` - `CommandRegistry` for centralized command management
- **Usage**: Features can register their commands and access standard command libraries

#### Device Management (`framework/helpers/device/`)
- **Purpose**: Device-related utilities and filtering
- **Components**:
  - `core.py` - Device helper functions
  - `filter.py` - Device filtering utilities for config flow

#### Platform Setup Framework
- **Purpose**: Reusable platform setup patterns and automation support
- **Location**: Enhanced `framework/helpers/platform.py`
- **Features**:
  - `PlatformSetup` class with `async_setup_platform` method
  - Standard platform integration patterns
  - Integration with Home Assistant platform system

### 🛠️ Framework Services

#### Path Management
- **Python Paths**: `framework/helpers/paths.py` - Shared path constants
- **JavaScript Paths**: `framework/www/paths.js` - Environment-aware path constants
- **Asset Management**: Automatic deployment of JavaScript files and helpers

#### Message System
- **WebSocket Commands**: Feature-centric WebSocket API architecture
- **Message Listeners**: Real-time ramses_cc message handling
- **Event System**: Framework-level event handling for inter-feature communication

### 📖 Framework Usage Examples

#### Configuration Management Usage
```python
class HumidityConfig(ExtrasConfigManager):
    DEFAULT_CONFIG = {
        "target_humidity": 50,
        "auto_mode": True,
    }

    def validate_custom_config(self):
        # Custom validation only
        pass
```

#### Platform Entity Usage
```python
class HumiditySwitch(ExtrasSwitchEntity):
    """Switch entity for humidity control."""

    @property
    def is_on(self) -> bool:
        """Return true if dehumidification is active."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidification."""
        # Call service layer for fan speed control
        await self.hass.services.async_call(
            "ramses_extras", "activate_dehumidification",
            {"device_id": self.device_id}
        )
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidification."""
        # Call service layer for fan speed control
        await self.hass.services.async_call(
            "ramses_extras", "deactivate_dehumidification",
            {"device_id": self.device_id}
        )
        self._is_on = False
        self.async_write_ha_state()
```

#### Service Framework Usage
```python
class HumidityServices(ExtrasServiceManager):
    SERVICE_DEFINITIONS = {
        "set_target_humidity": {
            "type": ServiceType.ACTION,
            "parameters": {"humidity": {"type": int, "min": 30, "max": 80}},
        }
    }
```

---

## 6. Device Feature Management

Ramses Extras supports per-device feature management, allowing users to enable features for specific devices only.

So far this is only implemented to determine what entities will be created for what device. This is done with the DeviceFeatureMatrix. The generic config_flow step for features let users enable certain devices. Only for enabled devices (and enabled features) entities will be created ! The Default feature has it's own config_flow step that can act as an example if you want to override the generic (framework) step.

### Device Filtering

Each feature can specify which device types it supports using `allowed_device_slugs`:

```python
AVAILABLE_FEATURES = {
    "humidity_control": {
        "allowed_device_slugs": ["FAN"],  # Only works with FAN devices
        # ... other config
    },
    "hello_world": {
        "allowed_device_slugs": ["*"],   # Works with any device
        # ... other config
    }
}
```

### DeviceFeatureMatrix

The `DeviceFeatureMatrix` class tracks which features are enabled for which devices:

```python
matrix = DeviceFeatureMatrix()
matrix.enable_feature_for_device("fan_device_1", "humidity_control")
matrix.enable_feature_for_device("fan_device_2", "hvac_fan_card")

# Get features enabled for a device
features = matrix.get_enabled_features_for_device("fan_device_1")
# Returns: {"humidity_control": True}

# Get all enabled combinations
combinations = matrix.get_all_enabled_combinations()
# Returns: [("fan_device_1", "humidity_control"), ("fan_device_2", "hvac_fan_card")]
```

### Per-Device Feature Enablement

Users can enable features for specific devices through the config flow:

1. **Select Features**: Choose which features to configure
2. **Device Selection**: For each feature, select which devices to enable it for
3. **Confirmation**: Review entity changes before applying
4. **Application**: System creates entities only for selected device/feature combinations

### Matrix State Management

The DeviceFeatureMatrix supports state serialization for persistence:

```python
# Save matrix state
state = matrix.get_matrix_state()

# Save to config entry
new_data = dict(self._config_entry.data)
new_data["device_feature_matrix"] = state
self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)

# Restore matrix state
matrix.restore_matrix_state(saved_state)
```

The matrix state is stored in the Home Assistant config entry under the `device_feature_matrix` key. This allows the configuration to persist across restarts and be restored when the integration loads.

---

## 7. Entity Management

### SimpleEntityManager

The `SimpleEntityManager` provides a simplified approach to entity lifecycle management:

```python
class SimpleEntityManager:
    """Simple entity management for config flow operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize SimpleEntityManager."""
        self.hass = hass
        self.device_feature_matrix = DeviceFeatureMatrix()

    async def create_entities_for_feature(
        self, feature_id: str, device_ids: list[str]
    ) -> list[str]:
        """Create entities directly for feature/device combinations."""

    async def remove_entities_for_feature(
        self, feature_id: str, device_ids: list[str]
    ) -> list[str]:
        """Remove entities directly for feature/device combinations."""

    async def calculate_entity_changes(
        self,
        old_matrix_state: dict[str, dict[str, bool]],
        new_matrix_state: dict[str, dict[str, bool]],
    ) -> tuple[list[str], list[str]]:
        """Calculate entity changes between two matrix states."""

    async def validate_entities_on_startup(self) -> None:
        """Check entity consistency on startup."""
```

### Entity Creation Logic

Entities are created based on the device/feature matrix:

```python
for device_id, feature_id in combinations:
    # Generate entity IDs for this feature/device combination
    entity_ids = await self._generate_entity_ids_for_combination(
        feature_id, device_id
    )
    required_entities.extend(entity_ids)
```

### Entity Validation

The system validates entity consistency on startup:

```python
async def validate_entities_on_startup(self) -> None:
    """Check entity consistency on startup."""
    # Get current entities
    current_entities = await self._get_current_entities()

    # Calculate required entities based on current feature/device matrix
    required_entities = await self._calculate_required_entities()

    # Find extra entities (exist but shouldn't)
    extra_entities = set(current_entities) - set(required_entities)

    # Find missing entities (should exist but don't)
    missing_entities = set(required_entities) - set(current_entities)

    # Clean up extras and create missing entities
    await self._cleanup_extra_entities(extra_entities)
    await self._create_missing_entities(missing_entities)
```

### Entity Registration

Entities are registered directly with Home Assistant's entity registry:

```python
async def _create_entity_directly(self, entity_id: str) -> None:
    """Create a single entity directly."""
    entity_registry_instance = entity_registry.async_get(self.hass)

    # Extract domain from entity_id
    domain = entity_id.split(".")[0]
    unique_id = entity_id.replace(f"{domain}.", "")

    # Create entity in the registry
    entry = entity_registry_instance.async_get_or_create(
        domain=domain,
        platform="ramses_extras",
        unique_id=unique_id,
        suggested_object_id=entity_id.replace(f"{domain}.", ""),
        config_entry=None,
    )
```

---

## 8. Home Assistant Integration

### Platform Integration Architecture

Ramses Extras uses a **thin wrapper** architecture for Home Assistant platform integration:

#### Root Platform Files (Thin Wrappers)
```python
# sensor.py - ROOT PLATFORM (Thin Wrapper)
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Home Assistant platform integration - thin wrapper only."""
    # Forward to feature platforms
    await async_forward_entry_setups(
        config_entry, ["ramses_extras_humidity_control"], hass
    )
```

#### Feature Platforms (Business Logic)
```python
# features/humidity_control/platforms/sensor.py
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Humidity control sensor platform setup."""
    # Feature-specific platform logic
    entities = await create_humidity_sensor(hass, config_entry)
    async_add_entities(entities)

class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
    """Feature-specific sensor with business logic."""
    # All humidity calculation logic
    # Feature-specific behavior
```

### Entity Naming System

Universal entity naming with automatic format detection:

- **CC Format**: Device ID at beginning (`number.32_153289_param_3f`)
- **Extras Format**: Device ID at end (`sensor.indoor_absolute_humidity_32_153289`)
- **Automatic Detection**: Format determined by device_id position within entity name

### Configuration Flow Integration

```python
# config_flow.py
async def async_step_features(self, user_input):
    if feature_changes:
        # Use SimpleEntityManager for entity management
        self._entity_manager = SimpleEntityManager(self.hass)

        # Calculate entity changes
        entities_to_create, entities_to_remove = await self._entity_manager.calculate_entity_changes(
            old_matrix_state, new_matrix_state
        )

        return await self.async_step_confirm()
```

### Service Integration

- **Integration-Level Services**: Services defined in `services.yaml`
- **Feature-Specific Services**: Implemented in feature `services.py` files
- **Dynamic Registration**: Services registered based on enabled features
- **WebSocket APIs**: Real-time communication for UI components

---

## 9. Frontend Architecture

### JavaScript Card System

Ramses Extras provides a sophisticated JavaScript-based frontend system for Lovelace UI integration:

#### Card Architecture
- **Self-Contained Cards**: Each feature can have its own JavaScript card
- **Framework Helpers**: Reusable JavaScript utilities for all cards
- **Real-time Updates**: WebSocket APIs and message listeners for immediate updates
- **Responsive Design**: Mobile-friendly card layouts and interactions

#### Deployment Structure

**Source Structure (Development Files):**
```
custom_components/ramses_extras/
├── framework/www/                             # Reusable JavaScript utilities
│   ├── paths.js                               # Environment-aware path constants
│   ├── card-commands.js
│   ├── card-services.js
│   ├── card-translations.js
│   ├── card-validation.js
│   └── ramses-message-broker.js               # Global message handling
├── features/hvac_fan_card/www/hvac_fan_card/  # Feature-specific cards
│   ├── hvac-fan-card.js
│   ├── hvac-fan-card-editor.js
│   ├── message-handlers.js
│   ├── templates/
│   └── translations/
```

**Target Deployment Structure:**
```
hass/config/www/ramses_extras/
├── helpers/                         # Shared utilities (from framework/www/)
│   ├── paths.js
│   ├── card-commands.js
│   ├── card-services.js
│   ├── card-translations.js
│   ├── card-validation.js
│   └── ramses-message-broker.js
└── features/                        # Feature-specific cards
    └── hvac_fan_card/               # Each feature gets its own folder
        ├── hvac-fan-card.js
        ├── hvac-fan-card-editor.js
        ├── message-handlers.js
        ├── templates/
        └── translations/
```

### Real-Time Message System

#### JavaScript Message Listener Integration
The system provides real-time HVAC state updates through ramses_cc 31DA message handling:

```javascript
// Auto-registration in card connectedCallback()
const messageHelper = getRamsesMessageBroker();
messageHelper.addListener(this, "32:153289", ["31DA", "10D0"]);

// Called automatically by helper when messages received
handle_31DA(messageData) {
    const hvacData = HvacFanCardHandlers.handle_31DA(this, messageData);
    this.updateFrom31DA(hvacData);
}
```

#### Message Processing Flow
```
31DA Message → RamsesMessageBroker → HvacFanCardHandlers.handle_31DA() → Card Update
     ↓                  ↓                          ↓                         ↓
Real-time     Route to correct           Extract/format             Immediate UI
HVAC Data     card                       data                       re-render
```

### Translation System

#### Feature-Centric Translation Architecture

The translation system follows a **feature-centric design** where translations can be located within feature folders for better isolation and organization:

1. **Integration-Level Translations**
   - **Location**: `custom_components/ramses_extras/translations/` directory
   - **Purpose**: Home Assistant config flow, options, and integration strings
   - **Format**: JSON files per language (en.json, nl.json)

2. **Feature-Level Translations** (Preferred Approach)
   - **Location**: `features/{feature}/www/{feature}/translations/` directories
   - **Deployment Location**: `config/www/ramses_extras/features/{feature}/translations/` directories
   - **Purpose**: JavaScript cards, UI elements, and frontend strings for specific features
   - **Benefits**: Better isolation, easier maintenance, feature-specific organization
   - **Example**: The hello_world feature shows this pattern with translations within the feature folder

3. **Framework-Level Translations** (Shared Components)
   - **Location**: `framework/www/translations/` directory
   - **Purpose**: Shared utilities and framework components
   - **Format**: JSON files per language for reusable components

#### Translation Loading System

The system provides dynamic translation loading for both integration and frontend:

```python
# Translation loading pattern
def load_feature_translations(feature_name, language="en"):
    """Load translations for a specific feature."""
    try:
        # Try feature-level translations first
        feature_translations = load_from_feature_folder(feature_name, language)
        if feature_translations:
            return feature_translations

        # Fallback to integration-level translations
        return load_from_integration_folder(language)
    except TranslationNotFoundError:
        return DEFAULT_TRANSLATIONS
```

### Template Systems

#### JavaScript Template System (Frontend Cards)
- **Location**: `features/{feature}/www/{feature}/templates/` directories
- **Purpose**: Generate HTML dynamically for Home Assistant Lovelace card. We can for example generate all the commands and entities we need from only the device_id we choose when we edited the card in the dashboard.
- **Structure**: Modular template organization with separate files for header, controls, etc.

#### Translation Templates
- **Purpose**: UI localization with dynamic translation loading
- **Location**: `features/{feature}/www/{feature}/translations/` directories for both integration and frontend
- **Benefits**: Feature-specific translations provide better isolation and easier maintenance
- **Pattern**: Follows the same feature-centric approach as other feature components

#### Translation System Benefits

1. **Feature Isolation**: Each feature maintains its own translations
2. **Easy Maintenance**: Translations are co-located with feature code
3. **Consistent Structure**: Follows the same pattern as other feature components
4. **Dynamic Loading**: System automatically loads appropriate translations
5. **Fallback Support**: Graceful fallback to integration-level translations

---

## 10. Development Guide

You are welcome to contribute to this integration. If you are missing support for a device, or have a nice card that you like to share, please do. You can contribute to this github repo, leave a message (issue) when you have questions, an idea, or found bugs.

Also read the `Contributing` section on github to see how to setup a development environment.

### Coding Standards and Conventions

#### File Responsibilities
- **Root Platform Files**: Only HA integration code, forward to features
- **Feature Files**: Feature-specific business logic and entity implementations
- **Framework Files**: Reusable utilities and base classes
- **Frontend Files**: JavaScript/HTML assets for UI components

#### Naming Conventions
- **Feature Names**: snake_case (e.g., `humidity_control`)
- **Entity Classes**: PascalCase with feature prefix (e.g., `HumidityAbsoluteSensor`)
- **Helper Functions**: snake_case (e.g., `calculate_absolute_humidity`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `HUMIDITY_CONTROL_FEATURE`)

#### Import Patterns
```python
# Feature imports (relative)
from ...automation import HumidityAutomationManager

# Framework imports (absolute - due to module resolution)
from custom_components.ramses_extras.framework.helpers.automation import ExtrasBaseAutomation
from custom_components.ramses_extras.framework.helpers.entity import EntityHelpers

# Root imports (absolute)
from custom_components.ramses_extras.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
```

**Note**: Framework components should use absolute imports from features to avoid module resolution issues. Relative imports like `from ...framework.helpers.automation` may resolve incorrectly in some Python environments.

### Development Workflow

1. **Framework-First Development**
   - **Step 1**: Start with framework components for configuration, entities, and services
   - **Step 2**: Use platform entity base classes for HA integration
   - **Step 3**: Leverage brand customization and service frameworks
   - **Step 4**: Implement feature-specific business logic only

2. **Feature Development with Framework**
   ```python
   # Example: New feature using full framework
   def create_my_feature(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
       """Create feature using framework patterns."""

       # Configuration management
       config = MyFeatureConfig(hass, config_entry, "my_feature", MyFeatureConfig.DEFAULT_CONFIG)

       # Simple entity management
       entity_manager = SimpleEntityManager(hass)

       # Service framework
       service_manager = MyFeatureServices(hass, config_entry)

       # Platform setup framework
       platform_setup = PlatformSetup(hass, config_entry)

       return {
           "config": config,
           "entity_manager": entity_manager,
           "service_manager": service_manager,
           "platform_setup": platform_setup,
           "platforms": {
               "sensor": MyFeatureSensor,  # Uses ExtrasSensorEntity
               "switch": MyFeatureSwitch,  # Uses ExtrasSwitchEntity
               "number": MyFeatureNumber,  # Uses ExtrasNumberEntity
           },
       }
   ```

3. **Framework Component Integration**
   - Use `ExtrasConfigManager` for all configuration needs
   - Inherit from platform entity classes (`ExtrasSwitchEntity`, etc.)
   - Register services through `ExtrasServiceManager`
   - Apply brand customizations through `BrandCustomizerManager`
   - Use `SimpleEntityManager` for entity operations

4. **Testing**
   - Use framework helpers for consistent testing patterns
   - Test features independently using the framework foundation
   - Follow HA testing standards and patterns
   - Leverage framework validation and error handling

5. **Documentation**
   - Document feature API and configuration options
   - Update architecture guide for new patterns or components
   - Provide examples of framework usage
   - Include migration notes for legacy patterns

### Testing Structure

```
tests/
├── managers/                    # Feature management tests
│   └── test_humidity_automation.py
├── helpers/                     # Framework helper tests
│   ├── test_entity_naming_simple.py
│   ├── test_device.py
│   ├── test_service_registration.py
│   ├── test_device_feature_mapping.py
│   └── test_device_filter.py
├── frontend/                    # JavaScript frontend tests
│   ├── test-hvac-fan-card.js
│   ├── test-integration.js
│   └── test-template-helpers.js
├── config_flow/                 # Config flow tests
│   └── test_config_flow_integration.py
├── startup/                     # Startup flow tests
│   ├── test_startup_flow.py
│   └── test_default_entities_startup.py
└── test_registry.py             # Integration tests
```

---

## 11. Debugging and Troubleshooting Guide

This comprehensive troubleshooting guide covers common issues, debugging tools, and solutions for Ramses Extras integration.

### Common Issues and Solutions

#### Feature Not Loading

**Symptoms**: Feature doesn't appear in HA configuration options

**Solutions**:
1. Check `AVAILABLE_FEATURES` registration in main `const.py`
2. Verify feature factory function is properly implemented
3. Check HA logs for import or initialization errors
4. Ensure feature directory structure is correct

#### Entities Not Created

**Symptoms**: Features enabled but no entities appear in HA

**Solutions**:
1. Verify feature is enabled in HA configuration
2. Check SimpleEntityManager logs for entity creation issues
3. Ensure platform files are properly implemented
4. Verify device discovery is working correctly
5. Check entity states in HA

#### JavaScript Cards Not Loading

**Symptoms**: UI cards don't appear or show errors

**Solutions**:
1. Check that asset deployment completed successfully
2. Verify JavaScript files exist in `config/www/ramses_extras/`
3. Check browser console for JavaScript errors
4. Ensure feature has `ui_card: true` in configuration
5. Clear your browser cache (Ctrl+Shift+R or similar for your system)

#### WebSocket Command Failures

**Symptoms**: WebSocket commands return errors or time out

**Solutions**:
1. Verify WebSocket commands are registered during setup
2. Check parameter validation and required fields
3. Ensure device_id is properly formatted and exists
4. Check HA logs for WebSocket-related errors
5. Ensure device_id is properly passed to commands

#### Feature Not Working as Expected

**Symptoms**: Feature enabled but doesn't function correctly

**Solutions**:
1. Check the logs: home-assistant.log, ramses_log (or the filename you entered in Ramses RF)
2. Reload Home Assistant
3. Check parameter validation and error handling
4. Verify WebSocket commands are registered during setup

#### Performance Issues

**Symptoms**: Slow entity creation, high memory usage, or laggy UI

**Solutions**:
1. Use SimpleEntityManager bulk operations for entity changes
2. Enable caching for frequently accessed data
3. Monitor device discovery performance
4. Optimize JavaScript card update frequency

### Debug Tools

#### SimpleEntityManager Debug
- Use entity validation on startup for troubleshooting
- Check entity creation and removal logs
- Monitor device feature matrix state

#### WebSocket Testing
- Use `callWebSocket()` function for WebSocket command testing
- Test WebSocket commands in browser console

#### Message Listener Debug
- Use `RamsesMessageBroker.instance.getListenerInfo()` for message routing
- Check registered message listeners for debugging

#### Device Enumeration Debug
- Check logs for device enumeration and handler execution
- Monitor device discovery performance

### Working Debug Tool Examples

#### SimpleEntityManager Debug (Python)
```python
# In config flow or debug console
entity_manager = SimpleEntityManager(hass)
await entity_manager.validate_entities_on_startup()
```

#### WebSocket Testing (JavaScript console)
```javascript
// Test WebSocket commands in browser console
const result = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_bound_rem',
  device_id: '32:153289'
});
console.log('WebSocket result:', result);
```

#### Message Listener Debug (JavaScript console)
```javascript
// Check registered message listeners
const listenerInfo = RamsesMessageBroker.instance.getListenerInfo();
console.log('Active listeners:', listenerInfo);
```

### Debug Configuration

#### Logging Configuration

Enable detailed logging in HA configuration:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.ramses_extras: debug
    custom_components.ramses_extras.framework: debug
    custom_components.ramses_extras.features: debug
```

#### Debug Tools Summary

1. **SimpleEntityManager Debug**: Use `validate_entities_on_startup()` to check entity consistency
2. **WebSocket Testing**: Use `callWebSocket()` function to test WebSocket commands
3. **Message Listener Debug**: Use `RamsesMessageBroker.instance.getListenerInfo()` for message routing
4. **Device Enumeration Debug**: Check logs for device enumeration and handler execution

---

## 12. API Reference

### DeviceFeatureMatrix API

#### Core Methods

```python
class DeviceFeatureMatrix:
    def enable_feature_for_device(self, device_id: str, feature_id: str) -> None:
        """Enable a feature for a specific device."""

    def get_enabled_features_for_device(self, device_id: str) -> dict[str, bool]:
        """Get all enabled features for a device."""

    def get_enabled_devices_for_feature(self, feature_id: str) -> list[str]:
        """Get all devices that have this feature enabled."""

    def is_feature_enabled_for_device(self, feature_id: str, device_id: str) -> bool:
        """Check if feature is enabled for specific device."""

    def get_all_enabled_combinations(self) -> list[tuple[str, str]]:
        """Get all enabled feature/device combinations."""

    def get_matrix_state(self) -> dict[str, dict[str, bool]]:
        """Get the current matrix state for debugging/serialization."""

    def restore_matrix_state(self, state: dict[str, dict[str, bool]]) -> None:
        """Restore matrix state from saved state."""
```

### SimpleEntityManager API

#### Core Methods

```python
class SimpleEntityManager:
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize SimpleEntityManager."""

    async def create_entities_for_feature(
        self, feature_id: str, device_ids: list[str]
    ) -> list[str]:
        """Create entities directly for feature/device combinations."""

    async def remove_entities_for_feature(
        self, feature_id: str, device_ids: list[str]
    ) -> list[str]:
        """Remove entities directly for feature/device combinations."""

    async def calculate_entity_changes(
        self,
        old_matrix_state: dict[str, dict[str, bool]],
        new_matrix_state: dict[str, dict[str, bool]],
    ) -> tuple[list[str], list[str]]:
        """Calculate entity changes between two matrix states."""

    async def validate_entities_on_startup(self) -> None:
        """Check entity consistency on startup."""

    async def create_entity(self, entity_id: str) -> None:
        """Create a single entity directly."""

    async def remove_entity(self, entity_id: str) -> None:
        """Remove a single entity directly."""
```

### WebSocket Commands API

#### Command Registration

```python
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/default/get_bound_rem",
    vol.Required("device_id"): str,
})
@websocket_api.async_response
async def ws_get_bound_rem_default(hass, connection, msg):
    """Get bound REM device information."""
    device_id = msg["device_id"]
    # Implementation with SimpleEntityManager and device integration
```

#### Available Commands

The `default feature` is always enabled (and not listed in the config flow)

**Default Feature Commands:**
- **`ramses_extras/default/get_bound_rem`**: Get bound REM device information
- **`ramses_extras/default/get_2411_schema`**: Get device parameter schema
- **`ramses_extras`**: Get information about available commands

#### JavaScript Integration

```javascript
// Get bound REM device
const boundRem = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_bound_rem',
  device_id: '32:153289',
});

// Get parameter schema
const schema = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_2411_schema',
  device_id: '32:153289',
});
```

### Device Handler API

#### Device Type Handler Mapping

```python
# Framework mapping (const.py)
DEVICE_TYPE_HANDLERS = {
    "HvacVentilator": "handle_hvac_ventilator",
    "HvacController": "handle_hvac_controller",  # Future device type
    "Thermostat": "handle_thermostat",           # Future device type
}
```

#### Event System

**Event Name**: `ramses_device_ready_for_entities`

**Event Data**:
```python
{
    "device_id": "32:153289",
    "device_type": "HvacVentilator",
    "device_object": device,  # Full device object for inspection
    "entity_ids": ["sensor.indoor_absolute_humidity_32_153289", ...],
    "handled_by": "humidity_control"  # Which feature called the handler
}
```

---

## 13. Implementation Details

### Core Algorithms and Patterns

#### Entity Format Detection Algorithm

The automatic format detection system uses device_id position within entity names:

```python
def _detect_format_by_position(position: int, entity_name: str) -> str:
    """Detect format based on device_id position within entity name."""
    if position <= len(entity_name) * 0.3:
        return "cc"
    else:
        return "extras"
```

**Logic**:
- Device ID at **beginning** (≤30% of entity name length) → **CC Format**
- Device ID at **end** (>30% of entity name length) → **Extras Format**

#### Two-step Evaluation System

The enhanced device discovery uses a two-phase evaluation system.

**Phase 1 - Discovery:**
- Discover devices that should have entities
- Fire event for each discovered device
- Listeners can modify EntityRegistry or set flags, or whatever is needed. For example, if we know the model of the device we can adapt the min/max values, or disable certain entities. Do we know a certain FAN has only 1 humidity sensor,  we can adapt to this.

**Phase 2 - Creation:**
- Platform setup creates entities
- Check entity-specific flags before creation
- Apply any modifications from event listeners

#### Simple Entity Management Algorithm

Simplified entity management approach:

```python
async def calculate_entity_changes(
    self,
    old_matrix_state: dict[str, dict[str, bool]],
    new_matrix_state: dict[str, dict[str, bool]],
) -> tuple[list[str], list[str]]:
    """Calculate entity changes between two matrix states."""
    # Create temporary entity managers for old and new states
    old_entity_manager = SimpleEntityManager(self.hass)
    new_entity_manager = SimpleEntityManager(self.hass)

    # Restore old and new matrix states
    old_entity_manager.restore_device_feature_matrix_state(old_matrix_state)
    new_entity_manager.restore_device_feature_matrix_state(new_matrix_state)

    # Calculate required entities for old and new states
    old_required_entities = await old_entity_manager._calculate_required_entities()
    new_required_entities = await new_entity_manager._calculate_required_entities()

    # Calculate entity changes purely from the matrix-defined entities
    entities_to_create = set(new_required_entities) - set(old_required_entities)
    entities_to_remove = set(old_required_entities) - set(new_required_entities)

    return list(entities_to_create), list(entities_to_remove)
```

### Error Handling Strategies

#### Graceful Degradation
- Entity registry access failures return empty set (don't stop catalog building)
- Individual feature scanning errors are logged per feature but don't stop other features
- All operations designed for graceful degradation

#### Error Recovery Patterns
```python
async def validate_entities_on_startup(self) -> None:
    """Check entity consistency on startup."""
    try:
        # Get current entities
        current_entities = await self._get_current_entities()
    except Exception as e:
        _LOGGER.warning(f"Could not get entity registry: {e}")
        current_entities = []  # Continue with empty set

    # Continue with entity validation even if registry access failed
    required_entities = await self._calculate_required_entities()

    # Process entity changes with error handling
    if current_entities is not None:
        extra_entities = set(current_entities) - set(required_entities)
        await self._cleanup_extra_entities(extra_entities)

    missing_entities = set(required_entities) - set(current_entities or [])
    await self._create_missing_entities(missing_entities)
```

### Security Considerations

#### Input Validation
- Voluptuous schema validation for all WebSocket parameters
- Entity name validation with automatic format detection
- Device ID validation and sanitization

#### Access Control
- Device access control verification before operations
- Rate limiting for WebSocket commands to prevent abuse
- Error sanitization to prevent information leakage

#### WebSocket Security
- Required parameter validation for all commands
- Device permission verification before sensitive operations
- Comprehensive error handling with user-friendly messages

This architecture guide provides a comprehensive foundation for understanding and contributing to Ramses Extras. For additional technical details or specific implementation questions, refer to the inline code documentation and existing feature implementations.
