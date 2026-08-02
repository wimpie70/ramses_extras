"""HA REST/websocket API helpers and .storage readers.

These are module-level functions (not methods on RecipeContext) so recipes
can import exactly what they need.  Functions that require the current HA
token take it as an explicit parameter — recipes pass ``ctx.token``.

The target container (name, port, URL, config dir) is determined by the
current :class:`InstanceConfig` stored in a contextvar.  This is set
automatically when a :class:`RecipeContext` is constructed (see
:mod:`.base`), and by the parallel runner when it launches a per-container
asyncio task.  In single-container mode (``--parallel 1``) the default
instance (``ha-sim`` on port 8124) is used — identical to pre-parallel
behaviour.
"""

from __future__ import annotations

import contextvars
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .const import InstanceConfig

#: Scale factors for the two kinds of waits in the test suite.
#:
#: * ``WAIT_SCALE_BLIND`` — applied to every fixed ``wait()``/``ctx.wait()``
#:   blind sleep.  These are the dominant cost (80 of 138 calls use 5s,
#:   totalling ~400s), and also the riskiest to cut: 5s is already a
#:   deliberate "let MQTT/HA settle" pause, so 5→0.5 is a 10x cut on
#:   something that may genuinely need 2-3s.
#:
#: * ``WAIT_SCALE_POLL`` — applied to every ``wait_for()`` timeout ceiling.
#:   These poll and return as soon as the condition is met, so the
#:   timeout is just a safety margin.  On the simulator, conditions
#:   typically resolve in 2-3s; if they haven't, the test has probably
#:   failed.  Scaling 30s→3s just tightens the failure ceiling — safe to
#:   cut aggressively.
#:
#: Both default to ``HA_SIM_TEST_WAIT_SCALE`` (the legacy single knob) if
#: set, otherwise 1.0.  The per-bucket env vars take precedence when set.
WAIT_SCALE_BLIND: float = float(
    os.environ.get(
        "HA_SIM_TEST_WAIT_SCALE_BLIND",
        os.environ.get("HA_SIM_TEST_WAIT_SCALE", "1.0"),
    )
)
WAIT_SCALE_POLL: float = float(
    os.environ.get(
        "HA_SIM_TEST_WAIT_SCALE_POLL",
        os.environ.get("HA_SIM_TEST_WAIT_SCALE", "1.0"),
    )
)

#: Global minimum floors (seconds, pre-scaling) that all scaled waits respect.
#: Unlike the per-call ``floor=`` parameter (which takes the max with these),
#: these apply to *every* wait in the suite.  Set via env var or CLI flag.
#:
#: ``WAIT_FLOOR_BLIND`` ensures every blind sleep is at least N seconds real
#: time, regardless of ``WAIT_SCALE_BLIND``.  Useful when running at aggressive
#: scale factors: e.g. ``--wait-scale-blind 0.5 --wait-floor-blind 3`` means
#: ``wait(5)`` → max(2.5, 3) = 3s, ``wait(10)`` → max(5, 3) = 5s, but
#: ``wait(2)`` → max(1, 3) = 3s (slightly over, but safe).
#:
#: ``WAIT_FLOOR_POLL`` does the same for ``wait_for()`` timeout ceilings.
#: The per-call ``floor=`` parameter (e.g. ``wait_for_ha_ready`` uses floor=10)
#: takes the max with this global floor.
WAIT_FLOOR_BLIND: float = float(os.environ.get("HA_SIM_TEST_WAIT_FLOOR_BLIND", "0"))
WAIT_FLOOR_POLL: float = float(os.environ.get("HA_SIM_TEST_WAIT_FLOOR_POLL", "0"))

# ---------------------------------------------------------------------------
# Current instance contextvar — asyncio-safe per-task instance selection
# ---------------------------------------------------------------------------
_current_instance: contextvars.ContextVar[InstanceConfig | None] = (
    contextvars.ContextVar("ha_sim_instance", default=None)
)


def set_current_instance(
    inst: InstanceConfig,
) -> contextvars.Token[InstanceConfig | None]:
    """Set the current instance for this asyncio task/thread.

    Returns a token that can be used to restore the previous value.
    The parallel runner calls this at the start of each per-container task.
    """
    return _current_instance.set(inst)


def get_current_instance() -> InstanceConfig:
    """Return the current instance config (from contextvar)."""
    inst = _current_instance.get()
    if inst is None:
        from .const import InstanceConfig

        return InstanceConfig.default()
    return inst


def log_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# REST API helpers
# ---------------------------------------------------------------------------
def get_token() -> str:
    """Authenticate and return a bearer token."""
    inst = get_current_instance()
    ha_url = inst.ha_url
    data = json.dumps(
        {
            "client_id": ha_url + "/",
            "handler": ["homeassistant", None],
            "redirect_uri": ha_url + "/",
        }
    ).encode()
    req = urllib.request.Request(
        ha_url + "/auth/login_flow",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    flow_id = json.loads(urllib.request.urlopen(req).read())["flow_id"]

    data = json.dumps(
        {
            "client_id": ha_url + "/",
            "username": inst.ha_user,
            "password": inst.ha_pass,
        }
    ).encode()
    req = urllib.request.Request(
        f"{ha_url}/auth/login_flow/{flow_id}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    auth_code = json.loads(urllib.request.urlopen(req).read())["result"]

    data = (
        f"grant_type=authorization_code&code={auth_code}&client_id={ha_url}/"
    ).encode()
    req = urllib.request.Request(
        ha_url + "/auth/token",
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
    ha_url = get_current_instance().ha_url
    url = f"{ha_url}/api/services/{domain}/{service}"
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
async def ws_send(token: str, msg: dict, *, retries: int = 2) -> dict:
    """Send a websocket message and return the response.

    Retries up to *retries* times with 3s backoff for transient timeouts
    and connection errors (common under parallel container contention
    where HA may be too busy to respond within the 30s websocket timeout).
    """
    import aiohttp

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await _ws_send_once(token, msg)
        except (TimeoutError, aiohttp.ClientError, RuntimeError) as e:
            last_err = e
            err = str(e)
            # Don't retry on "unknown_command" (ramses_extras not loaded yet)
            # or on genuine WS error responses — only retry on timeouts and
            # connection issues.
            if "unknown_command" in err or "WS error:" in err:
                raise
            if attempt < retries:
                import asyncio as _asyncio

                print(
                    f"  ws_send: retry {attempt + 1}/{retries}"
                    f" ({type(e).__name__}: {err[:60]})"
                )
                await _asyncio.sleep(3)
    raise last_err  # type: ignore[misc]


async def _ws_send_once(token: str, msg: dict) -> dict:
    """Single websocket send attempt (no retry)."""
    import aiohttp

    uri = get_current_instance().ws_url
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(uri, timeout=30, receive_timeout=30) as ws:

            async def _recv_json() -> dict:
                """Receive a JSON message, handling CLOSE frames gracefully."""
                import json

                resp = await ws.receive(timeout=30)
                if resp.type == aiohttp.WSMsgType.CLOSE:
                    raise RuntimeError(f"WebSocket closed by server (code={resp.data})")
                if resp.type in (aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                    raise RuntimeError("WebSocket closed unexpectedly")
                if resp.type != aiohttp.WSMsgType.TEXT:
                    raise RuntimeError(f"Unexpected WS message type: {resp.type}")
                return json.loads(resp.data)

            # Wait for auth_required
            auth_req = await _recv_json()
            if auth_req["type"] != "auth_required":
                raise RuntimeError(f"Expected auth_required, got {auth_req}")

            # Send auth
            await ws.send_json({"type": "auth", "access_token": token})
            auth_resp = await _recv_json()
            if auth_resp["type"] != "auth_ok":
                raise RuntimeError(f"Auth failed: {auth_resp}")

            # Send our message with an ID
            msg_with_id = {"id": 1, **msg}
            await ws.send_json(msg_with_id)

            # Read responses until we get our result.
            # HA may close the websocket (e.g. during a reload) — handle
            # CLOSE frames gracefully instead of raising WSMessageTypeError.
            while True:
                data = await _recv_json()
                if data.get("type") == "result" and data.get("id") == 1:
                    if not data.get("success", False):
                        raise RuntimeError(f"WS error: {data.get('error', data)}")
                    return data.get("result", {})


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

    The created profile is tracked in the module-level ``_CREATED_PROFILES``
    set so it can be cleaned up by :func:`delete_test_profiles`.
    """
    profile_name = f"test_{int(time.time())}"
    result = await ws_send(
        token,
        {
            "type": "ramses_extras/device_simulator/start_scenario",
            "scenario": "load_profile_yaml",
            "params": {
                "profile_yaml": yaml_text,
                "profile_name": profile_name,
                "speed": speed,
                "preload_schema": preload_schema,
                "reload_ramses": reload_ramses,
            },
        },
    )
    _CREATED_PROFILES.add(profile_name)
    return result


# Track profiles created by load_profile_yaml for cleanup.
_CREATED_PROFILES: set[str] = set()


async def delete_test_profiles(token: str) -> int:
    """Delete all test profiles created during the test run.

    Called by the runner after each recipe and during teardown to prevent
    the user_profiles.json store from growing unboundedly.

    :return: Number of profiles deleted.
    """
    deleted = 0
    # Try deleting via the websocket API first (clean — updates in-memory store)
    for name in sorted(_CREATED_PROFILES):
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/delete_profile",
                    "profile": name,
                },
            )
            deleted += 1
        except Exception:
            pass
    _CREATED_PROFILES.clear()
    # Also clean up any leftover test_ profiles from previous runs by
    # editing the JSON store directly (the websocket API may not list them
    # if the store was reloaded).
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                get_current_instance().name,
                "python3",
                "-c",
                """
import json
path = '/root/.ramses_simulator/user_profiles.json'
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    raise SystemExit(0)
profiles = data.get('profiles', {})
removed = [k for k in list(profiles) if k.startswith('test_')]
for k in removed:
    del profiles[k]
if removed:
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
print(len(removed))
""",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        extra = int(result.stdout.strip() or "0")
        if extra:
            deleted += extra
    except Exception:
        pass
    return deleted


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
        [
            "docker",
            "exec",
            get_current_instance().name,
            "cat",
            "/config/.storage/core.config_entries",
        ],
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
    """Get the known_list from .storage.

    Phase 4: known_list is no longer stored in config entry options.
    It is derived from the schema.  This function now extracts device IDs
    from the schema (top-level device keys + TCS topology devices) and
    maps _-prefixed traits to their ramses_rf equivalents (class, alias,
    faked, bound, scheme) — matching what _derive_known_list_from_schema
    in coordinator.py produces.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            get_current_instance().name,
            "cat",
            "/config/.storage/core.config_entries",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    for e in data["data"]["entries"]:
        if e["domain"] == "ramses_cc":
            options = e.get("options", {})
            # Phase 4: check known_list first (backward compat), then schema
            if "known_list" in options:
                return options["known_list"]
            schema = options.get("schema", {})
            # Extract device IDs from schema — top-level device keys
            import re

            dev_id_re = re.compile(r"^\d{2}:[0-9A-Fa-f]{6}$")
            known = {}
            # Include gateway HGI ID (matching
            # coordinator._derive_known_list_from_schema)
            known.setdefault(get_current_instance().hgi_id, {})
            for k, v in schema.items():
                if dev_id_re.match(str(k)):
                    known[str(k)] = v if isinstance(v, dict) else {}
            # Also extract from TCS topology (zones, DHW, etc.)
            for k, v in schema.items():
                if not dev_id_re.match(str(k)) or not isinstance(v, dict):
                    continue
                # Zone sensors and actuators
                zones = v.get("zones", {})
                if isinstance(zones, dict):
                    for zone in zones.values():
                        if isinstance(zone, dict):
                            sensor = zone.get("sensor")
                            if sensor and dev_id_re.match(str(sensor)):
                                known.setdefault(str(sensor), {})
                            for act in zone.get("actuators", []):
                                if dev_id_re.match(str(act)):
                                    known.setdefault(str(act), {})
                # DHW sensor
                dhw = v.get("stored_hotwater", {})
                if isinstance(dhw, dict):
                    sensor = dhw.get("sensor")
                    if sensor and dev_id_re.match(str(sensor)):
                        known.setdefault(str(sensor), {})
                    valve = dhw.get("hotwater_valve")
                    if valve and dev_id_re.match(str(valve)):
                        known.setdefault(str(valve), {})
                # FAN remotes and sensors
                for rem in v.get("remotes", []):
                    if dev_id_re.match(str(rem)):
                        known.setdefault(str(rem), {})
                for sen in v.get("sensors", []):
                    if dev_id_re.match(str(sen)):
                        known.setdefault(str(sen), {})
            # Orphans
            for orphan_list_key in ("orphans_heat", "orphans_hvac"):
                for dev_id in schema.get(orphan_list_key, []):
                    if dev_id_re.match(str(dev_id)):
                        known.setdefault(str(dev_id), {})
            # Map _-prefixed traits to ramses_rf equivalents (matching
            # _derive_known_list_from_schema in coordinator.py)
            trait_map = {
                "_class": "class",
                "_alias": "alias",
                "_faked": "faked",
                "_bound": "bound",
                "_scheme": "scheme",
            }
            for dev_id, entry in known.items():
                if not isinstance(entry, dict):
                    continue
                mapped = {}
                for src_key, dst_key in trait_map.items():
                    if src_key in entry and entry[src_key] is not None:
                        val = entry[src_key]
                        if dst_key == "faked" and val is not True:
                            continue
                        mapped[dst_key] = val
                known[dev_id] = mapped
            return known
    return {}


def get_ramses_storage() -> dict:
    """Read .storage/ramses_cc directly from the container."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            get_current_instance().name,
            "cat",
            "/config/.storage/ramses_cc",
        ],
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
    # Read the current full file (envelope: version/minor_version/key/data).
    # Try docker exec first (works if container is running); fall back to the
    # host bind-mount path (needed when the container is stopped, since
    # `docker exec` requires a running container).
    inst = get_current_instance()
    storage_path = f"{inst.storage_path}/ramses_cc"
    result = subprocess.run(
        ["docker", "exec", inst.name, "cat", "/config/.storage/ramses_cc"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Container is likely stopped — read from the host bind mount instead.
        try:
            with open(storage_path) as f:
                content = f.read()
        except OSError as err:
            print(
                f"  write_ramses_storage: failed to read current file: "
                f"docker exec failed ({result.stderr[:60]}) and host read "
                f"failed ({err})"
            )
            return False
    else:
        content = result.stdout
    envelope = json.loads(content)
    envelope["data"] = data
    tmp_path = f"/tmp/ramses_cc_storage_{inst.name}.json"
    with open(tmp_path, "w") as f:
        json.dump(envelope, f, indent=2)
    # Try docker cp first; if the container is stopped, write directly to the
    # host bind-mount path (HA will pick up the file on next start).
    cp = subprocess.run(
        ["docker", "cp", tmp_path, f"{inst.name}:/config/.storage/ramses_cc"],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        try:
            import shutil

            shutil.copyfile(tmp_path, storage_path)
        except OSError as err:
            print(
                f"  write_ramses_storage: docker cp failed ({cp.stderr[:60]}) "
                f"and host write failed ({err})"
            )
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
        [
            "docker",
            "exec",
            get_current_instance().name,
            "cat",
            "/config/.storage/core.config_entries",
        ],
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
        get_current_instance().ha_url + "/api/states",
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


def wait(seconds: int, msg: str = "", *, floor: float = 0.0) -> None:
    """Wait and print progress (scaled by ``WAIT_SCALE_BLIND``).

    *floor* sets a minimum absolute sleep (seconds, real time) that the
    scaled sleep will not go below — use it for sensitive waits that need
    a hard minimum regardless of the global scale factor::

        wait(5, "for scan engine", floor=3)
        # At WAIT_SCALE_BLIND=0.5: scaled = min(max(2.5, 3), 5) = 3s, not 2.5s

    The floor never makes a wait *longer* than its original value — it
    only protects against scaling too aggressively.  So ``wait(2)`` with
    floor=3 stays 2s (the floor can't extend it beyond the original).

    The global ``WAIT_FLOOR_BLIND`` also applies — the effective floor is
    ``max(floor, WAIT_FLOOR_BLIND)``.
    """
    effective_floor = max(floor, WAIT_FLOOR_BLIND)
    scaled = min(max(seconds * WAIT_SCALE_BLIND, effective_floor), seconds)
    if scaled != seconds:
        scaled_str = f"{scaled:g}"
        print(f"  Waiting {seconds}s→{scaled_str}s {msg}...", end="", flush=True)
    else:
        print(f"  Waiting {seconds}s {msg}...", end="", flush=True)
    time.sleep(scaled)
    print(" done")


def wait_for(
    condition: Callable[[], bool],
    timeout: int = 30,
    interval: float = 1.0,
    msg: str = "",
    *,
    floor: float = 0.0,
) -> bool:
    """Poll a condition until True or timeout.

    Checks *condition* every *interval* seconds.  Returns True if the
    condition was met within *timeout* seconds, False otherwise.
    Prints progress like :func:`wait`.  Both *timeout* and *interval*
    are scaled by ``WAIT_SCALE_POLL`` — polling still exits as soon as
    *condition* is met, so scaling down mainly tightens the safety
    margin for genuinely slow conditions.

    *floor* sets a minimum absolute timeout (in seconds, real time) that
    the scaled timeout will not go below.  Use it for waits that have a
    hard physical minimum (e.g. docker container restart takes ~3-5s
    regardless of how aggressively you scale)::

        wait_for(is_ha_ready, timeout=30, floor=10, msg="for HA to start")
        # At WAIT_SCALE_POLL=0.05: scaled = min(max(1.5, 10), 30) = 10s

    The floor never makes the timeout *longer* than the original value —
    it only protects against scaling too aggressively.

    The global ``WAIT_FLOOR_POLL`` also applies — the effective floor is
    ``max(floor, WAIT_FLOOR_POLL)``.
    """
    effective_floor = max(floor, WAIT_FLOOR_POLL)
    scaled_timeout = min(max(timeout * WAIT_SCALE_POLL, effective_floor), timeout)
    scaled_interval = max(0.1, interval * WAIT_SCALE_POLL)
    if scaled_timeout != timeout:
        scaled_str = f"{scaled_timeout:g}"
        print(
            f"  Waiting up to {timeout}s→{scaled_str}s {msg}...",
            end="",
            flush=True,
        )
    else:
        print(f"  Waiting up to {timeout}s {msg}...", end="", flush=True)
    deadline = time.monotonic() + scaled_timeout
    while time.monotonic() < deadline:
        try:
            if condition():
                print(f" done ({int(scaled_timeout - (deadline - time.monotonic()))}s)")
                return True
        except Exception:
            pass  # condition may fail while HA is reloading
        time.sleep(scaled_interval)
    print(f" TIMEOUT ({scaled_timeout:g}s)")
    return False


def wait_for_ha_ready(timeout: int = 30, msg: str = "for ha-sim to start up") -> bool:
    """Wait for HA to be ready after a docker restart.

    Like :func:`wait_for` with :func:`is_ha_ready`, but with a *floor*
    of 10s — docker restarts take a hard 3-5s minimum before the API is
    even reachable, so scaling the timeout below 10s makes no sense.
    """
    return wait_for(is_ha_ready, timeout=timeout, interval=2, msg=msg, floor=10.0)


def wait_for_ramses_cc_loaded(
    timeout: int = 30, msg: str = "for ramses_cc to initialize"
) -> bool:
    """Wait for ramses_cc to be loaded after a docker restart.

    Like :func:`wait_for` with :func:`is_ramses_cc_loaded`, but with a
    *floor* of 15s — after a docker restart, ramses_cc's async_setup_entry
    takes 5-10s to complete (MQTT transport init, schema load, entity
    creation).  Scaling the timeout below 15s causes false TIMEOUTs that
    cascade into schema/profile load failures in subsequent steps.
    """
    return wait_for(
        is_ramses_cc_loaded, timeout=timeout, interval=2, msg=msg, floor=15.0
    )


# ---------------------------------------------------------------------------
# Composite wait helpers — poll for common conditions instead of fixed sleeps
# ---------------------------------------------------------------------------
def wait_for_schema_populated(min_keys: int = 5, timeout: int = 20) -> bool:
    """Wait until the schema has at least *min_keys* device entries.

    Replaces ``wait(10, "for CTL heartbeats + schema population")`` —
    typically returns in 2-5s once ramses_rf has processed the first
    heartbeat batch and written the learned schema.
    """
    return wait_for(
        lambda: len(get_schema_retry(max_tries=1)) >= min_keys,
        timeout=timeout,
        interval=2,
        msg=f"for schema to have >= {min_keys} keys",
    )


def wait_for_schema_stable(
    timeout: int = 10,
    quiet: float = 1.0,
    msg: str = "for schema to stabilise",
) -> bool:
    """Wait until the schema stops changing.

    Polls the schema every 0.5s and returns as soon as two consecutive
    reads produce the same JSON-serialised content (i.e. the schema has
    been quiet for *quiet* seconds).  Replaces blind ``wait(5, "for
    sync_learned_topology")`` and ``wait(5, "for save_client_state")``
    calls — typically returns in 1-2s instead of sleeping the full 5s.

    The *timeout* is the ceiling (scaled by ``WAIT_SCALE_POLL``); the
    *quiet* window is the stability threshold (not scaled — it's a
    real-time poll interval).
    """
    import json

    def _schema_hash() -> str:
        try:
            return json.dumps(get_schema_retry(max_tries=1), sort_keys=True)
        except Exception:
            return ""

    last = _schema_hash()
    quiet_until = time.monotonic() + quiet
    scaled_timeout = min(
        max(timeout * WAIT_SCALE_POLL, max(WAIT_FLOOR_POLL, 3.0)), timeout
    )
    print(
        f"  Waiting up to {timeout}s→{scaled_timeout:g}s {msg}...",
        end="",
        flush=True,
    )
    deadline = time.monotonic() + scaled_timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        current = _schema_hash()
        if current == last and current:
            if time.monotonic() >= quiet_until:
                print(" done (stable)")
                return True
        else:
            last = current
            quiet_until = time.monotonic() + quiet
    print(f" TIMEOUT ({scaled_timeout:g}s)")
    return False


def wait_for_transport_ready(timeout: int = 30) -> bool:
    """Wait until the ramses_rf MQTT transport has reconnected after a reload.

    After a profile reload with ``reload_ramses_cc=True``, the ramses_rf
    transport closes and takes ~15-20s to reconnect.  Injected packets are
    silently dropped ("Transport Error: Transport is closing or has closed")
    during this window.  This helper polls the HA log for the
    ``Subscribed to status topic`` message that indicates the MQTT transport
    has reconnected and the FSM is back in ``IsInIdle``.
    """
    inst = get_current_instance()

    def _check() -> bool:
        result = subprocess.run(
            ["docker", "logs", "--since", "5s", inst.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        logs = result.stderr or ""
        # The MQTT transport logs this when it (re)subscribes after connecting.
        # Use a short --since window so we only catch the reconnection after
        # the profile reload, not the initial startup message.
        return "Subscribed to status topic" in logs

    return wait_for(
        _check, timeout=timeout, interval=3, msg="for transport to reconnect"
    )


def wait_for_schema_has(
    device_id: str, timeout: int = 20, *, trait: str | None = None
) -> bool:
    """Wait until *device_id* appears in the schema.

    If *trait* is given (e.g. ``"_class"``), also require that the
    device's schema entry has that trait set.

    Replaces ``wait(10, "for sync_learned_topology to process")`` when
    the expected outcome is a specific device appearing in the schema.
    """

    def _check() -> bool:
        schema = get_schema_retry(max_tries=1)
        entry = schema.get(device_id)
        if entry is None:
            return False
        if trait is not None:
            return entry.get(trait) is not None
        return True

    return wait_for(
        _check, timeout=timeout, interval=2, msg=f"for {device_id} in schema"
    )


def wait_for_entity_state(
    token: str,
    entity_id: str,
    *,
    expected: str | None = None,
    not_none: bool = False,
    timeout: int = 15,
) -> bool:
    """Wait until an entity state matches a condition.

    :param expected: If given, wait until ``state == expected``.
    :param not_none: If True, wait until the entity exists and state is not None.

    Replaces ``wait(5, "for entity state write")`` / ``wait(3, "for 1260 to process")``
    — typically returns in 1-2s once HA has processed the state update.
    """

    def _check() -> bool:
        req = urllib.request.Request(
            f"{get_current_instance().ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            state = json.loads(resp.read()).get("state")
        except urllib.error.HTTPError:
            return False  # 404 = entity not yet created
        except Exception:
            return False
        if expected is not None:
            return state == expected
        if not_none:
            return state is not None
        return True  # entity exists

    return wait_for(
        _check,
        timeout=timeout,
        interval=1,
        msg=f"for {entity_id} state"
        + (f" == {expected!r}" if expected else " to be set"),
    )


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


def grep_ha_log(pattern: str, since_lines: int = 0) -> list[str]:
    """Grep the HA log inside the ha-sim container for a pattern.

    :param pattern: Extended regex to search for (case-insensitive, -iE).
    :param since_lines: If >0, only search the last N lines of the log.
    :return: List of matching log lines (stripped).
    """
    inst = get_current_instance()
    if since_lines > 0:
        cmd = [
            "docker",
            "exec",
            inst.name,
            "bash",
            "-c",
            f"tail -n {since_lines} /config/home-assistant.log | grep -iE '{pattern}'",
        ]
    else:
        cmd = ["docker", "exec", inst.name, "grep", "-iE", pattern]
        cmd += ["/config/home-assistant.log"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def docker_exec_python(code: str, timeout: int = 30) -> dict:
    """Run Python code inside the ha-sim container and return the result.

    The code must print a JSON line to stdout (typically via ``json.dumps``).
    This is used by structural recipes that need to inspect ramses_rf/ramses_tx
    internals (CommandDTO, PacketDTO, load_fan, etc.) which are only available
    in the container's newer ramses_rf installation.

    :param code: Python source code to execute inside the container.
    :param timeout: Timeout in seconds.
    :return: Parsed JSON dict from stdout, or ``{"error": "..."}`` on failure.
    """
    cmd = [
        "docker",
        "exec",
        get_current_instance().name,
        "python3",
        "-c",
        code,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()[:500]}
        # The code should print exactly one JSON line
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"error": f"no JSON in stdout: {result.stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except (json.JSONDecodeError, Exception) as e:
        return {"error": str(e)[:200]}


# ---------------------------------------------------------------------------
# Container lifecycle helpers
# ---------------------------------------------------------------------------
def is_ha_ready() -> bool:
    """Check if the ha-sim HA API is responding (event-driven startup wait).

    HA's /api/ endpoint returns 401 (Unauthorized) when the server is
    running but no auth token is provided.  Any HTTP response (even
    401) means the server is up — a connection refused means it's not.
    """
    try:
        req = urllib.request.Request(get_current_instance().ha_url + "/api/")
        urllib.request.urlopen(req, timeout=5)
        return True  # 200 (rare for /api/ without auth)
    except urllib.error.HTTPError as e:
        # 401 Unauthorized means HA is running (just needs auth)
        return e.code in (200, 401, 403)
    except Exception:
        return False  # connection refused = not ready yet


def is_ramses_cc_loaded() -> bool:
    """Check if ramses_cc is loaded and its schema is populated."""
    schema = get_schema()
    return bool(schema)


def is_ramses_extras_ready() -> bool:
    """Check if ramses_extras websocket commands are registered.

    During a cold start, ramses_extras takes ~60s to load after HA is ready.
    The ``device_simulator`` websocket commands are only available once
    ramses_extras' websocket_integration setup completes.
    """
    inst = get_current_instance()
    # HA logs go to stderr; check the full log for the setup-complete line
    result = subprocess.run(
        ["docker", "logs", inst.name],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return False
    # docker logs output goes to stderr
    logs = result.stderr or ""
    return "WebSocket integration setup complete" in logs


def clear_cached_state(
    log_monitor: Any = None,
    label: str = "",
) -> None:
    """Stop ha-sim, delete .storage/ramses_cc + ramses.db, clear CONF_SCHEMA.

    This is the shared clean-slate pattern used by R34, R37, R38 (and
    any recipe that needs to eliminate cached state from previous tests).

    1. ``capture_before_restart`` (if log_monitor given) to save logs.
    2. ``docker stop <instance>``
    3. Delete ``.storage/ramses_cc`` (client state cache).
    4. Delete ``ramses.db`` (message database — replays old packets).
    5. Clear CONF_SCHEMA from ``core.config_entries`` (config entry options).
    6. ``docker start <instance>`` (caller then waits for readiness).
    """
    import os

    inst = get_current_instance()
    if log_monitor is not None:
        log_monitor.capture_before_restart(label)

    subprocess.run(["docker", "stop", inst.name], capture_output=True)
    time.sleep(2)

    # Delete .storage/ramses_cc (client state cache)
    storage_path = f"{inst.storage_path}/ramses_cc"
    if os.path.exists(storage_path):
        os.remove(storage_path)

    # Delete ramses.db (message database — replays old packets)
    for db_path in (
        f"{inst.config_dir}/ramses.db",
        f"{inst.config_dir}/ramses_rf/ramses.db",
    ):
        if os.path.exists(db_path):
            os.remove(db_path)

    # Clear CONF_SCHEMA from core.config_entries (config entry options).
    # The file is root-owned inside the container, so we can't edit it
    # directly from the host.  The container is stopped, so docker exec
    # won't work either.  Use a temporary python container with the config
    # volume mounted to modify the file.
    ce_path_host = f"{inst.storage_path}/core.config_entries"
    if os.path.exists(ce_path_host):
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{inst.config_dir}:/config",
                "python:3.12-slim",
                "python3",
                "-c",
                "import json; "
                "p='/config/.storage/core.config_entries'; "
                "d=json.load(open(p)); "
                "[e.get('options',{}).pop('schema',None) "
                "for e in d.get('data',{}).get('entries',[]) "
                "if e.get('domain')=='ramses_cc']; "
                "json.dump(d, open(p,'w')); "
                "print('Cleared CONF_SCHEMA')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    subprocess.run(["docker", "start", inst.name], capture_output=True)
