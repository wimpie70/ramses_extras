# CO2 Control Feature

## Overview

The CO2 Control feature provides CO2-based ventilation control for HVAC fan systems. It monitors multiple CO2 sensors across different zones and automatically adjusts fan speed when CO2 levels exceed configured thresholds.

**Key Features:**
- Multi-zone CO2 monitoring
- Automatic fan speed adjustment based on CO2 levels
- Priority over humidity control (CO2 takes precedence)
- Configurable thresholds per zone
- Hysteresis support to prevent oscillation
- Zone-ready architecture for future valve control

## Architecture

### Priority System

CO2 Control has **higher priority** than Humidity Control:

```
CO2 Triggered → Fan Speed Increases (Humidity Control Paused)
CO2 Normal → Humidity Control Resumes (if enabled)
```

### Zone Management

Each device can have multiple zones, each with:
- Zone ID and name
- CO2 sensor entity
- Threshold (ppm)
- Enabled/disabled state
- Future: Zone-specific valve control

## Configuration

### Enable CO2 Control

1. Navigate to **Settings → Devices & Services → Ramses Extras**
2. Click **Configure**
3. Enable **CO2 Control** feature
4. Configure zones and thresholds

### Zone Configuration

For each zone, configure:
- **Zone Name**: Descriptive name (e.g., "Living Room")
- **CO2 Sensor**: Entity ID of CO2 sensor
- **Threshold**: CO2 level in ppm (default: 1000 ppm)
- **Enabled**: Whether zone is active

### Thresholds and Hysteresis

- **Threshold**: Base CO2 level to trigger ventilation
- **Activation Hysteresis**: Additional ppm above threshold to activate (default: +100 ppm)
- **Deactivation Hysteresis**: ppm below threshold to deactivate (default: -100 ppm)

**Example:**
- Threshold: 1000 ppm
- Activation: 1100 ppm (1000 + 100)
- Deactivation: 900 ppm (1000 - 100)

## Entities

### Switch Entities

- `switch.co2_control_{device_id}` - Enable/disable CO2 control

### Number Entities

- `number.co2_threshold_{device_id}` - Global CO2 threshold (400-2000 ppm)
- `number.co2_activation_hysteresis_{device_id}` - Activation hysteresis (0-500 ppm)
- `number.co2_deactivation_hysteresis_{device_id}` - Deactivation hysteresis (-500-0 ppm)

### Binary Sensor Entities

- `binary_sensor.co2_active_{device_id}` - CO2 control active state

### Sensor Entities

- `sensor.co2_zone_status_{device_id}` - Zone status information

## Services

### `ramses_extras.enable_co2_control`

Enable CO2 control for a device.

```yaml
service: ramses_extras.enable_co2_control
data:
  device_id: "32:153289"
```

### `ramses_extras.disable_co2_control`

Disable CO2 control for a device.

```yaml
service: ramses_extras.disable_co2_control
data:
  device_id: "32:153289"
```

### `ramses_extras.set_zone_threshold`

Set CO2 threshold for a specific zone.

```yaml
service: ramses_extras.set_zone_threshold
data:
  device_id: "32:153289"
  zone_id: "zone_1"
  threshold: 1200
```

### `ramses_extras.trigger_co2_boost`

Manually trigger CO2-based boost mode.

```yaml
service: ramses_extras.trigger_co2_boost
data:
  device_id: "32:153289"
  duration_minutes: 30
```

## WebSocket API

### Get CO2 Status

```javascript
{
  "type": "ramses_extras/co2/get_status",
  "device_id": "32:153289"
}
```

**Response:**
```javascript
{
  "enabled": true,
  "automation_enabled": true,
  "active": false,
  "activation_time": null,
  "last_fan_speed": 1,
  "zones": {
    "32:153289": {
      "zones": [...],
      "active_zone_count": 0,
      "total_zone_count": 3
    }
  }
}
```

### Get Zone Details

```javascript
{
  "type": "ramses_extras/co2/get_zone_details",
  "device_id": "32:153289",
  "zone_id": "zone_1"
}
```

### Update Zone Configuration

```javascript
{
  "type": "ramses_extras/co2/update_zone",
  "device_id": "32:153289",
  "zone_id": "zone_1",
  "updates": {
    "threshold": 1200,
    "enabled": true
  }
}
```

## Automation Examples

### Notify on High CO2

```yaml
automation:
  - alias: "Notify High CO2"
    trigger:
      - platform: state
        entity_id: binary_sensor.co2_active_32_153289
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "High CO2 detected - ventilation increased"
```

### Disable CO2 Control at Night

```yaml
automation:
  - alias: "Disable CO2 at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: ramses_extras.disable_co2_control
        data:
          device_id: "32:153289"
```

### Enable CO2 Control in Morning

```yaml
automation:
  - alias: "Enable CO2 in Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: ramses_extras.enable_co2_control
        data:
          device_id: "32:153289"
```

## Fan Speed Calculation

Fan speed is calculated based on the worst (highest) zone:

1. **No zones triggered**: Fan at idle speed (1)
2. **Zone triggered**: Fan speed increases based on CO2 exceedance
3. **Multiple zones**: Worst zone determines fan speed

**Formula:**
```
exceedance = current_co2 - threshold
exceedance_ratio = min(exceedance / 500, 1.0)
fan_speed = base_speed + (max_speed - base_speed) * exceedance_ratio
```

**Example:**
- Threshold: 1000 ppm
- Current CO2: 1250 ppm
- Exceedance: 250 ppm
- Ratio: 250/500 = 0.5
- Fan speed: 2 + (5-2) * 0.5 = 3.5 → 4

## Integration with Humidity Control

When both CO2 Control and Humidity Control are enabled:

1. **CO2 Active**: CO2 control sets fan speed, humidity control paused
2. **CO2 Inactive**: Humidity control resumes normal operation
3. **Priority**: CO2 always takes precedence

## Troubleshooting

### CO2 Control Not Activating

1. Check `switch.co2_control_{device_id}` is ON
2. Verify CO2 sensor entities are available
3. Check threshold settings
4. Review logs for errors

### Fan Speed Not Changing

1. Verify ramses_cc integration is working
2. Check device communication
3. Review automation logs
4. Ensure CO2 levels exceed activation threshold

### Zone Not Triggering

1. Check zone is enabled
2. Verify sensor entity is correct
3. Check CO2 value exceeds threshold + hysteresis
4. Review zone manager logs

## Future Enhancements

- **Zone-specific valves**: Per-zone ventilation control
- **CO2 trend analysis**: Predictive ventilation
- **Learning algorithms**: Automatic threshold optimization
- **Occupancy integration**: Adjust based on room occupancy
- **Multi-device coordination**: Coordinate multiple HVAC fans

## See Also

- [Humidity Control](../humidity_control/README.md)
- [HVAC Fan Card](../hvac_fan_card/README.md)
- [Sensor Control](../sensor_control/README.md)
