# Entity Organization Strategy for Feature-Based Architecture

## Problem Statement

Current entity definitions in `const.py` show that some entities are **shared across multiple features**:

- `indoor_absolute_humidity` → used by humidity_sensors, hvac_fan_card, humidity_control
- `outdoor_absolute_humidity` → used by humidity_sensors, hvac_fan_card, humidity_control
- `dehumidify` switch → used by humidity_control
- `dehumidifying_active` binary sensor → used by humidity_control

**Key Question**: How do we avoid duplicating these shared entity definitions across features while maintaining clean feature boundaries?

## Solution: Hybrid Entity Organization

### 1. Core Entity Registry (Framework Level)

**Location**: `framework/entity_registry.py`

```python
"""Core entity registry shared across all features."""

from homeassistant.helpers.entity import EntityCategory
from typing import Dict, Any

# Core entity definitions that can be used by multiple features
CORE_ENTITY_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
    },
    "dehumidify": {
        "name_template": "Dehumidify",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
    },
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
    },
    # ... other shared entities
}

# Core device type mappings
CORE_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": ["dehumidify"],
        "binary_sensors": ["dehumidifying_active"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
    },
}

class EntityRegistry:
    """Registry for managing entity definitions across features."""

    def __init__(self):
        self._entities = CORE_ENTITY_CONFIGS.copy()
        self._device_mappings = CORE_DEVICE_ENTITY_MAPPING.copy()

    def register_entity(self, entity_name: str, config: Dict[str, Any]):
        """Register a new entity definition."""
        self._entities[entity_name] = config

    def register_device_mapping(self, device_type: str, mapping: Dict[str, Any]):
        """Register a new device type to entity mapping."""
        self._device_mappings[device_type] = mapping

    def get_entity_config(self, entity_name: str) -> Dict[str, Any]:
        """Get entity configuration."""
        return self._entities.get(entity_name)

    def get_device_mapping(self, device_type: str) -> Dict[str, Any]:
        """Get device type to entity mapping."""
        return self._device_mappings.get(device_type)

    def get_all_entities(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered entity configurations."""
        return self._entities.copy()

# Global registry instance
entity_registry = EntityRegistry()
```

### 2. Feature Entity Extensions

**Location**: `features/humidity_control/entities.py`

```python
"""Humidity control feature entity extensions."""

from ...framework.entity_registry import entity_registry
from homeassistant.helpers.entity import EntityCategory

# Feature-specific entities that extend the core registry
HUMIDITY_ENTITY_CONFIGS = {
    "relative_humidity_minimum": {
        "name_template": "Relative Humidity Minimum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-minus",
        "device_class": None,
        "min_value": 30,
        "max_value": 80,
        "step": 1,
        "default_value": 40,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_minimum_{device_id}",
    },
    "relative_humidity_maximum": {
        "name_template": "Relative Humidity Maximum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-plus",
        "device_class": None,
        "min_value": 50,
        "max_value": 90,
        "step": 1,
        "default_value": 60,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_maximum_{device_id}",
    },
    "absolute_humidity_offset": {
        "name_template": "Absolute Humidity Offset",
        "entity_category": EntityCategory.CONFIG,
        "unit": "g/m³",
        "icon": "mdi:swap-horizontal",
        "device_class": None,
        "min_value": -3.0,
        "max_value": 3.0,
        "step": 0.1,
        "default_value": 0.4,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "absolute_humidity_offset_{device_id}",
    },
}

# Feature-specific device mappings (extends core)
HUMIDITY_DEVICE_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        "switches": ["dehumidify"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "binary_sensors": ["dehumidifying_active"],
    },
}

def register_humidity_entities():
    """Register humidity-specific entities with the core registry."""
    # Register entities
    for entity_name, config in HUMIDITY_ENTITY_CONFIGS.items():
        entity_registry.register_entity(entity_name, config)

    # Register device mappings
    for device_type, mapping in HUMIDITY_DEVICE_MAPPING.items():
        # Merge with existing mapping (extend, don't replace)
        existing_mapping = entity_registry.get_device_mapping(device_type)
        if existing_mapping:
            # Merge entity lists, avoiding duplicates
            for entity_type, entities in mapping.items():
                if entity_type in existing_mapping:
                    existing_entities = set(existing_mapping[entity_type])
                    new_entities = set(entities)
                    merged_entities = list(existing_entities.union(new_entities))
                    existing_mapping[entity_type] = merged_entities
                else:
                    existing_mapping[entity_type] = entities
        else:
            entity_registry.register_device_mapping(device_type, mapping)
```

### 3. Feature Initialization

**Location**: `features/humidity_control/__init__.py`

```python
"""Humidity control feature initialization."""

from .entities import register_humidity_entities
from .config import HUMIDITY_FEATURE_CONFIG

# Register entities when module is imported
register_humidity_entities()

# Export feature configuration
FEATURE_CONFIG = HUMIDITY_FEATURE_CONFIG
```

### 4. Consolidated Root const.py

**Location**: `const.py` (simplified)

```python
"""Ramses Extras - Root constants (HA Required)."""

from pathlib import Path
from homeassistant.helpers.entity import EntityCategory

# Integration basics
DOMAIN = "ramses_extras"
INTEGRATION_DIR = Path(__file__).parent

# Import feature configurations
from .features.humidity_control import FEATURE_CONFIG as HUMIDITY_CONFIG
from .features.fan_control import FEATURE_CONFIG as FAN_CONFIG
# ... other features

# Consolidated AVAILABLE_FEATURES
AVAILABLE_FEATURES = {
    "humidity_control": HUMIDITY_CONFIG,
    "fan_control": FAN_CONFIG,
    # ... other features
}

# Import entity registry for backward compatibility
from .framework.entity_registry import entity_registry

# Create legacy mappings for backward compatibility
SENSOR_CONFIGS = {}
SWITCH_CONFIGS = {}
BOOLEAN_CONFIGS = {}
NUMBER_CONFIGS = {}

# Populate legacy mappings from registry
for entity_name, config in entity_registry.get_all_entities().items():
    entity_type = config.get("entity_type", "sensor")  # Determine type
    if entity_type == "sensor":
        SENSOR_CONFIGS[entity_name] = config
    elif entity_type == "switch":
        SWITCH_CONFIGS[entity_name] = config
    elif entity_type == "binary_sensor":
        BOOLEAN_CONFIGS[entity_name] = config
    elif entity_type == "number":
        NUMBER_CONFIGS[entity_name] = config

# Legacy device mapping (backward compatibility)
DEVICE_ENTITY_MAPPING = {}
for device_type, mapping in entity_registry._device_mappings.items():
    DEVICE_ENTITY_MAPPING[device_type] = mapping

# Entity type to config mapping (backward compatibility)
ENTITY_TYPE_CONFIGS = {
    "sensor": SENSOR_CONFIGS,
    "switch": SWITCH_CONFIGS,
    "binary_sensor": BOOLEAN_CONFIGS,
    "number": NUMBER_CONFIGS,
}
```

### 5. Entity Access Patterns

#### For Framework/Helpers:

```python
# In framework/helpers/entity/helpers.py
from ...framework.entity_registry import entity_registry

def get_entity_config(entity_name: str):
    """Get entity configuration from registry."""
    return entity_registry.get_entity_config(entity_name)
```

#### For Features:

```python
# In features/humidity_control/automation.py
from ...framework.entity_registry import entity_registry

# Access shared entities
indoor_humidity_config = entity_registry.get_entity_config("indoor_absolute_humidity")

# Access feature-specific entities
humidity_min_config = entity_registry.get_entity_config("relative_humidity_minimum")
```

#### For Platform (HA Integration):

```python
# In platform/sensor.py (unchanged)
from ..const import SENSOR_CONFIGS  # Backward compatibility maintained
```

## Benefits of This Approach

### ✅ **No Duplication**

- Shared entities defined once in core registry
- Features extend rather than duplicate
- Single source of truth for entity configurations

### ✅ **Clean Boundaries**

- Core entities in framework
- Feature-specific entities in features
- Clear import paths and responsibilities

### ✅ **Backward Compatibility**

- Root const.py maintains existing structure
- Legacy mappings still work
- No breaking changes for existing code

### ✅ **Extensibility**

- New features can easily add entities
- Easy to override/extend core entities if needed
- Plugin-style entity registration

### ✅ **Testability**

- Entity registry can be mocked for testing
- Features can be tested in isolation
- Clear separation of concerns

## Migration Strategy

1. **Phase 1**: Create entity registry in framework
2. **Phase 2**: Move core entities to registry
3. **Phase 3**: Create feature entity extensions
4. **Phase 4**: Update root const.py for backward compatibility
5. **Phase 5**: Test all features work with new structure

This hybrid approach gives us the best of both worlds: clean organization without duplication, while maintaining backward compatibility.
