# AI Agent Instructions for ramses_extras

The canonical coding standards, guardrails, and behavioural rules for
AI/LLM contributors live in the repo itself. **You MUST read both of
these files before working on ramses_extras:**

- **`LLM_INSTRUCTIONS.md`** (repo root) — behavioural rules, guardrails,
  identity/tone, no-advertising, wait-for-approval, PR framing,
  architecture, backward compatibility.
- **`CONTRIBUTING.md`** (repo root) — coding standards, typing,
  docstrings, testing, tooling.

## Test Environments (Home Assistant instances)

- **`hass` (port 8123)**: the normal dev HA instance, used for day-to-day
  development and debugging.
- **`ha-sim` (port 8124)**: a dedicated simulation HA instance running in
  Docker. The `tools/ha_sim_test` tool makes use of the device simulator
  feature and runs against this instance.
- **Production HA**: runs on a separate server. Do not point dev tools or
  tests at it.

### MQTT connectivity (recurring gotcha)

`ha-sim` and `ha-sim-mqtt` both run on Docker's **host network**. This means
`ha-sim` must use `localhost:1884` for its MQTT broker address — **not**
`host.docker.internal:1884` (which only works for bridge-network containers
like the parallel clones `ha-sim-2`, `ha-sim-3`).

If you see `MQTT connection failed` or `Transport did not bind to Prot`
errors in the ha-sim log, check the config entry:

```
docker exec ha-sim python3 -c "
import json; d=json.load(open('/config/.storage/core.config_entries'))
for e in d['data']['entries']:
    if e['domain']=='ramses_cc': print(e['options']['serial_port']['port_name'])
    if e['domain']=='mqtt': print(e['data']['broker'])
"
```

If it says `host.docker.internal`, fix it:

```
docker exec ha-sim python3 -c "
import json; p='/config/.storage/core.config_entries'; d=json.load(open(p))
for e in d['data']['entries']:
    if e['domain']=='ramses_cc':
        e['options']['serial_port']['port_name']='mqtt://localhost:1884/RAMSES/GATEWAY_SIM/18:001234'
    if e['domain']=='mqtt': e['data']['broker']='localhost'
json.dump(d, open(p,'w'), indent=2)
" && docker restart ha-sim
```

The parallel runner (`tools/ha_sim_test/parallel.py`) has a defensive
`_ensure_localhost_mqtt()` check that runs after every config switch, but
a crashed parallel run can still leave a stale config. The canonical config
files (`core.config_entries.minimal.json` and `core.config_entries.full.json`
in `tools/ha_sim_test/ha_configs/`) both use `localhost` for ha-sim.

### Integration Tester (install PRs/branches/commits from GitHub)

Both `hass` and `ha-sim` have the
[Integration Tester](https://github.com/raman325/ha-integration-tester)
custom integration installed. It lets you install custom integrations from
GitHub URLs (PRs, branches, or specific commits) via the HA UI:

- Go to **Settings > Devices & Services > Add Integration > "Integration Tester"**
- Enter a URL like `github.com/ramses-rf/ramses_cc/pull/1029`
- It downloads the PR's files to `custom_components/<domain>/` and prompts
  you to restart

Supported URL formats:

- `github.com/owner/repo` — default branch
- `github.com/owner/repo/tree/branch-name` — specific branch
- `github.com/owner/repo/pull/123` — pull request
- `github.com/owner/repo/commit/abc123` — specific commit

**What works:**

- `ramses_cc` and `ramses_extras` — installed as custom components on both
  containers. No bind mounts for these on either container (removed from
  ha-sim's `docker-compose.yml`).

**What doesn't work yet:**

- `ramses_rf` — it's a pip package, not a custom component, so
  integration_tester can't install it. Both containers have a bind mount
  at `/config/ramses_rf` (from `/home/willem/dev/ramses_rf`). To test a
  specific ramses_rf PR/branch:
  ```
  docker exec hass bash -c "cd /config/ramses_rf && git fetch origin && git checkout <branch-or-commit>"
  docker restart hass
  ```
  Feature request filed for pip package support:
  https://github.com/raman325/ha-integration-tester/issues

**HACS note:** `ramses_cc` is removed from HACS tracking on both containers
(managed by integration_tester instead). `ramses_extras` remains in HACS.
HACS may re-show `ramses_cc` as a dependency of `ramses_extras` — this is
harmless as long as you don't click "update" on it in HACS while testing
a PR via integration_tester.
