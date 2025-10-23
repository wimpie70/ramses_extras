# 🎯 Ramses Extras - Dehumidify Feature Implementation Plan

📅 **Created:** Thu Oct 23 03:45:24 PM CEST 2025
📋 **Status:** Planning Phase


## 🏗️ Architecture Strategy

### 🎮 Card (UI Layer)
- **Display Only**: Show dehumidify controls when entities exist
- **No Logic**: Don't create entities or handle automation
- **Responsive**: Hide controls when feature disabled

### 🔧 Integration (Data Layer)
- **Entity Provider**: Create switch, binary_sensor, number entities
- **Feature-Based**: Only create when "Humidity Control" enabled
- **Type-Safe**: Proper entity configurations

### 🤖 Automation (Logic Layer)
- **Smart Control**: Monitor humidity vs thresholds
- **Auto Mode**: Activate/deactivate based on conditions
- **Integration**: Work with fan speed controls

---

## 📊 Implementation Phases

### 🚀 Phase 1: Card Improvements (Current)
- [ ] Hide dehumidify controls when entities missing
- [ ] Better error handling for missing entities
- [ ] Enhanced debugging information
- [ ] Update entity availability checks

### 🔧 Phase 2: Integration Features
- [ ] Create "Humidity Control" feature flag
- [ ] Add dehumidify entity configurations
- [ ] Implement switch.dehumidify entity
- [ ] Implement binary_sensor.dehumidifying entity
- [ ] Add rel_humid_min/max number entities

### ⚙️ Phase 3: Configuration Entities
- [ ] Create input_number.dehumidify_min_humidity
- [ ] Create input_number.dehumidify_max_humidity
- [ ] Create input_boolean.dehumidify_auto_mode
- [ ] Add configuration UI in card settings

### 🤖 Phase 4: Automation Logic
- [ ] Create humidity monitoring automation
- [ ] Implement threshold comparison logic
- [ ] Add fan speed integration
- [ ] Create auto/manual mode switching

---

## 📋 Entity Structure

### 🎯 Display Entities (Card reads)
```
sensor.indoor_absolute_humidity_32_153289
sensor.outdoor_absolute_humidity_32_153289
binary_sensor.dehumidifying_32_153289
```

### ⚙️ Control Entities (Card writes)
```
switch.dehumidify_32_153289
number.rel_humid_min_32_153289
number.rel_humid_max_32_153289
```

### 🔧 Configuration Entities (User sets)
```
input_number.dehumidify_min_humidity
input_number.dehumidify_max_humidity
input_boolean.dehumidify_auto_mode
```

---

## 🎮 Card Behavior Matrix

| Feature State | Switch Visible | Status Visible | Controls Work |
|---------------|----------------|----------------|---------------|
| **Disabled** | ❌ Hidden | ❌ Hidden | ❌ N/A |
| **Enabled** | ✅ Visible | ✅ Visible | ✅ Yes |
| **Entities Missing** | ❌ Hidden | ❌ Hidden | ❌ No |

---

## ⚡ Control Flow

### Manual Mode:
1. User clicks dehumidify button → Card toggles switch
2. Automation detects switch change → Adjusts fan speed
3. Card updates status indicator → Shows current state

### Auto Mode:
1. Automation monitors humidity → Compares vs thresholds
2. Conditions met → Auto-toggles switch
3. Fan speed adjusted → Card reflects status

---

## 🔍 Debugging Strategy

### Error Scenarios:
- **Entities Missing**: Card hides controls, logs warning
- **Calculation Failed**: Shows "unavailable" (gray, italic)
- **Integration Error**: Clear error messages in logs

### Logging Levels:
- **ERROR**: Missing entities, invalid data
- **WARNING**: Configuration issues
- **DEBUG**: Normal operation details
- **INFO**: Feature state changes

---

## 📈 Success Metrics

### ✅ Working Indicators:
- Card shows/hides controls appropriately
- Switch toggles work correctly
- Status indicators update in real-time
- Auto mode respects thresholds
- Clear error messages for issues

### ❌ Failure Indicators:
- Missing controls when should be visible
- Switch doesn't respond to clicks
- Status doesn't update
- Auto mode ignores thresholds
- Unclear error messages

---

## 🚧 Current Status

### ✅ Completed:
- Absolute humidity calculation system
- Event-driven sensor updates
- Proper error handling for missing data
- Type-safe Python implementation

### 🔄 In Progress:
- [Phase 1] Card improvements for missing entities

### 📋 Next Steps:
1. Implement entity availability checks in card
2. Create integration feature configurations
3. Add automation logic framework
4. Test end-to-end functionality

---

## 📝 Notes

- **Clean Architecture**: Each component has single responsibility
- **Feature-Based**: Users opt-in to humidity control
- **Type-Safe**: Full mypy compliance
- **Maintainable**: Clear separation of concerns
- **Debuggable**: Comprehensive logging strategy

**🎯 Goal**: Robust, user-friendly dehumidify system that integrates seamlessly with ventilation controls.


## 🎯 Quick Reference - Next 3 Tasks

### 1. 🎮 Card Entity Checks
- [ ] Check if dehumidify entities exist before showing controls
- [ ] Hide switch/status when entities unavailable
- [ ] Add entity availability logging

### 2. 🔧 Integration Features
- [ ] Add 'Humidity Control' feature to const.py
- [ ] Create entity configurations for dehumidify entities
- [ ] Update device entity mapping

### 3. 📊 Card Display Logic
- [ ] Update render() to check entity availability
- [ ] Implement conditional visibility for dehumidify controls
- [ ] Add proper fallbacks when entities missing
