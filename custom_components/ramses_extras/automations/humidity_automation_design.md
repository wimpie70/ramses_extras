# Hardcoded Humidity Automation Design

## Overview

This document describes the hardcoded Python automation system that replaces the problematic YAML template approach for humidity control in the Ramses Extras integration.

## Background

**Problem with YAML Template System:**
- Template substitution errors (wrong entity IDs, missing device context)
- Maintenance complexity (YAML + Python config + documentation)
- Device-specific generation (separate automations per fan device)
- Limited error handling and debugging capabilities

**Solution Benefits:**
- ✅ Single automation logic handles all devices
- ✅ Direct entity handling eliminates template errors
- ✅ Better error handling with Python-level validation
- ✅ Extensible for complex logic and multi-device coordination
- ✅ Improved performance vs YAML template processing

## Architecture

### Core Component: HumidityAutomationManager

**Location:** `ramses_extras/custom_components/ramses_extras/automations/humidity_automation.py`

**Purpose:** Manages hardcoded humidity automation logic with global state listeners

### Class Structure

```python
class HumidityAutomationManager:
    """Manages hardcoded humidity automation logic."""

    # Global entity patterns to monitor across all devices
    ENTITY_PATTERNS = [
        "sensor.indoor_relative_humidity_*",
        "sensor.indoor_absolute_humidity_*",
        "sensor.outdoor_absolute_humidity_*",
        "number.absolute_humidity_offset_*",
        "number.max_humidity_*",
        "number.min_humidity_*",
        "switch.dehumidify_*"
    ]

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._listeners = []           # State change listeners
        self._change_timers = {}       # device_id -> timer for 2-min debouncing

    async def start(self):
        """Start automation when humidity_control feature is enabled."""
        await self._wait_for_entities()
        self._register_global_listeners()

    async def stop(self):
        """Stop automation when feature is disabled."""
        self._cleanup_listeners()
        self._cancel_all_timers()
```

## Entity Patterns & Naming

### Entity Naming Convention

**Format:** `{entity_type}.{entity_name}_{device_id_underscore}`

**Examples:**
- `sensor.indoor_relative_humidity_32_153289`
- `sensor.indoor_absolute_humidity_32_153289`
- `number.absolute_humidity_offset_32_153289`
- `switch.dehumidify_32_153289`
- `binary_sensor.dehumidifying_active_32_153289`

### Device ID Conversion

**Entity naming:** Underscore format (`32_153289`)
**Fan service calls:** Colon format (`32:153289`)

```python
# Entity ID to fan service conversion
device_id_underscore = "32_153289"
device_id_colon = device_id_underscore.replace("_", ":")  # "32:153289"
```

## State Listener Architecture

### Global Listener Approach (Option A)

**Benefits:**
- Single listener registration vs per-device listeners
- Efficient entity monitoring across all devices
- Automatic handling of new devices added later

**Implementation:**
```python
async def _register_global_listeners(self):
    """Register global state change listeners."""
    for pattern in self.ENTITY_PATTERNS:
        listener = await self.hass.helpers.event.async_track_state_change(
            pattern, self._handle_state_change
        )
        self._listeners.append(listener)
```

### Entity Validation

**Validation on Every Trigger:**
```python
async def _validate_device_entities(self, device_id: str) -> bool:
    """Validate all required entities exist for device."""
    required_entities = [
        f"sensor.indoor_relative_humidity_{device_id}",
        f"sensor.indoor_absolute_humidity_{device_id}",
        f"sensor.outdoor_absolute_humidity_{device_id}",
        f"number.absolute_humidity_offset_{device_id}",
        f"number.max_humidity_{device_id}",
        f"number.min_humidity_{device_id}",
        f"switch.dehumidify_{device_id}",
        f"binary_sensor.dehumidifying_active_{device_id}",
    ]

    for entity_id in required_entities:
        if not self.hass.states.get(entity_id):
            _LOGGER.warning(f"Entity {entity_id} not found for device {device_id}")
            return False
    return True
```

## Decision Logic Implementation

### Exact Mermaid Flow Implementation

Based on `humidity_decision_flow.md`, the logic follows this exact sequence:

```mermaid
COND1{Switch ON?}
COND1 -->|NO| END1[No Action - Manual Control Preserved]
COND1 -->|YES| D1{Indoor RH > Max%}
D1 -->|YES| I1{Indoor abs > Outdoor abs + Offset?}
I1 -->|YES| E1[Set Fan HIGH - Active dehumidification]
I1 -->|NO| J1[Set Fan LOW - Avoid bringing moisture]

D1 -->|NO| F1{Indoor RH < Min%}
F1 -->|YES| K1{Indoor abs < Outdoor abs - Offset?}
K1 -->|YES| G1[Set Fan HIGH - Active humidification]
K1 -->|NO| L1[Set Fan LOW - Avoid over-humidifying]

# No action if indoor RH between Min/Max (acceptable range)
```

### Python Implementation

```python
async def _handle_state_change(self, entity_id, old_state, new_state):
    """Handle state changes following exact mermaid decision flow."""
    device_id = self._extract_device_id(entity_id)

    # Validate entities exist
    if not await self._validate_device_entities(device_id):
        _LOGGER.warning(f"Device {device_id} entities not ready")
        return

    # Reset logic: switch turned OFF
    if entity_id == f"switch.dehumidify_{device_id}" and new_state.state == "off":
        await self._reset_fan_to_auto(device_id)
        return

    # Only process if switch is ON
    switch_state = self.hass.states.get(f"switch.dehumidify_{device_id}")
    if not switch_state or switch_state.state != "on":
        return

    # Apply 2-minute debouncing
    if device_id in self._change_timers:
        _LOGGER.debug(f"Debouncing device {device_id} - ignoring rapid change")
        return

    # Set debouncing timer
    self._change_timers[device_id] = self.hass.loop.call_later(120,
        lambda: self._change_timers.pop(device_id, None))

    # Get all entity states
    indoor_rh = float(self.hass.states.get(f"sensor.indoor_relative_humidity_{device_id}").state)
    indoor_abs = float(self.hass.states.get(f"sensor.indoor_absolute_humidity_{device_id}").state)
    outdoor_abs = float(self.hass.states.get(f"sensor.outdoor_absolute_humidity_{device_id}").state)
    max_humidity = float(self.hass.states.get(f"number.max_humidity_{device_id}").state)
    min_humidity = float(self.hass.states.get(f"number.min_humidity_{device_id}").state)
    offset = float(self.hass.states.get(f"number.absolute_humidity_offset_{device_id}").state)

    # EXACT MERMAID LOGIC IMPLEMENTATION
    if indoor_rh > max_humidity:  # D1: Indoor RH > Max?
        if indoor_abs > outdoor_abs + offset:  # I1: Indoor abs > Outdoor abs + Offset?
            await self._set_fan_high(device_id, "Active dehumidification")
        else:
            await self._set_fan_low(device_id, "Avoid bringing moisture")
    elif indoor_rh < min_humidity:  # F1: Indoor RH < Min?
        if indoor_abs < outdoor_abs - offset:  # K1: Indoor abs < Outdoor abs - Offset?
            await self._set_fan_high(device_id, "Active humidification")
        else:
            await self._set_fan_low(device_id, "Avoid over-humidifying")
    # No action if between Min/Max (acceptable range)
```

## Fan Control Integration

### Integration with fan_services.py

**Benefits of using existing fan_services.py:**
- Proven fan control logic
- Built-in exception handling
- Proper logging and error reporting
- Duration and reason tracking

### Fan Control Methods

```python
async def _set_fan_high(self, device_id: str, reason: str):
    """Set fan to HIGH mode via fan_services.py."""
    try:
        from ..services.fan_services import async_set_fan_speed_mode

        # Convert underscore device_id to colon format for fan service
        colon_device_id = device_id.replace("_", ":")

        await async_set_fan_speed_mode(
            self.hass,
            colon_device_id,  # "32:153289"
            "high",
            reason=f"Humidity automation: {reason}"
        )

        # Update binary sensor: HIGH mode = active dehumidifying
        await self.hass.services.async_call(
            "binary_sensor", "turn_on",
            {"entity_id": f"binary_sensor.dehumidifying_active_{device_id}"}
        )

        _LOGGER.info(f"Device {device_id}: Set fan HIGH - {reason}")

    except Exception as e:
        _LOGGER.error(f"Failed to set fan HIGH for device {device_id}: {e}")

async def _set_fan_low(self, device_id: str, reason: str):
    """Set fan to LOW mode via fan_services.py."""
    # Similar to _set_fan_high but mode="low" and binary_sensor.turn_off()

async def _reset_fan_to_auto(self, device_id: str):
    """Reset fan to AUTO when switch turned OFF."""
    # Set fan to AUTO mode
    # Turn off binary sensor
    # Log the reset action
```

### Binary Sensor Logic

**Definition:** Binary sensor reflects if automation is actively controlling and set fan to HIGH (extra ventilation due to humidity conditions).

**States:**
- **ON:** Fan mode is HIGH due to automation decision (active dehumidification/humidification)
- **OFF:** Fan mode is LOW/AUTO or automation not active

## Debouncing & Rate Limiting

### 2-Minute Debouncing Timer

**Purpose:** Prevent rapid fan mode changes that could damage equipment or create noise pollution.

**Implementation:**
```python
# Set debouncing timer on every state change
self._change_timers[device_id] = self.hass.loop.call_later(120,
    lambda: self._change_timers.pop(device_id, None))

# Check for existing timer before processing
if device_id in self._change_timers:
    _LOGGER.debug(f"Debouncing device {device_id} - ignoring rapid change")
    return
```

**Timer Cleanup:**
```python
async def _cancel_all_timers(self):
    """Cancel all pending debouncing timers."""
    for timer in self._change_timers.values():
        timer.cancel()
    self._change_timers.clear()
```

## Error Handling & Logging

### Entity State Validation

**Unavailable/Unknown States:**
```python
# Fail fast with warning if entity is not in valid state
state = self.hass.states.get(entity_id)
if not state or state.state in ["unavailable", "unknown"]:
    _LOGGER.warning(f"Entity {entity_id} state unavailable")
    return False

try:
    value = float(state.state)
except (ValueError, TypeError):
    _LOGGER.warning(f"Entity {entity_id} has invalid numeric value: {state.state}")
    return False
```

### Exception Handling

**Fan Service Failures:**
```python
try:
    await async_set_fan_speed_mode(...)
except Exception as e:
    _LOGGER.error(f"Failed to set fan mode for device {device_id}: {e}")
    # Automation continues, but logs the failure
```

### Logging Levels

- **DEBUG:** Debouncing, timer operations, routine state checks
- **INFO:** Fan mode changes, automation start/stop, successful operations
- **WARNING:** Entity validation failures, missing entities, invalid states
- **ERROR:** Fan service failures, critical automation errors

## Configuration Integration

### Feature Configuration

**Updated `const.py`:**
```python
"humidity_control": {
    "name": "Humidity Control",
    "description": "Hardcoded humidity automation for ventilation control",
    "category": "automations",
    "automation_type": "hardcoded",  # NEW: indicates hardcoded vs template
    "location": "automations/humidity_automation.py",  # NEW: points to Python class
    "default_enabled": False,
    "supported_device_types": ["HvacVentilator"],
    # ... existing entity requirements ...
}
```

### Integration Flow

**Feature Enable Sequence:**
1. User enables `humidity_control` feature
2. Integration creates all required entities
3. **HumidityAutomationManager** starts after entities exist
4. Global state listeners are registered
5. Automation monitors all humidity entities

**Feature Disable Sequence:**
1. User disables `humidity_control` feature
2. **HumidityAutomationManager** stops
3. All listeners are cleaned up
4. Any pending timers are cancelled
5. Fan may remain in current state (manual control resumes)

## Startup & Shutdown

### Startup Requirements

**Entity Creation Dependency:**
```python
async def _wait_for_entities(self, timeout: int = 30):
    """Wait for all entities to be created before starting automation."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        # Check if we have at least one device with all entities
        if await self._check_any_device_ready():
            _LOGGER.info("Humidity automation: Entities ready, starting automation")
            return True

        await asyncio.sleep(1)

    _LOGGER.warning("Humidity automation: Timeout waiting for entities")
    return False

async def _check_any_device_ready(self) -> bool:
    """Check if any device has all required entities ready."""
    # Look for existing humidity control switches
    # Validate all related entities exist
    # Return True if at least one device is ready
```

### Shutdown Cleanup

```python
async def stop(self):
    """Stop automation and clean up resources."""
    _LOGGER.info("Stopping humidity automation")

    # Remove all state listeners
    for listener in self._listeners:
        listener()
    self._listeners.clear()

    # Cancel all debouncing timers
    await self._cancel_all_timers()

    _LOGGER.info("Humidity automation stopped")
```

## Multi-Device Support

### Device Discovery

**Dynamic Device Detection:**
- Automation monitors all entities matching patterns
- Extracts device_id from entity names automatically
- No hardcoded device list required
- Supports unlimited devices

**Entity Pattern Matching:**
```
"switch.dehumidify_*" → Matches all switches
- switch.dehumidify_32_153289
- switch.dehumidify_32_153290
- switch.dehumidify_32_153291
```

### Per-Device Processing

```python
async def _handle_state_change(self, entity_id, old_state, new_state):
    """Handle state changes for any device."""
    device_id = self._extract_device_id(entity_id)

    # Process only this specific device
    if await self._validate_device_entities(device_id):
        await self._process_humidity_logic(device_id)
```

## Migration from Template System

### Removed Components

1. **YAML Template:** `automations/humidity_control_template.yaml` (deprecated)
2. **Template Substitution Logic:** No longer needed
3. **YAML Generation Code:** Remove from integration

### New Components

1. **HumidityAutomationManager:** Core automation logic
2. **Global State Listeners:** Replaces YAML triggers
3. **Direct Entity Handling:** No template substitution
4. **Enhanced Error Handling:** Python-level validation and logging

### Migration Strategy

1. **Phase 1:** Add hardcoded automation alongside existing template
2. **Phase 2:** Test hardcoded automation thoroughly
3. **Phase 3:** Remove template system entirely
4. **Phase 4:** Update documentation and examples

## Testing Strategy

### Unit Testing

**Decision Logic Testing:**
- Test each decision branch independently
- Validate exact mermaid logic implementation
- Test edge cases (boundary values, unavailable entities)

**Integration Testing:**
- Mock Home Assistant state changes
- Test fan service integration
- Validate timer and debouncing behavior

### Manual Testing

**Scenario Testing:**
- Indoor humidity above max threshold
- Indoor humidity below min threshold
- Indoor humidity within acceptable range
- Switch turned OFF (reset logic)
- Entity unavailability handling
- Multi-device scenarios

## Performance Considerations

### Efficiency Gains

**vs. YAML Template System:**
- No template substitution overhead
- Direct entity state access
- Optimized decision logic
- Reduced YAML parsing

**Memory Usage:**
- Single automation instance vs multiple YAML automations
- Minimal state tracking (only debouncing timers)
- Automatic cleanup on feature disable

### Scalability

**Device Scaling:**
- O(1) listener registration regardless of device count
- Efficient entity pattern matching
- Minimal per-device processing overhead

## Future Enhancements

### Potential Improvements

1. **Advanced Debouncing:** Variable timer based on recent changes
2. **Hysteresis:** Prevent oscillation around threshold values
3. **Seasonal Adjustments:** Automatic threshold adjustments
4. **Energy Optimization:** Consider energy prices or usage patterns
5. **Learning Algorithm:** Adapt thresholds based on user behavior

### Extensibility

**Additional Automation Types:**
- CO2 control automation
- Temperature-based ventilation
- Air quality automation
- Multi-sensor fusion algorithms

## Conclusion

This hardcoded automation approach provides a robust, maintainable, and scalable solution for humidity control that eliminates the problems inherent in the YAML template system while providing better integration with the existing Home Assistant ecosystem.

The design prioritizes:
- **Reliability:** Solid error handling and validation
- **Maintainability:** Clear separation of concerns and comprehensive documentation
- **Performance:** Efficient state monitoring and decision processing
- **Extensibility:** Easy to add new features and automation types
