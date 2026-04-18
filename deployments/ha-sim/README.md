# Simulator HA (ha-sim)

Isolated Home Assistant instance for testing the **device_simulator** feature
without affecting real hardware.

## Setup

### 1. Create the config directory

```bash
# Set your preferred path (adjust as needed)
export HA_SIM_CONFIG=/path/to/your/ha-sim/config
mkdir -p $HA_SIM_CONFIG
```

### 2. Copy docker-compose.yml and configuration

```bash
# Copy from the ramses_extras repository
cp /path/to/ramses_extras/deployments/ha-sim/docker-compose.yml $HA_SIM_CONFIG/../
cp /path/to/ramses_extras/deployments/ha-sim/configuration.yaml.example $HA_SIM_CONFIG/configuration.yaml
```

**Important:** The `configuration.yaml` sets the HTTP port to 8124. Without this, HA defaults to 8123 and conflicts with your production HA.

### 3. Start the container

```bash
cd $HA_SIM_CONFIG/..
docker compose up -d
```

Or with explicit environment variable:

```bash
HA_SIM_CONFIG=/path/to/your/ha-sim/config docker compose -f docker-compose.yml up -d
```

### 4. Deploy components

Set the `HA_SIM_CONFIG` environment variable in the Makefile or pass it:

```bash
cd /path/to/ramses_rf    && HA_SIM_CONFIG=/path/to/ha-sim/config make install-sim
cd /path/to/ramses_cc    && HA_SIM_CONFIG=/path/to/ha-sim/config make install-sim
cd /path/to/ramses_extras && HA_SIM_CONFIG=/path/to/ha-sim/config make install-sim
docker restart ha-sim
```

Or edit the Makefile to set `HA_SIM_CONFIG` permanently.

### 5. Configure ramses_cc in ha-sim

On first run, go to http://localhost:8124 and set up ramses_cc.
Point it at the MQTT broker (same host, port 1883) but use a different
HGI ID (e.g. `18:001234`) so it doesn't conflict with production.

## Ports

| Service           | Port |
| ----------------- | ---- |
| Home Assistant UI | 8124 |
| MQTT (shared)     | 1883 |

## Notes

- Uses `network_mode: host` so it can reach the MQTT broker at `localhost:1883`
- HA runs on port 8124 (configured in `configuration.yaml` to avoid conflict with production HA on 8123)
- The `RAMSES/GATEWAY_SIM/*` MQTT topics are used exclusively by the simulator
- Config path is configurable via `HA_SIM_CONFIG` environment variable (defaults to `./config`)
- Timezone is configurable via `TZ` environment variable (defaults to `Europe/Amsterdam`)
