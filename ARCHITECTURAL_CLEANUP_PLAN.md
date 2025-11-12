# Architectural Cleanup Plan: Feature-Specific Platform Code

## Current Problem

**Root platform files contain mixed responsibilities:**

- ✅ **Correct**: HA integration wrappers (`async_setup_entry`)
- ❌ **Wrong**: Feature-specific business logic (e.g., `RamsesExtraHumiditySensor`)

**Example of problematic code in `sensor.py`:**

```python
# Platform integration (correct location)
async def async_setup_entry(hass, config_entry, async_add_entities):

# Feature-specific business logic (wrong location)
sensors.append(RamsesExtraHumiditySensor(hass, device_id, sensor_type, config))
class RamsesExtraHumiditySensor(SensorEntity, ExtrasBaseEntity):
    # Humidity calculation logic
```

## Current Feature Architecture

**Existing structure:**

```
features/humidity_control/
├── __init__.py          # Feature factory functions
├── entities.py          # Entity management (configs, creation)
├── automation.py        # Feature automation logic
├── services.py          # Feature services
├── const.py            # Feature constants/configs
└── binary_sensor.py     # Feature-specific binary sensor
```

**Current `entities.py` role:**

- Entity configuration management
- Entity creation tracking
- Entity registry management
- **Missing**: Actual HA entity class implementations

## Design Options Analysis

### Option 1: Extend Existing `entities.py`

**Approach:** Add HA entity classes to current `entities.py`

**Pros:**

- All humidity code in one file
- Minimal new files
- Follows existing pattern

**Cons:**

- Mixed concerns (manager + implementations)
- `entities.py` becomes bloated
- Violates single responsibility principle

### Option 2: Separate Platform Files per Feature

**Approach:** Create `features/humidity_control/sensor.py`, `switch.py`, etc.

**Pros:**

- Clean separation of concerns
- Follows HA platform naming conventions
- Feature owns its complete platform implementation
- Easy to understand and maintain

**Cons:**

- Multiple platform files might seem redundant
- Slightly more files

### Option 3: Factory Pattern Integration

**Approach:** Features provide factory functions, root platforms call them

**Pros:**

- Root platforms remain thin
- Features control their entity creation
- Maintains HA integration standards
- Most flexible approach

**Cons:**

- More complex architecture
- Multiple layers of indirection

## Recommended Architecture: **Option 2 + Factory Pattern**

### New Structure

```
features/humidity_control/
├── entities/               # NEW: HA entity implementations
│   ├── __init__.py
│   ├── sensor.py          # NEW: Humidity sensor classes
│   ├── switch.py          # NEW: Humidity switch classes
│   ├── number.py          # NEW: Humidity number classes
│   └── binary_sensor.py   # NEW: Humidity binary sensor classes
├── platform.py            # NEW: Feature platform integration
├── entities.py            # KEEP: Entity management (configs)
├── automation.py          # KEEP: Feature automation logic
├── services.py            # KEEP: Feature services
├── const.py              # KEEP: Feature constants
└── __init__.py           # KEEP: Feature factory functions
```

### Root Platform Files (Thin Wrappers)

```python
# sensor.py - ROOT PLATFORM (simplified)
async def async_setup_entry(hass, config_entry, async_add_entities):
    """HA platform integration - thin wrapper only."""
    await async_forward_entry_setups(
        config_entry, ["humidity_control"], hass
    )

# humidity_control/platform.py - FEATURE PLATFORM
async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Feature-specific platform setup."""
    # Import feature-specific entity classes
    from ..entities.sensor import HumidityAbsoluteSensor

    # Create entities using feature logic
    entities = await create_humidity_sensors(hass, config, discovery_info)
    add_entities(entities)
```

### Feature Platform Integration

```python
# features/humidity_control/platform.py
async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up humidity control sensor platform."""

    # Get devices from HA
    devices = discovery_info.get("devices", [])

    # Use feature's entity creation logic
    sensors = []
    for device_id in devices:
        # Create feature-specific sensors
        sensor = HumidityAbsoluteSensor(hass, device_id)
        sensors.append(sensor)

    add_entities(sensors)

class HumidityAbsoluteSensor(SensorEntity, ExtrasBaseEntity):
    """Feature-specific sensor with business logic."""

    def __init__(self, hass, device_id):
        # Feature-specific initialization
        super().__init__(hass, device_id, "indoor_absolute_humidity")

    @property
    def native_value(self):
        # Feature-specific calculation logic
        return self._calculate_absolute_humidity()
```

## Implementation Strategy

### Phase 1: Create Feature Platform Structure

1. Create `features/humidity_control/entities/` directory
2. Move `RamsesExtraHumiditySensor` to `entities/sensor.py`
3. Create `features/humidity_control/platform.py`
4. Update feature factory to include platform setup

### Phase 2: Simplify Root Platform Files

1. Remove business logic from root platform files
2. Make them thin HA integration wrappers
3. Forward to feature platforms

### Phase 3: Update Integration Registration

1. Modify config flow to forward to feature platforms
2. Update manifest to include feature platforms
3. Test integration

## Benefits of This Approach

1. **Clean Architecture**: Feature-specific code in feature directories
2. **HA Compatibility**: Maintains Home Assistant integration standards
3. **Maintainability**: Each feature owns its complete implementation
4. **Testability**: Feature code can be tested independently
5. **Scalability**: Easy to add new features with their own platforms
6. **Single Responsibility**: Each file has one clear purpose

## Migration Path

1. **Non-breaking**: Existing functionality preserved
2. **Incremental**: Can migrate features one by one
3. **Reversible**: Can rollback if issues arise
4. **Well-documented**: Clear migration steps

This approach provides the cleanest separation while maintaining full Home Assistant compatibility.
