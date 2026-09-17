"""Helper to ensure multi-HGI pool config is set up in ha-sim.

The profile load resets the schema, removing _owner and _preferred_type
from HGI entries.  This helper loads a custom profile via the HA websocket
API that includes both HGIs, so the MQTT pool includes both as accepted
members.

Uses HA's native mqtt.publish service for LWT messages (no paho, issue 1119).
"""

from __future__ import annotations

import json
import subprocess
import urllib.request


async def ensure_multi_hgi_config(
    container: str = "",
    hgi_primary: str = "",
    hgi_secondary: str = "",
    mqtt_url: str = "",
    *,
    token: str = "",
    ha_url: str = "http://localhost:8124",
) -> bool:
    """Ensure the ramses_cc config has both HGIs with _owner set.

    Loads a custom profile via the HA websocket API that includes both
    HGIs in the known_list and schema (with _owner and _preferred_type set).
    This properly updates HA's in-memory config entries, unlike writing
    to the storage file directly.

    Also ensures additional_ports includes the secondary HGI's MQTT URL
    by writing to the storage file before the profile load (the profile
    loader preserves existing additional_ports).

    Empty ``container``/``hgi_*``/``mqtt_url`` values default to the
    current instance's values — this keeps the helper correct on
    parallel clone containers whose gateway IDs differ from the base
    ``ha-sim`` instance.

    :param container: Docker container name.
    :param hgi_primary: Primary HGI device ID.
    :param hgi_secondary: Secondary HGI device ID.
    :param mqtt_url: MQTT URL for the secondary HGI.
    :param token: HA auth token.
    :param ha_url: HA URL.
    :return: True if the config was updated successfully.
    """
    from .helpers import get_current_instance

    inst = get_current_instance()
    container = container or inst.name
    hgi_primary = hgi_primary or inst.hgi_id
    hgi_secondary = hgi_secondary or inst.hgi_id_2
    # The callback-driven child only uses the trailing HGI segment, but
    # keep the broker host correct per instance network mode anyway.
    mqtt_url = mqtt_url or f"{inst.mqtt_url.rsplit('/', 1)[0]}/{hgi_secondary}"

    # Step 1: Ensure additional_ports includes the secondary MQTT URL.
    # The profile loader preserves existing additional_ports, so we
    # write to the storage file before the profile load.
    code = f"""
import json
p = '/config/.storage/core.config_entries'
d = json.load(open(p))
changed = False
for e in d['data']['entries']:
    if e['domain'] != 'ramses_cc':
        continue
    ap = e['options'].get('additional_ports', [])
    # Keep this simulator helper deterministic: stale MQTT pool ports from
    # earlier recipes must not create unexpected third/fourth children.
    desired_ap = ['{mqtt_url}']
    if ap != desired_ap:
        e['options']['additional_ports'] = desired_ap
        changed = True
    # Also ensure serial_port points to the primary HGI's MQTT URL
    sp = e['options'].get('serial_port', {{}})
    if not sp.get('port_name', '').startswith('mqtt://'):
        sp['port_name'] = '{inst.mqtt_url}'
        e['options']['serial_port'] = sp
        changed = True
    break
if changed:
    json.dump(d, open(p, 'w'), indent=2)
print(json.dumps({{'changed': changed}}))
"""
    result = _docker_exec_retry(container, code)
    if result is None or result.returncode != 0:
        print(
            "  ensure_multi_hgi_config: storage write failed"
            + (f" — {result.stderr.strip()[:200]}" if result else "")
        )
        return False

    # Step 2: Load a custom profile via websocket that includes both HGIs.
    # This uses the same mechanism as the runner, so it properly updates
    # HA's in-memory config entries.
    from .helpers import ws_send

    # Read the current working schema from the config entry and add the
    # second HGI to it.  This ensures the schema format matches what
    # ramses_rf expects (stored_hotwater, zones, etc.) because it's
    # the same schema that was working before.
    read_schema_code = f"""
import json
p = '/config/.storage/core.config_entries'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] != 'ramses_cc':
        continue
    schema = dict(e['options'].get('schema', {{}}))
    # Remove HGI candidates left by earlier recipes.  This helper promises
    # a two-HGI pool, so retaining them creates 2/3 or 2/4 state and makes
    # the live failover recipes order-dependent.
    desired_hgis = {{'{hgi_primary}', '{hgi_secondary}'}}
    for dev_id in list(schema):
        if dev_id.startswith('18:') and dev_id not in desired_hgis:
            schema.pop(dev_id)
    # Set root _owner (required by _extract_pool_hgis_from_schema)
    schema['_owner'] = 'me'
    # Add both HGIs with _owner and _preferred_type, even after a
    # clean-schema recipe removed the primary entry.
    schema['{hgi_primary}'] = {{
        '_class': 'HGI',
        '_owner': 'me',
        '_preferred_type': 'mqtt',
    }}
    schema['{hgi_secondary}'] = {{
        '_class': 'HGI',
        '_owner': 'me',
        '_preferred_type': 'mqtt',
    }}
    # Build a known_list from the schema (HGI devices)
    known_list = {{}}
    for dev_id, cfg in schema.items():
        if dev_id.startswith('18:'):
            known_list[dev_id] = {{'class': 'HGI'}}
    # Add the CTL and other devices from the schema
    for dev_id, cfg in schema.items():
        if dev_id.startswith('18:'):
            continue
        cls = cfg.get('_class', '') if isinstance(cfg, dict) else ''
        if cls:
            known_list[dev_id] = {{'class': cls}}
    print(json.dumps({{'schema': schema, 'known_list': known_list}}))
    break
"""
    result = _docker_exec_retry(container, read_schema_code)
    if result is None or result.returncode != 0:
        print(
            "  ensure_multi_hgi_config: schema read failed"
            + (f" — {result.stderr.strip()[:200]}" if result else "")
        )
        return False
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
        schema = data["schema"]
        known_list = data["known_list"]
    except (json.JSONDecodeError, IndexError, KeyError) as err:
        print(f"  ensure_multi_hgi_config: schema parse failed — {err}")
        return False

    _seed_sim_devices(schema, known_list)

    # Build the YAML profile
    import yaml as _yaml

    profile_dict = {
        "known_list": known_list,
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    profile_yaml = _yaml.dump(
        profile_dict,
        default_flow_style=False,
        sort_keys=False,
    )
    # The device_simulator may not be initialized yet when a preceding
    # recipe restarted the container ("Simulator not initialized"), so
    # retry the profile load a few times.
    last_err: Exception | None = None
    for _attempt in range(4):
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/start_scenario",
                    "scenario": "load_profile_yaml",
                    "params": {
                        "profile_yaml": profile_yaml,
                        "profile_name": f"multi_hgi_{int(__import__('time').time())}",
                        "speed": 0.01,
                        "preload_schema": True,
                        "reload_ramses": True,
                        "enable_eavesdrop": False,
                    },
                },
            )
            break
        except Exception as err:
            last_err = err
            import asyncio as _asyncio

            await _asyncio.sleep(2)
    else:
        print(f"  ensure_multi_hgi_config: profile load failed — {last_err}")
        return False

    # The profile load triggers a ramses_cc reload, which takes
    # ~1-2s for the MQTT pool to connect both HGIs.
    import asyncio as _asyncio

    await _asyncio.sleep(3)
    return True


def _docker_exec_retry(
    container: str, code: str, *, attempts: int = 4, timeout: int = 20
) -> subprocess.CompletedProcess | None:
    """Run ``docker exec`` with retries.

    ``core.config_entries`` is rewritten by HA during startup — reading
    it mid-write raises ``json.JSONDecodeError`` in the container, and
    dockerd itself can stall under parallel load.  Retrying keeps
    ``ensure_multi_hgi_config`` deterministic when a preceding recipe
    just restarted the container.
    """
    import time as _time

    result: subprocess.CompletedProcess | None = None
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                ["docker", "exec", container, "python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0:
            return result
        if attempt < attempts - 1:
            _time.sleep(2)
    return result


def publish_mqtt_lwt(
    container: str,
    topic: str,
    status: str,
    broker: str = "localhost",
    port: int = 1884,
    token: str = "",
    ha_url: str = "http://localhost:8124",
) -> bool:
    """Publish an MQTT LWT status message via HA's native mqtt.publish service.

    Uses HA's built-in MQTT integration (homeassistant.components.mqtt),
    never paho (issue 1119 no-paho invariant).

    :param container: Docker container name (unused — HA service is HTTP).
    :param topic: MQTT topic (e.g. 'RAMSES/GATEWAY_SIM/18:149488').
    :param status: Status message ('online' or 'offline').
    :param broker: Unused (kept for API compat).
    :param port: Unused (kept for API compat).
    :param token: HA auth token.
    :param ha_url: HA URL.
    :return: True if published successfully.
    """
    url = f"{ha_url}/api/services/mqtt/publish"
    body = json.dumps(
        {
            "topic": topic,
            "payload": status,
            "retain": True,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


async def set_preferred_type_via_profile(
    container: str = "",
    hgi_id: str = "",
    ptype: str = "mqtt",
    *,
    token: str = "",
    ha_url: str = "http://localhost:8124",
) -> bool:
    """Set _preferred_type for an HGI by loading a profile with the change.

    HA caches config entries in memory, so writing to the storage file
    doesn't update the running instance.  Instead, we load a profile
    via the websocket API that includes the _preferred_type change.
    This uses hass.config_entries.async_update_entry internally,
    which properly updates the in-memory config.

    :param container: Docker container name.
    :param hgi_id: HGI device ID to update.
    :param ptype: Preferred type ('mqtt' or 'usb').
    :param token: HA auth token.
    :param ha_url: HA URL.
    :return: True if the profile was loaded successfully.
    """
    from .helpers import get_current_instance, ws_send

    container = container or get_current_instance().name

    # Read the current schema from the config entry and update the
    # _preferred_type for the specified HGI.
    read_code = f"""
import json
p = '/config/.storage/core.config_entries'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] != 'ramses_cc':
        continue
    schema = dict(e['options'].get('schema', {{}}))
    # Set root _owner (required by _extract_pool_hgis_from_schema)
    schema['_owner'] = 'me'
    if '{hgi_id}' in schema and isinstance(schema['{hgi_id}'], dict):
        schema['{hgi_id}']['_preferred_type'] = '{ptype}'
    # Build known_list from schema
    known_list = {{}}
    for dev_id, cfg in schema.items():
        if dev_id.startswith('18:'):
            known_list[dev_id] = {{'class': 'HGI'}}
        elif isinstance(cfg, dict) and '_class' in cfg:
            known_list[dev_id] = {{'class': cfg['_class']}}
    print(json.dumps({{'schema': schema, 'known_list': known_list}}))
    break
"""
    result = _docker_exec_retry(container, read_code)
    if result is None or result.returncode != 0:
        print(
            "  set_preferred_type_via_profile: schema read failed"
            + (f" — {result.stderr.strip()[:200]}" if result else "")
        )
        return False
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
        schema = data["schema"]
        known_list = data["known_list"]
    except (json.JSONDecodeError, IndexError, KeyError) as err:
        print(f"  set_preferred_type_via_profile: parse failed — {err}")
        return False

    _seed_sim_devices(schema, known_list)

    import yaml as _yaml

    profile_dict = {
        "known_list": known_list,
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    profile_yaml = _yaml.dump(
        profile_dict,
        default_flow_style=False,
        sort_keys=False,
    )

    last_err: Exception | None = None
    for _attempt in range(4):
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/start_scenario",
                    "scenario": "load_profile_yaml",
                    "params": {
                        "profile_yaml": profile_yaml,
                        "profile_name": f"switch_{int(__import__('time').time())}",
                        "speed": 0.01,
                        "preload_schema": True,
                        "reload_ramses": True,
                        "enable_eavesdrop": False,
                    },
                },
            )
            break
        except Exception as err:
            last_err = err
            import asyncio as _asyncio

            await _asyncio.sleep(2)
    else:
        print(f"  set_preferred_type_via_profile: profile load failed — {last_err}")
        return False

    # Wait for the MQTT pool to reconnect after the reload.
    import asyncio as _asyncio

    await _asyncio.sleep(3)
    return True


def _seed_sim_devices(schema: dict, known_list: dict) -> None:
    """Seed the standard sim devices into ``schema`` and ``known_list``.

    A clean-schema recipe (or a ``preload_schema`` wipe) can leave the
    stored schema with only HGI entries.  Since the multi-HGI profile
    stops device broadcasts, ``enforce_known_list`` would then reject
    every ``send_packet`` to e.g. the CTL with HTTP 500 — and nothing
    would ever re-learn the device.  Seeding keeps the environment
    deterministic regardless of which recipe ran before.
    """
    from .profile import get_mixed_kl

    for dev_id, cfg in get_mixed_kl().items():
        if dev_id.startswith("18:"):
            continue  # HGIs are handled explicitly by the caller
        known_list.setdefault(dev_id, dict(cfg))
        if isinstance(cfg, dict) and cfg.get("class"):
            schema.setdefault(dev_id, {"_class": cfg["class"]})


def hgi_online_states(token: str, hgi_ids: list[str]) -> dict[str, bool]:
    """Return ``{hgi_id: online}`` from the pool's per-HGI binary sensors.

    Reads entity states instead of grepping "N/M connected" log lines —
    foreign HGIs discovered via the shared MQTT broker appear as
    receive-only pool children, so the M count is nondeterministic under
    parallel runs while the per-HGI sensor is not.
    """
    from .helpers import get_entities

    entities = get_entities(token)
    states: dict[str, bool] = {}
    for hgi_id in hgi_ids:
        needle = hgi_id.replace(":", "_")
        # Reloads can orphan stale entities and force the live entity to
        # a ``_2``-suffixed entity_id (registry name collision).  Match
        # every candidate and prefer a live state over ``unavailable``
        # orphans: "on" wins, then any live "off", else offline.
        matches = [
            s.get("state")
            for s in entities
            if s["entity_id"].startswith("binary_sensor.")
            and needle in s["entity_id"]
            and "online" in s["entity_id"]
        ]
        states[hgi_id] = "on" in matches
    return states


def wait_for_hgi_states(
    token: str,
    hgi_ids: list[str],
    *,
    want: bool = True,
    timeout: float = 30.0,
) -> dict[str, bool]:
    """Poll :func:`hgi_online_states` until all HGIs match ``want``.

    30s default: under parallel load the MQTT bridge reconnect and
    entity re-creation after a reload can take >15s while the pool
    itself is already functional.

    :returns: the last polled ``{hgi_id: online}`` mapping.
    """
    import time as _time

    deadline = _time.monotonic() + timeout
    states = hgi_online_states(token, hgi_ids)
    while _time.monotonic() < deadline and any(
        states.get(hgi) is not want for hgi in hgi_ids
    ):
        _time.sleep(1)
        states = hgi_online_states(token, hgi_ids)
    return states
