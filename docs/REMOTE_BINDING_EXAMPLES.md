# Remote Binding - Configuration Examples

Practical examples for configuring REM (remote) to FAN bindings in Ramses Extras.

## Overview

Remote binding allows you to associate physical REM devices with FAN units so that button presses are correctly attributed and reflected in Home Assistant.

## Configuration Methods

You can configure remote bindings through:
1. **Config Flow UI** (recommended for most users)
2. **YAML Import** (for advanced users and bulk configuration)

## Example 1: Single REM per FAN (Basic)

The simplest case: one remote controlling one FAN.

### Via Config Flow
1. Navigate to **Settings > Devices & Services > Ramses Extras > Configure**
2. Select your FAN device (e.g., `32:153289`)
3. Go to **Remote Binding** section
4. Click **Add REM**
5. Select the REM device from discovered devices or enter manually
6. Save

### Via YAML Import

```yaml
features:
  remote_binding:
    FANs:
      "32:153289":
        REMs:
          - rem_id: "37:169161"
            role: primary
            enabled: true
            source: manual_config
```

## Example 2: Multiple REMs per FAN (Different Roles)

Useful when you have multiple remotes for the same ventilation unit.

```yaml
features:
  remote_binding:
    FANs:
      "32:153289":
        REMs:
          # Main remote for daily use
          - rem_id: "37:169161"
            role: primary
            enabled: true
            source: manual_config

          # Secondary remote (e.g., in different room)
          - rem_id: "37:169162"
            role: secondary
            enabled: true
            source: manual_config

          # Boost-only remote (e.g., bathroom boost button)
          - rem_id: "37:169163"
            role: boost_only
            enabled: true
            source: manual_config
```

### Role Definitions

- **primary**: Full control (Auto, speeds, Away, timers)
- **secondary**: Full control but lower priority in arbitration
- **boost_only**: Only boost/override functions (limited control)

## Example 3: One REM per Multiple FANs (Not Allowed)

This configuration will be rejected due to conflict detection:

```yaml
# INVALID - Will fail validation
features:
  remote_binding:
    FANs:
      "32:153289":
        REMs:
          - rem_id: "37:169161"  # Same REM
            role: primary
      "32:153290":
        REMs:
          - rem_id: "37:169161"  # Same REM - CONFLICT!
            role: primary
```

**Error**: `"REM '37:169161' assigned to multiple FANs"`

## Example 4: Disabled Binding (Temporary)

To temporarily disable a binding without removing it:

```yaml
features:
  remote_binding:
    FANs:
      "32:153289":
        REMs:
          - rem_id: "37:169161"
            role: primary
            enabled: false  # Disabled but preserved
            source: manual_config
```

## Example 5: Complete Multi-FAN Setup

Full example for a home with multiple ventilation units:

```yaml
features:
  remote_binding:
    FANs:
      # Upstairs unit
      "32:153289":
        REMs:
          - rem_id: "37:169161"
            role: primary
            enabled: true
            source: manual_config

      # Downstairs unit
      "32:153290":
        REMs:
          - rem_id: "37:169162"
            role: primary
            enabled: true
            source: manual_config
          - rem_id: "37:169163"
            role: secondary
            enabled: true
            source: manual_config

      # Garage unit (stand-alone)
      "32:153291":
        REMs:
          - rem_id: "37:169164"
            role: primary
            enabled: true
            source: manual_config
```

## YAML Import/Export

### Export Current Bindings

Use the WebSocket command or service call to export:

```yaml
# WebSocket command
{
  "type": "ramses_extras/export_config",
  "feature": "remote_binding"
}
```

Response:
```yaml
features:
  remote_binding:
    FANs:
      "32:153289":
        REMs:
          - rem_id: "37:169161"
            role: primary
            enabled: true
```

### Import Bindings

1. Prepare your YAML file with the configuration
2. Use the **Import YAML** option in the config flow
3. Or use the WebSocket command:

```yaml
{
  "type": "ramses_extras/import_config",
  "feature": "remote_binding",
  "config": "...yaml content..."
}
```

## Troubleshooting

### "REM presses not reflected in HA"

**Symptoms**: You press buttons on the physical remote but Home Assistant doesn't update.

**Diagnostic steps**:

1. **Check binding exists**:
   ```yaml
   # WebSocket command
   {
     "type": "ramses_extras/get_bindings",
     "fan_id": "32:153289"
   }
   ```

2. **Verify REM is sending traffic**:
   - Check `ramses_cc` logs for REM device activity
   - Look for packets from the REM device ID

3. **Check binding resolution**:
   ```python
   # In Home Assistant developer tools
   {{ state_attr('sensor.ramses_extras_diagnostics', 'remote_bindings') }}
   ```

4. **Common fixes**:
   - Ensure binding is `enabled: true`
   - Verify `rem_id` format (should be `xx:xxxxxx`)
   - Check that REM and FAN are on the same RF network

### "REM traffic unmatched"

**Symptoms**: REM is sending packets but they're not being matched to a FAN.

**Diagnostic steps**:

1. Check unmatched traffic counter:
   ```python
   {{ state_attr('sensor.ramses_extras_diagnostics', 'unmatched_remote_count') }}
   ```

2. Get unmatched traffic details:
   ```yaml
   # WebSocket command
   {
     "type": "ramses_extras/get_unmatched_traffic",
     "limit": 10
   }
   ```

3. **Resolution**:
   - If you see consistent unmatched traffic with a `fan_id`, create a binding
   - Check if REM device ID matches your binding configuration
   - Enable debug logging to see raw packets

### "Binding conflict detected"

**Symptoms**: Error message about REM assigned to multiple FANs.

**Resolution**:

1. List all bindings to find conflicts:
   ```yaml
   # WebSocket command
   {
     "type": "ramses_extras/list_bindings"
   }
   ```

2. Edit configuration to ensure each REM is bound to only one FAN

3. Or use conflict detection API:
   ```yaml
   # WebSocket command
   {
     "type": "ramses_extras/detect_conflicts"
   }
   ```

### "Arbiter not updating from remote"

**Symptoms**: REM works physically but HA arbiter state doesn't change.

**Checks**:

1. Verify arbiter is enabled:
   ```python
   {{ states('sensor.fan_arbiter_state') }}
   ```

2. Check for duplicate handling:
   - REM packets may be debounced (normal for repeated packets)
   - Wait 2-3 seconds after pressing for state to update

3. Ensure `extras_control_enabled` is true for the FAN

## Testing Checklist

Use this checklist when testing remote bindings:

- [ ] Binding configured and enabled
- [ ] REM device is visible in `ramses_cc`
- [ ] Press REM Auto button → HA state updates to Auto
- [ ] Press REM speed buttons → HA speed updates
- [ ] Press REM Away → HA shows Away mode
- [ ] Wait 5 seconds → no duplicate commands sent
- [ ] HA offline test: REM still controls FAN physically
- [ ] HA online: state reconciles to observed FAN state

## Advanced: Binding Suggestions

The system can suggest bindings based on observed traffic:

```yaml
# WebSocket command
{
  "type": "ramses_extras/get_binding_suggestions",
  "fan_id": "32:153289"  # Optional: filter by FAN
}
```

Suggestions appear after observing 3+ packets from an unbound REM targeting a specific FAN.

## Device ID Formats

- **FAN IDs**: `32:xxxxxx` (e.g., `32:153289`)
- **REM IDs**: `37:xxxxxx` (e.g., `37:169161`)

Always use canonical format with colon (`:`) in configuration. Legacy format with underscore (`_`) is automatically converted.
