"""Shared constants for ha_sim_test recipes and infrastructure.

Module-level constants (``HA_URL``, ``HGI``, ``CTL``, ...) are retained as
defaults for backward compatibility with ``--parallel 1`` (single container).
For parallel runs, per-instance values are carried by :class:`InstanceConfig`
and propagated via a contextvar in :mod:`.helpers`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Default HA sim instance (single-container mode, backward compatible)
# ---------------------------------------------------------------------------
HA_URL = "http://localhost:8124"
HA_USER = "admin"
HA_PASS = "admin123"

# Default host path to the ha-sim config directory (bind mount source).
HA_SIM_CONFIG_DIR = "/home/willem/docker_files/ha-sim/config"

# MQTT broker connection string (shared across instances — topic isolation
# is via the HGI ID in the topic path).
#
# Local broker (port 1884) — isolated from production broker at
# 192.168.40.11:1883.
# Start:  cd ~/docker_files/ha-sim && \
#   docker compose -f docker-compose.mqtt.yml up -d
# Logs:   docker logs -f ha-sim-mqtt
MQTT_BROKER_URL = "mqtt://localhost:1884"
MQTT_TOPIC_NS = "RAMSES/GATEWAY_SIM"

# Sim device IDs (from system_config.py) — same across all parallel instances
# because MQTT topic namespaces are isolated per HGI ID.
HGI = "18:001234"
CTL = "01:150000"
TRV = "04:150003"  # zone 03 actuator
DHW = "07:150000"
FAN = "32:150000"
CO2 = "37:120000"
REM = "37:170000"


# ---------------------------------------------------------------------------
# Per-instance configuration (parallel mode)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InstanceConfig:
    """Configuration for a single ha-sim container instance.

    Instance 1 (the default) uses the original ``ha-sim`` container name,
    port 8124, and HGI ``18:001234`` — identical to pre-parallel behaviour.
    Instances 2+ use ``ha-sim-N``, incremented ports, and unique HGI IDs
    so each container gets its own MQTT topic namespace.
    """

    name: str  # container name, e.g. "ha-sim" or "ha-sim-2"
    port: int  # HA port, e.g. 8124
    ha_url: str  # e.g. "http://localhost:8124"
    ha_user: str = HA_USER
    ha_pass: str = HA_PASS
    hgi_id: str = HGI  # gateway ID for MQTT topic isolation
    mqtt_topic_ns: str = MQTT_TOPIC_NS
    config_dir: str = HA_SIM_CONFIG_DIR  # host path to bind-mounted /config
    # Device IDs — same across instances (MQTT topic isolation makes this safe)
    ctl: str = CTL
    trv: str = TRV
    fan: str = FAN
    rem: str = REM
    co2: str = CO2
    dhw: str = DHW
    # Extra tags for logging/reporting
    index: int = 1  # 1-based instance index

    @property
    def mqtt_url(self) -> str:
        """Full MQTT URL for this instance's ramses_cc serial port.

        Instance 1 (ha-sim) uses ``network_mode: host`` and can reach
        the broker at ``localhost:1884``.  Parallel instances (2+) use
        bridge networking and must use ``host.docker.internal:1884``.
        """
        broker = (
            MQTT_BROKER_URL
            if self.index <= 1
            else MQTT_BROKER_URL.replace("localhost", "host.docker.internal")
        )
        return f"{broker}/{self.mqtt_topic_ns}/{self.hgi_id}"

    @property
    def ws_url(self) -> str:
        """Websocket URL for this instance."""
        return f"ws://localhost:{self.port}/api/websocket"

    @property
    def storage_path(self) -> str:
        """Host path to .storage directory."""
        return f"{self.config_dir}/.storage"

    @staticmethod
    def default() -> InstanceConfig:
        """The default single-container instance (backward compatible)."""
        return InstanceConfig(
            name="ha-sim",
            port=8124,
            ha_url=HA_URL,
            hgi_id=HGI,
            config_dir=HA_SIM_CONFIG_DIR,
            index=1,
        )

    @staticmethod
    def for_index(i: int, *, base: str = "ha-sim", port: int = 8124) -> InstanceConfig:
        """Create config for the i-th parallel instance (1-based).

        Instance 1 uses the original ``ha-sim`` container (no suffix) for
        backward compatibility. Instances 2+ use ``{base}-{i}`` with
        incremented ports and unique HGI IDs (``18:00{i:02d}234``).
        """
        if i == 1:
            return InstanceConfig(
                name=base,
                port=port,
                ha_url=f"http://localhost:{port}",
                hgi_id=HGI,
                config_dir=HA_SIM_CONFIG_DIR,
                index=1,
            )
        inst_port = port + i - 1
        # Unique HGI ID per instance: 18:002234, 18:003234, ...
        # (6 hex digits — same length as the default 18:001234)
        hgi = f"18:00{i}234"
        # Config dir: /home/willem/docker_files/ha-sim/config-2, ...
        config_dir = f"{HA_SIM_CONFIG_DIR}-{i}"
        return InstanceConfig(
            name=f"{base}-{i}",
            port=inst_port,
            ha_url=f"http://localhost:{inst_port}",
            hgi_id=hgi,
            config_dir=config_dir,
            index=i,
        )


def make_instances(
    n: int, *, base: str = "ha-sim", port: int = 8124
) -> list[InstanceConfig]:
    """Create InstanceConfigs for N parallel containers."""
    return [InstanceConfig.for_index(i, base=base, port=port) for i in range(1, n + 1)]
