# FAN Configuration - User Guide

**Document Version:** 1.0.0
**Created:** March 31, 2026
**Applies to:** Ramses Extras v0.15+

---

## Table of Contents

- [Overview](#overview)
- [Accessing FAN Configuration](#accessing-fan-configuration)
- [Configuration Menu Structure](#configuration-menu-structure)
- [Device Selection & Feature Enablement](#device-selection--feature-enablement)
- [Internal Fan Sensors](#internal-fan-sensors)
  - [CO2 Sensors](#co2-sensors)
  - [Absolute Humidity Inputs](#absolute-humidity-inputs)
- [Zone Configuration](#zone-configuration)
- [Remote Binding](#remote-binding)
- [Sensor Sources](#sensor-sources)
- [Saving and Exporting](#saving-and-exporting)
- [Quick Start Example](#quick-start-example)

---

## Overview

**FAN Configuration** is the central place to configure your ventilation system in Ramses Extras. It allows you to:

- Select which sensors (temperature, humidity, CO2) feed into your fan control
- Configure zones for room-specific ventilation
- Bind remote controls (REM devices) to your FAN unit
- Set up automatic humidity and CO2-based fan speed control

> **Note:** FAN Configuration was previously called "Sensor Control". The functionality is the same; only the name has changed to better reflect its purpose.

---

## Accessing FAN Configuration

1. Go to **Settings** → **Devices & Services** in Home Assistant
2. Find **Ramses Extras** in your integrations
3. Click **Configure**
4. Select **FAN Configuration** from the menu

If you don't see FAN Configuration, ensure your FAN device (e.g., Orcon ventilation unit) is properly detected by `ramses_cc`.

---

## Configuration Menu Structure

When you enter FAN Configuration, you'll see a device selection screen:

```
┌─────────────────────────────────────────┐
│ FAN Configuration                       │
├─────────────────────────────────────────┤
│                                         │
│ Select a FAN device to configure:       │
│                                         │
│ ○ 32:153289 (Main Ventilation)           │
│ ○ 32:153290 (Garage Unit)                │
│                                         │
│ [Configure Selected Device]              │
│                                         │
└─────────────────────────────────────────┘
```

After selecting a device, you'll see the **Group Selection** menu:

```
┌─────────────────────────────────────────┐
│ Configure 32:153289                     │
├─────────────────────────────────────────┤
│                                         │
│ Select configuration area:              │
│                                         │
│ • Sensor Sources                        │
│ • Internal Fan Sensors                  │
│ • Zones                                 │
│ • Remote Binding                        │
│                                         │
│ [Save and Exit]                         │
│                                         │
└─────────────────────────────────────────┘
```

---

## Device Selection & Feature Enablement

### Prerequisites

Before configuring FAN settings:

1. Your FAN device must be discovered by `ramses_cc`
2. The device should have the `bound` trait configured (links FAN to REM)
3. Ramses Extras must be installed and running

### Selecting a Device

1. FAN Configuration shows all discovered FAN devices (device class `FAN` or `HvacVentilator`)
2. Select the device you want to configure
3. The configuration menu appears with available options for that device

---

## Internal Fan Sensors

The **Internal Fan Sensors** section consolidates sensor configuration for your FAN device:

```
┌─────────────────────────────────────────┐
│ Internal Fan Sensors - 32:153289        │
├─────────────────────────────────────────┤
│                                         │
│ CO2 Sensors:                            │
│   [Select CO2 sensor entities...]       │
│                                         │
│ Absolute Humidity - Indoor:             │
│   Temperature: [Auto / Select entity]    │
│   Humidity:    [Auto / Select entity]    │
│                                         │
│ Absolute Humidity - Outdoor:            │
│   Temperature: [Auto / Select entity]    │
│   Humidity:    [Auto / Select entity]    │
│                                         │
│ [Save Configuration]                   │
│                                         │
└─────────────────────────────────────────┘
```

### CO2 Sensors

CO2 sensors trigger ventilation when CO2 levels exceed configured thresholds:

- **Priority:** CO2 control has higher priority than humidity control
- **Multiple sensors:** You can assign multiple CO2 sensors to one FAN
- **Source types:**
  - `internal`: Use built-in ramses_cc CO2 entities (if available)
  - `external`: Use any Home Assistant sensor entity (e.g., `sensor.living_room_co2`)
  - `none`: Disable CO2 for this device

**Configuration steps:**
1. Select **Internal Fan Sensors** from the group menu
2. Choose CO2 sensor source type
3. If external, select or type the entity ID
4. Configure threshold in the Humidity Control feature settings

### Absolute Humidity Inputs

Absolute humidity is calculated from temperature and relative humidity:

- **Indoor side:** Used for humidity control decisions
- **Outdoor side:** Used for humidity control decisions
- **Input types per side:**
  - `internal`: Use built-in ramses_cc sensors
  - `external_temp` + `external`: Use specific HA entities
  - `external_abs`: Use a direct absolute humidity sensor

**Configuration steps:**
1. Select **Internal Fan Sensors**
2. For each side (indoor/outdoor), choose input type
3. Select or enter the appropriate entity IDs
4. Save to enable automatic absolute humidity calculation

---

## Zone Configuration

Zones allow room-specific ventilation control:

```
┌─────────────────────────────────────────┐
│ Zones - 32:153289                       │
├─────────────────────────────────────────┤
│                                         │
│ Configured Zones:                       │
│ • bathroom (ORCON native)               │
│ • living_room (Custom valves)           │
│                                         │
│ [Add Zone]  [Edit Zone]  [Remove Zone]   │
│                                         │
│ [Save and Exit]                          │
│                                         │
└─────────────────────────────────────────┘
```

### Zone Types

| Zone Type | Description | Use Case |
|-----------|-------------|----------|
| **ORCON native** | Uses built-in Orcon zone support | Standard Orcon ventilation units |
| **Custom valves** | External valve/actuator control | Custom installations, non-Orcon systems |

### Zone Settings

When adding/editing a zone:

| Setting | Description | Example |
|---------|-------------|---------|
| `zone_id` | Unique identifier for the zone | `bathroom`, `bedroom_1` |
| `zone_name` | Human-readable name | "Main Bathroom" |
| `source_type` | ORCON or custom valves | `orcon_native` |
| `min_position` | Minimum valve position (safety) | `5` (prevents full close) |
| `max_position` | Maximum valve position | `100` |
| `actuator_entity` | HA entity for custom valves | `switch.bathroom_valve` |

### Safety Limits

- **Minimum position:** Prevents all valves from closing simultaneously (protects the fan)
- **Maximum position:** Upper bound for valve opening
- **Conflict detection:** Alerts if one REM is assigned to multiple zones incorrectly

---

## Remote Binding

Remote binding associates physical REM (remote) devices with your FAN:

```
┌─────────────────────────────────────────┐
│ Remote Binding - 32:153289              │
├─────────────────────────────────────────┤
│                                         │
│ Bound REMs:                             │
│ • 37:169161 (primary, enabled)           │
│ • 37:169162 (secondary, enabled)         │
│                                         │
│ [Add REM]  [Edit]  [Remove]  [Test]      │
│                                         │
│ Binding Health: ✅ Healthy               │
│ Last seen: 37:169161 - 2 minutes ago    │
│                                         │
└─────────────────────────────────────────┘
```

### REM Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `primary` | Main remote | Full control (Auto, speeds, Away, timers) |
| `secondary` | Additional remote | Full control, lower priority |
| `boost_only` | Limited remote | Only boost/override functions |

### Binding Configuration

1. Select **Remote Binding** from the group menu
2. Click **Add REM**
3. Select REM device from:
   - Discovered REM devices (recommended)
   - Manual entry (advanced)
4. Assign a role
5. Enable the binding
6. Save

### Validation

The system validates:
- **Uniqueness:** One REM cannot be bound to multiple FANs
- **Existence:** REM device must exist in `ramses_cc`
- **Format:** Device IDs must be canonical (`xx:xxxxxx`)

---

## Sensor Sources

The **Sensor Sources** section maps metrics to entity sources:

| Metric | Purpose | Source Types |
|--------|---------|--------------|
| Indoor temperature | Humidity control | internal, external, none |
| Indoor humidity | Humidity control | internal, external, none |
| Outdoor temperature | Humidity control | internal, external, none |
| Outdoor humidity | Humidity control | internal, external, none |
| Indoor CO2 | CO2 ventilation | internal, external, none |
| Outdoor CO2 | CO2 ventilation | internal, external, none |

### Source Types Explained

- **`internal`**: Uses built-in ramses_cc/Ramses Extras entities (e.g., `sensor.fan_indoor_temp_32_153289`)
- **`external`**: Uses any Home Assistant entity (e.g., `sensor.my_sensor_temperature`)
- **`derived`**: Computed metric (absolute humidity from temp + RH)
- **`none`**: Disabled for this device

### Resolution Order

The system resolves sensors in this priority:
1. User override from FAN Configuration
2. Internal baseline from `INTERNAL_SENSOR_MAPPINGS`
3. Falls back to `none` if entity doesn't exist (fail-closed)

---

## Saving and Exporting

### Saving Configuration

Changes are saved immediately when you click **Save** in each section. The configuration is stored in:

```yaml
# Stored in config entry options
ramses_extras:
  features:
    sensor_control:
      sources:
        "32:153289":
          indoor_temp:
            kind: internal
          indoor_humidity:
            kind: external
            entity_id: sensor.living_room_humidity
```

### Exporting Configuration

You can export your complete FAN Configuration as strict YAML:

1. Via WebSocket command:
   ```json
   {
     "type": "ramses_extras/export_config",
     "feature": "sensor_control"
   }
   ```

2. Via service call:
   ```yaml
   service: ramses_extras.export_config
   data:
     feature: sensor_control
   ```

The export includes:
- Sensor source mappings
- Internal fan sensor configuration
- Zone definitions
- Remote bindings

It excludes:
- Runtime state (timestamps, caches)
- Discovery suggestions not yet accepted
- Security-sensitive data

---

## Quick Start Example

### Typical Setup for New Installation

**Scenario:** Orcon HRC-300 with one REM, humidity and CO2 control

**Steps:**

1. **Verify device discovery:**
   - Check `ramses_cc` shows your FAN (e.g., `32:153289`)
   - Verify REM appears (e.g., `37:169161`)
   - Ensure FAN has `bound` trait in ramses_rf config

2. **Open FAN Configuration:**
   - Settings → Devices & Services → Ramses Extras → Configure
   - Select FAN Configuration

3. **Configure Sensor Sources:**
   - Select device `32:153289`
   - Choose **Sensor Sources**
   - Set indoor/outdoor temperature and humidity to `internal`
   - Save

4. **Configure Internal Fan Sensors:**
   - Select **Internal Fan Sensors**
   - Add CO2 sensor (external entity: `sensor.living_room_co2`)
   - Verify absolute humidity inputs are set to `Auto` (uses internal)
   - Save

5. **Configure Remote Binding:**
   - Select **Remote Binding**
   - Add REM `37:169161`
   - Set role to `primary`
   - Save

6. **Enable Humidity Control:**
   - Go back to main Ramses Extras configuration
   - Enable **Humidity Control** feature for your device
   - Set thresholds as desired

7. **Test:**
   - Press REM buttons → HA state should update
   - Trigger humidity threshold → fan should speed up
   - Trigger CO2 threshold → fan should speed up (priority over humidity)

---

## Troubleshooting Quick Reference

| Issue | Check | Solution |
|-------|-------|----------|
| FAN not appearing in list | `ramses_cc` device discovery | Verify FAN device class and `bound` trait |
| REM presses not reflected | Remote binding exists and enabled | Check binding in FAN Configuration |
| Sensors show "unavailable" | Entity resolution | Verify sensor source configuration |
| CO2 not triggering fan | CO2 enabled and threshold set | Check Humidity Control thresholds |
| Zones not working | Zone configuration | Verify `source_type` matches hardware |

For detailed troubleshooting, see `TROUBLESHOOTING.md`.

---

## Related Documentation

- `FAN_CONTROL_ARCHITECTURE.md` - Technical details of fan speed arbitration
- `ZONES_IMPLEMENTATION_PLAN.md` - Zone feature design and capabilities
- `REMOTE_BINDING_EXAMPLES.md` - YAML configuration examples
- `CONFIGURATION_STRATEGY.md` - Overall configuration architecture

---

**Last Updated:** March 31, 2026
