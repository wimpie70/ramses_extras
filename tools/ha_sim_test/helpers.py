"""HA REST/websocket API helpers and .storage readers.

These are module-level functions (not methods on RecipeContext) so recipes
can import exactly what they need.  Functions that require the current HA
token take it as an explicit parameter — recipes pass ``ctx.token``.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request

from .const import HA_PASS, HA_URL, HA_USER


def log_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# REST API helpers
# ---------------------------------------------------------------------------
def get_token() -> str:
    """Authenticate and return a bearer token."""
    data = json.dumps(
        {
            "client_id": HA_URL + "/",
            "handler": ["homeassistant", None],
            "redirect_uri": HA_URL + "/",
        }
    ).encode()
    req = urllib.request.Request(
        HA_URL + "/auth/login_flow",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    flow_id = json.loads(urllib.request.urlopen(req).read())["flow_id"]

    data = json.dumps(
        {
            "client_id": HA_URL + "/",
            "username": HA_USER,
            "password": HA_PASS,
        }
    ).encode()
    req = urllib.request.Request(
        f"{HA_URL}/auth/login_flow/{flow_id}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    auth_code = json.loads(urllib.request.urlopen(req).read())["result"]

    data = (
        f"grant_type=authorization_code&code={auth_code}&client_id={HA_URL}/"
    ).encode()
    req = urllib.request.Request(
        HA_URL + "/auth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def call_service(
    token: str, domain: str, service: str, data: dict | None = None
) -> dict:
    """Call a HA service and return the response.

    Retries up to 3 times with 5s backoff for transient connection errors
    (HA may be restarting after a profile reload).
    """
    url = f"{HA_URL}/api/services/{domain}/{service}"
    body = json.dumps(data or {}).encode()

    for attempt in range(3):
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
            resp = urllib.request.urlopen(req, timeout=30)
            content = resp.read()
            return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(f"HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            if attempt < 2:
                print(f"  call_service: retry {attempt + 1}/3 (connection refused)")
                time.sleep(5)
                continue
            raise RuntimeError(f"Connection failed after 3 retries: {e}") from e
    return {}  # unreachable


# ---------------------------------------------------------------------------
# Websocket API helpers (for profile loading)
# ---------------------------------------------------------------------------
async def ws_send(token: str, msg: dict) -> dict:
    """Send a websocket message and return the response."""
    import aiohttp

    uri = "ws://localhost:8124/api/websocket"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(uri) as ws:
            # Wait for auth_required
            auth_req = await ws.receive_json()
            if auth_req["type"] != "auth_required":
                raise RuntimeError(f"Expected auth_required, got {auth_req}")

            # Send auth
            await ws.send_json({"type": "auth", "access_token": token})
            auth_resp = await ws.receive_json()
            if auth_resp["type"] != "auth_ok":
                raise RuntimeError(f"Auth failed: {auth_resp}")

            # Send our message with an ID
            msg_with_id = {"id": 1, **msg}
            await ws.send_json(msg_with_id)

            # Read responses until we get our result
            while True:
                resp = await ws.receive_json()
                if resp.get("type") == "result" and resp.get("id") == 1:
                    if not resp.get("success", False):
                        raise RuntimeError(f"WS error: {resp.get('error', resp)}")
                    return resp.get("result", {})


async def load_profile_yaml(
    token: str,
    yaml_text: str,
    *,
    speed: float = 0.01,
    preload_schema: bool = True,
    reload_ramses: bool = True,
) -> dict:
    """Load a custom YAML profile via the device_simulator scenario.

    This avoids a full docker restart — ramses_cc is reloaded in-process
    with the new schema/known_list, preserving logs and saving ~20s.
    """
    return await ws_send(
        token,
        {
            "type": "ramses_extras/device_simulator/start_scenario",
            "scenario": "load_profile_yaml",
            "params": {
                "profile_yaml": yaml_text,
                "profile_name": f"test_{int(time.time())}",
                "speed": speed,
                "preload_schema": preload_schema,
                "reload_ramses": reload_ramses,
            },
        },
    )


# ---------------------------------------------------------------------------
# Storage helpers (read .storage files directly from container)
# ---------------------------------------------------------------------------
def get_schema() -> dict:
    """Get the config entry schema from .storage (API may be stale).

    Reads from .storage/core.config_entries.  During profile reloads the
    schema may be temporarily empty — use get_schema_retry() if you need
    to wait for it to be populated.
    """
    result = subprocess.run(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/core.config_entries"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    for e in data["data"]["entries"]:
        if e["domain"] == "ramses_cc":
            return e.get("options", {}).get("schema", {})
    return {}


def get_cached_schema() -> dict:
    """Get the cached schema from .storage/ramses_cc (client_state).

    This is the schema that ramses_cc's coordinator actually uses at runtime.
    It's more reliable than the config entry schema during reloads.
    """
    storage = get_ramses_storage()
    return storage.get("client_state", {}).get("schema", {})


def get_schema_retry(max_tries: int = 5, delay: int = 3) -> dict:
    """Get schema with retries (profile reload may be in progress).

    Tries config entry schema first, falls back to cached schema.
    """
    for i in range(max_tries):
        schema = get_schema()
        if schema:
            return schema
        # Try cached schema as fallback
        cached = get_cached_schema()
        if cached:
            return cached
        print(f"  (schema empty, retry {i + 1}/{max_tries}...)")
        time.sleep(delay)
    return {}


def get_known_list() -> dict:
    """Get the known_list from .storage."""
    result = subprocess.run(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/core.config_entries"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    for e in data["data"]["entries"]:
        if e["domain"] == "ramses_cc":
            return e.get("options", {}).get("known_list", {})
    return {}


def get_ramses_storage() -> dict:
    """Read .storage/ramses_cc directly from the container."""
    result = subprocess.run(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/ramses_cc"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout).get("data", {})


def write_ramses_storage(data: dict) -> bool:
    """Write the data portion back to .storage/ramses_cc in the container.

    The container MUST be stopped before calling this (HA's storage is not
    safe to write while the container is running — HA will overwrite our
    edit on shutdown).  Reads the current file to preserve the version/key
    envelope, replaces the ``data`` key, writes a temp file locally, then
    ``docker cp``s it into the container.

    :return: True if the write succeeded.
    """
    # Read the current full file (envelope: version/minor_version/key/data)
    result = subprocess.run(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/ramses_cc"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  write_ramses_storage: failed to read current file: {result.stderr[:80]}"
        )
        return False
    envelope = json.loads(result.stdout)
    envelope["data"] = data
    tmp_path = "/tmp/ramses_cc_storage.json"
    with open(tmp_path, "w") as f:
        json.dump(envelope, f, indent=2)
    cp = subprocess.run(
        ["docker", "cp", tmp_path, "ha-sim:/config/.storage/ramses_cc"],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        print(f"  write_ramses_storage: docker cp failed: {cp.stderr[:80]}")
        return False
    return True


def find_battery_entity(entities: list, device_id: str) -> dict | None:
    """Find the battery binary_sensor entity for a ramses device.

    The entity_id slug is built from the device class + id + ``battery_low``
    (e.g. ``binary_sensor.trv_04_150003_battery_low``), so we match on the
    normalized device id AND ``battery`` being present in the entity_id.
    """
    normalized = device_id.replace(":", "_")
    for s in entities:
        eid = s.get("entity_id", "")
        if "battery" in eid and normalized in eid:
            return s
    return None


def _get_ramses_cc_entry_id() -> str:
    """Get the config entry ID for ramses_cc from .storage."""
    result = subprocess.run(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/core.config_entries"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    data = json.loads(result.stdout)
    for e in data["data"]["entries"]:
        if e["domain"] == "ramses_cc":
            return e.get("entry_id", e.get("id", ""))
    return ""


def get_entities(token: str) -> list:
    """Get all entity states from the HA API.

    Returns all states — caller should use find_entity_for_device with a
    prefix to narrow matches to ramses_cc entities (e.g. "trv_", "ctl_").
    """
    req = urllib.request.Request(
        HA_URL + "/api/states",
        headers={"Authorization": f"Bearer {token}"},
    )
    return json.loads(urllib.request.urlopen(req).read())


def find_entity_for_device(
    entities: list, device_id: str, *, prefix: str = ""
) -> dict | None:
    """Find an entity that references the given device_id.

    :param prefix: Optional entity-type prefix (e.g. "trv_", "ctl_") to
        narrow the match and avoid false positives from zone entities.
    """
    normalized = device_id.replace(":", "_")
    needle = prefix + normalized if prefix else normalized
    for s in entities:
        if needle in s["entity_id"]:
            return s
    return None


def wait(seconds: int, msg: str = "") -> None:
    """Wait and print progress."""
    print(f"  Waiting {seconds}s {msg}...", end="", flush=True)
    time.sleep(seconds)
    print(" done")


async def get_persistent_notifications(token: str) -> list:
    """Get all persistent notifications from the HA websocket API.

    Returns a list of notification dicts (notification_id, title, message).
    Uses the websocket API because the REST /api/states endpoint does not
    expose persistent notifications in recent HA versions.
    """
    return await ws_send(token, {"type": "persistent_notification/get"})


def get_entity_attributes(token: str, device_id: str, prefix: str = "") -> dict:
    """Get the state attributes for an entity associated with a device.

    :param device_id: The ramses device ID (e.g. "32:150000")
    :param prefix: Optional entity-type prefix (e.g. "fan_", "remote_")
    :return: The attributes dict, or empty dict if entity not found.
    """
    entities = get_entities(token)
    entity = find_entity_for_device(entities, device_id, prefix=prefix)
    if entity is None:
        return {}
    return entity.get("attributes", {})
