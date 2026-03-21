# CO2 Control - User Guide

## Quick Start

### 1. Enable the Feature

1. Go to **Settings → Devices & Services**
2. Find **Ramses Extras** integration
3. Click **Configure**
4. Enable **CO2 Control** feature
5. Click **Submit**

### 2. Configure Zones

For each zone you want to monitor:

1. **Zone Name**: Give it a descriptive name (e.g., "Living Room", "Bedroom")
2. **CO2 Sensor**: Select the CO2 sensor entity for this zone
3. **Threshold**: Set the CO2 level that triggers ventilation (default: 1000 ppm)
4. **Enabled**: Check to activate this zone

### 3. Adjust Settings

- **Global Threshold**: Default CO2 level for all zones
- **Activation Hysteresis**: How much above threshold to activate (+100 ppm)
- **Deactivation Hysteresis**: How much below threshold to deactivate (-100 ppm)

### 4. Enable Automation

Toggle the **CO2 Control** switch entity to start automatic ventilation control.

## Understanding CO2 Levels

### Typical CO2 Levels

- **400-600 ppm**: Outdoor air, excellent
- **600-800 ppm**: Indoor air, good
- **800-1000 ppm**: Indoor air, acceptable
- **1000-1500 ppm**: Stuffy air, ventilation recommended
- **1500-2000 ppm**: Poor air quality, ventilation needed
- **2000+ ppm**: Very poor air quality, immediate ventilation required

### Recommended Thresholds

- **Home Office**: 800-1000 ppm
- **Living Room**: 1000-1200 ppm
- **Bedroom**: 800-1000 ppm (lower for better sleep)
- **Kitchen**: 1200-1500 ppm (cooking generates CO2)

## How It Works

### Zone Monitoring

The system continuously monitors CO2 levels in all configured zones:

1. **Normal Operation**: CO2 below threshold → Fan at idle speed
2. **Zone Triggered**: CO2 exceeds threshold + hysteresis → Fan speed increases
3. **Multiple Zones**: Worst zone determines fan speed
4. **Deactivation**: CO2 drops below threshold + deactivation hysteresis → Fan returns to idle

### Priority System

When both CO2 Control and Humidity Control are enabled:

- **CO2 has priority**: If CO2 is high, CO2 control takes over
- **Humidity paused**: Humidity control pauses while CO2 is active
- **Automatic handoff**: When CO2 normalizes, humidity control resumes

### Hysteresis Explained

Hysteresis prevents the fan from constantly switching on/off:

**Example:**
- Threshold: 1000 ppm
- Activation hysteresis: +100 ppm
- Deactivation hysteresis: -100 ppm

**Behavior:**
- Fan activates at: 1100 ppm (1000 + 100)
- Fan deactivates at: 900 ppm (1000 - 100)
- Between 900-1100 ppm: Fan maintains current state

This creates a "dead zone" that prevents oscillation.

## Dashboard Integration

### Lovelace Card Example

```yaml
type: entities
title: CO2 Control
entities:
  - entity: switch.co2_control_32_153289
    name: CO2 Control
  - entity: binary_sensor.co2_active_32_153289
    name: CO2 Active
  - entity: number.co2_threshold_32_153289
    name: Threshold
  - entity: sensor.living_room_co2
    name: Living Room CO2
  - entity: sensor.bedroom_co2
    name: Bedroom CO2
```

### Gauge Card for CO2 Levels

```yaml
type: gauge
entity: sensor.living_room_co2
name: Living Room CO2
unit: ppm
min: 400
max: 2000
severity:
  green: 0
  yellow: 800
  red: 1200
```

### History Graph

```yaml
type: history-graph
title: CO2 Levels
entities:
  - entity: sensor.living_room_co2
  - entity: sensor.bedroom_co2
  - entity: sensor.office_co2
hours_to_show: 24
```

## Common Scenarios

### Scenario 1: Office Work from Home

**Setup:**
- Zone: "Office"
- Threshold: 800 ppm
- Sensor: `sensor.office_co2`

**Behavior:**
- During work hours, CO2 rises from breathing
- At 900 ppm (800 + 100 hysteresis), fan activates
- Fan increases ventilation
- CO2 drops to 700 ppm
- Fan returns to idle

### Scenario 2: Dinner Party

**Setup:**
- Zone: "Living Room"
- Threshold: 1000 ppm
- Multiple people in room

**Behavior:**
- CO2 rises quickly with multiple people
- At 1100 ppm, fan activates
- Fan speed increases proportionally to CO2 level
- At 1500 ppm, fan at maximum speed
- After guests leave, CO2 drops
- At 900 ppm, fan returns to idle

### Scenario 3: Sleeping

**Setup:**
- Zone: "Bedroom"
- Threshold: 800 ppm (lower for better sleep)
- Automation to disable at night if too noisy

**Behavior:**
- During sleep, CO2 rises slowly
- At 900 ppm, fan activates gently
- Maintains good air quality
- Optional: Disable if noise is an issue

## Troubleshooting

### Problem: CO2 Control Not Working

**Check:**
1. Is `switch.co2_control_{device_id}` turned ON?
2. Are zones configured and enabled?
3. Are CO2 sensor entities available (not "unavailable" or "unknown")?
4. Is threshold set correctly?

**Solution:**
- Turn on CO2 control switch
- Verify sensor entities in Developer Tools → States
- Check threshold is reasonable (800-1200 ppm)

### Problem: Fan Not Responding

**Check:**
1. Is ramses_cc integration working?
2. Can you manually control fan speed?
3. Are there errors in logs?

**Solution:**
- Check ramses_cc integration status
- Test manual fan control
- Review logs: Settings → System → Logs

### Problem: Fan Switching Too Often

**Cause:** Hysteresis too small

**Solution:**
- Increase activation hysteresis (e.g., +150 ppm)
- Increase deactivation hysteresis magnitude (e.g., -150 ppm)
- This creates a larger "dead zone"

### Problem: Fan Not Activating Soon Enough

**Cause:** Threshold too high or hysteresis too large

**Solution:**
- Lower threshold (e.g., from 1000 to 800 ppm)
- Reduce activation hysteresis (e.g., from +100 to +50 ppm)

### Problem: Zone Not Triggering

**Check:**
1. Is zone enabled in configuration?
2. Is sensor entity correct?
3. Is CO2 value high enough?

**Solution:**
- Enable zone in config
- Verify sensor entity ID
- Check current CO2 value vs threshold + hysteresis

## Advanced Configuration

### Per-Zone Thresholds

Each zone can have its own threshold via service call:

```yaml
service: ramses_extras.set_zone_threshold
data:
  device_id: "32:153289"
  zone_id: "zone_1"
  threshold: 800  # Lower for bedroom
```

### Automation-Based Control

Disable CO2 control during specific times:

```yaml
automation:
  - alias: "Disable CO2 at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.co2_control_32_153289
```

### Boost Mode

Manually trigger boost when needed:

```yaml
service: ramses_extras.trigger_co2_boost
data:
  device_id: "32:153289"
  duration_minutes: 30
```

## Best Practices

### 1. Start Conservative

- Begin with threshold at 1000 ppm
- Use default hysteresis values
- Monitor for a few days
- Adjust based on comfort and air quality

### 2. Zone Placement

- Place CO2 sensors at breathing height (1-1.5m)
- Avoid direct airflow from vents
- Keep away from windows and doors
- Central location in room is best

### 3. Calibration

- Most CO2 sensors need periodic calibration
- Expose to outdoor air (400 ppm) for calibration
- Follow sensor manufacturer's instructions

### 4. Maintenance

- Check sensor battery/power regularly
- Clean sensor according to manufacturer
- Verify sensor readings periodically
- Update thresholds seasonally if needed

### 5. Integration with Other Systems

- Use with humidity control for complete air quality
- Integrate with occupancy sensors for efficiency
- Combine with window/door sensors for smart ventilation
- Link to air quality dashboard for monitoring

## FAQ

**Q: Can I use CO2 control without humidity control?**
A: Yes, CO2 control works independently.

**Q: What happens if both CO2 and humidity trigger?**
A: CO2 takes priority. Humidity control pauses until CO2 normalizes.

**Q: Can I have different thresholds for different zones?**
A: Yes, each zone can have its own threshold.

**Q: How many zones can I configure?**
A: Up to 3 zones per device currently (expandable in future).

**Q: Does this work with any CO2 sensor?**
A: Yes, any Home Assistant CO2 sensor entity works.

**Q: Can I disable specific zones temporarily?**
A: Yes, use the zone configuration to enable/disable zones.

**Q: Will this increase my energy usage?**
A: Slightly, but improved air quality often improves comfort and health.

**Q: Can I see historical CO2 data?**
A: Yes, use Home Assistant's history feature or create custom graphs.

## Support

For issues or questions:
- Check logs: Settings → System → Logs
- Review [GitHub Issues](https://github.com/wimpie70/ramses_extras/issues)
- Consult [Wiki](https://github.com/wimpie70/ramses_extras/wiki)
