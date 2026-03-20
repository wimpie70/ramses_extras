# CO2 Control Feature - Implementation Plan

## Quick Reference

**Feature ID:** `co2_control`
**Priority:** CO2 control > Humidity control (OR-logic)
**Complexity:** High (multi-sensor, priority coordination, zone infrastructure)
**Estimated Effort:** 3-5 days

---

## Implementation Sequence

### ✅ Phase 1: Core Infrastructure (Day 1)

**1.1 Create Feature Structure**

```bash
mkdir -p features/co2_control/{platforms,translations,docs}
touch features/co2_control/{__init__.py,const.py,config.py,zone_manager.py}
touch features/co2_control/platforms/{__init__.py,sensor.py,switch.py,number.py,binary_sensor.py}
```

**Files to create:**

- `features/co2_control/__init__.py` - Feature initialization (based on humidity_control pattern)
- `features/co2_control/const.py` - Entity definitions, constants
- `features/co2_control/config.py` - Configuration management
- `features/co2_control/zone_manager.py` - Multi-sensor zone logic

**Key tasks:**

- [ ] Define `FEATURE_DEFINITION` dict in `const.py`
- [ ] Define switch/number/binary_sensor entity configs
- [ ] Create zone data structures
- [ ] Register feature in `const.py` AVAILABLE_FEATURES

---

### ✅ Phase 2: Sensor Control Extension (Day 1)

**2.1 Extend Sensor Control for CO2**

**Files to modify:**

- `features/sensor_control/const.py` - Add CO2 metrics
- `features/sensor_control/resolver.py` - Add CO2 resolution logic
- `features/sensor_control/config_flow.py` - Add CO2 sensor selection

**Changes:**

```python
# In sensor_control/const.py
INTERNAL_SENSOR_MAPPINGS = {
    ...
    "co2_zone_1": "sensor.co2_zone_1_{device_id}",
    "co2_zone_2": "sensor.co2_zone_2_{device_id}",
    "co2_zone_3": "sensor.co2_zone_3_{device_id}",
}

# New metrics list
SUPPORTED_METRICS.extend(["co2_zone_1", "co2_zone_2", "co2_zone_3"])
```

**Key tasks:**

- [ ] Add CO2 to supported metrics
- [ ] Update resolver to handle CO2 entities
- [ ] Add CO2 to config flow sensor selection

---

### ✅ Phase 3: Automation & Priority (Day 2)

**3.1 Create CO2 Automation**

**Files to create:**

- `features/co2_control/automation.py` - Main automation logic

**Key components:**

```python
class CO2AutomationManager(BaseAutomation):
    """Manages CO2-based ventilation automation."""

    async def initialize(self):
        """Initialize CO2 automation."""

    async def check_co2_triggers(self):
        """Check all zones for CO2 threshold breaches."""

    async def calculate_co2_fan_speed(self):
        """Calculate required fan speed based on CO2 levels."""

    async def coordinate_with_humidity(self):
        """Implement priority logic with humidity control."""
```

**3.2 Update Humidity Control for Priority**

**Files to modify:**

- `features/humidity_control/automation.py`

**Changes:**

```python
class HumidityAutomationManager:

    def __init__(self):
        self.co2_manager = None  # Reference to CO2 manager
        self.is_paused = False

    async def check_priority(self):
        """Check if CO2 control has priority."""
        if self.co2_manager and self.co2_manager.is_active():
            self.is_paused = True
            return False
        self.is_paused = False
        return True
```

**Key tasks:**

- [ ] Implement CO2 threshold monitoring
- [ ] Add zone-level trigger detection
- [ ] Create priority coordination methods
- [ ] Add control pause/resume logic
- [ ] Test priority handoff

---

### ✅ Phase 4: Entities (Day 2)

**4.1 Create CO2 Entities**

**Files to create:**

- `features/co2_control/entities.py` - Entity state management
- `features/co2_control/platforms/switch.py` - CO2 control switch
- `features/co2_control/platforms/number.py` - CO2 threshold numbers
- `features/co2_control/platforms/binary_sensor.py` - CO2 active binary sensor
- `features/co2_control/platforms/sensor.py` - Zone status sensors

**Entity list:**

- `switch.co2_control_{device_id}` - Enable/disable CO2 control
- `number.co2_threshold_{device_id}` - Global CO2 threshold
- `binary_sensor.co2_active_{device_id}` - CO2 automation active indicator
- `sensor.co2_zone_{zone_id}_{device_id}` - Per-zone CO2 status

**Key tasks:**

- [ ] Implement switch entity for CO2 control toggle
- [ ] Implement number entities for thresholds
- [ ] Implement binary sensor for active state
- [ ] Add entity registration in **init**.py
- [ ] Test entity creation and state updates

---

### ✅ Phase 5: Configuration Flow (Day 3)

**5.1 Add CO2 Config Steps**

**Files to modify:**

- Main `config_flow.py` - Add CO2 setup steps

**New config flow steps:**

1. `co2_setup` - Enable CO2 control, set default threshold
2. `co2_sensors` - Select CO2 sensor entities for zones
3. `co2_zones` - Configure zone names and associations
4. `co2_advanced` - Advanced settings (hysteresis, runtime limits)

**Config structure:**

```python
{
    "co2_control": {
        "enabled": True,
        "automation_enabled": False,
        "default_threshold": 1000,
        "zones": [
            {
                "zone_id": "zone_1",
                "zone_name": "Living Room",
                "sensor_entity": "sensor.living_room_co2",
                "threshold": 1000,
                "enabled": True,
            }
        ],
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
    }
}
```

**Key tasks:**

- [ ] Create config flow step handlers
- [ ] Add sensor entity selection UI
- [ ] Implement zone configuration UI
- [ ] Add validation logic
- [ ] Test config persistence

---

### ✅ Phase 6: HVAC Fan Card UI (Day 3-4)

**6.1 Update Card Layout**

**Files to modify:**

- `features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js`
- `features/hvac_fan_card/www/hvac_fan_card/card-styles.js`
- `features/hvac_fan_card/www/hvac_fan_card/templates/top-section.js`

**UI Changes:**

1. **Left Panel - Add CO2 Sensors:**

```javascript
_createCO2SensorsList() {
    const co2Zones = this._getCO2Zones();

    return `
        <div class="r-xtrs-hvac-fan-co2-divider"></div>
        <div class="r-xtrs-hvac-fan-co2-sensors">
            <div class="r-xtrs-hvac-fan-co2-title">CO2 Sensors</div>
            ${co2Zones.map(zone => this._createCO2ZoneItem(zone)).join('')}
        </div>
    `;
}

_createCO2ZoneItem(zone) {
    const isActive = zone.is_triggered;
    const statusClass = isActive ? 'active' : '';

    return `
        <div class="r-xtrs-hvac-fan-co2-zone ${statusClass}">
            <span class="zone-indicator">${isActive ? '●' : '○'}</span>
            <span class="zone-name">${zone.name}</span>
            <span class="co2-value">${zone.co2_value} ppm</span>
        </div>
    `;
}
```

2. **Top Buttons - Add CO2 Control:**

```javascript
// Update button grid from 3 to 4 columns
.r-xtrs-hvac-fan-buttons {
    display: grid;
    grid-template-columns: repeat(4, 1fr);  /* Changed from 3 to 4 */
    gap: 8px;
}

// Add CO2 button
<button class="r-xtrs-hvac-fan-button ${co2ControlEnabled ? 'active' : ''}"
        @click="${() => this._toggleCO2Control()}">
    <ha-icon icon="mdi:molecule-co2"></ha-icon>
    <span>CO2 Control</span>
</button>
```

**Key tasks:**

- [ ] Add CO2 sensor list to left panel
- [ ] Implement horizontal divider below filter
- [ ] Add CO2 control button to top row
- [ ] Implement active zone highlighting
- [ ] Add real-time CO2 value updates
- [ ] Update button grid to 4 columns
- [ ] Add CSS styling for CO2 elements

---

### ✅ Phase 7: Services & WebSocket (Day 4)

**7.1 Create CO2 Services**

**Files to create:**

- `features/co2_control/services.py`
- `features/co2_control/websocket_commands.py`

**Services to implement:**

```python
SERVICE_ENABLE_CO2_CONTROL = "enable_co2_control"
SERVICE_DISABLE_CO2_CONTROL = "disable_co2_control"
SERVICE_SET_ZONE_THRESHOLD = "set_zone_threshold"
SERVICE_TRIGGER_CO2_BOOST = "trigger_co2_boost"
```

**WebSocket commands:**

```python
WS_GET_CO2_STATUS = "ramses_extras/co2/get_status"
WS_GET_ZONE_DETAILS = "ramses_extras/co2/get_zone_details"
WS_UPDATE_ZONE_CONFIG = "ramses_extras/co2/update_zone"
```

**Key tasks:**

- [ ] Implement service handlers
- [ ] Register services with HA
- [ ] Implement WebSocket commands
- [ ] Add real-time state updates
- [ ] Test service calls from UI

---

### ✅ Phase 8: Zone Infrastructure (Day 4-5)

**8.1 Prepare Zone System**

**Files to create/modify:**

- `features/co2_control/zone_manager.py` - Complete implementation

**Zone Manager Features:**

```python
class CO2ZoneManager:
    """Manages CO2 zones and multi-sensor monitoring."""

    def __init__(self, hass, device_id, config):
        self.zones: dict[str, CO2Zone] = {}

    async def update_zone_co2(self, zone_id, co2_value):
        """Update CO2 value for a zone."""

    async def check_zone_triggers(self):
        """Check which zones have exceeded thresholds."""

    async def get_active_zones(self):
        """Get list of zones with active CO2 triggers."""

    async def calculate_combined_fan_speed(self):
        """Calculate fan speed based on worst zone."""
```

**Valve Preparation (future):**

```python
@dataclass
class CO2Zone:
    zone_id: str
    zone_name: str
    sensor_entity: str
    threshold: int
    enabled: bool

    # Future: valve control
    valve_entity: str | None = None
    valve_position: int | None = None
```

**Key tasks:**

- [ ] Implement zone tracking logic
- [ ] Add multi-sensor monitoring
- [ ] Create trigger detection per zone
- [ ] Add fan speed calculation based on zones
- [ ] Prepare valve entity placeholders
- [ ] Document valve integration points

---

### ✅ Phase 9: Testing & Documentation (Day 5)

**9.1 Create Tests**

**Files to create:**

- `tests/frontend/test-co2-control.js`
- `tests/backend/test_co2_automation.py`

**Test coverage:**

- [ ] CO2 threshold detection
- [ ] Priority coordination with humidity
- [ ] Zone manager multi-sensor handling
- [ ] Config flow validation
- [ ] UI state updates
- [ ] Service call handling

**9.2 Documentation**

**Files to create/update:**

- `features/co2_control/docs/USER_GUIDE.md`
- `features/co2_control/docs/API.md`
- Update `docs/RAMSES_EXTRAS_ARCHITECTURE.md`

**Key tasks:**

- [ ] Write unit tests for automation
- [ ] Write integration tests
- [ ] Test CO2 + humidity interaction
- [ ] Write user guide
- [ ] Document API and services
- [ ] Update architecture docs

**9.3 Wiki & README Updates**

**Wiki Updates (ramses_extras.wiki):**

- [ ] Create new wiki page for CO2 Control feature
  - Feature overview and benefits
  - Configuration guide with screenshots
  - Zone setup instructions
  - Troubleshooting section
- [ ] Update Humidity Control (Balance) wiki page
  - Document balance triggers section
  - Document area sensor configuration
  - Document enabled/disabled sensor states
  - Document high humidity trigger flags
  - Update screenshots with new UI layout
- [ ] Update HVAC Fan Card wiki page
  - Document 4-button layout (Fan Speed, Balance, CO2 Control, Settings)
  - Document CO2 sensor display panel
  - Document balance triggers UI improvements
  - Update card configuration examples

**README.md Updates:**

- [ ] Add CO2 Control to features list
- [ ] Update feature comparison table
- [ ] Add CO2 Control configuration example
- [ ] Update humidity control section with balance improvements
- [ ] Add screenshots of new UI elements
- [ ] Update quick start guide

**Change Documentation:**

- [ ] Update CHANGELOG.md with CO2 Control addition
- [ ] Document humidity control balance enhancements
- [ ] Note breaking changes (if any)
- [ ] Document migration steps for existing users

---

## Integration Checklist

### Core System

- [ ] Add `co2_control` to `AVAILABLE_FEATURES` in main `const.py`
- [ ] Update `services.yaml` with CO2 services
- [ ] Update main `config_flow.py` to include CO2 steps
- [ ] Register CO2 WebSocket commands in `websocket_integration.py`

### Sensor Control

- [ ] Add CO2 metrics to `INTERNAL_SENSOR_MAPPINGS`
- [ ] Update `SensorControlResolver` for CO2
- [ ] Add CO2 to config flow sensor selection

### Humidity Control

- [ ] Add priority coordination methods
- [ ] Add reference to CO2 manager
- [ ] Implement pause/resume logic
- [ ] Test priority handoff

### HVAC Fan Card

- [ ] Add CO2 sensor display panel
- [ ] Add CO2 control button (4th button)
- [ ] Implement CO2 message handlers
- [ ] Add CO2 state change listeners
- [ ] Update card styles for 4-column layout

### Translations

- [ ] Add English translations (`en.json`)
- [ ] Add Dutch translations (`nl.json`)
- [ ] Update card translations

---

## Critical Dependencies

1. **Sensor Control Must Support CO2**
   - CO2 entities need to be resolvable via SensorControlResolver
   - Config flow must allow CO2 sensor selection

2. **Priority Coordination**
   - Both automation managers need references to each other
   - Clear priority resolution logic required
   - State synchronization critical

3. **UI Layout Changes**
   - Button grid changes from 3 to 4 columns
   - Left panel needs space for CO2 sensors
   - Responsive design must accommodate both features

4. **Config Entry Structure**
   - CO2 config must coexist with humidity config
   - Zone data stored per-device in config entry
   - Migration logic for existing installations

---

## Risk Mitigation

### High-Risk Areas

1. **Priority Logic Conflicts**
   - Risk: CO2 and humidity fighting for control
   - Mitigation: Clear priority rules, state machine, mutex locks

2. **Config Flow Complexity**
   - Risk: Too many steps, user confusion
   - Mitigation: Sensible defaults, optional advanced steps

3. **UI Layout Breakage**
   - Risk: Adding 4th button breaks mobile layout
   - Mitigation: Responsive grid, test on mobile

4. **Performance Impact**
   - Risk: Multiple sensor updates slow system
   - Mitigation: Debouncing, batch updates, efficient state management

### Testing Strategy

- Unit test each automation manager independently
- Integration test priority coordination
- UI test with mock data
- Real-device test with actual CO2 sensors

---

## Success Metrics

### Functional

- ✅ CO2 control triggers fan speed increase
- ✅ Priority over humidity control works correctly
- ✅ Multiple zones monitored simultaneously
- ✅ UI shows all zones with current values
- ✅ Config flow is intuitive and complete

### Technical

- ✅ No conflicts with existing humidity control
- ✅ Sensor updates processed < 1 second
- ✅ UI updates reflect state < 2 seconds
- ✅ No memory leaks or performance degradation

### User Experience

- ✅ Easy to configure via UI
- ✅ Clear visual feedback in card
- ✅ Intuitive control button
- ✅ Helpful error messages

---

## Post-Implementation

### Future Enhancements

1. Zone-specific valve control
2. CO2 trend charts
3. Predictive ventilation
4. Learning optimal thresholds
5. Multi-device coordination

### Maintenance

- Monitor for priority logic edge cases
- Optimize zone checking performance
- Gather user feedback on thresholds
- Consider adding presets (home/away/sleep)

---

## End of Plan
