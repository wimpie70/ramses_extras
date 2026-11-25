# CO2 Control Feature

## Overview

The CO2 Control feature provides CO2-based ventilation control for HVAC fan
systems. It monitors CO2 sensors — the FAN's internal sensor and/or external
room sensors configured as *area sensors* in Sensor Control — and demands
more ventilation when levels exceed configured thresholds.

**Key features:**
- Stepped demand bands (low / medium / high) instead of proportional speed
- Optional fixed fan mode override for over/under-capacity units
- Per-area thresholds and per-area band thresholds
- Zone demand publication for DIY valve zones (area sensors carry a `zone_id`)
- Priority over humidity control (CO2 takes precedence)
- Hysteresis support to prevent oscillation

## How it works

### Trigger sources

CO2 control evaluates every configured source independently:

1. **Area sensors** — external room sensors configured in the Sensor Control
   feature with `area_co2_enabled` and a `co2_entity`. Each area can have its
   own threshold and band thresholds.
2. **Internal CO2 sensor** — the FAN device's own CO2 sensor
   (`sensor.{device_id}_co2_level` or the sensor control `co2` mapping),
   using the global threshold.

A source *triggers* when its CO2 value reaches **threshold + activation
hysteresis**, and *releases* when it drops to **threshold + deactivation
hysteresis** (a negative offset). CO2 control is active while at least one
source is triggered.

### Stepped demand bands

The fan baseline already runs at low speed continuously, so demanding
`fan_low` would change nothing — control starts at medium. While active,
the demanded fan speed is a stepped band based on the worst (highest)
triggered source value:

| worst CO2 level | demand |
|---|---|
| below `high_threshold` (default 1200 ppm) | `fan_medium` |
| above `high_threshold` | `fan_high` |

Anti-flap: the activation hysteresis doubles as the step-down margin — the
high band only steps *down* when the CO2 level falls below `high_threshold`
minus the hysteresis.

The demand is submitted to the fan speed arbiter, so other automations with
higher priority can still overrule it.

### Fixed fan mode

Because low/medium/high percentages are installation-specific (dipswitches,
2411 parameters), a fixed mode can be demanded instead of the bands —
configure **Fan mode** in the CO2 control settings: `auto` (stepped bands,
default), `low`, `medium`, or `high`.

### Zone demands (DIY valve zones)

Area sensors can carry a `zone_id`. While a source is triggered, CO2 control
publishes a demand for that zone into the zone demand registry — the same
mechanism humidity, REM, and manual demands use. The zone coordinator turns
those demands into valve positions and FAN-level speed demands, so rooms
behind a valve get air exactly when their sensors say they need it.

## Configuration

### Enable CO2 control

1. Navigate to **Settings → Devices & Services → Ramses Extras**
2. Click **Configure** → **CO2 Control**
3. Select the FAN devices to enable it for
4. Adjust the settings (below)

### Settings (per config flow, global)

| setting | default | meaning |
|---|---|---|
| `fan_mode` | `auto` | stepped bands, or fixed low/medium/high |
| `default_threshold` | 800 ppm | trigger level for the internal sensor and areas without their own |
| `high_threshold` | 1200 ppm | above this → `fan_high` |

| `activation_hysteresis` | +25 ppm | activation offset; doubles as band anti-flap margin |
| `deactivation_hysteresis` | −25 ppm | release offset |
| `priority_over_humidity` | true | pause humidity control while CO2 is active |

### Area sensor settings (Sensor Control)

In the Sensor Control area mapping:

| field | meaning |
|---|---|
| `area_co2_enabled` | include this area's CO2 sensor in CO2 control |
| `co2_entity` | the CO2 sensor entity |
| `co2_threshold_entity` | optional entity (e.g. input_number) holding a dynamic threshold |
| `co2_threshold` | static threshold for this area |
| `co2_high_threshold` | per-area high band threshold; 0 = inherit the global value |

**Threshold precedence**: a set-and-available threshold entity wins;
otherwise the static `co2_threshold` applies; if neither is set the global
default is used.

## Entities

- `switch.co2_control_{device_id}` — enable/disable CO2 control
- `number.co2_threshold_{device_id}` — global trigger level (400–2000 ppm)
- `number.co2_activation_hysteresis_{device_id}` — activation hysteresis
- `number.co2_deactivation_hysteresis_{device_id}` — deactivation hysteresis
- `binary_sensor.co2_active_{device_id}` — whether CO2 control is active,
  with trigger details in its attributes
- `sensor.co2_zone_status_{device_id}` — human-readable trigger status

## Integration with humidity control

When both features are enabled and CO2 control activates, humidity control is
paused; it resumes when CO2 control releases. Disable this with the
`priority_over_humidity` setting.

## Troubleshooting

### CO2 control not activating

1. Check `switch.co2_control_{device_id}` is ON
2. Verify the CO2 sensor entities are available and updating
3. Check that values actually reach threshold + activation hysteresis
4. Review the log for trigger evaluation details

### Fan speed not changing

1. Verify the device is not in manual override (manual mode suspends automation)
2. Check the fan speed arbiter state — a higher-priority automation may hold the fan
3. Review `binary_sensor.co2_active_{device_id}` attributes for trigger details

## See also

- [Humidity Control](../humidity_control/README.md)
- [Sensor Control](../sensor_control/README.md)
