# CO2 Control Feature - Implementation Summary

**Date:** March 20, 2026
**Status:** Core Implementation Complete
**Version:** Initial Release

---

## Overview

Successfully implemented the CO2 Control feature for Ramses Extras, providing CO2-based ventilation control with multi-zone monitoring and priority coordination with humidity control.

## Implementation Phases Completed

### ✅ Phase 1: Core Infrastructure
- Created feature directory structure
- Defined entity configurations (switch, number, binary_sensor, sensor)
- Implemented configuration management (`CO2Config`)
- Created zone manager (`CO2ZoneManager`) for multi-sensor tracking
- Added translations (English and Dutch)

### ✅ Phase 2: Sensor Control Extension
- Added CO2 zone metrics to `SUPPORTED_METRICS`
- Extended `INTERNAL_SENSOR_MAPPINGS` with zone-specific CO2 sensors
- Enabled CO2 entity resolution via `SensorControlResolver`

### ✅ Phase 3: Automation & Priority Coordination
- Implemented `CO2AutomationManager` with zone monitoring
- Added state change listeners for CO2 sensors
- Implemented fan speed calculation based on worst zone
- Updated `HumidityAutomationManager` with priority coordination
- Added `pause_for_co2()`, `resume_from_co2()`, and `check_priority()` methods
- Integrated priority check into humidity evaluation logic

### ✅ Phase 4: Feature Registration
- Registered CO2 Control in `AVAILABLE_FEATURES`
- Added feature to main `const.py`

### ✅ Phase 5: Services & WebSocket
- Implemented service handlers (enable, disable, set threshold, trigger boost)
- Created WebSocket commands (get status, zone details, update config, history)
- Added service definitions to `services.yaml`

### ✅ Phase 6: Documentation
- Created comprehensive README
- Wrote detailed user guide
- Documented API and services
- Provided automation examples

---

## Files Created

### Core Feature Files
```
features/co2_control/
├── __init__.py                 # Feature initialization
├── const.py                    # Entity definitions and constants
├── config.py                   # Configuration management
├── automation.py               # CO2 automation logic
├── zone_manager.py             # Multi-zone CO2 monitoring
├── entities.py                 # Entity management
├── services.py                 # Service handlers
├── websocket_commands.py       # WebSocket API
├── README.md                   # Feature documentation
├── IMPLEMENTATION_PLAN.md      # Implementation roadmap
├── platforms/
│   ├── __init__.py
│   ├── switch.py              # CO2 control switch
│   ├── number.py              # Threshold and hysteresis numbers
│   ├── binary_sensor.py       # CO2 active binary sensor
│   └── sensor.py              # Zone status sensor
├── translations/
│   ├── en.json                # English translations
│   └── nl.json                # Dutch translations
└── docs/
    └── USER_GUIDE.md          # Comprehensive user guide
```

### Modified Files
```
const.py                                    # Added CO2 Control to AVAILABLE_FEATURES
services.yaml                               # Added CO2 service definitions
features/sensor_control/const.py            # Added CO2 zone metrics
features/humidity_control/automation.py     # Added priority coordination
```

---

## Key Features Implemented

### Multi-Zone CO2 Monitoring
- Support for up to 3 zones per device (expandable)
- Per-zone thresholds and enabled/disabled state
- Real-time CO2 value tracking
- Trigger detection with hysteresis

### Priority Coordination
- CO2 control has priority over humidity control
- Automatic pause/resume of humidity control
- Clean handoff between control systems
- State tracking and logging

### Fan Speed Control
- Automatic fan speed adjustment based on CO2 levels
- Worst-zone algorithm for multi-zone scenarios
- Proportional control based on CO2 exceedance
- Smooth transitions to/from idle

### Zone Management
- Dynamic zone configuration
- Zone-level enable/disable
- Per-zone sensor entity mapping
- Future-ready for valve control

---

## Entities Created

### Switch Entities
- `switch.co2_control_{device_id}` - Enable/disable CO2 control

### Number Entities
- `number.co2_threshold_{device_id}` - Global CO2 threshold (400-2000 ppm)
- `number.co2_activation_hysteresis_{device_id}` - Activation hysteresis (0-500 ppm)
- `number.co2_deactivation_hysteresis_{device_id}` - Deactivation hysteresis (-500-0 ppm)

### Binary Sensor Entities
- `binary_sensor.co2_active_{device_id}` - CO2 automation active state

### Sensor Entities
- `sensor.co2_zone_status_{device_id}` - Zone status information

---

## Services Implemented

1. **`ramses_extras.enable_co2_control`** - Enable CO2 control for a device
2. **`ramses_extras.disable_co2_control`** - Disable CO2 control for a device
3. **`ramses_extras.set_zone_threshold`** - Set CO2 threshold for a specific zone
4. **`ramses_extras.trigger_co2_boost`** - Manually trigger CO2-based boost mode

---

## WebSocket API

1. **`ramses_extras/co2/get_status`** - Get current CO2 control status
2. **`ramses_extras/co2/get_zone_details`** - Get details for a specific zone
3. **`ramses_extras/co2/update_zone`** - Update zone configuration
4. **`ramses_extras/co2/get_history`** - Get CO2 history (placeholder)

---

## Priority Logic

### CO2 Active
```python
if co2_triggered:
    await humidity_manager.pause_for_co2()
    fan_speed = calculate_co2_fan_speed()
    set_fan_speed(fan_speed)
```

### CO2 Inactive
```python
if not co2_triggered:
    await humidity_manager.resume_from_co2()
    return_to_idle()
```

### Humidity Check
```python
def check_priority():
    if paused_for_co2 or co2_manager.is_active():
        return False  # Skip humidity control
    return True  # Humidity can operate
```

---

## Configuration Schema

```python
{
    "enabled": bool,
    "automation_enabled": bool,
    "default_threshold": int,  # ppm
    "activation_hysteresis": int,  # ppm
    "deactivation_hysteresis": int,  # ppm
    "zones": [
        {
            "zone_id": str,
            "zone_name": str,
            "sensor_entity": str,
            "threshold": int,
            "enabled": bool,
            "valve_entity": str | None  # Future
        }
    ],
    "max_runtime_minutes": int,
    "cooldown_period_minutes": int,
    "priority_over_humidity": bool  # Always True
}
```

---

## Remaining Work

### Phase 7: HVAC Fan Card UI (Implemented)
**Implemented in codebase:**
- [x] CO2 sensor display integrated into the HVAC fan card
- [x] CO2 control button added to the controls section
- [x] Unified TOP-RIGHT panel rendering Balance + CO2 status and area sensor summaries
- [x] Trigger highlighting (internal trigger flag surfaced via CSS class)

**Files to modify:**
- `features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js`
- `features/hvac_fan_card/www/hvac_fan_card/card-styles.js`
- `features/hvac_fan_card/www/hvac_fan_card/templates/top-section.js`
- `features/hvac_fan_card/www/hvac_fan_card/message-handlers.js`

### Phase 8: Config Flow Integration (Implemented)
**Implemented in codebase:**
- [x] CO2 feature config step is wired into the integration config flow
- [x] Feature-owned config-flow helper schemas and validation exist

**Files to modify:**
- `config_flow.py` - Add CO2 config steps

### Phase 9: Testing (Implemented)
- [x] Unit tests for CO2 automation
- [x] Tests for priority coordination with humidity control
- [x] Zone manager tests
- [x] Config validation tests
- [x] WebSocket command tests

### Phase 10: Wiki Documentation (Not Yet Implemented)
- [ ] Create CO2 Control wiki page
- [ ] Update Humidity Control wiki with balance improvements
- [ ] Update HVAC Fan Card wiki with 4-button layout
- [ ] Add screenshots and examples
- [ ] Update main README

---

## Testing Recommendations

### Unit Tests
```python
# Test zone trigger detection
test_zone_triggers_at_threshold_plus_hysteresis()
test_zone_deactivates_at_threshold_minus_hysteresis()
test_multiple_zones_worst_zone_wins()

# Test priority coordination
test_co2_pauses_humidity_control()
test_humidity_resumes_when_co2_clears()
test_humidity_skips_when_co2_active()

# Test fan speed calculation
test_fan_speed_proportional_to_exceedance()
test_fan_speed_capped_at_maximum()
test_fan_returns_to_idle_when_cleared()
```

### Integration Tests
```python
# Test full workflow
test_co2_rise_triggers_ventilation()
test_co2_fall_returns_to_idle()
test_co2_and_humidity_priority_handoff()
```

---

## Known Limitations

1. **No Valve Control**: CO2 does not directly actuate per-zone valves (zones feature owns valve actuation)
2. **History Placeholder**: CO2 history WebSocket command may be limited depending on configured storage/logging
3. **User acceptance testing**: Always validate on a live system with real CO2 sensors and a FAN device

---

## Future Enhancements

### Short-term (Next Release)
1. Implement HVAC Fan Card UI updates
2. Add config flow integration
3. Create test suite
4. Update wiki documentation

### Medium-term
1. Zone-specific valve control
2. CO2 trend analysis and graphing
3. Predictive ventilation based on patterns
4. Occupancy sensor integration

### Long-term
1. Learning algorithms for optimal thresholds
2. Multi-device coordination
3. Advanced air quality metrics
4. Integration with weather data

---

## Migration Notes

### For Existing Installations
- CO2 Control is disabled by default
- No breaking changes to existing features
- Humidity control continues to work independently
- Enable CO2 Control via config when ready

### Backward Compatibility
- All existing humidity control functionality preserved
- Priority system only activates when CO2 Control enabled
- No changes to existing entity IDs
- Services remain backward compatible

---

## Performance Considerations

### Memory Usage
- Zone managers: ~1KB per zone
- State tracking: Minimal overhead
- History: Not yet implemented

### CPU Usage
- State change listeners: Event-driven, minimal CPU
- Fan speed calculations: O(n) where n = number of zones
- Priority checks: O(1) constant time

### Network
- WebSocket commands: On-demand only
- State updates: Only on CO2 sensor changes
- No polling, fully event-driven

---

## Success Criteria

### ✅ Completed
- [x] Multi-zone CO2 monitoring implemented
- [x] Priority coordination with humidity control working
- [x] Automatic fan speed adjustment functional
- [x] Services and WebSocket API created
- [x] Documentation complete
- [x] Feature registered and loadable

### ⏳ Pending
- [x] UI integration in HVAC Fan Card
- [x] Config flow implementation
- [x] Test suite created
- [ ] Wiki documentation updated
- [ ] User acceptance testing

---

## Conclusion

The core CO2 Control feature is **functionally complete** with robust automation logic, priority coordination, and comprehensive API. The remaining work focuses on user-facing components (UI and config flow) and quality assurance (testing and documentation).

The implementation follows Ramses Extras architecture patterns and integrates cleanly with existing features. The priority system ensures CO2 control takes precedence over humidity control while maintaining smooth handoffs between systems.

**Next Steps:**
1. Implement HVAC Fan Card UI updates (Phase 7)
2. Add config flow integration (Phase 8)
3. Create test suite (Phase 9)
4. Update wiki and README (Phase 10)
