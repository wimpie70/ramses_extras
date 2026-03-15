# Humidity Automation Entity Naming Fix

## Problem Summary

The humidity automation was failing with missing-entity errors because the automation expected abbreviated internal names while the entity managers create full descriptive entity IDs.

## Root Cause

- **const definitions**
  - use internal keys such as `indoor_abs`, `outdoor_abs`, `min_humidity`, `max_humidity`, and `offset`

- **entity creation**
  - produces concrete Home Assistant entity IDs such as `sensor.indoor_absolute_humidity_{device_id}`

- **automation validation**
  - must resolve the actual entity IDs dynamically instead of relying on outdated hardcoded names

## Expected Entity Names

| Entity Type | Expected Entity ID | Description |
| --- | --- | --- |
| Sensor | `sensor.32_153289_indoor_humidity` | CC: Indoor relative humidity |
| Sensor | `sensor.indoor_absolute_humidity_32_153289` | Extras: Calculated indoor absolute humidity |
| Sensor | `sensor.outdoor_absolute_humidity_32_153289` | Extras: Calculated outdoor absolute humidity |
| Number | `number.relative_humidity_minimum_32_153289` | Extras: Min threshold |
| Number | `number.relative_humidity_maximum_32_153289` | Extras: Max threshold |
| Number | `number.absolute_humidity_offset_32_153289` | Extras: Offset value |
| Switch | `switch.dehumidify_32_153289` | Extras: Balance control switch |
| Binary Sensor | `binary_sensor.dehumidifying_active_32_153289` | Extras: Balance status indicator |

## Decision Logic Reminder

The automation follows the humidity-balancing flow described in
`Humidity Control Decision Flow Diagram - original.md`:

```text
IF indoor_rh > max_humidity:
  IF indoor_abs > outdoor_abs + offset:
    Set fan HIGH
  ELSE:
    Set fan LOW
ELIF indoor_rh < min_humidity:
  IF indoor_abs < outdoor_abs - offset:
    Set fan HIGH
  ELSE:
    Set fan LOW
ELSE:
  Set fan LOW
```

## Current Naming Guidance

- **Keep entity IDs stable**
  - `switch.dehumidify_*` and `binary_sensor.dehumidifying_active_*` stay as-is for compatibility

- **Use clearer frontend wording**
  - show the switch as `Balance`
  - show the status sensor as `Balance Active`

- **Treat the binary sensor as output**
  - it is intended for frontend/status display
  - it should not be used as a normal automation trigger

## Verification

- **Logs**
  - confirm missing-entity errors are gone

- **UI**
  - confirm the card button label is `Balance`

- **Behavior**
  - confirm only one fan command is issued per automation decision
  - confirm turning the switch off sets the fan to `fan_auto`
  - confirm the active binary sensor reflects status only
