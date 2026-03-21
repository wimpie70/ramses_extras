# CO2 Control Feature - Design & Implementation Plan

**Document Version:** 1.0.0
**Created:** March 20, 2026
**Feature ID:** `co2_control`

## Table of Contents
- [1. Overview](#1-overview)
- [2. Architecture & Flow](#2-architecture--flow)
- [3. System Integration](#3-system-integration)
- [4. Implementation Plan](#4-implementation-plan)
- [5. Technical Specifications](#5-technical-specifications)

---

## 1. Overview

### 1.1. Purpose
The CO2 Control feature extends the HVAC fan automation system with CO2-based ventilation control. It monitors multiple CO2 sensors across different zones and triggers ventilation when CO2 levels exceed configured thresholds.

### 1.2. Key Features
- **Multi-sensor monitoring**: Support for multiple CO2 sensors (similar to area sensors in humidity control)
- **Priority-based control**: CO2 control has **higher priority** than humidity control (OR-logic with priority)
- **Zone preparation**: Infrastructure for future zone-specific valve control
- **Configuration flow**: User-friendly setup via Home Assistant config flow
- **Real-time UI**: Integration with HVAC Fan Card showing CO2 sensors and control status
- **Enable/disable toggle**: User control over CO2 automation activation

### 1.3. Relationship to Existing Features

```
┌─────────────────────────────────────────────────────────┐
│              HVAC Fan Control System                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────┐    ┌────────────────────┐      │
│  │   CO2 Control      │    │  Humidity Control   │      │
│  │  (HIGH PRIORITY)   │    │  (LOWER PRIORITY)   │      │
│  └─────────┬──────────┘    └──────────┬─────────┘      │
│            │                           │                 │
│            └────────── OR-Logic ───────┘                 │
│                         ↓                                │
│            ┌────────────────────────┐                    │
│            │   Fan Speed Control    │                    │
│            │  (ramses_cc commands)  │                    │
│            └────────────────────────┘                    │
│                                                          │
├─────────────────────────────────────────────────────────┤
│                   Sensor Control                         │
│  (Resolves CO2, Temperature, Humidity entity sources)   │
└─────────────────────────────────────────────────────────┘
```

**Control Priority:**
1. **CO2 Control** - If enabled and triggered → Fan speed increases
2. **Humidity Control** - If enabled and triggered (and CO2 not active) → Fan speed increases
3. Both can run simultaneously, but CO2 takes precedence for fan speed decisions

---

## 2. Architecture & Flow

### 2.1. Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    CO2 Control Feature                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐│
│  │ CO2 Automation  │  │  CO2 Services   │  │  CO2 Config  ││
│  │   (Python)      │  │                 │  │    Flow      ││
│  └────────┬────────┘  └─────────────────┘  └──────────────┘│
│           │                                                  │
│  ┌────────▼─────────────────────────────────────────────┐   │
│  │              CO2 Zone Manager                        │   │
│  │  - Multi-sensor monitoring                           │   │
│  │  - Zone-based trigger detection                      │   │
│  │  - Priority coordination with humidity control       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   Entities                           │   │
│  │  - switch.co2_control_{device_id}                   │   │
│  │  - binary_sensor.co2_active_{device_id}             │   │
│  │  - number.co2_threshold_{device_id}                 │   │
│  │  - sensor.co2_zone_{zone_id}_{device_id}            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                  HVAC Fan Card UI                            │
│  - CO2 sensor status display (left panel, below filter)    │
│  - CO2 Control toggle button (top row)                     │
│  - Active CO2 zone highlighting                            │
│  - Real-time CO2 value updates                             │
└──────────────────────────────────────────────────────────────┘
```

### 2.2. Data Flow

```
CO2 Sensors (HA) → Sensor Control Resolver → CO2 Zone Manager
                                                      ↓
                                              Threshold Check
                                                      ↓
                                              Priority Logic ←→ Humidity Control
                                                      ↓
                                              Fan Speed Command
                                                      ↓
                                              ramses_cc Broker
                                                      ↓
                                              HVAC Fan Device
```

### 2.3. Priority Resolution Logic

```python
def calculate_target_fan_speed():
    """Calculate target fan speed based on active controls."""

    # 1. Check CO2 control (HIGHEST PRIORITY)
    if co2_control_enabled and co2_triggered:
        return calculate_co2_fan_speed()

    # 2. Check Humidity control (LOWER PRIORITY)
    if humidity_control_enabled and humidity_triggered:
        return calculate_humidity_fan_speed()

    # 3. Return to idle/normal
    return get_idle_fan_speed()
```

### 2.4. Zone Architecture

**Current Implementation:**
- Single device-level CO2 monitoring
- Multiple CO2 sensors per device
- Zones tracked logically within feature

**Future Enhancement (with valves):**
```
Device (FAN)
  ├── Zone 1 (Living Room)
  │   ├── CO2 Sensor: sensor.living_room_co2
  │   ├── Valve: switch.zone_1_valve
  │   └── Threshold: number.co2_threshold_zone_1
  │
  ├── Zone 2 (Bedroom)
  │   ├── CO2 Sensor: sensor.bedroom_co2
  │   ├── Valve: switch.zone_2_valve
  │   └── Threshold: number.co2_threshold_zone_2
  │
  └── Zone 3 (Office)
      ├── CO2 Sensor: sensor.office_co2
      ├── Valve: switch.zone_3_valve
      └── Threshold: number.co2_threshold_zone_3
```

---

## 3. System Integration

### 3.1. Sensor Control Integration

CO2 Control leverages Sensor Control for entity resolution:

```python
# In sensor_control/const.py - Add CO2 metrics
INTERNAL_SENSOR_MAPPINGS = {
    ...existing mappings...

    # CO2 sensors per zone (future expansion)
    "co2_zone_1": "sensor.co2_zone_1_{device_id}",
    "co2_zone_2": "sensor.co2_zone_2_{device_id}",
    "co2_zone_3": "sensor.co2_zone_3_{device_id}",
}
```

### 3.2. Config Flow Integration

Add CO2-specific configuration steps to `config_flow.py`:

```python
# Step flow
CONFIG_FLOW_STEPS = [
    ...existing steps...
    "co2_setup",       # Enable/disable CO2 control
    "co2_sensors",     # Configure CO2 sensor entities
    "co2_zones",       # Map sensors to zones
    "co2_thresholds",  # Set CO2 thresholds per zone
]
```

### 3.3. HVAC Fan Card Integration

**Left Panel Layout (new):**
```
┌─────────────────────────┐
│  Indoor Sensor          │
│  Outdoor Sensor         │
│  Remaining Filter       │
├─────────────────────────┤ ← Horizontal Divider
│  CO2 Sensors:           │
│  ○ Living Room: 650 ppm │
│  ● Bedroom: 1100 ppm    │ ← Active (highlighted)
│  ○ Office: 580 ppm      │
└─────────────────────────┘
```

**Top Button Row (updated):**
```
┌──────┬──────┬──────┬──────┐
│ Fan  │Balance│ CO2  │Settings│
│Speed │      │Control│       │
└──────┴──────┴──────┴──────┘
        ↑       ↑
      existing  new
```

### 3.4. Automation Coordination

```python
class CO2AutomationManager:
    """Manages CO2-based ventilation automation."""

    def __init__(self, hass, device_id):
        self.hass = hass
        self.device_id = device_id
        self.humidity_manager = None  # Reference to humidity automation

    async def coordinate_with_humidity(self):
        """Coordinate priority with humidity control."""
        if self.is_co2_active():
            # CO2 is active - take control
            await self.humidity_manager.pause_control()
            return "co2_priority"
        else:
            # CO2 not active - allow humidity control
            await self.humidity_manager.resume_control()
            return "humidity_allowed"
```

---

## 4. Implementation Plan

### Phase 1: Core Infrastructure (Foundation)

**Step 1.1: Create CO2 Control Feature Structure**
- Create `/features/co2_control/` directory
- Create `__init__.py`, `const.py`, `config.py`
- Define feature constants and entity definitions
- Create `FEATURE_DEFINITION` dict

**Step 1.2: Extend Sensor Control**
- Add CO2 metrics to `sensor_control/const.py`
- Update `SensorControlResolver` to handle CO2 entities
- Add CO2 sensor resolution logic

**Step 1.3: Create CO2 Zone Manager**
- Implement `co2_control/zone_manager.py`
- Multi-sensor tracking logic
- Zone-to-sensor mapping
- Threshold monitoring per zone

**Deliverables:**
- Feature directory structure
- Basic entity definitions
- Zone management infrastructure

---

### Phase 2: Automation & Priority Logic

**Step 2.1: Implement CO2 Automation**
- Create `co2_control/automation.py`
- Extend `BaseAutomation` class
- Implement CO2 threshold monitoring
- Add fan speed calculation logic

**Step 2.2: Priority Coordination**
- Implement priority resolution between CO2 and humidity
- Add coordination methods in both automation managers
- Create shared priority state tracker
- Handle control handoff logic

**Step 2.3: Create CO2 Entities**
- Create `co2_control/entities.py`
- Implement switch, number, binary_sensor entities
- Add entity state management
- Register entities with platform

**Deliverables:**
- Working CO2 automation
- Priority coordination logic
- Entity platform implementations

---

### Phase 3: Configuration Flow

**Step 3.1: CO2 Config Flow Steps**
- Extend `config_flow.py` with CO2 setup steps
- Implement sensor selection UI
- Add zone configuration interface
- Implement threshold configuration

**Step 3.2: CO2 Configuration Storage**
- Extend config entry options for CO2 settings
- Add validation for CO2 configuration
- Implement config migration logic

**Deliverables:**
- User-facing CO2 configuration interface
- Config persistence and validation

---

### Phase 4: HVAC Fan Card UI

**Step 4.1: CO2 Sensor Display**
- Update card layout to show CO2 sensors
- Add horizontal divider below filter info
- Implement sensor value display
- Add active zone highlighting

**Step 4.2: CO2 Control Button**
- Add 4th button to top row layout
- Implement CO2 control toggle
- Add button state synchronization
- Update button grid styling

**Step 4.3: Real-time Updates**
- Extend message handlers for CO2 data
- Update WebSocket command APIs
- Implement CO2 state change notifications
- Add CO2 chart/graph (optional)

**Deliverables:**
- Updated HVAC Fan Card UI
- CO2 sensor display panel
- CO2 control button

---

### Phase 5: Services & Integration

**Step 5.1: CO2 Control Services**
- Create `co2_control/services.py`
- Implement manual CO2 control services
- Add zone-specific services
- Register services with HA

**Step 5.2: WebSocket Commands**
- Add CO2-specific WebSocket commands
- Implement real-time CO2 status queries
- Add CO2 zone state commands

**Deliverables:**
- Service definitions
- WebSocket API extensions

---

### Phase 6: Zone Preparation & Future-Proofing

**Step 6.1: Zone Infrastructure**
- Design zone entity structure
- Prepare valve entity placeholders
- Document valve integration points

**Step 6.2: Zone Configuration**
- Add zone naming in config flow
- Implement zone-device associations
- Prepare for per-zone valve control

**Deliverables:**
- Zone-ready architecture
- Documentation for valve integration

---

### Phase 7: Testing & Documentation

**Step 7.1: Unit Tests**
- Write tests for CO2 automation logic
- Test priority coordination
- Test zone manager functionality

**Step 7.2: Integration Tests**
- Test CO2 + humidity interaction
- Test config flow end-to-end
- Test UI updates and state sync

**Step 7.3: Documentation**
- Update architecture documentation
- Write user guide for CO2 control
- Document API and service calls

**Deliverables:**
- Test coverage
- User documentation
- Developer documentation

---

## 5. Technical Specifications

### 5.1. Entity Definitions

```python
# co2_control/const.py

CO2_SWITCH_CONFIGS = {
    "co2_control": {
        "name_template": "CO2 Control {device_id}",
        "icon": "mdi:molecule-co2",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_control_{device_id}",
    },
}

CO2_NUMBER_CONFIGS = {
    "co2_threshold": {
        "name_template": "CO2 Threshold {device_id}",
        "entity_category": EntityCategory.CONFIG,
        "unit": "ppm",
        "icon": "mdi:molecule-co2",
        "min_value": 400,
        "max_value": 2000,
        "step": 50,
        "default_value": 1000,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_threshold_{device_id}",
    },
}

CO2_BINARY_SENSOR_CONFIGS = {
    "co2_active": {
        "name_template": "CO2 Active {device_id}",
        "icon": "mdi:molecule-co2",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_active_{device_id}",
    },
}

CO2_SENSOR_CONFIGS = {
    "co2_zone_status": {
        "name_template": "CO2 Zone {zone_id} {device_id}",
        "icon": "mdi:home-analytics",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": None,
        "unit": "ppm",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "co2_zone_{zone_id}_{device_id}",
    },
}
```

### 5.2. Configuration Schema

```python
CO2_CONTROL_CONFIG_SCHEMA = {
    "enabled": bool,
    "automation_enabled": bool,
    "zones": [
        {
            "zone_id": str,
            "zone_name": str,
            "sensor_entity": str,
            "threshold": int,  # ppm
            "enabled": bool,
            "valve_entity": str | None,  # Future: zone-specific valve
        }
    ],
    "default_threshold": int,
    "activation_hysteresis": int,  # ppm above threshold to activate
    "deactivation_hysteresis": int,  # ppm below threshold to deactivate
    "max_runtime_minutes": int,
    "priority_over_humidity": bool,  # Always True
}
```

### 5.3. Zone Data Structure

```python
@dataclass
class CO2Zone:
    """Represents a CO2 monitoring zone."""

    zone_id: str
    zone_name: str
    sensor_entity: str
    threshold: int
    enabled: bool
    valve_entity: str | None = None

    # Runtime state
    current_co2: int | None = None
    is_triggered: bool = False
    last_update: datetime | None = None
    trigger_count: int = 0
```

### 5.4. API Service Definitions

```yaml
# services.yaml additions

co2_control:
  enable_co2_control:
    description: Enable CO2-based ventilation control
    fields:
      device_id:
        description: Device ID of the HVAC fan
        required: true

  disable_co2_control:
    description: Disable CO2-based ventilation control
    fields:
      device_id:
        description: Device ID of the HVAC fan
        required: true

  set_zone_threshold:
    description: Set CO2 threshold for a specific zone
    fields:
      device_id:
        description: Device ID of the HVAC fan
        required: true
      zone_id:
        description: Zone identifier
        required: true
      threshold:
        description: CO2 threshold in ppm
        required: true

  trigger_co2_boost:
    description: Manually trigger CO2-based boost mode
    fields:
      device_id:
        description: Device ID of the HVAC fan
        required: true
      duration_minutes:
        description: Duration in minutes
        default: 30
```

### 5.5. WebSocket Commands

```python
WS_COMMANDS = {
    "get_co2_status": "ramses_extras/co2/get_status",
    "get_zone_details": "ramses_extras/co2/get_zone_details",
    "update_zone_config": "ramses_extras/co2/update_zone",
    "get_co2_history": "ramses_extras/co2/get_history",
}
```

---

## 6. File Structure

```
features/co2_control/
├── __init__.py                 # Feature initialization
├── const.py                    # Entity and constant definitions
├── config.py                   # Configuration management
├── automation.py               # CO2 automation logic
├── zone_manager.py             # Zone and multi-sensor management
├── entities.py                 # Entity state management
├── services.py                 # Service implementations
├── websocket_commands.py       # WebSocket API
├── platforms/                  # HA platform implementations
│   ├── __init__.py
│   ├── sensor.py
│   ├── switch.py
│   ├── number.py
│   └── binary_sensor.py
├── translations/
│   ├── en.json
│   └── nl.json
└── docs/
    ├── USER_GUIDE.md
    └── API.md
```

---

## 7. Migration & Backward Compatibility

### 7.1. Existing System Impact
- No breaking changes to existing humidity control
- Config entry extended, not replaced
- HVAC Fan Card layout adjusted (non-breaking)

### 7.2. Feature Flag
- CO2 Control can be independently enabled/disabled
- Graceful degradation if sensors not configured
- Backward compatible with existing installations

---

## 8. Future Enhancements

### 8.1. Zone-Specific Valves
- Per-zone valve control entities
- Independent zone ventilation
- Selective zone boost mode

### 8.2. Advanced Features
- CO2 trend analysis
- Predictive ventilation
- Learning algorithms for optimal thresholds
- Integration with occupancy sensors

### 8.3. Multi-Device Support
- Coordinate multiple HVAC fans
- Cross-device zone management
- Centralized CO2 monitoring

---

## 9. Success Criteria

### 9.1. Functional Requirements
- ✅ Multiple CO2 sensors monitored simultaneously
- ✅ CO2 triggers increase fan speed
- ✅ CO2 control has priority over humidity control
- ✅ User can enable/disable CO2 control
- ✅ UI shows all CO2 sensors with values and status
- ✅ Config flow allows easy sensor setup

### 9.2. Performance Requirements
- Sensor updates processed within 1 second
- Priority resolution < 100ms
- UI updates reflect state within 2 seconds

### 9.3. Reliability Requirements
- Graceful handling of missing sensors
- No impact on system if CO2 control disabled
- Safe fallback if priority logic fails

---

## End of Document
