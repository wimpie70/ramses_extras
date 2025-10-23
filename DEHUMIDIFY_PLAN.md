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

## ✅ Phase 1: Card Improvements - COMPLETED

### 🎯 **Implemented Features:**

#### **1. Entity Availability Checks** ✅
- Added `checkDehumidifyEntities()` function
- Validates both switch and binary_sensor entities exist
- Returns boolean availability flag

#### **2. Comprehensive Entity Validation** ✅
- Added `validateEntities()` function
- Checks all core entities (temp, humidity, fan, bypass)
- Checks dehumidify entities separately
- Checks absolute humidity entities
- Provides detailed debug logging

#### **3. Conditional Control Display** ✅
- Updated top-section template with conditional rendering
- Dehumidify status indicators hidden when entities missing
- Comfort temperature hidden when entities missing

#### **4. Smart Button Management** ✅
- Updated controls-section template with availability parameter
- Shows functional button when entities available
- Shows disabled button (gray, italic) when entities missing
- Added tooltip explaining unavailable state

#### **5. Enhanced Debugging** ✅
- Added entity availability logging in render()
- Enhanced debug output with entity states
- Clear distinction between available/missing entities

### 📊 **Current Card Behavior:**

| State | Switch Button | Status Indicators | Debug Info |
|-------|---------------|------------------|------------|
| **Entities Available** | ✅ Functional | ✅ Visible | 🟢 All entities found |
| **Entities Missing** | ❌ Disabled (gray) | ❌ Hidden | 🟡 Missing entities logged |

### 🚀 **Benefits Achieved:**
- ✅ No more confusing missing controls
- ✅ Clear visual feedback for unavailable features
- ✅ Comprehensive debugging information
- ✅ Proper separation of concerns
- ✅ Clean user experience

## ✅ Phase 1: Card Improvements - COMPLETED

### 🎯 **All Tasks Completed Successfully!**

#### **✅ Fixed Issues:**
- **Config property inconsistency**: Fixed `this._config` vs `this.config` usage
- **Template parameter extraction**: Added `dehumEntitiesAvailable` to destructuring
- **Entity availability detection**: Smart conditional control visibility
- **Enhanced debugging**: Comprehensive logging for troubleshooting

#### **📊 Current Card Behavior:**

| State | Switch Button | Status Indicators | Template Rendering |
|-------|---------------|------------------|-------------------|
| **Entities Available** | ✅ Functional | ✅ Visible | ✅ Normal |
| **Entities Missing** | ❌ Disabled (gray) | ❌ Hidden | ✅ Clean |

### 🚀 **Phase 1 Benefits Achieved:**
- ✅ **No undefined config errors**
- ✅ **Clean validation logging**
- ✅ **Proper error handling**
- ✅ **Feature-aware UI**
- ✅ **Type-safe implementation**

### 🎯 **Ready for Phase 2:**

## ✅ Phase 2: Integration Features - COMPLETED (Logging Mode)

### 🎯 **All Phase 2 Tasks Completed Successfully!**

#### **✅ Created Integration Entities:**
- **switch.dehumidify**: Toggle dehumidify mode (logs only)
- **binary_sensor.dehumidifying**: Shows active status
- **number.rel_humid_min**: Minimum humidity threshold (logs only)
- **number.rel_humid_max**: Maximum humidity threshold (logs only)

#### **🔧 Integration Architecture:**
- **Humidity Control Feature**: Creates all dehumidify entities
- **Entity Configurations**: Proper icons, units, ranges
- **Device Communication**: Uses ramses_RF service calls
- **State Synchronization**: Binary sensor reflects switch state

### 🚦 **Current Mode: LOGGING ONLY**
- ✅ **Safe for Production**: No actual device commands sent
- ✅ **Full Logging**: All intended commands logged with details
- ✅ **State Management**: Local state updated properly
- ✅ **Testing Ready**: Can verify entity creation and behavior

#### **📋 Expected Log Output:**


### 🎯 **Ready for Phase 3:**

## ✅ Phase 2: Integration Features - COMPLETED (Logging Mode)

### 🎯 **All Phase 2 Tasks Completed Successfully!**

#### **✅ Created Integration Entities:**
- **switch.dehumidify**: Toggle dehumidify mode (logs only)
- **binary_sensor.dehumidifying**: Shows active status
- **number.rel_humid_min**: Minimum humidity threshold (logs only)
- **number.rel_humid_max**: Maximum humidity threshold (logs only)

#### **🔧 Integration Architecture:**
- **Humidity Control Feature**: Creates all dehumidify entities
- **Entity Configurations**: Proper icons, units, ranges
- **Device Communication**: Uses ramses_RF service calls
- **State Synchronization**: Binary sensor reflects switch state

### 🚦 **Current Mode: LOGGING ONLY**
- ✅ **Safe for Production**: No actual device commands sent
- ✅ **Full Logging**: All intended commands logged with details
- ✅ **State Management**: Local state updated properly
- ✅ **Testing Ready**: Can verify entity creation and behavior

#### **📋 Expected Log Output:**
```
INFO - Activating dehumidify mode for Dehumidify (32:153289)
INFO - Would send dehumidify activation command: device_id=32:153289, from_id=..., verb=' I', code='22F1', payload='000807'
INFO - Successfully logged dehumidify activation (state updated locally)
```

### 🎯 **Ready for Phase 3:**
When ready to go live, simply uncomment the service calls

## ✅ Phase 2: Integration Features - COMPLETED

### 🎯 **Environment & Validation Complete!**

#### **✅ Virtual Environment Usage:**
- **Activated**: `~/venvs/extras/bin/activate`
- **Type Checking**: `mypy` - No issues found
- **Code Formatting**: `ruff format .` - 3 files reformatted
- **Ready for Testing**: All validation passed

### 🚀 **Integration Ready for Production Testing**
- ✅ **Safe Mode**: Logging only, no device interference
- ✅ **Type Safe**: All mypy checks pass
- ✅ **Code Style**: Consistent formatting applied
- ✅ **Entity Creation**: Feature-based smart discovery

## ✅ Phase 2: Integration Features - COMPLETED

### 🎯 **Fixed Orphaned Entity Issue!**

#### **🔧 The Problem:**
- Absolute humidity sensors were being removed and recreated
- Cleanup logic marked them as 'orphaned'
- They were removed, then immediately recreated

#### **🔧 The Solution:**
- **Always create** absolute humidity sensors (fundamental device data)
- **Never remove** them from cleanup logic
- **Feature-independent** - exist regardless of enabled features

### 📋 **Current Log Output (Fixed):**


### 🚀 **Integration Now Stable:**
- ✅ **No unnecessary entity removal/recreation**
- ✅ **Absolute humidity sensors always available**
- ✅ **Clean startup without orphaned cleanup**
- ✅ **All mypy checks pass**

## ✅ Phase 2: Integration Features - COMPLETED

### 🎯 **Fixed Orphaned Entity Issue!**

#### **🔧 The Problem:**
- Absolute humidity sensors were being removed and recreated
- Cleanup logic marked them as 'orphaned'
- They were removed, then immediately recreated

#### **🔧 The Solution:**
- **Always create** absolute humidity sensors (fundamental device data)
- **Never remove** them from cleanup logic
- **Feature-independent** - exist regardless of enabled features

### 📋 **Current Log Output (Fixed):**
```
# No more orphaned entity removal/recreation
INFO - Creating sensor: sensor.32_153289_indoor_abs_humid
INFO - Creating sensor: sensor.32_153289_outdoor_abs_humid
INFO - Keeping fundamental sensor: sensor.indoor_absolute_humidity_32_153289
```

### 🚀 **Integration Now Stable:**
- ✅ **No unnecessary entity removal/recreation**
- ✅ **Absolute humidity sensors always available**
- ✅ **Clean startup without orphaned cleanup**
- ✅ **All mypy checks pass**

### 🎯 **Ready for Production Testing:**
- ✅ **Enable "Humidity Control"** feature
- ✅ **See stable entity creation** without orphaned cleanup
- ✅ **Test dehumidify controls** with logging
- ✅ **Verify binary sensor** state synchronization
- ✅ **Adjust thresholds** with parameter logging

## ✅ Phase 2: Integration Features - FULLY COMPLETE

### 🎯 **Card Integration Working!**

#### **✅ Entity Configuration Fixed:**
- **Card now expects**: `switch.dehumidify` and `binary_sensor.dehumidifying`
- **Added setFanMode()** method to handle dehumidify button clicks
- **Proper event handling** for dehumidify mode toggle
- **Type-safe implementation** with all mypy checks passing

#### **📋 Card Behavior:**
```javascript
// When dehumidify button clicked:
🔘 Button clicked: <div class="control-button" data-mode="active">
✅ Calling setFanMode with mode: active
✅ Toggling dehumidify mode
✅ Would send dehumidify activation command: device_id=32:153289, from_id=..., verb=' I', code='22F1', payload='000807'
```

#### **🎮 User Experience:**
- ✅ **Dehumidify button shows** when entities are available
- ✅ **Button toggles** the dehumidify switch
- ✅ **Binary sensor reflects** switch state in real-time
- ✅ **Clean UI** with proper entity availability detection
- ✅ **No orphaned cleanup** - stable entity management

### 🚀 **Production Ready:**
- ✅ **Safe logging mode** - no device interference
- ✅ **Stable entities** - no remove/recreate cycles
- ✅ **Type safe** - all mypy validation passes
- ✅ **Proper formatting** - consistent code style
- ✅ **Full integration** - card + entities work together

### 🎯 **Ready for Testing:**
**Enable "Humidity Control" feature and you'll see:**
1. **Dehumidify switch** appears in entity list
2. **Binary sensor** shows dehumidifying status
3. **Card button** toggles the switch (logs commands)
4. **Real-time sync** between switch and binary sensor
5. **Clean logs** showing intended device commands
