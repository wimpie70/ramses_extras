# Ramses Extras Architecture Migration Plan

## Overview

This document outlines the comprehensive architectural refactoring of Ramses Extras from a mixed helper/manager structure to a clean, feature-based organization with proper separation of concerns.

## Current State Analysis

### Existing Structure

```
ramses_extras/custom_components/ramses_extras/
├── 🔴 HA Required Files (Root Level)
│   ├── manifest.json
│   ├── __init__.py
│   ├── config_flow.py
│   └── const.py
│
├── 🟡 Mixed Responsibilities
│   ├── 📁 automations/
│   │   └── humidity_automation.py
│   ├── 📁 services/
│   │   └── fan_services.py
│   ├── 📁 helpers/
│   │   ├── automation.py
│   │   ├── broker.py
│   │   ├── device.py
│   │   ├── entities.py
│   │   ├── entity.py
│   │   └── platform.py
│   └── 📁 managers/
│       ├── automation_manager.py
│       ├── card_manager.py
│       ├── device_monitor.py
│       ├── entity_manager.py
│       └── platform_reloader.py
│
├── 🟢 Platform Files (HA Integration)
│   ├── binary_sensor.py
│   ├── number.py
│   ├── sensor.py
│   └── switch.py
│
└── 🟠 Web Assets
    └── 📁 www/
        ├── cards/
        ├── helpers/
        └── translations/
```

### Problems Identified

1. **Overlapping Responsibilities**: Entity operations scattered across `entity.py`, `entities.py`, and `entity_manager.py`
2. **Feature Fragmentation**: Humidity control logic split across `automations/`, `services/`, and `helpers/`
3. **Unclear Separation**: No distinction between utilities (helpers) and services (managers)
4. **Import Complexity**: Cross-dependencies between helpers and managers create tight coupling
5. **Testing Challenges**: Difficult to test features in isolation due to scattered code

## Target Architecture

### New Structure Overview

```
ramses_extras/custom_components/ramses_extras/
├── 🔑 HA Required Files (Root Level - UNCHANGED)
│   ├── manifest.json
│   ├── __init__.py
│   ├── config_flow.py
│   └── const.py
│
├── 🏗️ Features (Feature-Centric Organization)
│   ├── 📁 humidity_control/
│   │   ├── __init__.py
│   │   ├── automation.py          # HumidityAutomationManager
│   │   ├── services.py            # Humidity-specific services
│   │   ├── entities.py            # Humidity entity definitions
│   │   ├── config.py              # Feature configuration
│   │   ├── const.py               # Feature constants
│   │   └── tests/                 # Feature-specific tests
│   │       ├── __init__.py
│   │       ├── test_automation.py
│   │       ├── test_services.py
│   │       └── test_entities.py
│   │
│   ├── 📁 fan_control/
│   │   ├── __init__.py
│   │   ├── automation.py
│   │   ├── services.py
│   │   ├── entities.py
│   │   ├── config.py
│   │   ├── const.py
│   │   └── tests/
│   │
│   ├── 📁 sensor_management/
│   │   ├── __init__.py
│   │   ├── automation.py
│   │   ├── services.py
│   │   ├── entities.py
│   │   ├── config.py
│   │   ├── const.py
│   │   └── tests/
│   │
│   └── 📁 websocket_handler/
│       ├── __init__.py
│       ├── handler.py             # WebSocket message handling
│       ├── protocols.py           # Protocol definitions
│       ├── tests/
│       │   ├── test_handler.py
│       │   └── test_protocols.py
│
├── 🏛️ Framework (Reusable Foundation)
│   ├── 📁 helpers/
│   │   ├── 📁 entity/
│   │   │   ├── __init__.py
│   │   │   ├── core.py            # Entity base classes
│   │   │   ├── helpers.py         # Entity utilities
│   │   │   ├── state.py           # Entity state management
│   │   │   └── patterns.py        # Entity pattern generation
│   │   ├── 📁 device/
│   │   │   ├── __init__.py
│   │   │   ├── core.py            # Device base classes
│   │   │   ├── helpers.py         # Device utilities
│   │   │   └── parsers.py         # Device ID parsing
│   │   ├── 📁 automation/
│   │   │   ├── __init__.py
│   │   │   ├── core.py            # ExtrasBaseAutomation
│   │   │   ├── framework.py       # Automation patterns
│   │   │   └── lifecycle.py       # Automation lifecycle management
│   │   └── 📁 common/
│   │       ├── __init__.py
│   │       ├── logging.py         # Structured logging
│   │       ├── validation.py      # Input validation
│   │       └── exceptions.py      # Custom exceptions
│   │
│   ├── 📁 managers/
│   │   ├── __init__.py
│   │   ├── entity_manager.py      # Entity lifecycle service
│   │   ├── device_manager.py      # Device management service
│   │   ├── feature_manager.py     # Feature activation/deactivation
│   │   ├── automation_service.py  # Automation execution service
│   │   ├── websocket_manager.py   # WebSocket connection management
│   │   └── discovery_service.py   # Device/feature discovery
│   │
│   └── 📁 base_classes/
│       ├── __init__.py
│       ├── base_entity.py
│       ├── base_automation.py
│       ├── base_manager.py
│       └── base_service.py
│
├── 🔧 Services (Cross-Feature Services)
│   ├── __init__.py
│   ├── notification_service.py    # User notifications
│   ├── discovery_service.py       # Device discovery
│   ├── broker_service.py          # Message broker
│   └── health_service.py          # System health monitoring
│
├── 🌐 Platform (HA Integration - CONSOLIDATED)
│   ├── __init__.py
│   ├── const.py                   # Consolidated constants
│   ├── config_flow.py
│   ├── manifest.json
│   ├── sensor.py
│   ├── switch.py
│   ├── binary_sensor.py
│   ├── number.py
│   └── __init__.py
│
└── 📊 Testing (Centralized Test Structure)
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── __init__.py
    │   ├── devices.py
    │   ├── entities.py
    │   └── automations.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_humidity_control.py
    │   ├── test_fan_control.py
    │   └── test_sensor_management.py
    ├── unit/
    │   ├── __init__.py
    │   ├── helpers/
    │   │   ├── test_entity_helpers.py
    │   │   ├── test_device_helpers.py
    │   │   └── test_automation_framework.py
    │   ├── managers/
    │   │   ├── test_entity_manager.py
    │   │   ├── test_device_manager.py
    │   │   └── test_feature_manager.py
    │   └── services/
    │       ├── test_notification_service.py
    │       └── test_discovery_service.py
    └── e2e/
        ├── __init__.py
        ├── test_humidity_automation.py
        └── test_fan_control.py
```

## File Migration Plan

### Phase 1: Framework Consolidation

#### Files to be consolidated/moved within helpers/:

| Current Location        | New Location                                | Action                              |
| ----------------------- | ------------------------------------------- | ----------------------------------- |
| `helpers/entity.py`     | `framework/helpers/entity/core.py`          | Move (contains ExtrasBaseEntity)    |
| `helpers/entity.py`     | `framework/helpers/entity/helpers.py`       | Extract EntityHelpers class         |
| `helpers/entities.py`   | `framework/helpers/entity/state.py`         | Consolidate entity state operations |
| `helpers/device.py`     | `framework/helpers/device/core.py`          | Move device-related classes         |
| `helpers/device.py`     | `framework/helpers/device/helpers.py`       | Extract device helper functions     |
| `helpers/automation.py` | `framework/helpers/automation/core.py`      | Move ExtrasBaseAutomation           |
| `helpers/automation.py` | `framework/helpers/automation/framework.py` | Extract automation patterns         |
| `helpers/broker.py`     | `services/broker_service.py`                | Move to services                    |
| `helpers/platform.py`   | `platform/`                                 | Consolidate with platform files     |

#### Files to be consolidated/moved within managers/:

| Current Location                 | New Location                               | Action                          |
| -------------------------------- | ------------------------------------------ | ------------------------------- |
| `managers/entity_manager.py`     | `framework/managers/entity_manager.py`     | Consolidate entity lifecycle    |
| `managers/device_monitor.py`     | `framework/managers/device_manager.py`     | Consolidate device management   |
| `managers/automation_manager.py` | `framework/managers/automation_service.py` | Convert to service pattern      |
| `managers/card_manager.py`       | `services/notification_service.py`         | Move to services                |
| `managers/platform_reloader.py`  | `platform/`                                | Consolidate with platform files |

### Phase 2: Feature Creation

#### New feature folders to create:

1. **humidity_control** (Priority 1)
   - `features/humidity_control/automation.py` ← from `automations/humidity_automation.py`
   - `features/humidity_control/services.py` ← from `services/fan_services.py` (humidity-specific part)
   - `features/humidity_control/entities.py` ← new: Humidity entity definitions
   - `features/humidity_control/config.py` ← new: Feature configuration
   - `features/humidity_control/const.py` ← new: Feature constants
   - `features/humidity_control/tests/` ← new: Feature-specific tests

2. **websocket_handler** (Priority 1)
   - `features/websocket_handler/handler.py` ← new: WebSocket message handling
   - `features/websocket_handler/protocols.py` ← new: Protocol definitions
   - `features/websocket_handler/tests/` ← new: WebSocket tests

3. **fan_control** (Priority 2)
   - `features/fan_control/automation.py` ← new: Fan control automation
   - `features/fan_control/services.py` ← from `services/fan_services.py` (fan-specific part)
   - `features/fan_control/entities.py` ← new: Fan entity definitions
   - `features/fan_control/config.py` ← new: Feature configuration
   - `features/fan_control/const.py` ← new: Feature constants
   - `features/fan_control/tests/` ← new: Feature-specific tests

4. **sensor_management** (Priority 3)
   - `features/sensor_management/automation.py` ← new: Sensor management automation
   - `features/sensor_management/services.py` ← new: Sensor-specific services
   - `features/sensor_management/entities.py` ← from existing sensor entities
   - `features/sensor_management/config.py` ← new: Feature configuration
   - `features/sensor_management/const.py` ← new: Feature constants
   - `features/sensor_management/tests/` ← new: Feature-specific tests

### Phase 3: Platform Consolidation

#### Files to consolidate in platform/:

| Current Location     | New Location                | Action                                       |
| -------------------- | --------------------------- | -------------------------------------------- |
| `sensor.py`          | `platform/sensor.py`        | Move (consolidate with other platform files) |
| `switch.py`          | `platform/switch.py`        | Move (consolidate with other platform files) |
| `binary_sensor.py`   | `platform/binary_sensor.py` | Move (consolidate with other platform files) |
| `number.py`          | `platform/number.py`        | Move (consolidate with other platform files) |
| `__init__.py` (root) | `platform/__init__.py`      | Consolidate initialization                   |
| `const.py` (root)    | `platform/const.py`         | Consolidate constants                        |

## Import Update Strategy

### 1. Systematic Import Updates

All imports will need to be updated according to the new structure:

#### Before (Current):

```python
from ..helpers.entity import EntityHelpers, get_feature_entity_mappings
from ..helpers.automation import ExtrasBaseAutomation
from ..managers.entity_manager import EntityManager
from ..services.fan_services import async_set_fan_speed_mode
```

#### After (Target):

```python
from ...framework.helpers.entity import EntityHelpers, get_feature_entity_mappings
from ...framework.helpers.automation import ExtrasBaseAutomation
from ...framework.managers import EntityManager
from ...features.humidity_control.services import async_set_fan_speed_mode
```

### 2. Import Path Hierarchy

```
# Framework imports (relative to features/)
from ....framework.helpers.entity import EntityHelpers
from ....framework.helpers.automation import ExtrasBaseAutomation
from ....framework.managers import EntityManager

# Cross-feature service imports
from ....services.notification_service import NotificationService

# Same-feature imports (relative to feature/)
from .automation import HumidityAutomationManager
from .services import async_set_fan_speed_mode
from .entities import HumidityEntity
```

### 3. Circular Dependency Prevention

- **Helpers** can import from other helpers
- **Managers** can import from helpers
- **Services** can import from managers and helpers
- **Features** can import from framework layers
- **No reverse dependencies** (features cannot be imported by framework)

## Test Organization

### Test Structure

```
📊 tests/
├── 🔧 fixtures/                    # Shared test data
│   ├── devices.py                  # Mock device configurations
│   ├── entities.py                 # Mock entity states
│   └── automations.py              # Mock automation states
│
├── 🏗️ unit/                        # Unit tests
│   ├── helpers/                    # Framework helper tests
│   │   ├── test_entity_helpers.py
│   │   ├── test_device_helpers.py
│   │   └── test_automation_framework.py
│   ├── managers/                   # Framework manager tests
│   │   ├── test_entity_manager.py
│   │   ├── test_device_manager.py
│   │   └── test_feature_manager.py
│   └── services/                   # Cross-feature service tests
│       ├── test_notification_service.py
│       └── test_discovery_service.py
│
├── 🏢 integration/                 # Feature integration tests
│   ├── test_humidity_control.py    # Complete humidity feature test
│   ├── test_fan_control.py         # Complete fan control test
│   └── test_sensor_management.py   # Complete sensor management test
│
└── 🎭 e2e/                         # End-to-end tests
    ├── test_humidity_automation.py # Full automation flow
    └── test_fan_control.py         # Full fan control flow
```

### Feature-Specific Tests

Each feature will have its own test folder:

```
features/humidity_control/tests/
├── __init__.py
├── test_automation.py              # Humidity automation tests
├── test_services.py                # Humidity service tests
├── test_entities.py                # Humidity entity tests
└── test_config.py                  # Humidity configuration tests
```

## WebSocket Handling

### Current WebSocket Integration

WebSocket handling is currently scattered across multiple files. In the new architecture:

### Target WebSocket Structure

```
features/websocket_handler/
├── __init__.py
├── handler.py                      # Main WebSocket handler
├── protocols.py                    # Protocol definitions
├── message_types.py                # Message type definitions
├── connection_manager.py           # Connection lifecycle management
├── error_handler.py                # Error handling and recovery
└── tests/
    ├── __init__.py
    ├── test_handler.py             # Handler tests
    ├── test_protocols.py           # Protocol tests
    └── test_integration.py         # End-to-end WebSocket tests
```

### Integration with Features

- **humidity_control** can register WebSocket message handlers
- **fan_control** can register WebSocket message handlers
- **websocket_handler** provides the infrastructure for all features

## Implementation Phases

### Phase 1: Foundation (Week 1)

1. **Create framework structure**
2. **Move and consolidate helpers**
3. **Move and consolidate managers**
4. **Update all framework imports**

**Deliverables:**

- Clean framework structure
- All helpers and managers in proper locations
- Framework tests passing

### Phase 2: Core Features (Week 2-3)

1. **Create humidity_control feature**
2. **Create websocket_handler feature**
3. **Migrate existing humidity automation**
4. **Update all feature imports**

**Deliverables:**

- Working humidity_control feature
- WebSocket infrastructure
- Updated humidity automation

### Phase 3: Additional Features (Week 4)

1. **Create fan_control feature**
2. **Create sensor_management feature**
3. **Migrate remaining services**
4. **Platform consolidation**

**Deliverables:**

- All features migrated
- Clean platform layer
- Full test coverage

### Phase 4: Testing & Validation (Week 5)

1. **Complete test migration**
2. **Integration testing**
3. **Performance validation**
4. **Documentation updates**

**Deliverables:**

- Full test suite migrated and passing
- Performance benchmarks
- Updated documentation

## Risk Mitigation

### 1. Backward Compatibility

- **Maintain existing public APIs** during migration
- **Deprecation warnings** for removed interfaces
- **Gradual migration path** for external consumers

### 2. Testing Strategy

- **Incremental testing** after each phase
- **Feature isolation testing** to ensure no regressions
- **Performance regression testing** to catch performance issues

### 3. Rollback Plan

- **Git branches** for each major phase
- **Automated rollback scripts** for each migration step
- **Feature flags** to enable/disable migrated features

### 4. Quality Assurance

- **Code review required** for all migrations
- **Automated testing** must pass before merge
- **Manual testing** of critical user flows

## Success Criteria

### 1. Architectural Goals

- ✅ **Clear separation of concerns** between framework and features
- ✅ **Feature modularity** with minimal cross-feature dependencies
- ✅ **Maintainable code structure** that scales with new features
- ✅ **Testable architecture** with isolated unit and integration tests

### 2. Technical Goals

- ✅ **Zero breaking changes** for existing users during migration
- ✅ **Improved test coverage** and faster test execution
- ✅ **Better code organization** with logical file locations
- ✅ **Enhanced developer experience** with clearer code boundaries

### 3. Performance Goals

- ✅ **No performance degradation** from architectural changes
- ✅ **Faster development** due to better code organization
- ✅ **Easier debugging** with feature-isolated logging and testing
- ✅ **Improved maintainability** reducing technical debt

## Migration Checklist

### Pre-Migration

- [ ] Create feature branches for migration phases
- [ ] Set up automated testing pipeline
- [ ] Document current API dependencies
- [ ] Create rollback procedures

### Phase 1 - Framework

- [ ] Create framework directory structure
- [ ] Move and consolidate helpers
- [ ] Move and consolidate managers
- [ ] Update framework imports
- [ ] Framework tests passing

### Phase 2 - Core Features

- [ ] Create humidity_control feature
- [ ] Create websocket_handler feature
- [ ] Migrate humidity automation
- [ ] Update feature imports
- [ ] Core feature tests passing

### Phase 3 - Additional Features

- [ ] Create fan_control feature
- [ ] Create sensor_management feature
- [ ] Migrate remaining services
- [ ] Platform consolidation
- [ ] All feature tests passing

### Phase 4 - Testing & Validation

- [ ] Complete test migration
- [ ] Integration testing
- [ ] Performance validation
- [ ] Documentation updates
- [ ] Full test suite passing

### Post-Migration

- [ ] Remove deprecated code
- [ ] Clean up old directory structure
- [ ] Update developer documentation
- [ ] Performance benchmarking
- [ ] User acceptance testing

## Conclusion

This migration plan provides a comprehensive roadmap for transforming Ramses Extras from its current mixed-responsibility structure to a clean, feature-based architecture. The phased approach ensures minimal risk while delivering significant improvements in code organization, maintainability, and testability.

The new architecture will enable:

- **Faster feature development** through clear boundaries
- **Better testing** through feature isolation
- **Easier maintenance** through logical organization
- **Improved scalability** for future features

This migration represents a significant investment in the long-term health and maintainability of the Ramses Extras codebase.
