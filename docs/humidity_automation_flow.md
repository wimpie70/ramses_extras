# Humidity Automation Flow

This document describes the exact flow from Home Assistant startup to switch interaction for the humidity automation feature.

## Overview

The humidity automation is coordinated between three main components:
1. **Binary Sensor** (binary_sensor.dehumidifying_active_32_153289) - Creates and controls the automation
2. **Switch** (switch.dehumidify_32_153289) - User interface to activate/deactivate automation
3. **Automation Manager** - Implements the humidity control logic

## Initialization Flow

```mermaid
graph TD
    A[Home Assistant Startup] --> B[ramses_extras Integration Loads]
    B --> C[Config Entry Setup]
    C --> D[Platform Setup: binary_sensor]
    C --> E[Platform Setup: switch]

    D --> F[Create Binary Sensors]
    F --> G[Create binary_sensor.dehumidifying_active_32_153289]
    G --> H[RamsesBinarySensor.async_added_to_hass]

    E --> I[Create Switches]
    I --> J[Create switch.dehumidify_32_153289]
    J --> K[RamsesDehumidifySwitch.async_added_to_hass]
```

## Binary Sensor Automation Creation

```mermaid
graph TD
    H --> L[If boolean_type == dehumidifying_active]
    L --> M[Start Humidity Automation]
    M --> N[Create HumidityAutomationManager]
    N --> O[automation start]
    O --> P[Store in hass data ramses extras automations 32 153289]
    P --> Q[Binary sensor ready for automation control]
```

## Switch Interaction Flow

```mermaid
graph TD
    S[User clicks switch ON] --> T[RamsesDehumidifySwitch async turn on]
    T --> U[Look for automation in hass data ramses extras automations 32 153289]

    U --> V{Automation Found?}
    V -->|No| W[No automation found log]
    V -->|Yes| X[automation switch_state equals True]
    X --> Y[automation evaluate current conditions]
    Y --> Z[Get humidity sensor states]
    Z --> AA[Apply humidity decision logic]
    AA --> BB[Set fan speed to HIGH or LOW]
    BB --> CC[Update binary sensor async turn on or off]
    CC --> DD[Fan and binary sensor synchronized]
```

## Switch Deactivation Flow

```mermaid
graph TD
    S2[User clicks switch OFF] --> T2[RamsesDehumidifySwitch async turn off]
    T2 --> U2[Look for automation in hass data ramses extras automations 32 153289]
    U2 --> V2{Automation Found?}
    V2 -->|No| W2[No automation found log]
    V2 -->|Yes| X2[automation switch_state equals False]
    X2 --> Y2[Reset fan to AUTO]
    Y2 --> Z2[Update binary sensor async turn off]
    Z2 --> DD2[Fan reset, binary sensor updated]
```

## Complete End-to-End Flow

```mermaid
graph TD
    A[Home Assistant Startup] --> B[ramses_extras Integration Loads]
    B --> C[Config Entry Setup in __init__.py:232]
    C --> D[hass.config_entries.async_forward_entry_setups]
    D --> E[Forward to PLATFORMS: sensor, switch, binary_sensor, number]

    E --> F[Platform Setup: binary_sensor]
    E --> G[Platform Setup: switch]

    F --> H[binary_sensor.py:33 - async_setup_entry]
    G --> I[switch.py:29 - async_setup_entry]

    H --> J[Create RamsesBinarySensor entities]
    I --> K[Create RamsesDehumidifySwitch entities]

    J --> L[Home Assistant calls async_added_to_hass]
    K --> M[Home Assistant calls async_added_to_hass]

    L --> N[If boolean_type == 'dehumidifying_active']
    N --> O[binary_sensor.py:211 - _start_humidity_automation_for_device]
    O --> P[Create HumidityAutomationManager]
    P --> Q[automation.start]
    Q --> R[Store: hass.data.ramses_extras.automations.32:153289]
    R --> S[Binary sensor ready]

    M --> T[Switch subscribes to device updates]
    T --> U[Switch ready]

    V[User Interaction] --> W[Switch clicked ON/OFF]
    W --> X[switch.py:194/219 - async_turn_on/async_turn_off]
    X --> Y[Look for: hass.data.ramses_extras.automations.32:153289]

    Y --> Z{Automation Found?}
    Z -->|No| AA[No automation found - DEBUG THIS]
    Z -->|Yes| BB[Update automation.switch_state]
    BB --> CC[automation._evaluate_current_conditions]
    CC --> DD[Get sensor states]
    DD --> EE[Apply decision logic]
    EE --> FF[Set fan speed]
    FF --> GG[Update binary sensor]
    GG --> HH[Coordinated control]
```

## Key File Locations

### Entry Point
- **File**: `ramses_extras/custom_components/ramses_extras/__init__.py`
- **Function**: `async def async_setup_entry` (line 232)
- **Key**: `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)` (line 265)

### Platforms
- **Binary Sensor**: `ramses_extras/custom_components/ramses_extras/binary_sensor.py`
  - Setup: `async def async_setup_entry` (line 33)
  - Creation: `async def async_added_to_hass` (line 179)
  - Automation: `async def _start_humidity_automation_for_device` (line 211)

- **Switch**: `ramses_extras/custom_components/ramses_extras/switch.py`
  - Setup: `async def async_setup_entry` (line 29)
  - Creation: `async def async_added_to_hass` (line 171)
  - ON Action: `async def async_turn_on` (line 194)
  - OFF Action: `async def async_turn_off` (line 219)

### Automation
- **File**: `ramses_extras/custom_components/ramses_extras/automations/humidity_automation.py`
- **Class**: `HumidityAutomationManager`

## Data Flow Summary

### Storage Path
```
hass.data['ramses_extras']['automations']['32:153289'] = HumidityAutomationManager
```

### Lookup Path
```python
automation = (
    self.hass.data.get("ramses_extras", {})
    .get("automations", {})
    .get(self._device_id)  # "32:153289"
)
```

### Device ID Format
- **Format**: "32:153289" (colon, not underscore)
- **Binary sensor stores**: "32:153289"
- **Switch looks for**: "32:153289"

## Current Issue

The switch reports "No automation found" when trying to activate, suggesting:

1. **Binary sensor never runs** `async_added_to_hass` or `async_added_to_hass` fails
2. **Automation creation fails** in `_start_humidity_automation_for_device`
3. **Device ID mismatch** between storage and lookup
4. **Data path issue** in the nested dictionary access

## Debug Strategy

Added logging to both binary sensor and switch to identify the exact failure point:
- **Binary sensor logs**: When automation starts and stores
- **Switch logs**: What automations are actually available

This will show whether the issue is in creation, storage, or lookup phases.
