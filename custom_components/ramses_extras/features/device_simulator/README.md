# Device Simulator

Simulates RAMSES devices for testing without hardware. Provides a virtual gateway that injects events into the `ramses_cc_message` bus and supports scenario-based testing.

## Prerequisites

### 1. MQTT Integration in ha-sim

The simulator requires Home Assistant MQTT integration configured in `configuration.yaml` or UI:

```yaml
mqtt:
  broker: 192.168.40.11  # Replace with your MQTT broker IP
  port: 1883
  username: "your_username"  # Replace with your MQTT username
  password: "your_password"  # Replace with your MQTT password
```

### 2. MQTT Broker Permissions

The MQTT user must have subscribe/publish rights to:
- `RAMSES/GATEWAY_SIM/#` (simulator namespace)

Same broker credentials as production are typically used.

### 3. Port Configuration

ha-sim uses port **8124** (not 8123) to avoid conflict with production HA:

```yaml
http:
  server_port: 8124
```

## Automatic Isolation

When the device_simulator feature is enabled, it **automatically enforces isolation** from production devices:

1. Detects if ramses_cc is using production MQTT topics
2. Reconfigures ramses_cc to use isolated namespace:
   - **Topic**: `RAMSES/GATEWAY_SIM`
   - **HGI**: `18:001234` (fake, never collides with hardware)
3. Reloads ramses_cc to apply changes

**Topic namespace details:**
- ramses_rf requires topic prefix `RAMSES/GATEWAY` (strict validation)
- The `_SIM` suffix (`RAMSES/GATEWAY_SIM`) passes validation while providing complete isolation
- Exactly 3 path segments required: `RAMSES/GATEWAY_SIM/18:001234`

**Isolation behavior:**
- Production devices: `RAMSES/GATEWAY/18:xxxxxx`
- Simulator: `RAMSES/GATEWAY_SIM/18:001234`
- Zero crosstalk between namespaces

## Deployment

Use the Makefile targets for deployment:

```bash
# Deploy to ha-sim container and restart
make install-sim && docker restart ha-sim

# Or separately:
make install-sim    # Deploy files to /home/willem/docker_files/ha-sim/config/
docker restart ha-sim
```

### Verification

Check logs for successful isolation:

```bash
docker logs ha-sim 2>&1 | grep -iE "simulator isolation|GATEWAY_SIM|endpoint connected"
```

Expected output:
```
ramses_cc already configured for simulator isolation
Simulator MQTT endpoint connected. sub=RAMSES/GATEWAY_SIM/18:001234/tx pub=RAMSES/GATEWAY_SIM/18:001234/rx
```

## Architecture

- **Device Database**: Parses `ramses_rf/tests/fixtures/regression_packets_sorted.txt` for message patterns
- **Virtual Gateway**: Injects events into `ramses_cc_message` bus
- **Scenario Engine**: Device playback, flooding, timeout, conversation tests
- **WebSocket API**: Device simulator and scenario builder UI cards

## Services

The feature registers these Home Assistant services:
- `ramses_extras.device_simulator_import_user_config` - Import ramses_cc config profiles
- `ramses_extras.device_simulator_load_scenario` - Load test scenarios
- `ramses_extras.device_simulator_start_scenario` - Start scenario playback
- `ramses_extras.device_simulator_stop_scenario` - Stop scenario playback
