# Entity Organization Strategy for Feature-Based Architecture

## Problem Statement

Current entity definitions show **duplication across files**:

- `SENSOR_CONFIGS`, `SWITCH_CONFIGS`, `NUMBER_CONFIGS` duplicated between:
  - Root `const.py`
  - Feature `const.py` files
- Same entity definitions scattered in multiple locations
- No clear authority for which file owns which definitions
- Difficult to maintain consistency across features

## Solution: Framework-Aggregated Feature Entity Management

### 1. Default Feature (Shared Definitions)

**Location**: `features/default/const.py`

```python
"""Shared entity definitions that all features can inherit from."""

from homeassistant.helpers.entity import EntityCategory
from typing import Dict, Any

# Base entity definitions (shared across features)
DEFAULT_SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity {device_id}",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
    },
}

# Empty base configs - features will define their own
DEFAULT_SWITCH_CONFIGS = {}
DEFAULT_NUMBER_CONFIGS = {}
DEFAULT_BOOLEAN_CONFIGS = {}

# Base device type to entity mapping (only shared sensors)
DEFAULT_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],
        # Other entity types will be added by individual features
    },
}
```

### 2. Feature-Specific Entity Definitions

**Location**: `features/humidity_control/const.py`

```python
"""Humidity control feature - feature-specific entity definitions."""

from homeassistant.helpers.entity import EntityCategory
from typing import Dict, Any

# Feature-specific entities (prefixed with feature name)
HUMIDITY_SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
    },
}

HUMIDITY_NUMBER_CONFIGS = {
    "relative_humidity_minimum": {
        "name_template": "Min Humidity {device_id}",
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
}

HUMIDITY_BOOLEAN_CONFIGS = {
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active {device_id}",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
    },
}

# Feature-specific device mapping (inherits base sensors, adds feature-specific)
HUMIDITY_DEVICE_ENTITY_MAPPING = {
    "HvacVentilator": {
        "sensors": ["indoor_absolute_humidity", "outdoor_absolute_humidity"],  # Inherited from default
        "switches": ["dehumidify"],
        "numbers": [
            "relative_humidity_minimum",
            "relative_humidity_maximum",
            "absolute_humidity_offset",
        ],
        "binary_sensors": ["dehumidifying_active"],
    },
}

# Feature-specific logic constants
HUMIDITY_DECISION_THRESHOLDS = {
    "activation": 1.0,  # g/m³
    "deactivation": -1.0,  # g/m³
    "high_confidence": 2.0,  # g/m³
}

HUMIDITY_DECISION_ACTIONS = {
    "ACTIVATE": "dehumidify",
    "DEACTIVATE": "stop",
    "MAINTAIN": "maintain",
}
```

### 3. Framework Aggregation System

**Location**: `framework/helpers/entity/registry.py`

```python
"""Framework entity registry - aggregates definitions from all features."""

from typing import Dict, Any, List
import importlib

class EntityDefinitionRegistry:
    """Aggregates entity definitions from all enabled features."""

    def __init__(self):
        self._sensor_configs = {}
        self._switch_configs = {}
        self._number_configs = {}
        self._boolean_configs = {}
        self._device_mappings = {}

    def load_feature_definitions(self, feature_name: str, feature_module_path: str):
        """Load entity definitions from a feature module."""
        try:
            # Import the feature module
            feature_module = importlib.import_module(feature_module_path)

            # Load feature's entity definitions
            if hasattr(feature_module, f"{feature_name.upper()}_SENSOR_CONFIGS"):
                sensor_configs = getattr(feature_module, f"{feature_name.upper()}_SENSOR_CONFIGS")
                self._sensor_configs.update(sensor_configs)

            if hasattr(feature_module, f"{feature_name.upper()}_SWITCH_CONFIGS"):
                switch_configs = getattr(feature_module, f"{feature_name.upper()}_SWITCH_CONFIGS")
                self._switch_configs.update(switch_configs)

            if hasattr(feature_module, f"{feature_name.upper()}_NUMBER_CONFIGS"):
                number_configs = getattr(feature_module, f"{feature_name.upper()}_NUMBER_CONFIGS")
                self._number_configs.update(number_configs)

            if hasattr(feature_module, f"{feature_name.upper()}_BOOLEAN_CONFIGS"):
                boolean_configs = getattr(feature_module, f"{feature_name.upper()}_BOOLEAN_CONFIGS")
                self._boolean_configs.update(boolean_configs)

            if hasattr(feature_module, f"{feature_name.upper()}_DEVICE_ENTITY_MAPPING"):
                device_mapping = getattr(feature_module, f"{feature_name.upper()}_DEVICE_ENTITY_MAPPING")
                self._device_mappings.update(device_mapping)

        except ImportError:
            pass  # Feature not available

    def load_all_features(self, enabled_features: List[str]):
        """Load definitions from all enabled features."""
        # Always load default feature definitions first
        self.load_feature_definitions("default", "custom_components.ramses_extras.features.default")

        # Load each enabled feature
        for feature_name in enabled_features:
            feature_module_path = f"custom_components.ramses_extras.features.{feature_name}"
            self.load_feature_definitions(feature_name, feature_module_path)

    def get_all_sensor_configs(self) -> Dict[str, Any]:
        """Get all sensor configurations."""
        return self._sensor_configs.copy()

    def get_all_switch_configs(self) -> Dict[str, Any]:
        """Get all switch configurations."""
        return self._switch_configs.copy()

    def get_all_number_configs(self) -> Dict[str, Any]:
        """Get all number configurations."""
        return self._number_configs.copy()

    def get_all_boolean_configs(self) -> Dict[str, Any]:
        """Get all boolean configurations."""
        return self._boolean_configs.copy()

    def get_all_device_mappings(self) -> Dict[str, Any]:
        """Get all device to entity mappings."""
        return self._device_mappings.copy()

# Global registry instance
entity_registry = EntityDefinitionRegistry()
```

### 4. Minimal Root const.py

**Location**: `const.py` (simplified)

```python
"""Ramses Extras - Root constants (HA Required)."""

from pathlib import Path
from typing import Dict, Any

# Integration basics
DOMAIN = "ramses_extras"
INTEGRATION_DIR = Path(__file__).parent

# Feature identifiers
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"
FEATURE_ID_FAN_CONTROL = "fan_control"
FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"

# Lightweight feature registry (metadata only)
AVAILABLE_FEATURES: Dict[str, Dict[str, Any]] = {
    FEATURE_ID_HUMIDITY_CONTROL: {
        "name": "Humidity Control",
        "description": "Automatic humidity control and dehumidification management",
        "category": "automations",
        "default_enabled": False,
        "feature_module": "features.humidity_control",
    },
    FEATURE_ID_FAN_CONTROL: {
        "name": "Fan Control",
        "description": "Advanced fan control and management",
        "category": "controls",
        "default_enabled": False,
        "feature_module": "features.fan_control",
    },
}

# NO ENTITY DEFINITIONS HERE - all moved to features
# Entity definitions are now loaded by framework from feature modules
```

### 5. Feature Initialization with Aggregation

**Location**: `features/humidity_control/__init__.py`

```python
"""Humidity control feature initialization."""

from .const import (
    HUMIDITY_SWITCH_CONFIGS,
    HUMIDITY_NUMBER_CONFIGS,
    HUMIDITY_BOOLEAN_CONFIGS,
    HUMIDITY_DECISION_THRESHOLDS,
    HUMIDITY_DECISION_ACTIONS,
    FEATURE_ID_HUMIDITY_CONTROL
)

# Export all definitions for framework aggregation
__all__ = [
    "FEATURE_ID_HUMIDITY_CONTROL",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DECISION_THRESHOLDS",
    "HUMIDITY_DECISION_ACTIONS",
]
```

### 6. Entity Access Patterns

#### Framework Level:

```python
# In framework/helpers/entity/helpers.py
from custom_components.ramses_extras.framework.helpers.entity.registry import entity_registry

def get_all_entity_configs():
    """Get all entity configurations from all features."""
    return {
        "sensors": entity_registry.get_all_sensor_configs(),
        "switches": entity_registry.get_all_switch_configs(),
        "numbers": entity_registry.get_all_number_configs(),
        "booleans": entity_registry.get_all_boolean_configs(),
    }
```

#### Feature Level:

```python
# In features/humidity_control/automation.py
from custom_components.ramses_extras.features.humidity_control.const import HUMIDITY_DECISION_THRESHOLDS
from custom_components.ramses_extras.framework.helpers.entity.registry import entity_registry

# Access own definitions
own_switches = HUMIDITY_SWITCH_CONFIGS

# Access all definitions (including from other features)
all_sensors = entity_registry.get_all_sensor_configs()

# Access default definitions (always available)
default_sensors = entity_registry.get_all_sensor_configs()  # Includes default from default feature
```

## Benefits of This Approach

### ✅ **No Duplication**

- Each entity definition has exactly one owner (feature)
- Base definitions in default feature
- Feature-specific definitions in respective features
- Framework aggregates, doesn't duplicate

### ✅ **Clear Authority**

- `DEFAULT_*` definitions owned by `features/default/`
- `FEATURE_*` definitions owned by respective feature
- Root const.py has no entity definitions
- Framework is aggregation service only

### ✅ **Clean Separation**

- Each feature is self-contained
- Features inherit shared sensors from default
- Easy to add new features
- Clear import paths and responsibilities

### ✅ **Feature Independence**

- Features don't depend on each other's entity definitions
- Framework provides unified access
- Features can be enabled/disabled independently
- Easy testing in isolation

### ✅ **Extensibility**

- New features add their own entity definitions
- Existing features can be extended without modification
- Framework automatically discovers and aggregates new features

## Migration Plan

### Phase 1: Create Default Feature

- [ ] Create `features/default/` with base entity definitions
- [ ] Move `SENSOR_CONFIGS` from root to default (only indoor/outdoor humidity)
- [ ] Create framework entity registry

### Phase 2: Update Feature Definitions

- [ ] Update `features/humidity_control/const.py` with feature-specific definitions
- [ ] Add `HUMIDITY_SWITCH_CONFIGS`, `HUMIDITY_NUMBER_CONFIGS`, etc.
- [ ] Remove duplicate entity definitions from feature const.py

### Phase 3: Framework Aggregation

- [ ] Implement entity registry aggregation logic
- [ ] Update framework to use registry instead of root const.py
- [ ] Test aggregation from all features

### Phase 4: Root const.py Cleanup

- [ ] Remove all entity definitions from root const.py
- [ ] Keep only domain constants and feature registry
- [ ] Update imports throughout codebase

### Phase 5: Validation

- [ ] Test that all features work with new structure
- [ ] Verify no breaking changes
- [ ] Update documentation

This approach eliminates all duplication while maintaining clear feature boundaries and providing a powerful aggregation system for the framework.
