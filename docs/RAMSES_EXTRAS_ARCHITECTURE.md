always read .kilocode/rules/kilo rules.txt
# Ramses Extras Complete Architecture Guide

## Overview

Ramses Extras is a **feature-centric** Home Assistant integration built on a reusable **framework foundation**. It extends the ramses_cc integration with additional features, entities, and UI components through a clean, modular architecture.

## 🏗️ Architecture Principles

### 1. **Feature-Centric Organization**

- Each feature is **self-contained** with its own automation, services, entities, and config
- Features are **discoverable** and **modular**
- Clear **separation of concerns** within each feature

### 2. **Framework Foundation**

- **Reusable helpers** that all features can use
- **Base classes** for common functionality
- **Common utilities** for logging, validation, etc.

### 3. **Home Assistant Integration**

- Standard HA platform integration (sensor, switch, binary_sensor, number)
- Type-safe entity implementations
- Full compatibility with HA ecosystem

## 📁 Directory Structure

```
custom_components/ramses_extras/
├── 🔑 Core Integration (HA Requirements)
│   ├── __init__.py              # Integration entry point
│   ├── config_flow.py           # HA config flow
│   ├── const.py                 # Core constants
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
│   │   └── www/                 # Feature-specific web assets (integration structure)
│   │       └── hvac_fan_card/   # Feature card files
│   │           ├── hvac-fan-card.js
│   │           ├── hvac-fan-card-editor.js
│   │           ├── airflow-diagrams.js
│   │           ├── card-styles.js
│   │           ├── message-handlers.js
│   │           ├── templates/
│   │           └── translations/
│   │
│   └── default/                 # Default feature scaffold
│       ├── __init__.py
│       └── const.py
│
├── 🏛️ Framework (Reusable Foundation)
│   ├── base_classes/            # Base classes
│   │   ├── base_entity.py       # Entity base class
│   │   └── __init__.py
│   │
│   ├── helpers/                 # Reusable Python utilities
│   │   ├── entity/              # Entity helpers
│   │   │   ├── core.py          # Entity core functionality
│   │   │   ├── manager.py       # Entity manager (config flow)
│   │   │   └── __init__.py
│   │   ├── device/              # Device helpers
│   │   │   ├── core.py          # Device core functionality
│   │   │   └── __init__.py
│   │   ├── automation/          # Automation helpers
│   │   │   ├── base.py          # Automation base class
│   │   │   └── __init__.py
│   │   ├── common/              # Common utilities
│   │   │   ├── validation.py    # Input validation
│   │   │   └── __init__.py
│   │   ├── paths.py             # Shared path constants (Python)
│   │   └── __init__.py
│   │
│   ├── www/                     # Reusable JavaScript utilities
│   │   ├── paths.js             # Environment-aware path constants
│   │   ├── card-commands.js
│   │   ├── card-services.js
│   │   ├── card-translations.js
│   │   ├── card-validation.js
│   │   └── ramses-message-broker.js
│   │
│   ├── managers/                # Framework managers
│   │   ├── feature_manager.py   # Feature lifecycle management
│   │   └── __init__.py
│   │
│   ├── entity_registry.py       # Entity registry
│   └── __init__.py
│
├── 🌐 Platform (HA Integration)
│   ├── sensor.py                # Root sensor platform
│   ├── switch.py                # Root switch platform
│   ├── binary_sensor.py         # Root binary sensor platform
│   ├── number.py                # Root number platform
│   └── __init__.py
│
└── translations/                # Integration-level translations
    ├── en.json                 # English integration strings
    └── nl.json                 # Dutch integration strings
```

## 🚀 Deployment Structure (Home Assistant)

When features are enabled, files are copied to Home Assistant's `config/www/` directory with the following structure:

### Current vs Target Deployment Structure

**Current Structure:**

```
hass/config/www/ramses_extras/
├── helpers/                   # Shared utilities (copied from framework/www/)
│   ├── paths.js
│   ├── card-commands.js
│   ├── card-services.js
│   ├── card-translations.js
│   ├── card-validation.js
│   └── ramses-message-broker.js
└── features/                  # Feature-specific folders
    └── hvac_fan_card/         # Each feature gets its own folder
        ├── hvac-fan-card.js
        ├── hvac-fan-card-editor.js
        ├── airflow-diagrams.js
        ├── card-styles.js
        ├── message-handlers.js
        ├── templates/
        └── translations/
```

**Target Structure:**

```
hass/config/www/ramses_extras/
├── helpers/                   # Shared utilities (copied from framework/www/)
│   ├── paths.js
│   ├── card-commands.js
│   ├── card-services.js
│   ├── card-translations.js
│   ├── card-validation.js
│   └── ramses-message-broker.js
└── features/                  # Feature-specific folders
    └── hvac_fan_card/         # Each feature gets its own folder
        ├── hvac-fan-card.js
        ├── hvac-fan-card-editor.js
        ├── airflow-diagrams.js
        ├── card-styles.js
        ├── message-handlers.js
        ├── templates/
        └── translations/
```

**Source Locations:**

- **Helpers**: Copied from `framework/www/` (JavaScript framework utilities)
- **Features**: Copied from `features/{feature}/www/{feature}/` (feature-specific assets)

### Benefits of Target Structure

- **Clear Separation**: Helpers and features have distinct locations
- **Scalable**: Each feature gets its own folder within `features/`
- **Consistent URLs**: `/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js`
- **Organized**: Easy to add multiple features without conflicts

### Key Changes

1. **Path Separation**: Helpers copied to `helpers/`, features to `features/`
2. **Feature Folders**: Each feature gets its own folder (not single files)
3. **URL Structure**: Predictable pattern for all feature assets
4. **Integration Preservation**: Development file organization remains unchanged

## 🎯 Feature Architecture

### Feature Structure Pattern

Each feature follows the same pattern:

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

- **automation.py**: Feature-specific automation logic (e.g., `HumidityAutomationManager`)
- **services.py**: Feature-specific service methods (e.g., `HumidityServices`)
- **entities.py**: Feature-specific entity management (e.g., `HumidityEntities`)
- **config.py**: Feature-specific configuration (e.g., `HumidityConfig`)
- **const.py**: Feature-specific constants and mappings
- **platforms/**: HA platform implementations with feature-specific entity classes
- \***\*init**.py\*\*: Feature factory functions

## 🏛️ Framework Foundation

### Base Classes

- **ExtrasBaseEntity**: Base class for all custom entities
- **ExtrasBaseAutomation**: Base class for automation logic

### Helper Modules

- **Entity Helpers**: Entity creation, validation, naming utilities
- **Device Helpers**: Device ID parsing, discovery utilities
- **Automation Helpers**: Automation patterns and lifecycle management
- **Common Utilities**: Logging, validation, error handling

### Managers

- **FeatureManager**: Feature activation/deactivation lifecycle
- **EntityRegistry**: Centralized entity registration and management

## 🎯 Entity Management Architecture (EntityManager)

### Overview

The EntityManager is the central system for handling entity lifecycle management during config flow operations. It provides a centralized, efficient approach for tracking, creating, and removing entities based on feature changes.

#### Core Data Structure

```python
all_possible_entities: dict[str, EntityInfo] = {
    "entity_id": {
        "exists_already": bool,      # Whether entity currently exists in HA
        "enabled_by_feature": bool,  # Whether entity should exist based on enabled features
        "feature_id": str,           # Which feature creates this entity
        "entity_type": str,          # sensor, switch, automation, card, etc.
        "entity_name": str,          # Base entity name
    }
}
```

#### Key Components

1. **EntityManager Class**: Central orchestrator for all entity operations
2. **EntityInfo TypedDict**: Type-safe entity metadata structure
3. **Single-Pass Catalog Building**: Efficient entity discovery and cataloging
4. **Centralized Change Detection**: Clean separation of creation vs removal logic
5. **Bulk Operations**: Efficient entity creation/removal operations

### EntityManager Core Architecture

#### 1. Entity Catalog Building

```python
async def build_entity_catalog(
    self,
    available_features: dict[str, dict[str, Any]],
    current_features: dict[str, bool],
) -> None:
    """Build complete entity catalog with existence and feature status."""

    # Single iteration over all features
    for feature_id, feature_config in available_features.items():
        await self._scan_feature_entities(feature_id, feature_config, existing_entities)
```

#### 2. Feature Target Updates

```python
def update_feature_targets(self, target_features: dict[str, bool]) -> None:
    """Update feature targets for entity comparison."""

    # Single pass to update all entities
    for entity_id, info in self.all_possible_entities.items():
        feature_id = info["feature_id"]
        info["enabled_by_feature"] = self.target_features.get(feature_id, False)
```

#### 3. Change Detection

```python
def get_entities_to_remove(self) -> list[str]:
    """Get list of entities to be removed."""
    return [
        entity_id for entity_id, info in self.all_possible_entities.items()
        if info["exists_already"] and not info["enabled_by_feature"]
    ]

def get_entities_to_create(self) -> list[str]:
    """Get list of entities to be created."""
    return [
        entity_id for entity_id, info in self.all_possible_entities.items()
        if info["enabled_by_feature"] and not info["exists_already"]
    ]
```

#### 4. Bulk Operations

```python
async def apply_entity_changes(self) -> None:
    """Apply removal and creation operations."""
    to_remove = self.get_entities_to_remove()
    to_create = self.get_entities_to_create()

    # Group by entity type for efficient bulk operations
    if to_remove:
        await self._bulk_remove_entities(to_remove)
    if to_create:
        await self._bulk_create_entities(to_create)
```

### Config Flow Integration

```python
# config_flow.py
async def async_step_features(self, user_input):
    if feature_changes:
        # Single EntityManager instance
        self._entity_manager = EntityManager(self.hass)
        await self._entity_manager.build_entity_catalog(
            AVAILABLE_FEATURES, current_features
        )

        # Update targets for comparison
        self._entity_manager.update_feature_targets(enabled_features)

        # Clean, simple lists
        self._entities_to_remove = self._entity_manager.get_entities_to_remove()
        self._entities_to_create = self._entity_manager.get_entities_to_create()

        return await self.async_step_confirm()
```

## 🚀 Enhanced Device Discovery Architecture

### Overview

The Enhanced Device Discovery system provides advanced device detection, brand-specific customization, and runtime entity management. It builds on the framework foundation to deliver better separation of concerns, extensibility, and user customization capabilities.

### Core Components

#### 1. Device Type Handler Mapping

Central framework-level mapping from device types to specialized handlers:

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
- No handler duplication across features
- Clear separation between device handling and feature logic
- Easy addition of new device types

#### 2. Event System

**Event Name**: `ramses_device_ready_for_entities`

**Timing**: After device handler completes but BEFORE entity creation

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

#### 3. Double Evaluation System

**Phase 1 - Discovery:**

- Discover devices that should have entities
- Fire event for each discovered device
- Listeners can modify EntityRegistry or set flags

**Phase 2 - Creation:**

- Platform setup creates entities
- Check entity-specific flags before creation
- Apply any modifications from event listeners

#### 4. Entity Configuration Enhancement

**New Flag**: `default_enabled` in all entity configurations

```python
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify {device_id}",
        "default_enabled": True,  # NEW: defaults to True for existing entities
        "entity_template": "dehumidify_{device_id}",
        # ... other config
    }
}
```

### Brand-Specific Customization

#### Event Listener Pattern

```python
async def _on_device_ready_for_entities(self, event_data):
    """Handle device discovery with brand-specific logic."""
    device = event_data["device_object"]

    # Brand detection
    if self._is_orcon_device(device):
        await self._handle_orcon_device(event_data)

    # Generic brand customization
    brand_info = self._detect_device_brand(device)
    if brand_info:
        await self._apply_brand_customization(event_data, brand_info)
```

#### Orcon Device Customization

```python
async def _handle_orcon_device(self, event_data):
    """Apply Orcon-specific customizations."""
    device = event_data["device_object"]

    # Add Orcon-specific entities
    event_data["entity_ids"].extend([
        f"sensor.orcon_filter_usage_{device.id}",
        f"select.orcon_operation_mode_{device.id}",
        f"number.orcon_target_humidity_{device.id}"
    ])

    # Set Orcon-specific defaults
    event_data["orcon_defaults"] = {
        "target_humidity": 55,
        "auto_mode_enabled": True,
        "smart_boost_enabled": True
    }
```

## 🔧 Entity Naming System

### Simplified Universal Entity Naming

The Ramses Extras entity naming system uses **automatic format detection** to handle both CC and Extras entity formats seamlessly. This eliminates the need for manual format specification and simplifies entity management throughout the system.

#### Universal Entity Format

**Format:** `{entity_type}.{template}` with automatic format detection

**Key Innovation:** Templates use `{device_id}` placeholders, and the position within the template automatically determines the entity format:

- **CC Format** (device_id prefix): `{device_id}_{specific_identifier}`
  - Example: `number.32_153289_param_7c00`
  - Example: `sensor.29_099029_temp`

- **Extras Format** (device_id suffix): `{entity_name}_{device_id}`
  - Example: `sensor.indoor_absolute_humidity_32_153289`
  - Example: `switch.dehumidify_32_153289`
  - Example: `number.relative_humidity_minimum_32_153289`

#### Automatic Format Detection

**How It Works:**
1. **Device ID Recognition**: System matches patterns like `12_345678` or `12:345678`
2. **Position Analysis**:
   - Device ID at beginning (≤30% of entity name) → CC format (prefix)
   - Device ID at end → Extras format (suffix)
3. **Seamless Processing**: All entities processed using the same logic regardless of format

#### Core Entity Helper Methods

**1. Universal Entity Generation**
```python
# Automatic format detection based on template position
EntityHelpers.generate_entity_name_from_template(
    "sensor", "indoor_absolute_humidity_{device_id}",
    device_id="32_153289"
)
# Returns: "sensor.indoor_absolute_humidity_32_153289" (Extras format)

EntityHelpers.generate_entity_name_from_template(
    "number", "{device_id}_param_{param_id}",
    device_id="32_153289", param_id="7c00"
)
# Returns: "number.32_153289_param_7c00" (CC format)
```

**2. Universal Entity Parsing**
```python
# Works for both formats automatically
EntityHelpers.parse_entity_id("sensor.indoor_absolute_humidity_32_153289")
# Returns: ("sensor", "indoor_absolute_humidity", "32_153289")

EntityHelpers.parse_entity_id("number.32_153289_param_7c00")
# Returns: ("number", "param_7c00", "32_153289")
```

#### Feature-Centric Template Organization

**Template Structure (No Changes Required):**
```python
# features/humidity_control/const.py - Unchanged, works automatically
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "entity_template": "dehumidify_{device_id}",  # Automatic Extras format
        "name_template": "Dehumidify {device_id}",
    }
}

# features/default/const.py - Unchanged, works automatically
DEFAULT_SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "entity_template": "indoor_absolute_humidity_{device_id}",  # Automatic Extras format
        "name_template": "Indoor Absolute Humidity {device_id}",
    }
}
```

**Benefits:**
- ✅ **Feature-Centric**: Templates remain in feature const files as designed
- ✅ **Backward Compatible**: All existing templates continue to work unchanged
- ✅ **No Manual Specification**: Automatic format detection eliminates format choices
- ✅ **Simplified Maintenance**: Single template system with intelligent detection

#### Integration with EntityManager

The EntityManager automatically uses the enhanced EntityHelpers for all entity operations:

```python
# EntityManager leverages automatic detection
class EntityManager:
    async def _scan_feature_entities(self, feature_id, feature_config, existing_entities):
        # Use automatic format detection for all entities
        for entity_id in existing_entities:
            parsed = EntityHelpers.parse_entity_id(entity_id)  # Works for both formats
            if parsed:
                entity_type, entity_name, device_id = parsed
                # Process entity regardless of format

        # Generate new entities using universal templates
        entity_mappings = get_feature_entity_mappings(feature_id, device_id)
        # Automatic format detection works for all generated entities
```

This approach provides a **unified, maintainable entity naming system** that automatically handles format differences without requiring manual specification or complex conditional logic.

## 🌐 Home Assistant Integration

### Root Platform Files (Thin Wrappers)

```python
# sensor.py - ROOT PLATFORM (Thin Wrapper)
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Home Assistant platform integration - thin wrapper only."""
    # Forward to feature platforms
    await async_forward_entry_setups(
        config_entry, ["ramses_extras_humidity_control"], hass
    )
```

### Feature Platforms (Business Logic)

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

## 🔄 Data Flow

### Integration Startup

1. **HA Integration Loads**: `__init__.py` handles integration setup
2. **Platform Forwarding**: Root platforms forward to feature platforms
3. **Feature Creation**: Feature factories create feature instances
4. **Entity Registration**: Entities register with HA via platforms

### Feature Lifecycle

1. **Discovery**: Device discovery identifies available devices
2. **Feature Activation**: Features are enabled based on configuration
3. **Entity Creation**: Platform entities are created for each device
4. **Automation Start**: Feature automations begin monitoring and control
5. **Runtime Operation**: Entities update states, automations make decisions

### Enhanced Discovery Flow

1. **HA Integration Loads**: `__init__.py` handles integration setup
2. **Enhanced Discovery**: Framework discovers devices with type handlers
3. **Customization**: Brand-specific listeners apply customizations via events
4. **Feature Activation**: Features are enabled based on configuration
5. **Entity Creation**: Platform entities are created for each device with filtering
6. **Automation Start**: Feature automations begin monitoring and control
7. **Runtime Operation**: Entities update states, automations make decisions

## 🌍 Translations and Localization

### Two-Level Translation System

Ramses Extras uses a **dual-level translation system** to support both Home Assistant integration strings and frontend UI localization:

#### 1. Integration-Level Translations

- **Location**: `translations/` directory
- **Purpose**: Home Assistant config flow, options, and integration strings
- **Format**: JSON files per language (en.json, nl.json)
- **Usage**: HA setup wizard, configuration options, service descriptions

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Ramses Extras Setup"
      }
    }
  },
  "options": {
    "step": {
      "features": {
        "title": "Ramses Extras Options"
      }
    }
  }
}
```

#### 2. Frontend-Level Translations

- **Integration Location**: `features/{feature}/www/{feature}/translations/` directories
- **Deployment Location**: `config/www/ramses_extras/features/{feature}/translations/` directories
- **Purpose**: JavaScript cards, UI elements, and frontend strings
- **Format**: JSON files per language (en.json, nl.json)
- **Usage**: Lovelace cards, control interfaces, status displays

```json
{
  "card": {
    "title": "HVAC Ventilation Control",
    "settings": "Settings"
  },
  "status": {
    "away": "Away",
    "low": "Low",
    "medium": "Medium"
  }
}
```

## 🎨 Template Systems Architecture

Ramses Extras uses multiple template systems depending on the context and requirements:

### 1. JavaScript Template System (Frontend Cards)

**Purpose**: Generate HTML dynamically for Home Assistant Lovelace cards

**Integration Location**: `features/{feature}/www/{feature}/templates/` directories

**Deployment Location**: `config/www/ramses_extras/features/{feature}/templates/` directories

**Structure**: Modular template organization

```
Integration: features/hvac_fan_card/www/hvac_fan_card/templates/
Deployment:  config/www/ramses_extras/features/hvac_fan_card/templates/

├── card-templates.js        # Central export/import index
├── card-header.js          # Header section template
├── top-section.js          # Main data display template
├── controls-section.js     # Control buttons template
├── parameter-edit.js       # Parameter editing template
├── card-footer.js          # Footer actions template
└── template-helpers.js     # Data transformation utilities
```

### 2. Entity Template System (Python)

**Purpose**: Generate consistent entity names and display names for Home Assistant entities

**Location**: Configuration files and entity helper functions

### 3. Translation Templates

**Purpose**: UI localization with dynamic translation loading

**Location**: `translations/` directories for both integration and frontend

## 🧪 Testing and Documentation

### Test Structure

- **Location**: `tests/` directory at project root
- **Purpose**: Unit tests, integration tests, and validation
- **Organization**: Tests mirror the feature-centric structure

```
tests/
├── managers/                    # Feature management tests
│   ├── test_humidity_automation.py # ✅ Current and functional
│   ├── test_device_monitor.py      # ⚠️ May need updating
│   └── test_platform_reloader.py   # ⚠️ May need updating
├── helpers/                     # Framework helper tests
│   ├── test_entity_naming_simple.py # ✅ Current and functional
│   ├── test_device.py             # ✅ Current and functional
│   └── test_service_registration.py # ✅ Current and functional
├── frontend/                    # JavaScript frontend tests
│   ├── test-hvac-fan-card.js
│   ├── test-integration.js
│   ├── test-template-helpers.js
│   └── README.md                 # Frontend testing guide
├── test_registry.py             # Integration tests
└── test_const_consolidation_verification.py # Integration tests
```

### Documentation Structure

- **Location**: `docs/` directory at project root
- **Purpose**: Technical documentation and architecture guides
- **Content**: Developer guides, technical references, and implementation notes

## 🔧 Development Guidelines

### File Responsibilities

- **Root Platform Files**: Only HA integration code, forward to features
- **Feature Files**: Feature-specific business logic and entity implementations
- **Framework Files**: Reusable utilities and base classes
- **Frontend Files**: JavaScript/HTML assets for UI components

### Import Patterns

```python
# Feature imports (relative)
from ...automation import HumidityAutomationManager
from ...framework.helpers.automation import ExtrasBaseAutomation
from ...framework.helpers.entity import EntityHelpers

# Root imports (absolute)
from custom_components.ramses_extras.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
```

### Naming Conventions

- **Feature Names**: snake_case (e.g., `humidity_control`)
- **Entity Classes**: PascalCase with feature prefix (e.g., `HumidityAbsoluteSensor`)
- **Helper Functions**: snake_case (e.g., `calculate_absolute_humidity`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `HUMIDITY_CONTROL_FEATURE`)

## 📋 Key Benefits

### 1. Maintainability

- Clear separation of concerns
- Feature isolation prevents cascading changes
- Logical file organization

### 2. Testability

- Features can be tested independently
- Framework provides testable utilities
- Component isolation enables focused testing

### 3. Extensibility

- Easy to add new features using established patterns
- Framework foundation supports any number of features
- Feature-centric approach enables user customization

### 4. Compatibility

- Full Home Assistant integration compliance
- Standard platform implementations
- Type-safe entity implementations

## 🎯 Adding New Features

### 1. Create Feature Structure

```bash
mkdir -p custom_components/ramses_extras/features/my_new_feature
cd custom_components/ramses_extras/features/my_new_feature
touch __init__.py automation.py services.py entities.py config.py const.py
mkdir -p platforms
touch platforms/__init__.py platforms/sensor.py platforms/switch.py
```

### 2. Implement Core Components

- **automation.py**: Feature-specific automation logic
- **services.py**: Feature-specific service methods
- **entities.py**: Entity configuration and management
- **config.py**: Feature configuration handling
- **const.py**: Feature-specific constants

### 3. Implement Platform Files

- **platforms/sensor.py**: Sensor entity classes
- **platforms/switch.py**: Switch entity classes
- **platforms/number.py**: Number entity classes
- **platforms/binary_sensor.py**: Binary sensor entity classes

### 4. Add Feature Factory

```python
# features/my_new_feature/__init__.py
def create_my_new_feature(hass, config_entry):
    return {
        "automation": MyNewFeatureAutomation(hass, config_entry),
        "entities": MyNewFeatureEntities(hass, config_entry),
        "services": MyNewFeatureServices(hass, config_entry),
        "config": MyNewFeatureConfig(hass, config_entry),
    }
```

### 5. Register Feature

Add feature to main integration registration in `__init__.py`.

## 🎯 Current Features

### ✅ Implemented Features

1. **Humidity Control**: Complete implementation with all components
   - Automation logic for humidity-based fan control
   - Entities for humidity sensor and controls
   - Services for humidity management
   - Platform integrations for all entity types

2. **HVAC Fan Card**: Partial implementation
   - Card structure and configuration
   - UI templates and styling
   - JavaScript message handling

### 📋 Planned Features

1. **Humidity Control Card**: Dedicated Card for the Humidity Control
2. **Your Feature**: ???

## Performance Characteristics

### EntityManager Performance

- **Single Pass Processing**: Efficient entity catalog building in one iteration
- **Efficient Change Detection**: List comprehensions for fast queries
- **Bulk Operations**: Grouped entity operations for optimal performance
- **Centralized Architecture**: Single data structure for optimal memory usage

## Platform Registration Architecture

### Core Implementation

The platform registration system ensures that only enabled features create entities through comprehensive feature filtering:

1. **Feature Registry**: All platform registrations stored in `hass.data["ramses_extras"]["PLATFORM_REGISTRY"]`
2. **Enabled Feature Filtering**: Platform setup functions check enabled status before execution
3. **Debug Logging**: Skipped features logged for troubleshooting
4. **Entity Creation Control**: Only enabled features create entities

### Files

- `__init__.py`: Platform registry management
- `sensor.py`: Sensor platform with feature filtering
- `switch.py`: Switch platform with feature filtering
- `binary_sensor.py`: Binary sensor platform with feature filtering
- `number.py`: Number platform with feature filtering

### Key Features

✅ **Feature-based filtering** - Only enabled features create entities
✅ **Coordinated device discovery** - Happens before platform setup
✅ **Robust broker access** - Multiple fallback strategies
✅ **Entity management** - Centralized EntityManager integration

## JavaScript Message Listener Integration

### Overview

Implemented a reusable JavaScript-based message listener system for handling ramses_cc 31DA messages in real-time, providing immediate HVAC state updates to the user interface.

### Architecture

#### 1. Configuration-Driven Setup (const.py)

```python
"hvac_fan_card": {
    "handle_codes": ["31DA", "10D0"],
    "callback_prefix": "handle_",
    # ... existing config
}
```

#### 2. Global Message Helper

- **Singleton Pattern**: Single instance per page for efficient message routing
- **Global Event Listener**: Listens to `ramses_cc_message` events
- **Auto-Discovery**: Calls `handle_31DA()`, `handle_10D0()` methods on cards
- **Device Filtering**: Routes messages to correct cards based on device_id

#### 3. Message Handlers

- **Separated Logic**: Card-specific handlers in dedicated file
- **Data Processing**: Extract and normalize 31DA data
- **Utility Functions**: Format temperature, humidity, fan speeds

#### 4. Card Integration

- **Auto-Registration**: Cards register for their configured message codes
- **Real-time Updates**: Immediate UI updates when messages received

### File Structure

**Integration Structure (Development):**

```
custom_components/ramses_extras/
├── framework/www/
│   └── ramses-message-helper.js      # Global singleton helper
└── features/hvac_fan_card/www/hvac_fan_card/
    └── [card_files]                  # Feature card files
```

**Deployment Structure (Home Assistant):**

```
hass/config/www/ramses_extras/
├── helpers/
│   └── ramses-message-helper.js      # Global singleton helper
└── features/
    └── hvac_fan_card/               # Feature card folder
        └── [card_files]              # Feature card files
```

### Key Features

#### Real-time Processing

- **Zero Polling Delay**: Messages processed as they arrive
- **Batch Updates**: Multiple entities updated per 31DA message
- **Device-Specific**: Only relevant cards receive messages

#### Performance Optimized

- **Singleton Architecture**: Single global listener for all cards
- **Efficient Filtering**: Only checks registered device/message combinations
- **Memory Management**: Automatic cleanup on card removal

#### Backward Compatible

- **Entity Fallback**: Uses existing entity data when 31DA unavailable
- **Progressive Enhancement**: Works with or without 31DA support
- **No Breaking Changes**: Existing functionality preserved

This architecture provides significant improvements to user experience by providing immediate feedback on HVAC system changes.

## Documentation Organization

### Primary Architecture Document

This document (`RAMSES_EXTRAS_ARCHITECTURE.md`) serves as the comprehensive architecture guide covering:

- **Core Architecture**: Feature-centric design principles and directory structure
- **Entity Management**: EntityManager architecture and benefits
- **Enhanced Device Discovery**: Advanced device detection and brand customization
- **Entity Naming System**: Consistent naming conventions and helper methods
- **Home Assistant Integration**: Platform implementation patterns
- **Data Flow**: Startup, feature lifecycle, and discovery flows
- **Template Systems**: Multi-template architecture for frontend and backend
- **Development Guidelines**: Best practices and patterns
- **Performance Benefits**: Benchmark results and improvements
- **JavaScript Integration**: Real-time message handling system

### Supporting Technical References

The following documents remain as separate technical references:

- **ENHANCED_DEVICE_DISCOVERY_ARCHITECTURE.md**: Detailed device discovery implementation guide
- **ENTITYMANAGER_API_REFERENCE.md**: Complete API documentation for developers
- **JS_MESSAGE_LISTENER.md**: JavaScript implementation guide
- **FILES_NO_LONGER_NEEDED.md**: Historical cleanup record

### Removed Documentation

The following redundant files have been removed to reduce documentation duplication:

- **ARCHITECTURE.md**: Merged into main architecture document
- **ENTITY_MANAGEMENT_STRATEGY.md**: Content integrated into main architecture
- **ENTITYMANAGER_FRAMEWORK_INTEGRATION.md**: Content integrated into main architecture
- **entity_naming_improvements.md**: Content integrated into main architecture
- **ENTITYMANAGER_MIGRATION_GUIDE.md**: Preserved as migration reference (moved to separate location)

This consolidation provides a single, comprehensive source of truth for the Ramses Extras architecture while maintaining access to specialized technical references when needed.

**Key Architecture Decisions:**

- ✅ Feature-centric organization for modularity
- ✅ Framework foundation for code reuse
- ✅ Thin HA integration wrappers for compatibility
- ✅ Type-safe implementations for reliability
- ✅ Clear separation of concerns for maintainability
