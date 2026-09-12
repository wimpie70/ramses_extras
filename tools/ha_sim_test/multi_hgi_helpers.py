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
    container: str = "ha-sim",
    hgi_primary: str = "18:001234",
    hgi_secondary: str = "18:149488",
    mqtt_url: str = "mqtt://localhost:1884/RAMSES/GATEWAY_SIM/18:149488",
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

    :param container: Docker container name.
    :param hgi_primary: Primary HGI device ID.
    :param hgi_secondary: Secondary HGI device ID.
    :param mqtt_url: MQTT URL for the secondary HGI.
    :param token: HA auth token.
    :param ha_url: HA URL.
    :return: True if the config was updated successfully.
    """
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
        sp['port_name'] = 'mqtt://localhost:1884/RAMSES/GATEWAY_SIM/{hgi_primary}'
        e['options']['serial_port'] = sp
        changed = True
    break
if changed:
    json.dump(d, open(p, 'w'), indent=2)
print(json.dumps({{'changed': changed}}))
"""
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", code],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
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
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", read_schema_code],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
        schema = data["schema"]
        known_list = data["known_list"]
    except json.JSONDecodeError, IndexError, KeyError:
        return False

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
        # Wait for the MQTT pool to connect both children.
        # The profile load triggers a ramses_cc reload, which takes
        # ~1-2s for the MQTT pool to connect both HGIs.
        import asyncio as _asyncio

        await _asyncio.sleep(3)
        return True
    except Exception:
        return False


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
    container: str = "ha-sim",
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
    from .helpers import ws_send

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
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", read_code],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
        schema = data["schema"]
        known_list = data["known_list"]
    except json.JSONDecodeError, IndexError, KeyError:
        return False

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
        # Wait for the MQTT pool to reconnect after the reload.
        import asyncio as _asyncio

        await _asyncio.sleep(3)
        return True
    except Exception:
        return False
