# Makefile targets reference

Each repo has `make install-sim` (or `install_rf-sim` for ramses_rf) to deploy
to the simulator HA at `/home/willem/docker_files/ha-sim/config/`.

## Target overview

| Repo            | Target                | Deploys to                                   |
| --------------- | --------------------- | -------------------------------------------- |
| `ramses_extras` | `make install`        | `docker_files/hass/config/` (production)     |
| `ramses_extras` | `make install-sim`    | `docker_files/ha-sim/config/` (simulator)    |
| `ramses_cc`     | `make install`        | `docker_files/hass/config/` (production)     |
| `ramses_cc`     | `make install-sim`    | `docker_files/ha-sim/config/` (simulator)    |
| `ramses_rf`     | `make install_rf`     | `hass` container site-packages (production)  |
| `ramses_rf`     | `make install_rf-sim` | `ha-sim` container site-packages (simulator) |

## Full deploy to simulator

```bash
cd /home/willem/dev/ramses_rf    && make install_rf-sim
cd /home/willem/dev/ramses_cc    && make install-sim
cd /home/willem/dev/ramses_extras && make install-sim
docker restart ha-sim
```

## Full deploy to production

```bash
cd /home/willem/dev/ramses_rf    && make install_rf
cd /home/willem/dev/ramses_cc    && make install
cd /home/willem/dev/ramses_extras && make install
docker restart hass
```

## Local CI (run before pushing)

Each repo supports `make local-ci` which runs ruff + mypy + pytest:

```bash
cd /home/willem/dev/ramses_extras && make local-ci
cd /home/willem/dev/ramses_cc     && make local-ci
cd /home/willem/dev/ramses_rf     && make local-ci
```
