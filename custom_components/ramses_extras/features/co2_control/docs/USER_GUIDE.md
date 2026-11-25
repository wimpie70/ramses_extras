# CO2 Control — User Guide

## Quick start

### 1. Enable the feature

1. Go to **Settings → Devices & Services → Ramses Extras**
2. Click **Configure** → **CO2 Control**
3. Select the FAN devices you want CO2 control on
4. Click **Submit**

### 2. Configure your sensors

CO2 control uses two kinds of sources:

- **The FAN's internal CO2 sensor** — automatic, nothing to configure
- **Room sensors** — configure these as *area sensors* in the **Sensor
  Control** feature: enable `area_co2_enabled` and pick the `co2_entity`

### 3. Enable automation

Turn on the **CO2 Control** switch entity
(`switch.co2_control_{device_id}`) — automation only runs while it is on.

## Understanding CO2 levels

- **400–600 ppm**: outdoor air, excellent
- **600–800 ppm**: good indoor air
- **800–1000 ppm**: acceptable
- **1000–1500 ppm**: stuffy, ventilation recommended
- **1500–2000 ppm**: poor, ventilation needed
- **2000+ ppm**: very poor, ventilate immediately

Recommended trigger thresholds:

- **Bedroom**: 800–1000 ppm (lower for better sleep)
- **Home office**: 800–1000 ppm
- **Living room**: 1000–1200 ppm

## How it works

### Triggering

A source triggers when its CO2 reaches **threshold + activation hysteresis**
and releases at **threshold + deactivation hysteresis**. Example with
defaults: triggers at 825 ppm, releases at 775 ppm. This dead zone prevents
the fan from constantly switching on and off.

While at least one source is triggered, CO2 control is active. When the last
source releases, the demand is cleared and the fan returns to its normal
schedule/auto behavior.

### Stepped bands

The demanded fan speed depends on the worst (highest) triggered CO2 value:

```
below 1000 ppm   → fan_low
1000 – 1200 ppm  → fan_medium
above 1200 ppm   → fan_high
```

The band only steps *down* when CO2 falls below the lower threshold minus the
activation hysteresis, so it can't flap between bands. The thresholds
themselves (`medium_threshold`, `high_threshold`) are configurable.

### Fixed fan mode

If your unit is over- or under-capacity for your home, the generic bands may
not fit — a "medium" on a 400-class unit can move more air than a "high" on a
smaller one. Set **Fan mode** to `low`, `medium`, or `high` in the CO2
control settings to always demand that mode while active. `auto` (default)
uses the stepped bands.

### Per-area tuning

Each area sensor can override the global values:

- **Threshold**: set a static `co2_threshold`, or point
  `co2_threshold_entity` at an input_number you can tune from your dashboard.
  The entity wins when set and available; the static value is the fallback;
  the global default applies when neither is set.
- **Bands**: `co2_medium_threshold` / `co2_high_threshold` (0 = use the
  global values). A bedroom can escalate earlier than a living room.

### Zones and valves

Assign a `zone_id` to an area sensor and CO2 control publishes demand for
that zone while its air is bad. The zone coordinator uses these demands —
together with humidity, REM, and manual demands — to position DIY zone
valves and shape FAN-level speed demand. Rooms behind a valve get air
exactly when their own sensors say so.

### Priority over humidity

CO2 control takes precedence over humidity control: humidity automation
pauses while CO2 is active and resumes afterwards. This can be disabled with
the `priority_over_humidity` setting.

### Interaction with manual mode

Manually picking a fan speed suspends extras automation — CO2 control resumes
when you return to auto.

## Examples

### Bedroom monitoring

1. Put a CO2 sensor in the bedroom
2. In Sensor Control, create/edit the bedroom area sensor:
   - enable `area_co2_enabled`, pick the sensor as `co2_entity`
   - set `co2_threshold` to 900
   - set `co2_medium_threshold` to 1100 and `co2_high_threshold` to 1400 if
     you want gentler escalation than the global bands
3. CO2 control now ventilates when the bedroom air degrades overnight

### Multi-room setup

Configure one area sensor per room, each with its own `zone_id` matching
your valve zones. CO2 control monitors all rooms; any room can trigger
ventilation, and zone valves follow the demand.

## Troubleshooting

### CO2 control never activates

1. Is `switch.co2_control_{device_id}` on?
2. Are the sensor entities available and actually updating?
3. Do values reach threshold + activation hysteresis (default 825 ppm)?
4. Check the attributes of `binary_sensor.co2_active_{device_id}` for the
   trigger evaluation details

### Fan doesn't speed up when CO2 is high

1. Is the fan in manual override? Automation is suspended in manual mode
2. A higher-priority automation may hold the fan — check the arbiter state
3. Check `sensor.co2_zone_status_{device_id}` for the current trigger status

### Ventilation flaps on and off

Increase the activation hysteresis — it widens both the trigger dead zone and
the band step-down margin.

## Tips

- Place CO2 sensors at breathing height, away from supply air grilles and
  frequently opened windows
- FAN devices have their own native CO2 logic as a fallback — if Home
  Assistant or the network goes down, basic ventilation continues
- Use an `input_number` as `co2_threshold_entity` to tune thresholds from
  your dashboard without editing configuration
