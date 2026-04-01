# Troubleshooting Guide

**Document Version:** 1.0.0
**Created:** March 31, 2026
**Applies to:** Ramses Extras v0.15+

---

## Table of Contents

- [Diagnostic Tools](#diagnostic-tools)
- [FAN Configuration Issues](#fan-configuration-issues)
- [Sensor Resolution Problems](#sensor-resolution-problems)
- [Remote Binding Issues](#remote-binding-issues)
- [Zone Configuration Issues](#zone-configuration-issues)
- [Fan Control & Automation Issues](#fan-control--automation-issues)
- [WebSocket & Real-time Updates](#websocket--real-time-updates)
- [YAML Export/Import Issues](#yaml-exportimport-issues)
- [Getting Help](#getting-help)

---

## Diagnostic Tools

### Checking System State

Use the Ramses Extras diagnostics sensor to verify system health:

```yaml
# In Home Assistant Developer Tools → Template
{{ states('sensor.ramses_extras_diagnostics') }}

# View specific attributes
{{ state_attr('sensor.ramses_extras_diagnostics', 'remote_bindings') }}
{{ state_attr('sensor.ramses_extras_diagnostics', 'unmatched_remote_count') }}
{{ state_attr('sensor.ramses_extras_diagnostics', 'zones') }}
```

### WebSocket Diagnostic Commands

Access via browser console on a page with Ramses Extras cards, or via HA WebSocket API:

```javascript
// Get current config export
{
  "type": "ramses_extras/export_config",
  "feature": "sensor_control"
}

// List remote bindings
{
  "type": "ramses_extras/list_bindings"
}

// Check for binding conflicts
{
  "type": "ramses_extras/detect_conflicts"
}

// Get binding suggestions from observed traffic
{
  "type": "ramses_extras/get_binding_suggestions",
  "fan_id": "32:153289"
}

// Get unmatched remote traffic
{
  "type": "ramses_extras/get_unmatched_traffic",
  "limit": 10
}

// Get zone status
{
  "type": "ramses_extras/get_zone_status",
  "fan_id": "32:153289"
}
```

### Checking ramses_cc Status

```yaml
# Verify ramses_cc is loaded
{{ 'ramses_cc' in states | map(attribute='entity_id') | map('split', '.') | map('first') | unique | list }}

# Check if FAN device is visible
{{ states.sensor | selectattr('entity_id', 'search', '32_153289') | list }}
```

---

## FAN Configuration Issues

### "FAN Configuration menu doesn't appear"

**Symptoms:**
- Ramses Extras Configure shows no FAN Configuration option
- Only shows other features (Humidity Control, etc.)

**Diagnostic Steps:**

1. **Verify ramses_cc has discovered FAN devices:**
   ```bash
   # Check Home Assistant logs
   grep -i "ramses_cc.*fan" /config/home-assistant.log
   ```

2. **Check device class:**
   ```python
   # In HA Developer Tools
   {{ device_attr('32:153289', 'name') }}
   {{ device_attr('32:153289', 'model') }}
   ```

3. **Verify bound trait in ramses_rf config:**
   ```yaml
   # In configuration.yaml or known_list.txt
   "32:153289":
     class: FAN
     bound: "37:169161"  # Required for FAN features
   ```

**Solutions:**
- Add `bound` trait to FAN device in ramses_rf configuration
- Restart Home Assistant after config changes
- Verify FAN device is discovered by ramses_cc before Ramses Extras starts

---

### "FAN device not in device list"

**Symptoms:**
- FAN Configuration opens but device list is empty
- Other devices (REM, DIS) appear but not FAN

**Diagnostic Steps:**

1. Check Ramses RF traffic:
   ```bash
   # Enable debug logging in configuration.yaml
   logger:
     logs:
       ramses_rf: debug
       custom_components.ramses_extras: debug
   ```

2. Verify device enumeration:
   ```python
   # In HA Developer Tools → Python
   hass.data.get('ramses_extras', {}).get('devices', {})
   ```

**Solutions:**
- Ensure ramses_cc loads before Ramses Extras (automatic, but verify)
- Check that FAN device ID format is correct (`32:xxxxxx`)
- Verify FAN is sending/receiving traffic on RF network

---

## Sensor Resolution Problems

### "Sensors show as 'unavailable' or 'none'"

**Symptoms:**
- Humidity Control shows unavailable sensors
- Graphs in HVAC Fan Card don't populate
- Automation logic can't read values

**Diagnostic Steps:**

1. **Check sensor resolution state:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'sensor_sources') }}
   ```

2. **Verify entity exists:**
   ```python
   {{ states('sensor.fan_indoor_temp_32_153289') }}
   {{ states('sensor.living_room_humidity') }}  # For external sensors
   ```

3. **Check FAN Configuration source settings:**
   - Settings → Devices & Services → Ramses Extras → Configure
   - FAN Configuration → Sensor Sources
   - Verify `kind` and `entity_id` settings

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| External entity doesn't exist | Check entity ID spelling; ensure sensor is available |
| `kind: external` but no `entity_id` | Edit in FAN Configuration and select entity |
| `kind: internal` but no ramses_cc sensor | Verify ramses_cc is creating expected entities |
| Device ID format mismatch | Ensure canonical format (`32:153289` not `32_153289`) |

---

### "Absolute humidity shows wrong values"

**Symptoms:**
- Absolute humidity values don't match expectations
- Calculated values are negative or impossibly high

**Diagnostic Steps:**

1. **Check absolute humidity inputs:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'abs_humidity_inputs') }}
   ```

2. **Verify input sensors:**
   ```python
   {{ states('sensor.indoor_absolute_humidity_32_153289') }}
   {{ states('sensor.outdoor_absolute_humidity_32_153289') }}
   ```

3. **Check source entities for derived calculation:**
   - If using `external_temp` + `external`: verify both entities exist
   - If using `external_abs`: verify absolute humidity entity is correct

**Solutions:**
- Verify temperature is in °C and humidity is %RH
- Check that indoor/outdoor aren't swapped in configuration
- For derived calculation, both inputs must be valid

---

## Remote Binding Issues

### "REM presses not reflected in HA"

**Symptoms:**
- Physical remote works (FAN responds)
- Home Assistant state doesn't update
- HVAC Fan Card doesn't show remote actions

**Diagnostic Steps:**

1. **Verify binding exists:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'remote_bindings') }}
   ```

2. **Check if REM is sending traffic:**
   ```bash
   # In ramses_cc logs
   grep -i "37:169161" /config/ramses_log
   ```

3. **Verify binding resolution:**
   ```javascript
   // WebSocket command
   {
     "type": "ramses_extras/get_bindings",
     "fan_id": "32:153289"
   }
   ```

4. **Check arbiter state:**
   ```python
   {{ states('sensor.fan_arbiter_state_32_153289') }}
   ```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Binding not configured | Add binding in FAN Configuration → Remote Binding |
| Binding disabled | Check `enabled: true` in binding |
| REM ID format wrong | Use canonical format with colon: `37:169161` |
| REM not discovered | Verify REM appears in ramses_cc |
| Arbiter disabled | Check Humidity Control or relevant feature is enabled |

---

### "REM traffic unmatched"

**Symptoms:**
- REM is sending packets
- Logs show "unmatched remote traffic"
- No binding is triggered

**Diagnostic Steps:**

1. **Check unmatched traffic counter:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'unmatched_remote_count') }}
   ```

2. **Get unmatched traffic details:**
   ```javascript
   // WebSocket command
   {
     "type": "ramses_extras/get_unmatched_traffic",
     "limit": 10
   }
   ```

3. **Verify REM is sending to expected FAN:**
   - Check packet destination in logs
   - Verify FAN device ID matches binding

**Solutions:**
- If you see consistent traffic for a FAN, create binding
- Check if REM device ID matches your binding configuration
- Enable debug logging to see raw packets

---

### "Binding conflict detected"

**Symptoms:**
- Error message: "REM assigned to multiple FANs"
- Configuration validation fails
- Multiple bindings appear for same REM

**Diagnostic Steps:**

1. **List all bindings:**
   ```javascript
   // WebSocket command
   {
     "type": "ramses_extras/list_bindings"
   }
   ```

2. **Detect conflicts:**
   ```javascript
   // WebSocket command
   {
     "type": "ramses_extras/detect_conflicts"
   }
   ```

3. **Check configuration export:**
   ```javascript
   {
     "type": "ramses_extras/export_config",
     "feature": "remote_binding"
   }
   ```

**Solutions:**
- Edit configuration to ensure each REM is bound to only one FAN
- Remove duplicate or conflicting bindings
- Use conflict detection API to identify issues

---

## Zone Configuration Issues

### "Zones not appearing in UI"

**Symptoms:**
- HVAC Fan Card doesn't show zone controls
- Zone configuration saved but not visible
- Zone entities not created

**Diagnostic Steps:**

1. **Check zone configuration:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'zones') }}
   ```

2. **Verify zone export:**
   ```javascript
   // WebSocket command
   {
     "type": "ramses_extras/export_config",
     "feature": "zones"
   }
   ```

3. **Check zone coordinator state:**
   ```python
   {{ states('sensor.zone_coordinator_32_153289') }}
   ```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Zones feature not enabled | Enable zones in Ramses Extras configuration |
| Wrong `source_type` | ORCON native needs Orcon hardware; custom needs valve entities |
| Invalid `zone_id` | Use only alphanumeric and underscores |
| Missing actuator entity | For custom zones, specify valid HA switch entity |

---

### "Zone valves not responding"

**Symptoms:**
- Zone shows in UI but valve doesn't move
- Actuator entity exists but no physical response
- Min/max position limits not working

**Diagnostic Steps:**

1. **Test actuator entity directly:**
   ```yaml
   # In Developer Tools → Services
   service: switch.turn_on
   target:
     entity_id: switch.your_zone_valve
   ```

2. **Check zone configuration:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'zones') }}
   ```

3. **Verify safety limits:**
   - Check `min_position` and `max_position` are within 0-100
   - Verify sum of all zone min positions < 100

**Solutions:**
- Test valve entity works independently in HA
- Verify `min_position` isn't preventing movement
- Check valve wiring and power
- For ORCON native: verify Orcon supports zone control

---

## Fan Control & Automation Issues

### "Humidity Control not triggering"

**Symptoms:**
- Humidity exceeds threshold but fan doesn't speed up
- Automation appears enabled but no action
- Threshold entities exist but logic not running

**Diagnostic Steps:**

1. **Check Humidity Control state:**
   ```python
   {{ states('switch.humidity_control_32_153289') }}
   {{ states('number.humidity_threshold_high_32_153289') }}
   ```

2. **Verify sensor values:**
   ```python
   {{ states('sensor.indoor_absolute_humidity_32_153289') }}
   {{ states('sensor.outdoor_absolute_humidity_32_153289') }}
   ```

3. **Check arbiter mode:**
   ```python
   {{ states('sensor.fan_arbiter_state_32_153289') }}
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'manual_override') }}
   ```

4. **Enable debug logging:**
   ```yaml
   logger:
     logs:
       custom_components.ramses_extras.features.humidity_control: debug
   ```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Humidity Control disabled | Enable the switch entity |
| Threshold not exceeded | Check threshold vs current value |
| Manual override active | Clear manual override or wait for timeout |
| CO2 has priority | CO2 control takes precedence when active |
| Sensor unavailable | Fix sensor resolution issues (see above) |

---

### "CO2 Control not triggering"

**Symptoms:**
- CO2 exceeds threshold but fan doesn't respond
- CO2 switch enabled but no automation
- Priority issue with humidity control

**Diagnostic Steps:**

1. **Check CO2 Control state:**
   ```python
   {{ states('switch.co2_control_32_153289') }}
   {{ states('number.co2_threshold_32_153289') }}
   ```

2. **Verify CO2 sensor:**
   ```python
   {{ states('sensor.co2_zone_1_32_153289') }}
   ```

3. **Check priority status:**
   ```python
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'active_control') }}
   ```

**Solutions:**
- CO2 has higher priority than humidity - this is by design
- Verify CO2 sensor source in FAN Configuration
- Check threshold is in ppm (not ppb or other unit)

---

### "Fan speed arbiter stuck"

**Symptoms:**
- Fan speed doesn't change despite conditions
- Arbiter shows fixed mode
- Manual override won't clear

**Diagnostic Steps:**

1. **Check arbiter state:**
   ```python
   {{ states('sensor.fan_arbiter_state_32_153289') }}
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'extras_control_enabled') }}
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'manual_override_until') }}
   ```

2. **Verify transport state:**
   ```python
   {{ states('sensor.fan_transport_32_153289') }}
   ```

3. **Check effective speed:**
   ```python
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'effective_speed') }}
   {{ state_attr('sensor.fan_arbiter_state_32_153289', 'requested_speed') }}
   ```

**Solutions:**
- Wait for manual override timeout (typically 30 min)
- Send explicit command via HVAC Fan Card to clear override
- Restart Ramses Extras integration (Settings → Devices & Services → Ramses Extras → ⋮ → Reload)
- Check if transport monitoring is receiving updates

---

## WebSocket & Real-time Updates

### "HVAC Fan Card not updating"

**Symptoms:**
- Card shows old data
- Changes don't reflect immediately
- WebSocket appears disconnected

**Diagnostic Steps:**

1. **Check browser console for errors:**
   ```javascript
   // Press F12 → Console
   // Look for WebSocket connection errors
   ```

2. **Test WebSocket manually:**
   ```javascript
   // In browser console
   const ws = new WebSocket('ws://your-ha:8123/api/websocket');
   ```

3. **Verify Ramses Extras WebSocket registration:**
   ```python
   {{ states('sensor.ramses_extras_diagnostics') }}
   ```

**Solutions:**
- Refresh browser page (F5)
- Clear browser cache and reload
- Check HA WebSocket proxy configuration if using reverse proxy
- Verify Ramses Extras is properly loaded (no startup errors)

---

## YAML Export/Import Issues

### "Export returns empty or error"

**Diagnostic Steps:**

1. **Check feature name spelling:**
   - Correct: `sensor_control`, `remote_binding`, `zones`
   - Case-sensitive

2. **Verify feature is configured:**
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'configured_features') }}
   ```

3. **Test export via WebSocket:**
   ```javascript
   {
     "type": "ramses_extras/export_config",
     "feature": "sensor_control"
   }
   ```

**Solutions:**
- Use correct feature ID from documentation
- Ensure feature has at least one configuration entry
- Check HA logs for export errors

---

### "Import validation fails"

**Symptoms:**
- YAML import shows validation errors
- Configuration not applied
- Error messages about schema

**Diagnostic Steps:**

1. **Validate YAML format:**
   ```yaml
   # Must start with features:
   features:
     sensor_control:
       # ... configuration
   ```

2. **Check device ID format:**
   - Correct: `"32:153289"` (with quotes and colon)
   - Wrong: `32:153289` (no quotes), `32_153289` (underscore)

3. **Verify entity IDs exist:**
   - External entity references must be valid HA entities

**Solutions:**
- Use strict YAML format with proper indentation
- Quote device IDs to prevent YAML from interpreting as time
- Validate all external entity IDs exist before import
- Check validation error messages for specific issues

---

## Getting Help

### Information to Collect

When reporting issues, provide:

1. **System Information:**
   - Home Assistant version
   - Ramses Extras version
   - ramses_cc version
   - Ramses RF version (if known)

2. **Configuration Export:**
   ```javascript
   {
     "type": "ramses_extras/export_config",
     "feature": "sensor_control"
   }
   ```

3. **Diagnostic State:**
   ```python
   {{ states('sensor.ramses_extras_diagnostics') }}
   ```

4. **Relevant Logs:**
   ```bash
   # Enable debug logging, reproduce issue, then collect:
   grep -i "ramses_extras" /config/home-assistant.log | tail -100
   ```

5. **Device Information:**
   - FAN device ID
   - REM device IDs (if applicable)
   - Hardware model (Orcon HRC-300, etc.)

### Community Resources

- Ramses RF Discord community
- Home Assistant community forums (Ramses RF thread)
- GitHub issues for ramses_extras (for bugs)

---

**Last Updated:** March 31, 2026
