# Simulator HA (ha-sim)

Isolated Home Assistant instance for testing the **device_simulator** feature
without affecting real hardware.

## Setup

### 1. Create the config directory

```bash
mkdir -p /home/willem/docker_files/ha-sim/config
```

### 2. Copy docker-compose.yml

```bash
cp deployments/ha-sim/docker-compose.yml /home/willem/docker_files/ha-sim/
```

Or use directly from the repo (the `docker compose` command accepts a `-f` flag):

```bash
docker compose -f /home/willem/dev/ramses_extras/deployments/ha-sim/docker-compose.yml up -d
```

### 3. Deploy components

```bash
cd /home/willem/dev/ramses_rf    && make install_rf-sim
cd /home/willem/dev/ramses_cc    && make install-sim
cd /home/willem/dev/ramses_extras && make install-sim
docker restart ha-sim
```

### 4. Configure ramses_cc in ha-sim

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
- HA runs internally on port 8123, mapped to host port 8124
- Config is stored in `/home/willem/docker_files/ha-sim/config/`
- The `ramses/simulator/*` MQTT topics are used exclusively by the simulator
