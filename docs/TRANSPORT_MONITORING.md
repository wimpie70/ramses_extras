# Transport Monitoring System

## Overview

The transport monitoring system provides per-device connectivity tracking for HVAC fan devices in the ramses_extras integration. It uses a command-based liveness detection model to accurately determine when devices are online or offline.

## Architecture

### Command-Based Liveness Detection

The system uses a **command-based liveness model** rather than passive monitoring:

1. **Timer Start**: When a command is sent to a device, a 61-second timeout timer starts
2. **Reply Detection**: Any message FROM the device cancels the timer and marks it online
3. **Timeout**: If no message is received within 61 seconds, the device is marked offline
4. **No Timer Reset**: Subsequent commands do not restart the timer - only one timer per device

This approach ensures:
- Fast offline detection (within 61 seconds of first command after device goes offline)
- Accurate per-device state tracking
- No false positives from other devices' messages
- Efficient resource usage (timers only for monitored devices)

### Components

#### TransportMonitor (`framework/helpers/transport_monitor.py`)

Core monitoring class that:
- Tracks per-device online/offline state
- Manages timeout timers for each device
- Listens to `ramses_cc_message` events for device replies
- Notifies registered callbacks on state changes
- Provides singleton instance via `get_transport_monitor()`

**Key Methods:**
- `notify_command_sent(device_id)` - Start timer when command sent
- `update_device_message_received(device_id)` - Cancel timer on device reply
- `register_callback(name, callback, device_id)` - Register for state change notifications
- `is_device_available(device_id)` - Check current device state

#### TransportStateBinarySensor (`features/default/platforms/binary_sensor.py`)

Binary sensor entity that:
- Displays device connectivity status in Home Assistant
- Entity ID format: `binary_sensor.transport_state_{device_id}`
- Device class: `connectivity`
- Entity category: `diagnostic`
- Automatically created for all HVAC fan devices

#### Command Integration (`framework/helpers/ramses_commands.py`)

The `send_command` method notifies the transport monitor when commands are sent:

```python
# After sending command
transport_monitor.notify_command_sent(device_id_formatted)
```

## Configuration

### Automatic Setup

Transport monitoring is automatically enabled for all HVAC fan devices. No configuration required.

### Timeout Duration

The default timeout is **61 seconds**, chosen because:
- Ramses RF polls devices approximately every 60 seconds
- Provides 1 second buffer for network/processing delays
- Fast enough to detect offline devices quickly
- Long enough to avoid false positives

## Usage

### Checking Device Status

**In Python:**
```python
from custom_components.ramses_extras.framework.helpers.transport_monitor import get_transport_monitor

monitor = get_transport_monitor()
is_online = monitor.is_device_available("32:153289")
```

**In Home Assistant:**
- Check entity: `binary_sensor.transport_state_32_153289`
- State: `on` = online, `off` = offline

### Registering Callbacks

```python
def on_state_change(available: bool):
    if available:
        print("Device came online")
    else:
        print("Device went offline")

monitor = get_transport_monitor()
monitor.register_callback("my_callback", on_state_change, "32:153289")
```

### HVAC Fan Card Integration

The HVAC fan card automatically displays the transport state:
- Green indicator when online
- Red indicator when offline
- Automatically updates in real-time

### Automation Protection

**All automations check device transport availability before processing:**

When a device is offline, automations automatically skip processing to prevent:
- Sending commands to unreachable devices
- Wasting resources on failed operations
- Queue buildup from repeated failures
- Unnecessary error logging

**Affected Automations:**
- **Humidity Control** - Skips dehumidify/spike logic when fan offline
- **CO2 Control** - Skips ventilation logic when fan offline
- **Future automations** - All inherit this protection via `BaseAutomation`

**Implementation:**
```python
# In automation _process_automation_logic()
if not self.is_device_transport_available(device_id):
    _LOGGER.debug("Transport unavailable - skipping logic for %s", device_id)
    return
```

**Behavior:**
- Automation pauses for offline devices
- Resumes automatically when device comes back online
- No manual intervention required
- Logged at DEBUG level to avoid noise

## Implementation Details

### Thread Safety

The system handles thread safety correctly:
- Event handlers run in `SyncWorker` threads
- Uses `call_soon_threadsafe` to schedule async tasks
- Proper asyncio task management

### State Management

**Device States:**
- `True` (online) - Device has replied within timeout
- `False` (offline) - No reply within 61s of command
- Default: `True` (assume online until proven otherwise)

**Timer Management:**
- One timer per device maximum
- Timers stored in `_device_timeout_tasks` dict
- Cancelled when device replies or new timer needed
- Cleaned up on monitoring stop

### Event Flow

```
1. User sends command via HVAC fan card
   ↓
2. ramses_commands.send_command() called
   ↓
3. transport_monitor.notify_command_sent() starts 61s timer
   ↓
4a. Device replies within 61s:
    - Event handler detects reply
    - Timer cancelled
    - Device marked online
    - Callbacks notified

4b. No reply within 61s:
    - Timer expires
    - Device marked offline
    - Callbacks notified
```

### Message Filtering

The event handler only processes messages FROM devices being monitored:

```python
# Check if we have a timer running for this device
if normalized_src in self._device_timeout_tasks:
    # Process this message
    self.update_device_message_received(src)
```

This prevents:
- Processing messages from unmonitored devices
- Wasting resources on irrelevant messages
- Cross-device state contamination

## Testing

### Unit Tests

Located in `tests/framework/test_transport_monitor.py`:

- `test_notify_command_sent` - Timer creation
- `test_notify_command_sent_does_not_restart_timer` - No timer reset
- `test_device_timeout_marks_offline` - Timeout handling
- `test_update_device_message_received_cancels_timeout` - Reply handling
- `test_device_id_normalization` - ID format handling
- `test_callback_notification` - Callback invocation

### Coverage

Current coverage: **73%**

Uncovered areas:
- Global transport state monitoring (legacy feature)
- Some error handling paths
- Edge cases in event listener setup

## Troubleshooting

### Device Shows Offline But Is Working

**Possible causes:**
1. Device doesn't reply to commands (check logs for `RP` messages)
2. Ramses RF not polling device (check for `RQ` messages)
3. Timer expired before first reply

**Solution:** Check Home Assistant logs for message flow

### Device Takes Too Long to Show Online

**Expected behavior:** Device marked online within 1 second of first reply after command sent

**If slower:**
1. Check if device is actually replying (look for messages FROM device)
2. Verify event handler is running (look for "Message FROM" debug logs)
3. Check for thread safety warnings

### False Offline Detections

**Should not happen** with current implementation because:
- Timer only starts when command sent
- Any reply from device cancels timer
- Timer doesn't reset on subsequent commands

**If occurring:** File bug report with logs

## Performance

### Resource Usage

- **Memory**: ~1KB per monitored device (timer + state)
- **CPU**: Minimal (event-driven, no polling)
- **Network**: No additional traffic (uses existing Ramses RF messages)

### Scalability

Tested with:
- 10+ concurrent devices
- 100+ messages per minute
- No performance degradation observed

## Future Enhancements

Potential improvements:
1. Configurable timeout duration per device
2. Exponential backoff for repeated offline detections
3. Historical connectivity statistics
4. Integration with Home Assistant availability system
5. Proactive health checks for critical devices

## Related Files

- `framework/helpers/transport_monitor.py` - Core monitoring logic
- `features/default/platforms/binary_sensor.py` - Binary sensor entity
- `framework/helpers/ramses_commands.py` - Command integration
- `tests/framework/test_transport_monitor.py` - Unit tests
- `features/hvac_fan_card/www/hvac_fan_card/hvac-fan-card.js` - Frontend display

## References

- [Ramses RF Documentation](https://github.com/ramses-rf/ramses_rf)
- [Home Assistant Binary Sensor](https://www.home-assistant.io/integrations/binary_sensor/)
- [Asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
