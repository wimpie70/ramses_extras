# Deployments

Helper files and instructions for deploying **ramses_extras** (and its dependencies)
to Home Assistant instances.

## Two HA instances

| Instance | Purpose                    | Port | Container |
| -------- | -------------------------- | ---- | --------- |
| `hass`   | Production (real hardware) | 8123 | `hass`    |
| `ha-sim` | Device Simulator testing   | 8124 | `ha-sim`  |

Both share the same MQTT broker (port 1883). They use separate MQTT topic namespaces:

- Production: `RAMSES/GATEWAY/...`
- Simulator: `RAMSES/GATEWAY_SIM/...`

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
# 1. Set config path and create directory
export HA_SIM_CONFIG=/path/to/your/ha-sim/config
mkdir -p $HA_SIM_CONFIG

# 2. Copy docker-compose.yml and configuration.yaml
cp /path/to/ramses_extras/deployments/ha-sim/docker-compose.yml $HA_SIM_CONFIG/../
cp /path/to/ramses_extras/deployments/ha-sim/configuration.yaml.example $HA_SIM_CONFIG/configuration.yaml

# 3. Start the container
cd $HA_SIM_CONFIG/..
docker compose up -d

# 4. Deploy all components (from their respective repos)
cd /path/to/ramses_rf    && HA_SIM_CONFIG=$HA_SIM_CONFIG make install-sim
cd /path/to/ramses_cc    && HA_SIM_CONFIG=$HA_SIM_CONFIG make install-sim
cd /path/to/ramses_extras && HA_SIM_CONFIG=$HA_SIM_CONFIG make install-sim

# 5. Restart to load
docker restart ha-sim
```

Access at: http://localhost:8124

**Note**: The `HA_SIM_CONFIG` environment variable can be set in your shell profile or passed inline. See `ha-sim/README.md` for detailed instructions.

## Deploying to production HA

```bash
cd /path/to/ramses_rf    && make install
cd /path/to/ramses_cc    && make install
cd /path/to/ramses_extras && make install
docker restart hass
```
