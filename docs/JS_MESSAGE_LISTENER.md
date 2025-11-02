# JavaScript 31DA Message Listener Implementation

## Overview

Implemented a reusable JavaScript-based message listener system for handling ramses_cc 31DA messages in real-time, providing immediate HVAC state updates to the user interface.

## Architecture

### 1. Configuration-Driven Setup (const.py)
```python
"hvac_fan_card": {
    "handle_codes": ["31DA", "10D0"],
    "callback_prefix": "handle_",
    # ... existing config
}
```

### 2. Global Message Helper
- **Singleton Pattern**: Single instance per page for efficient message routing
- **Global Event Listener**: Listens to `ramses_cc_message` events
- **Auto-Discovery**: Calls `handle_31DA()`, `handle_10D0()` methods on cards
- **Device Filtering**: Routes messages to correct cards based on device_id

### 3. Message Handlers
- **Separated Logic**: Card-specific handlers in dedicated file
- **Data Processing**: Extract and normalize 31DA data
- **Utility Functions**: Format temperature, humidity, fan speeds
- **Fallback Compatibility**: Works with existing entity-based data

### 4. Card Integration
- **Auto-Registration**: Cards register for their configured message codes
- **Real-time Updates**: Immediate UI updates when messages received
- **Graceful Degradation**: Falls back to entity data when 31DA unavailable

## File Structure
```
www/
├── helpers/
│   └── ramses-message-helper.js      # Global singleton helper
└── hvac_fan_card/
    ├── hvac-fan-card.js             # Main card with integration
    └── message-handlers.js          # Card-specific message handlers
```

## Data Flow

```
31DA Message → RamsesMessageHelper → HvacFanCardHandlers.handle_31DA() → Card Update
     ↓                ↓                          ↓                    ↓
Real-time    Route to correct      Extract/format      Immediate UI
HVAC Data       card               data            re-render
```

## Key Features

### Real-time Processing
- **Zero Polling Delay**: Messages processed as they arrive
- **Batch Updates**: Multiple entities updated per 31DA message
- **Device-Specific**: Only relevant cards receive messages

### Performance Optimized
- **Singleton Architecture**: Single global listener for all cards
- **Efficient Filtering**: Only checks registered device/message combinations
- **Memory Management**: Automatic cleanup on card removal

### Backward Compatible
- **Entity Fallback**: Uses existing entity data when 31DA unavailable
- **Progressive Enhancement**: Works with or without 31DA support
- **No Breaking Changes**: Existing functionality preserved

## Usage Examples

### For HVAC Fan Card
```javascript
// Auto-registered in connectedCallback()
 RamsesMessageHelper.instance.addListener(this, "32:153289", ["31DA", "10D0"]);

// Called automatically by helper
handle_31DA(messageData) {
    const hvacData = HvacFanCardHandlers.handle_31DA(this, messageData);
    this.updateFrom31DA(hvacData);
}
```

### For Other Cards
```javascript
// Simple registration for different message codes
const helper = RamsesMessageHelper.instance;
helper.addListener(this, deviceId, ["31DA", "30C9", "22F1"]);

// Implement handler methods
handle_31DA(messageData) { /* process message */ }
handle_30C9(messageData) { /* process message */ }
handle_22F1(messageData) { /* process message */ }
```

## Message Data Structure

### 31DA Message Processing
```javascript
// Input: ramses_cc_message event
{
    event_type: "ramses_cc_message",
    data: {
        code: "31DA",
        payload: {
            hvac_id: "00",
            indoor_temp: 14.1,
            outdoor_temp: 11.74,
            indoor_humidity: 0.66,
            exhaust_fan_speed: 0.1,
            // ... more fields
        }
    }
}

// Output: Normalized data for card
{
    indoor_temp: 14.1,
    outdoor_temp: 11.74,
    indoor_humidity: 66,    // Converted from 0-1 to percentage
    fan_info: "speed 1, low",
    source: "31DA_message"
}
```

## Benefits

### Response Time
- **Before**: Entity polling every 30+ seconds
- **After**: Real-time updates via 31DA messages
- **Improvement**: From seconds to milliseconds latency

### Data Freshness
- **Before**: Potential stale data between polls
- **After**: Immediate updates on state changes
- **Consistency**: All related parameters update simultaneously

### Resource Efficiency
- **Reduced Overhead**: No polling API calls
- **Smart Routing**: Messages only to relevant cards
- **Memory Efficient**: Singleton pattern minimizes overhead

## Monitoring & Debugging

### Debug Information
```javascript
// Check registered listeners
RamsesMessageHelper.instance.debugListeners();

// Get listener info
const info = RamsesMessageHelper.instance.getListenerInfo();
console.log('Active listeners:', info);
```

### Logging
- **Message Reception**: When 31DA messages are processed
- **Card Updates**: Which cards receive real-time data
- **Routing**: Message routing decisions and results

## Extensibility

### Adding New Message Types
1. **Update const.py**: Add new codes to `handle_codes`
2. **Implement Handler**: Add `handle_NEWCODE()` method to card
3. **Process Data**: Add extraction logic to handlers file
4. **Auto-Registration**: Cards automatically register for new codes

### Adding New Cards
1. **Import Helper**: `import { RamsesMessageHelper } from '/local/ramses_extras/helpers/ramses-message-helper.js'`
2. **Register**: `helper.addListener(this, deviceId, ["31DA", "10D0"])`
3. **Implement Handlers**: Add `handle_31DA()`, `handle_10D0()` methods
4. **Process Messages**: Use handlers class or custom logic

## Conclusion

The JavaScript-based 31DA message listener provides:
- **Real-time Updates**: Immediate HVAC state changes
- **Reusable Architecture**: Easy to extend to other cards
- **Performance Optimized**: Efficient singleton pattern
- **Backward Compatible**: Works with existing entity systems

This implementation significantly improves user experience by providing immediate feedback on HVAC system changes while maintaining full compatibility with the existing architecture.
