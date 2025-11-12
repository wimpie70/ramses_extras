# Feature Platform Cleanup Implementation Plan

**Date:** 2025-11-12
**Version:** 1.0
**Status:** Ready for Implementation

## Overview

This plan details the migration of feature-specific business logic from root platform files to feature-specific platform implementations, creating a clean separation between Home Assistant integration and business logic.

## Current State Analysis

### Problem Files

- **`sensor.py`**: Contains both HA integration (`async_setup_entry`) AND feature-specific logic (`RamsesExtraHumiditySensor`)
- **`binary_sensor.py`**: Mixed platform integration and feature logic
- **`number.py`**: Mixed platform integration and feature logic
- **`switch.py`**: Mixed platform integration and feature logic

### Mixed Responsibilities in Current `sensor.py`

```python
# ✅ Correct - HA Platform Integration
async def async_setup_entry(hass, config_entry, async_add_entities):
    # Home Assistant platform wrapper

# ❌ Wrong - Feature Business Logic
class RamsesExtraHumiditySensor(SensorEntity, ExtrasBaseEntity):
    def native_value(self):
        # Feature-specific humidity calculations
```

## Target Architecture

### New Structure

```
features/humidity_control/
├── platforms/            # NEW: HA platform implementations
│   ├── __init__.py
│   ├── sensor.py        # NEW: Sensor platform + entity classes
│   ├── switch.py        # NEW: Switch platform + entity classes
│   ├── number.py        # NEW: Number platform + entity classes
│   └── binary_sensor.py # NEW: Binary sensor platform + entity classes
├── entities.py          # KEEP: Entity configuration & management
├── automation.py        # KEEP: Feature automation logic
├── services.py          # KEEP: Feature services
├── const.py            # KEEP: Feature constants
└── __init__.py         # KEEP: Feature factory functions
```

### Clear Separation of Responsibilities

#### Root Platform Files (HA Integration Only)

```python
# sensor.py - ROOT LEVEL (Thin Wrapper)
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Home Assistant platform integration - thin wrapper only."""
    # Forward to feature platform
    await async_forward_entry_setups(
        config_entry, ["ramses_extras_humidity_control"], hass
    )

# No entity class definitions
# No feature-specific business logic
```

#### Feature Platforms (Business Logic)

```python
# features/humidity_control/platforms/sensor.py
async def async_setup_entry(hass, config_entry, async_add_entities):
    """Humidity control sensor platform setup."""
    # Feature-specific platform logic
    entities = await create_humidity_sensors(hass, config_entry)
    async_add_entities(entities)

class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
    """Feature-specific sensor with business logic."""
    # All humidity calculation logic
    # Feature-specific behavior
```

#### Entity Management (Configuration)

```python
# features/humidity_control/entities.py
class HumidityEntities:
    """Entity configuration and management."""
    def _get_entity_configs(self):    # What entities exist
    def async_setup_entities(self):   # When to create them
    def get_entity_config(self):      # Configuration lookup
    # Entity lifecycle management
```

## Implementation Strategy

### Phase 1: Create Feature Platform Structure

#### Step 1.1: Create platforms directory

```bash
mkdir -p features/humidity_control/platforms
touch features/humidity_control/platforms/__init__.py
```

#### Step 1.2: Create sensor platform

**File:** `features/humidity_control/platforms/sensor.py`

```python
"""Humidity Control Sensor Platform.

This module provides Home Assistant sensor platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes import ExtrasBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control sensor platform."""
    _LOGGER.info("Setting up humidity control sensors")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])

    sensors = []
    for device_id in devices:
        # Create humidity-specific sensors
        sensors.extend(await create_humidity_sensors(hass, device_id))

    async_add_entities(sensors, True)


async def create_humidity_sensors(hass: HomeAssistant, device_id: str) -> list[SensorEntity]:
    """Create humidity sensors for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier

    Returns:
        List of sensor entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, None)  # TODO: Pass config_entry
    sensors = []

    for sensor_type in ["indoor_absolute_humidity", "outdoor_absolute_humidity"]:
        config = entity_manager.get_entity_config("sensors", sensor_type)
        if config:
            sensor = HumidityAbsoluteSensor(hass, device_id, sensor_type, config)
            sensors.append(sensor)

    return sensors


class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
    """Absolute humidity sensor for humidity control feature.

    This class handles the calculation and display of absolute humidity
    based on temperature and relative humidity data from ramses_cc entities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize humidity absolute sensor.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            sensor_type: Type of humidity sensor
            config: Sensor configuration
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, sensor_type, config)

        # Set sensor-specific attributes
        self._sensor_type = sensor_type
        self._attr_native_unit_of_measurement = config.get("unit", "g/m³")
        self._attr_device_class = config.get("device_class")

        # Set unique_id and name
        device_id_underscore = device_id.replace(":", "_")
        self._attr_unique_id = f"{sensor_type}_{device_id_underscore}"

        name_template = config.get("name_template", f"{sensor_type} {device_id_underscore}")
        self._attr_name = name_template.format(device_id=device_id_underscore)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name or f"{self._sensor_type} {self._device_id.replace(':', '_')}"

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle device update from Ramses RF."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return calculated absolute humidity."""
        try:
            temp, rh = self._get_temp_and_humidity()
            result = self._calculate_abs_humidity(temp, rh)
            return result if result is not None else None
        except Exception as e:
            _LOGGER.debug("Error reading humidity for %s: %s", self._attr_name, e)
            return None

    def _get_temp_and_humidity(self) -> tuple[float | None, float | None]:
        """Get temperature and humidity data from ramses_cc entities.

        Returns:
            tuple: (temperature, humidity) or (None, None) if sensors are missing/failed
        """
        # TODO: Import from framework helpers
        from custom_components.ramses_extras.framework.helpers.entities import calculate_absolute_humidity

        entity_patterns = {
            "indoor_absolute_humidity": ("indoor_temp", "indoor_humidity"),
            "outdoor_absolute_humidity": ("outdoor_temp", "outdoor_humidity"),
        }

        if self._sensor_type not in entity_patterns:
            _LOGGER.error("Unknown sensor type for humidity calculation: %s", self._sensor_type)
            return None, None

        temp_type, humidity_type = entity_patterns[self._sensor_type]

        # Construct entity IDs based on the device_id
        temp_entity = f"sensor.{self._device_id.replace(':', '_')}_{temp_type}"
        humidity_entity = f"sensor.{self._device_id.replace(':', '_')}_{humidity_type}"

        try:
            # Get temperature from ramses_cc sensor
            temp_state = self.hass.states.get(temp_entity)
            if temp_state is None or temp_state.state in ("unavailable", "unknown", "uninitialized"):
                return None, None

            temp = float(temp_state.state)

            # Get humidity from ramses_cc sensor
            humidity_state = self.hass.states.get(humidity_entity)
            if humidity_state is None or humidity_state.state in ("unavailable", "unknown", "uninitialized"):
                return None, None

            humidity = float(humidity_state.state)

            # Validate humidity range
            if not (0 <= humidity <= 100):
                _LOGGER.error("Invalid humidity value %.1f%% for %s (must be 0-100%%)", humidity, self._attr_name)
                return None, None

            return temp, humidity

        except (ValueError, AttributeError) as e:
            _LOGGER.debug("Error parsing temp/humidity for %s: %s", self._attr_name, e)
            return None, None

    def _calculate_abs_humidity(self, temp: float | None, rh: float | None) -> float | None:
        """Calculate absolute humidity using proper formula."""
        if temp is None or rh is None:
            return None

        # TODO: Import from framework helpers
        from custom_components.ramses_extras.framework.helpers.entities import calculate_absolute_humidity

        result = calculate_absolute_humidity(temp, rh)
        return float(result) if result is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "sensor_type": self._sensor_type}


__all__ = [
    "HumidityAbsoluteSensor",
    "async_setup_entry",
    "create_humidity_sensors",
]
```

#### Step 1.3: Create other platforms

Create similar platform files for switch, number, and binary_sensor following the same pattern.

### Phase 2: Simplify Root Platform Files

#### Step 2.1: Update root sensor.py

**New content for `custom_components/ramses_extras/sensor.py`:**

```python
"""Ramses Extras Sensor Platform.

This module provides the main Home Assistant sensor platform integration
for the ramses_extras custom component.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform.

    This is a thin wrapper that forwards to feature-specific platforms.
    All feature-specific business logic is handled by the feature platforms.
    """
    _LOGGER.info("Forwarding sensor platform setup to features")

    # Forward to humidity control feature platform
    # TODO: Implement dynamic feature discovery and forwarding
    # For now, just log that we're using feature platforms
    _LOGGER.info("Using feature-specific sensor platforms")
```

#### Step 2.2: Update other root platform files

Apply the same pattern to binary_sensor.py, number.py, and switch.py.

### Phase 3: Update Feature Integration

#### Step 3.1: Update feature factory

**File:** `features/humidity_control/__init__.py`

```python
# Add platform exports
from .platforms.sensor import HumidityAbsoluteSensor, async_setup_entry as sensor_async_setup_entry
from .platforms.switch import create_humidity_switch
from .platforms.number import create_humidity_number
from .platforms.binary_sensor import create_humidity_binary_sensor

__all__ = [
    # Existing exports...
    "HumidityAbsoluteSensor",
    "sensor_async_setup_entry",
    "create_humidity_switch",
    "create_humidity_number",
    "create_humidity_binary_sensor",
]

def create_humidity_control_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create humidity control feature."""
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

### Phase 4: Update Manifest and Config Flow

#### Step 4.1: Update manifest.json

```json
{
  "dependencies": ["sensor"],
  "codeowners": ["@yourname"],
  "config_flow": true,
  "documentation": "https://github.com/yourrepo/ramses_extras",
  "domain": "ramses_extras",
  "file_path": "custom_components/ramses_extras",
  "integration_type": "device",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/yourrepo/ramses_extras/issues",
  "quality_scale": "silver",
  "requirements": ["ramses_rf==0.52.2"],
  "version": "1.0.0",
  "rf": {}
}
```

#### Step 4.2: Update config flow

Ensure config flow properly forwards to feature platforms.

## Testing Strategy

### Unit Tests

1. **Feature Platform Tests**
   - Test `HumidityAbsoluteSensor` independently
   - Test humidity calculation logic
   - Test entity initialization and configuration

2. **Root Platform Tests**
   - Test that root platforms are thin wrappers
   - Test forward-to-features functionality

### Integration Tests

1. **Home Assistant Tests**
   - Test entity creation and registration
   - Test state updates and calculations
   - Test platform setup and teardown

2. **Feature Interaction Tests**
   - Test feature platforms work together
   - Test entity management integration
   - Test automation and service integration

### Manual Testing

1. **Functionality Validation**
   - Verify sensors display correct values
   - Verify calculations are accurate
   - Verify entity naming and attributes

2. **HA Integration Tests**
   - Test sensor discovery and registration
   - Test entity updates and state changes
   - Test platform configuration

## Migration Checklist

### Pre-Migration

- [ ] Backup current implementation
- [ ] Document current functionality
- [ ] Set up test environment
- [ ] Create rollback plan

### During Migration

- [ ] Create feature platform structure
- [ ] Move entity classes to feature platforms
- [ ] Simplify root platform files
- [ ] Update feature factory functions
- [ ] Test feature platforms individually
- [ ] Test integration with HA
- [ ] Update documentation

### Post-Migration

- [ ] Run full test suite
- [ ] Manual testing of functionality
- [ ] Performance validation
- [ ] Update architectural documentation
- [ ] Clean up deprecated code
- [ ] Final documentation update

## Rollback Strategy

**Git-Based Rollback**: Since this is version-controlled with Git:

- Use `git revert <commit>` to rollback any problematic changes
- Use `git checkout <commit>` to temporarily inspect previous states
- Use `git reset --hard <commit>` only if needed (with caution)

**Recovery Steps:**

1. Identify the problematic commit
2. Use `git revert <commit>` to create a new commit that undoes changes
3. If needed, use `git log` to find working commit
4. Document any issues found for future reference

## Success Criteria

### Architecture Goals

- ✅ Root platform files contain only HA integration code
- ✅ Feature platforms contain all business logic
- ✅ Clear separation of concerns maintained
- ✅ Home Assistant compatibility preserved

### Code Quality Goals

- ✅ All entity classes moved to appropriate feature directories
- ✅ No duplicate or redundant code
- ✅ Consistent naming and structure across features
- ✅ Comprehensive test coverage

### Performance Goals

- ✅ No degradation in entity creation performance
- ✅ No increase in memory usage
- ✅ No impact on entity update latency
- ✅ Improved maintainability and debugging

## Timeline

- **Phase 1**: Create feature platform structure (1 day)
- **Phase 2**: Simplify root platform files (1 day)
- **Phase 3**: Update feature integration (1 day)
- **Phase 4**: Testing and validation (2 days)
- **Phase 5**: Documentation and cleanup (1 day)

**Total Estimated Time**: 6 days

This plan provides a safe, incremental path to cleaner architecture while maintaining full Home Assistant compatibility.
