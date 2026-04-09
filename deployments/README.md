# Deployments

Helper files and instructions for deploying **ramses_extras** (and its dependencies)
to Home Assistant instances.

## Two HA instances

| Instance | Purpose                    | Port | Container |
| -------- | -------------------------- | ---- | --------- |
| `hass`   | Production (real hardware) | 8123 | `hass`    |
| `ha-sim` | Device Simulator testing   | 8124 | `ha-sim`  |

Both share the same MQTT broker (port 1883). They use separate MQTT topic namespaces:

- Production: `ramses/gateway/...`
- Simulator: `ramses/simulator/...`

## Directory layout

```
deployments/
├── README.md               # This file
├── ha-sim/                 # Simulator HA container setup
│   ├── docker-compose.yml  # Docker Compose for ha-sim
│   └── README.md
└── makefile-targets/       # Reference for make targets across repos
    └── README.md
```

## Quick start — Simulator HA

```bash
# 1. Create config directory
mkdir -p /home/willem/docker_files/ha-sim/config

# 2. Start the container
cd /home/willem/docker_files/ha-sim
docker compose up -d

# 3. Deploy all components (from their respective repos)
cd /home/willem/dev/ramses_rf    && make install_rf-sim
cd /home/willem/dev/ramses_cc    && make install-sim
cd /home/willem/dev/ramses_extras && make install-sim

# 4. Restart to load
docker restart ha-sim
```

Access at: http://localhost:8124

## Deploying to production HA

```bash
cd /home/willem/dev/ramses_rf    && make install_rf
cd /home/willem/dev/ramses_cc    && make install
cd /home/willem/dev/ramses_extras && make install
docker restart hass
```
