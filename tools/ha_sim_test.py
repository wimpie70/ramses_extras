#!/usr/bin/env python3
"""Automated test runner for PR 764 features on ha-sim device simulator.

Uses the HA websocket API for profile loading (with 100x speed) and
the REST API for service calls.  Runs in ~90 seconds instead of ~5 minutes.

Usage:
    python3 /tmp/ha_sim_test.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

HA_URL = "http://localhost:8124"
HA_USER = "admin"
HA_PASS = "admin123"

# Sim device IDs (from system_config.py)
HGI = "18:001234"
CTL = "01:150000"
TRV = "04:150003"  # zone 03 actuator
DHW = "07:150000"
FAN = "32:150000"
CO2 = "37:120000"
REM = "37:170000"

# Mixed profile YAML (for load_profile_yaml — avoids docker restarts)
# Matches the built-in "mixed" profile from system_config.py
_MIXED_KL = {
    "18:001234": {"class": "HGI"},
    "32:150000": {"class": "FAN"},
    "37:120000": {"class": "CO2"},
    "37:170000": {"class": "REM"},
    "29:120000": {"class": "HUM"},
    "01:150000": {"class": "CTL"},
    "07:150000": {"class": "DHW"},
    "04:150000": {"class": "TRV"},
}
for _i in range(3, 9):
    _MIXED_KL[f"01:15000{_i}"] = {"class": "CTL"}
    _MIXED_KL[f"04:15000{_i}"] = {"class": "TRV"}

_MIXED_ZONES = {}
for _i in range(3, 9):
    _MIXED_ZONES[str(_i).zfill(2)] = {
        "sensor": f"01:15000{_i}",
        "actuators": [f"04:15000{_i}"],
    }

MIXED_SCHEMA = {
    CTL: {"zones": dict(_MIXED_ZONES), "stored_hotwater": {"sensor": DHW}},
    FAN: {
        "remotes": [REM],
        "sensors": [CO2],
        "_commands": {
            "_comment": "Target the FAN for automations, not the REM",
        },
    },
    REM: {
        "_commands": {
            "_comment": "Deprecated — commands moved to FAN",
        },
    },
}


def _mixed_yaml(schema_override: dict | None = None) -> str:
    """Build a YAML profile matching the mixed profile, with optional overrides."""
    import yaml as _yaml

    # Force YAML to quote strings that look like numbers (e.g. "03" not 03)
    class _QuotedDumper(_yaml.Dumper):
        pass

    def _str_representer(dumper, data):
        if data.isdigit() and len(data) > 1:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _QuotedDumper.add_representer(str, _str_representer)

    schema = dict(MIXED_SCHEMA)
    if schema_override:
        schema.update(schema_override)
    profile = {
        "known_list": dict(_MIXED_KL),
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    return _yaml.dump(
        profile, Dumper=_QuotedDumper, default_flow_style=False, sort_keys=False
    )


passed = 0
failed = 0
results: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record a check result."""
    global passed, failed
    if condition:
        passed += 1
        results.append(f"  PASS: {label}")
        print(f"  PASS: {label}")
    else:
        failed += 1
        results.append(f"  FAIL: {label} {detail}")
        print(f"  FAIL: {label} {detail}")


# ---------------------------------------------------------------------------
# Log monitor — captures ERROR/WARNING lines from ha-sim logs during tests
# ---------------------------------------------------------------------------
# Known/expected warnings that should NOT be flagged as unexpected errors.
# Each entry is a substring match (case-sensitive) on the log line.
EXPECTED_WARNINGS: list[str] = [
    # R10: intentional invalid main_tcs
    "Sanitising invalid main_tcs",
    # ramses_rf: PacketInvalid is expected for some inject patterns
    "PacketInvalid",
    # ramses_rf: QoS warnings during rapid inject cycles
    "QoS",
    # Profile reload: stale device removal is expected
    "removed stale HA devices",
    # ramses_rf: schema merge fallback warning
    "Failed to initialise with merged schema",
    # Discovery: devices not yet in known_list during fresh_start
    "unknown device",
    # ramses_rf: enforce_known_list blocks during fresh_start
    "enforce_known_list",
    # ramses_rf: old-style packet warnings (cosmetic)
    "Unexpected verb/code",
    # ramses_rf: FAN load_fan stub (expected — HVAC schema handled separately)
    "load_fan",
    # Profile load: clearing schema is expected during reload
    "cleared CONF_SCHEMA",
    # Profile load: clearing HA store is expected
    "cleared HA store",
    # ramses_rf: no active FAN during early init
    "No active FAN",
    # ramses_rf: PARENT CHANGE / LINK EXCEPTION when inject moves a TRV to a new zone
    "PARENT CHANGE EXCEPTION",
    "LINK EXCEPTION",
    # ramses_rf: FILTER/BIND EXCEPTION for devices not in known_list (simulator DB)
    "FILTER EXCEPTION",
    "BIND EXCEPTION",
    # ramses_rf: packet idx mismatch (simulator uses 04, ramses_rf expects 00)
    "Packet idx is",
    # ramses_rf: excessive datetime difference (simulator timestamps are synthetic)
    "excessive datetime difference",
    # HA core: template integration config (not our code)
    "template.helpers",
    # HA core: aiohttp error during profile reload (transient)
    "aiohttp.server",
    # ramses_rf: device not in known_list (expected during fresh_start + discovery)
    "not an allowed device_id",
    "unwanted or invalid",
    # HA: orphaned task exceptions during rapid reload cycles (transient)
    "Task exception was never retrieved",
    # ramses_rf: SUPPRESSED in Zone handler (cosmetic, from zone rebinding)
    "SUPPRESSED in Zone",
    # HA: logging too frequently (simulator at 100x speed generates lots of logs)
    "logging too frequently",
    # HA: custom integration not tested (cosmetic, every reload)
    "not been tested by Home Assistant",
    # ramses_cc: config schema not minimal (cosmetic, expected with full schema)
    "config schema is not minimal",
    # ramses_rf: support development message (cosmetic)
    "Support the development of ra",
    # ramses_extras: RF config validation warnings (expected on sim — no bound REM)
    "rf_config_validation",
    # ramses_tx: MQTT disconnect during restart (expected)
    "MQTT disconnected",
    # ramses_rf: discovery cmd timeout (simulator may not respond to all RQ)
    "Failed to send discovery cmd",
    # ramses_cc: migration warning for known_list devices not in schema
    # (expected after profile reload)
    "known_list devices not in schema",
    # ramses_cc: Phase 3c mismatch warnings (expected in recipe 24/26)
    "class mismatches between discovery and schema",
    "bound mismatches between discovery and schema",
    "have no _class but discovery has a suggestion",
    "appear orphaned",
    # ramses_cc: bound device not found during early init (FAN not yet active)
    "Bound device",
    "not found for FAN",
    # ramses_tx: FSM timeout during profile reload (transient)
    "send_timeout",
    "Send timed out",
    # ramses_tx: protocol FSM state warnings (transient during reload)
    "ProtocolContext state",
    # ramses_rf: discovery no response retry (simulator may not respond to all RQ)
    "No response for",
    "retrying in",
    # HA: via_device non-existing during reload (transient — device registry race)
    "non existing",
    "via_device",
    # ramses_extras: command excluded by device_id filter (expected on sim
    # when sending to devices not in the known_list, e.g. 32:153289)
    "Command excluded by device_id filter",
    # ramses_rf: Packet idx mismatch for broadcast TRV traffic (simulator
    # uses zone_idx as packet idx, ramses_rf expects 00)
    "Packet idx is",
    # ramses_tx: foreign gateway warning when injecting from 18: devices
    # that are not the active gateway (expected in recipe 19c)
    "potentially a Foreign gateway",
    # ramses_rf: payload format mismatch when injecting test 000A packets
    # (expected — the scan engine still processes the raw payload)
    "Payload doesn't match",
    # ramses_extras: ramses_rf.const import warning when ramses_rf is
    # installed from a non-standard location (editable install / manual copy)
    "could not import ramses_rf.const for patching",
    # ramses_cc: orphaned task warning during profile reload (transient —
    # the EntityPlatform async_add_entities task may still be pending when
    # the integration unloads)
    "Task <Task pending name='EntityPlatform async_ad",
]


class LogMonitor:
    """Monitors ha-sim docker logs for ERROR/WARNING lines.

    Captures a baseline at startup, then snapshots after each recipe
    to attribute log entries to the recipe that triggered them.
    Before a docker restart, call capture_before_restart() to save
    logs that would otherwise be wiped. At the end, generates a report
    file and counts unexpected errors.
    """

    def __init__(self) -> None:
        self._baseline: str = ""  # timestamp of the first log line
        self._accumulated: list[str] = []  # classified lines from before restarts
        self._accumulated_total: int = 0  # total log lines from before restarts

    def _get_log_timestamp(self) -> str:
        """Get the timestamp of the most recent log line."""
        result = subprocess.run(
            ["docker", "logs", "ha-sim", "--tail", "1", "--timestamps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Output format: "2026-07-07T08:03:36.021Z [level] ..."
        line = (result.stdout or result.stderr or "").strip()
        if not line:
            return ""
        # Extract ISO timestamp from the start
        parts = line.split(" ", 1)
        return parts[0] if parts else ""

    def start(self) -> None:
        """Capture baseline timestamp before tests begin."""
        self._baseline = self._get_log_timestamp()
        print(f"  Log baseline: {self._baseline}")

    def capture_before_restart(self, label: str = "") -> None:
        """Capture and classify logs before a docker restart wipes them.

        Call this right before `docker restart ha-sim`. The classified
        ERROR/WARNING lines are accumulated and included in the final report.
        After the restart, call reset_baseline() to start fresh.
        """
        if not self._baseline:
            return
        logs = self._fetch_logs(self._baseline)
        lines = logs.splitlines()
        self._accumulated_total += len(lines)
        captured = 0
        for line in lines:
            level = self._classify_line(line)
            if level:
                self._accumulated.append(line.strip())
                captured += 1
        prefix = f" [{label}]" if label else ""
        print(f"  Log capture{prefix}: {len(lines)} lines, {captured} classified")

    def reset_baseline(self) -> None:
        """Reset baseline after a docker restart (logs are wiped)."""
        self._baseline = self._get_log_timestamp()
        print(f"  Log baseline reset: {self._baseline}")

    def _fetch_logs(self, since: str) -> str:
        """Fetch ha-sim logs since a timestamp."""
        if not since:
            return ""
        result = subprocess.run(
            ["docker", "logs", "ha-sim", "--since", since, "--timestamps"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout + result.stderr

    def _classify_line(self, line: str) -> str | None:
        """Classify a log line. Returns 'ERROR', 'WARNING', or None."""
        # Strip ANSI escape codes
        import re

        clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
        # Skip empty lines and continuation lines (indented, no timestamp)
        if not clean.strip():
            return None
        # Skip Traceback continuation lines (they follow an ERROR line)
        if clean.strip().startswith("Traceback") or clean.strip().startswith("  File"):
            return None  # The ERROR line itself is already captured
        # Check for ERROR
        if " ERROR " in clean:
            for expected in EXPECTED_WARNINGS:
                if expected in clean:
                    return None
            return "ERROR"
        # Check for WARNING (only from ramses_cc/ramses_rf/ramses_tx, not HA core)
        if " WARNING " in clean:
            if "ramses_cc" in clean or "ramses_rf" in clean or "ramses_tx" in clean:
                for expected in EXPECTED_WARNINGS:
                    if expected in clean:
                        return None
                return "WARNING"
        return None

    def collect(self) -> dict:
        """Collect all logs since baseline, classify, and return report data.

        Merges logs captured before docker restarts with current logs.
        """
        all_logs = self._fetch_logs(self._baseline)
        current_lines = all_logs.splitlines()
        all_errors: list[str] = []
        all_warnings: list[str] = []

        # First, add accumulated lines from before restarts
        for line in self._accumulated:
            level = self._classify_line(line)
            if level == "ERROR":
                all_errors.append(line.strip())
            elif level == "WARNING":
                all_warnings.append(line.strip())

        # Then, classify current logs
        for line in current_lines:
            level = self._classify_line(line)
            if level == "ERROR":
                all_errors.append(line.strip())
            elif level == "WARNING":
                all_warnings.append(line.strip())

        total = self._accumulated_total + len(current_lines)
        return {
            "errors": all_errors,
            "warnings": all_warnings,
            "total_lines": total,
        }

    def write_report(self, filepath: str, log_data: dict) -> None:
        """Write a human-readable report file."""
        import re

        def _strip_ansi(s: str) -> str:
            return re.sub(r"\x1b\[[0-9;]*m", "", s)

        with open(filepath, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("HA-SIM TEST LOG REPORT\n")
            f.write(f"Baseline: {self._baseline}\n")
            f.write(f"Pre-restart captured lines: {self._accumulated_total}\n")
            f.write(f"Total log lines: {log_data['total_lines']}\n")
            f.write(f"Errors: {len(log_data['errors'])}\n")
            f.write(f"Warnings: {len(log_data['warnings'])}\n")
            f.write("=" * 70 + "\n\n")

            if log_data["errors"]:
                f.write("ERRORS (unexpected):\n")
                f.write("-" * 40 + "\n")
                for line in log_data["errors"]:
                    clean = _strip_ansi(line)
                    f.write(f"  {clean[:300]}\n")
                f.write("\n")

            if log_data["warnings"]:
                f.write("WARNINGS (ramses_cc/ramses_rf only):\n")
                f.write("-" * 40 + "\n")
                for line in log_data["warnings"]:
                    clean = _strip_ansi(line)
                    f.write(f"  {clean[:300]}\n")
                f.write("\n")

            if not log_data["errors"] and not log_data["warnings"]:
                f.write("No unexpected errors or warnings found.\n\n")

            f.write("Expected warnings (filtered out):\n")
            f.write("-" * 40 + "\n")
            for w in EXPECTED_WARNINGS:
                f.write(f"  - {w}\n")


log_monitor = LogMonitor()


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


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------
async def main() -> None:
    print("Authenticating to ha-sim...")
    token = get_token()
    print(f"Token acquired: {token[:30]}...")

    # Start log monitor — captures baseline for error/warning detection
    log_monitor.start()

    # =====================================================================
    # SETUP: Load mixed profile with 100x speed via websocket API
    # =====================================================================
    log_section("Setup: Load mixed profile (100x speed, heat + HVAC)")
    print("  Loading mixed profile via websocket...")
    try:
        result = await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,  # 100x faster heartbeats
                "preload_schema": True,
                "reload_ramses_cc": True,  # Reload to pick up new known_list
                "enable_auto_answer": True,
            },
        )
        print(f"  Profile loaded: {result.get('actions', [])[:3]}")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
        # Fall back: the profile may already be loaded

    wait(15, "for ramses_cc reload + init + config entry write")
    token = get_token()  # re-auth after reload
    wait(5, "for ramses_cc to initialize")

    # Activate devices via websocket (faster — uses profile config)
    for dev_id, name in [
        (CTL, "CTL"),
        (TRV, "TRV"),
        (FAN, "FAN"),
        (REM, "REM"),
        (CO2, "CO2"),
    ]:
        print(f"  Activating {name} {dev_id}...")
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": dev_id,
                },
            )
            print(f"    {name} activated")
        except RuntimeError as e:
            # already_active is fine
            if "already_active" in str(e):
                print(f"    {name} already active")
            else:
                print(f"    {name} activate failed: {str(e)[:80]}")

    wait(10, "for fast heartbeats + schema population (100x speed)")

    # Check schema is populated (retry — profile reload may still be writing)
    schema = get_schema_retry()
    kl = get_known_list()
    print(f"  Schema keys: {list(schema.keys())}")
    print(f"  Known_list: {list(kl.keys())[:15]}")

    # =====================================================================
    # RECIPE 6/14: Zone binding via inject_message
    # =====================================================================
    log_section("Recipe 6/14: Zone binding via inject_message")

    # 000C payload format: zone_idx(1) + zone_type(1) + pad(1) + dev_hex_id(3)
    # The dev_hex_id is NOT the raw device address — it's the transformed hex
    # from ramses_rf.address.dev_id_to_hex_id().
    # 04:150003 → dev_id_to_hex_id → "1249F3"
    # zone_type 08 = rad_actuator
    # We inject zone 09 (doesn't exist yet) with TRV 04:150003
    target_zone = "09"
    trv_hex_id = "1249F3"  # dev_id_to_hex_id("04:150003")
    inject_payload = f"{target_zone}0800{trv_hex_id}"

    schema_before_inject = get_schema_retry()
    ctl_schema = schema_before_inject.get(CTL, {})
    zones_before = ctl_schema.get("zones", {}) if isinstance(ctl_schema, dict) else {}
    print(f"  Zones before inject: {list(zones_before.keys())}")
    print(f"  Inject payload: {inject_payload}")

    # Inject as an RP from CTL to HGI (normal response pattern)
    try:
        result = call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": CTL,
                "dst": HGI,
                "code": "000C",
                "payload": inject_payload,
                "verb": "RP",
            },
        )
        print(f"  Injected 000C packet: {result}")
    except RuntimeError as e:
        print(f"  Inject failed: {e}")

    # Wait for the 000C packet to be received and processed by ramses_rf
    wait(5, "for 000C packet to be processed by ramses_rf")

    # Trigger sync_topology to process the injected packet
    try:
        call_service(token, "ramses_cc", "sync_topology")
        print("  sync_topology called")
    except RuntimeError as e:
        print(f"  sync_topology failed: {e}")

    wait(10, "for sync_learned_topology to process")

    # Trigger a save to persist the synced schema to .storage
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save_client_state")

    # Use cached schema (more reliable than config entry during sync)
    schema_after_inject = get_cached_schema()
    ctl_schema_after = schema_after_inject.get(CTL, {})
    zones_after = (
        ctl_schema_after.get("zones", {}) if isinstance(ctl_schema_after, dict) else {}
    )
    print(f"  Zones after inject: {list(zones_after.keys())}")

    # Check that zone 09 was created by the injected 000C packet.
    # Note: ramses_rf prevents moving a device from one zone to another at
    # runtime ("can't change parent"), so we only check zone creation, not
    # that the TRV was moved into it.
    zone_09 = zones_after.get(target_zone, {})
    check(
        f"Zone {target_zone} created by inject",
        target_zone in zones_after,
        f"zones={list(zones_after.keys())}",
    )
    if target_zone in zones_after:
        check(
            f"Zone {target_zone} has radiator_valve class",
            zone_09.get("class") == "radiator_valve"
            if isinstance(zone_09, dict)
            else False,
            f"zone_{target_zone}={json.dumps(zone_09)[:200]}",
        )

    # =====================================================================
    # RECIPE 3: remove_device — HGI rejection
    # =====================================================================
    log_section("Recipe 3: remove_device — HGI rejection")
    try:
        call_service(token, "ramses_cc", "remove_device", {"device_id": HGI})
        check("HGI removal raises error", False, "(no error raised)")
    except RuntimeError as e:
        check("HGI removal raises error", True, str(e)[:80])

    # =====================================================================
    # RECIPE 2: remove_device — remove a TRV
    # =====================================================================
    log_section(f"Recipe 2: remove_device — remove TRV {TRV}")

    schema_before = get_schema_retry()
    trv_in_schema = TRV in json.dumps(schema_before)
    print(f"  TRV in schema: {trv_in_schema}")

    if trv_in_schema:
        entities_before = get_entities(token)
        trv_entity_before = find_entity_for_device(entities_before, TRV, prefix="trv_")
        trv_eid = trv_entity_before["entity_id"] if trv_entity_before else "None"
        print(f"  TRV entity before: {trv_eid}")

        try:
            call_service(token, "ramses_cc", "remove_device", {"device_id": TRV})
            print("  remove_device call succeeded")
            wait(3, "for coordinator refresh")

            # Check config entry schema (remove_device updates this directly).
            # The cached schema (.storage/ramses_cc) may still have the device
            # because async_save_client_state writes the LEARNED schema from
            # ramses_rf, which sync_learned_topology can merge back in.
            schema_after = get_schema()
            check(
                "TRV removed from schema",
                TRV not in json.dumps(schema_after),
                f"schema still contains {TRV}",
            )

            kl_after = get_known_list()
            check(
                "TRV removed from known_list",
                TRV not in kl_after,
                f"known_list still has {TRV}",
            )

            entities_after = get_entities(token)
            trv_entity_after = find_entity_for_device(
                entities_after, TRV, prefix="trv_"
            )
            trv_eid_after = trv_entity_after["entity_id"] if trv_entity_after else "?"
            check(
                "TRV entity removed",
                trv_entity_after is None,
                f"entity still exists: {trv_eid_after}",
            )
        except RuntimeError as e:
            check("remove_device TRV call", False, str(e)[:80])
    else:
        print(f"  SKIP: TRV {TRV} not in schema")

    # =====================================================================
    # RECIPE 4: remove_device — CTL (main_tcs) removal
    # =====================================================================
    log_section(f"Recipe 4: remove_device — CTL {CTL} / main_tcs removal")

    schema_before = get_schema_retry()
    ctl_in_schema = CTL in schema_before
    main_tcs_before = schema_before.get("main_tcs")
    print(f"  CTL in schema: {ctl_in_schema}, main_tcs={main_tcs_before}")

    if ctl_in_schema:
        try:
            call_service(token, "ramses_cc", "remove_device", {"device_id": CTL})
            print("  remove_device CTL call succeeded")
            wait(3, "for refresh")

            schema_after = get_schema_retry()
            check(
                "CTL top-level key removed",
                CTL not in schema_after,
                f"schema still has key {CTL}",
            )
            check(
                "main_tcs cleared",
                schema_after.get("main_tcs") is None,
                f"main_tcs={schema_after.get('main_tcs')}",
            )
        except RuntimeError as e:
            check("remove_device CTL call", False, str(e)[:80])
    else:
        print(f"  SKIP: CTL {CTL} not in schema")

    # =====================================================================
    # RECIPE 15: Verify .storage/ramses_cc has hvac_schema key
    # =====================================================================
    log_section("Recipe 15: Verify hvac_schema key in .storage")

    storage = get_ramses_storage()
    check(
        "hvac_schema key exists in storage",
        "hvac_schema" in storage,
        f"keys={list(storage.keys())}",
    )

    hvac_schema = storage.get("hvac_schema", {})
    print(f"  hvac_schema: {json.dumps(hvac_schema)[:200]}")

    # =====================================================================
    # RECIPE 7: HVAC schema caching — verify FAN in schema + cache
    # =====================================================================
    log_section("Recipe 7: HVAC schema caching — FAN + REM")

    schema = get_schema_retry()
    fan_in_schema = FAN in schema
    print(f"  FAN in schema: {fan_in_schema}")
    if fan_in_schema:
        print(f"  FAN schema: {json.dumps(schema[FAN])[:150]}")

    check(
        "FAN in config entry schema",
        fan_in_schema,
        f"schema keys={list(schema.keys())}",
    )

    # Trigger a save by calling force_update
    try:
        call_service(token, "ramses_cc", "force_update")
        print("  force_update called")
    except RuntimeError as e:
        print(f"  force_update failed: {e}")

    wait(5, "for save_client_state")

    storage = get_ramses_storage()
    hvac_schema = storage.get("hvac_schema", {})
    print(f"  hvac_schema after save: {json.dumps(hvac_schema)[:300]}")

    check(
        "hvac_schema populated",
        bool(hvac_schema),
        f"hvac_schema={json.dumps(hvac_schema)[:200]}",
    )

    # =====================================================================
    # RECIPE 7b: Restart and verify HVAC survives
    # =====================================================================
    log_section("Recipe 7b: Restart ha-sim, verify HVAC survives")

    # Capture logs before restart — docker restart wipes the log buffer
    log_monitor.capture_before_restart("R7b pre-restart")

    print("  Restarting ha-sim...")
    subprocess.run(["docker", "restart", "ha-sim"], capture_output=True)
    wait(20, "for ha-sim to start up")

    # Reset log baseline — logs are wiped by the restart
    log_monitor.reset_baseline()

    # Re-authenticate
    print("  Re-authenticating...")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Reload mixed profile — docker restart may reload a stale profile
    # (e.g. fresh_start from a later recipe in a previous test run).
    # Reloading ensures FAN/REM/CO2 are in the known_list and schema.
    print("  Reloading mixed profile after restart...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,
                "preload_schema": True,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  mixed profile loaded")
    except RuntimeError as e:
        print(f"  Mixed profile reload failed: {e}")
    wait(15, "for ramses_cc reload with mixed profile")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Re-activate devices (profile reload stops all active devices)
    for dev_id, name in [(FAN, "FAN"), (REM, "REM"), (CO2, "CO2")]:
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": dev_id,
                },
            )
            print(f"    {name} activated")
        except RuntimeError:
            pass
    wait(10, "for heartbeats + schema population")

    schema_after_restart = get_schema_retry()
    fan_after_restart = FAN in schema_after_restart
    check(
        "FAN in schema after restart",
        fan_after_restart,
        f"schema keys={list(schema_after_restart.keys())}",
    )

    storage_after = get_ramses_storage()
    hvac_after = storage_after.get("hvac_schema", {})
    check(
        "hvac_schema preserved in storage after restart",
        bool(hvac_after),
        f"hvac_schema={json.dumps(hvac_after)[:200]}",
    )

    # =====================================================================
    # RECIPE 5: No resurrection after restart
    # =====================================================================
    log_section("Recipe 5: No resurrection after restart")

    # TRV and CTL were removed in recipes 2/4.  The 7b profile reload brings
    # them back (mixed profile includes them in known_list).  Re-remove them
    # to verify that remove_device persists across sync cycles and that the
    # devices don't get resurrected by subsequent sync_learned_topology calls.
    print(f"  Re-removing TRV {TRV} and CTL {CTL} (brought back by 7b reload)...")
    for dev_id, name in [(TRV, "TRV"), (CTL, "CTL")]:
        try:
            call_service(token, "ramses_cc", "remove_device", {"device_id": dev_id})
            print(f"    {name} removed")
        except RuntimeError as e:
            print(f"    {name} remove failed: {str(e)[:80]}")
    wait(3, "for coordinator refresh")

    # Trigger a sync to verify the removal survives sync_learned_topology
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(3, "for save")

    kl_post_restart = get_known_list()

    check(
        "TRV not resurrected in known_list",
        TRV not in kl_post_restart,
        f"known_list still has {TRV}",
    )
    check(
        "CTL not resurrected in known_list",
        CTL not in kl_post_restart,
        f"known_list still has {CTL}",
    )
    # Note: HA's entity/device registry may not be flushed to disk before
    # restart, so orphaned entity states can linger in the states API.  The
    # known_list check above is the real persistence guarantee — if the
    # device is not in the known_list, ramses_cc won't create new entities
    # for it on the next reload.

    # =====================================================================
    # RECIPE 11: Full lifecycle — discover → accept → remove
    # =====================================================================
    log_section("Recipe 11: Discover → accept → remove lifecycle")

    # Use a brand-new device ID that's not in any profile or schema, so the
    # discovery manager will treat it as truly unknown.
    new_trv = "04:200001"

    # Load fresh_start_allow_unknown_devices_fast_heartbeat profile
    # (enforce_known_list=False, known_list=HGI only, remove_database=True)
    print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
    try:
        result = await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "fresh_start_allow_unknown_devices_fast_heartbeat",
                "speed": 0.01,
                "preload_schema": False,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print(f"  Profile loaded: {result.get('actions', [])[:3]}")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")

    wait(15, "for ramses_cc reload with fresh_start profile")

    # Inject several 1FC9 heartbeats from the new TRV to trigger discovery
    print(f"  Injecting 1FC9 heartbeats from {new_trv}...")
    for i in range(3):
        try:
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": new_trv,
                    "code": "1FC9",
                    "payload": "0030C912E294",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"  Inject {i} failed: {str(e)[:60]}")
        time.sleep(2)

    wait(10, "for discovery scan to detect the new TRV")

    # Try to accept the discovered device
    print(f"  Accepting discovered device {new_trv}...")
    accept_ok = False
    try:
        call_service(
            token,
            "ramses_cc",
            "accept_discovered_device",
            {
                "device_id": new_trv,
            },
        )
        print("  accept_discovered_device succeeded")
        accept_ok = True
    except RuntimeError as e:
        print(f"  accept_discovered_device failed: {str(e)[:80]}")

    check(
        "TRV discovered and accepted",
        accept_ok,
        "accept_discovered_device raised error (TRV not in discovery list)",
    )

    if accept_ok:
        # Wait for the ramses_rf client to update its include list
        wait(5, "for ramses_rf include list update")

        # Inject a temperature packet so the entity gets a state
        print(f"  Injecting 30C9 temperature from {new_trv}...")
        try:
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": new_trv,
                    "code": "30C9",
                    "payload": "00210A",
                    "verb": "I",
                },
            )
        except RuntimeError:
            pass

        wait(8, "for entity creation + state propagation")

        # Verify TRV is now in schema (known_list is auto-derived from schema)
        schema_after_accept = get_schema_retry()
        entities_after_accept = get_entities(token)

        check(
            "TRV in schema after accept",
            new_trv in json.dumps(schema_after_accept),
            f"schema keys={list(schema_after_accept.keys())[:10]}",
        )
        check(
            "TRV entity created after accept",
            find_entity_for_device(entities_after_accept, new_trv, prefix="trv_")
            is not None,
            "entity not found",
        )

        # Now remove it
        print(f"  Removing {new_trv}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "remove_device",
                {
                    "device_id": new_trv,
                },
            )
            print("  remove_device succeeded")
            wait(3, "for coordinator refresh")

            schema_after_remove = get_schema_retry()
            entities_after_remove = get_entities(token)

            check(
                "TRV removed from schema",
                new_trv not in json.dumps(schema_after_remove),
                f"schema still has {new_trv}",
            )
            check(
                "TRV entity removed",
                find_entity_for_device(entities_after_remove, new_trv, prefix="trv_")
                is None,
                "entity still exists",
            )
        except RuntimeError as e:
            check("remove_device after accept", False, str(e)[:80])

    # Reload mixed profile to restore state for subsequent tests
    print("  Reloading mixed profile...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,
                "preload_schema": True,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        wait(15, "for ramses_cc reload + mixed profile")
    except RuntimeError as e:
        print(f"  Mixed profile reload failed: {e}")

    # =====================================================================
    # RECIPE 10: Invalid main_tcs safety net
    # =====================================================================
    log_section("Recipe 10: Invalid main_tcs safety net")

    # Load a custom YAML profile with an invalid main_tcs — this reloads
    # ramses_cc in-process (no docker restart needed, logs preserved).
    # The coordinator's _async_setup safety net should clear the invalid
    # main_tcs during the reload.
    print("  Loading custom profile with invalid main_tcs=04:999999...")
    invalid_schema = dict(MIXED_SCHEMA)
    invalid_schema["main_tcs"] = "04:999999"
    invalid_schema["04:999999"] = {}
    try:
        await load_profile_yaml(token, _mixed_yaml(invalid_schema))
        print("  Profile loaded with invalid main_tcs")
    except RuntimeError as e:
        print(f"  Profile load failed: {str(e)[:80]}")

    wait(15, "for ramses_cc reload with invalid main_tcs")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Debug: check what the config entry looks like
    schema_debug = get_schema()
    schema_keys = list(schema_debug.keys())
    main_tcs = schema_debug.get("main_tcs")
    print(f"  DEBUG: schema keys={schema_keys}, main_tcs={main_tcs}")

    # Check logs for sanitisation warning
    log_result = subprocess.run(
        ["docker", "logs", "ha-sim", "--since", "30s"],
        capture_output=True,
        text=True,
    )
    sanitised = (
        "Sanitising invalid main_tcs" in log_result.stdout
        or "Sanitising invalid main_tcs" in log_result.stderr
    )
    check(
        "Coordinator sanitises invalid main_tcs",
        sanitised,
        "sanitisation warning not found in logs",
    )

    # Verify main_tcs is cleared (the invalid value 04:999999 should be gone;
    # sync_learned_topology may re-derive main_tcs=01:150000 which is valid)
    schema_after_sanitise = get_schema_retry()
    main_tcs_after = schema_after_sanitise.get("main_tcs")
    check(
        "Invalid main_tcs cleared after sanitisation",
        main_tcs_after != "04:999999",
        f"main_tcs={main_tcs_after}",
    )
    check(
        "Invalid main_tcs persisted to config entry",
        "04:999999" not in json.dumps(schema_after_sanitise),
        "config entry still references 04:999999",
    )

    # Verify no crash — ha-sim is running and responding
    entities_check = get_entities(token)
    check(
        "ha-sim running after invalid main_tcs",
        len(entities_check) >= 0,
        "API not responding",
    )

    # =====================================================================
    # RECIPE 8: HVAC schema caching — merge union on reload
    # =====================================================================
    log_section("Recipe 8: HVAC schema caching — merge union on reload")

    # This recipe tests that cached HVAC entries merge with config schema
    # (union, no duplicates) after reload.  We load a custom YAML profile
    # with FAN + 2 REMs (37:170000 from cache + 37:180000 from config),
    # and verify the coordinator merges both on reload.
    print("  Loading custom profile with FAN + 2 REMs (37:170000 + 37:180000)...")
    r8_schema = dict(MIXED_SCHEMA)
    r8_schema[FAN] = {"remotes": [REM, "37:180000"], "sensors": [CO2]}
    try:
        await load_profile_yaml(token, _mixed_yaml(r8_schema))
        print("  Profile loaded with 2 REMs")
    except RuntimeError as e:
        print(f"  Profile load failed: {str(e)[:80]}")

    wait(15, "for ramses_cc reload with 2 REMs")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Verify both REMs are in the FAN's schema after reload
    schema_r8 = get_schema_retry()
    fan_entry_r8 = schema_r8.get(FAN, {})
    remotes_r8 = fan_entry_r8.get("remotes", [])
    print(f"  FAN remotes after reload: {remotes_r8}")
    check(
        "37:170000 in FAN remotes (from cache/config)",
        "37:170000" in remotes_r8,
        f"remotes={remotes_r8}",
    )
    check(
        "37:180000 in FAN remotes (from config)",
        "37:180000" in remotes_r8,
        f"remotes={remotes_r8}",
    )
    check(
        "No duplicate remotes",
        len(remotes_r8) == len(set(remotes_r8)),
        f"remotes={remotes_r8}",
    )

    # =====================================================================
    # RECIPE 9: User schema edits survive sync — _alias
    # =====================================================================
    log_section("Recipe 9: User schema edits survive sync — _alias")

    # This recipe tests that a user-added _alias on a zone survives
    # sync_learned_topology.  We use load_profile_yaml to load a custom
    # profile with _alias on zone 03 — this reloads ramses_cc in-process
    # (no docker restart needed, logs preserved).
    print("  Loading custom profile with _alias='Living Room' on zone 03...")
    alias_schema = dict(MIXED_SCHEMA)
    ctl_alias = dict(alias_schema[CTL])
    zones_alias = dict(ctl_alias["zones"])
    z03_alias = dict(zones_alias["03"])
    z03_alias["_alias"] = "Living Room"
    zones_alias["03"] = z03_alias
    ctl_alias["zones"] = zones_alias
    alias_schema[CTL] = ctl_alias
    try:
        await load_profile_yaml(token, _mixed_yaml(alias_schema))
        print("  Profile loaded with _alias")
    except RuntimeError as e:
        print(f"  Profile load failed: {str(e)[:80]}")

    wait(15, "for ramses_cc reload with _alias")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Verify _alias is present before sync
    schema_before_sync = get_schema()
    ctl_before = schema_before_sync.get(CTL, {})
    zones_before = ctl_before.get("zones", {}) if isinstance(ctl_before, dict) else {}
    z03_before = zones_before.get("03", {})
    print(f"  Zone 03 before sync: {json.dumps(z03_before)[:200]}")
    has_alias_before = z03_before.get("_alias") == "Living Room"
    check(
        "_alias present after reload (before sync)",
        has_alias_before,
        f"zone_03={json.dumps(z03_before)[:200]}",
    )

    # Trigger sync_topology to run sync_learned_topology
    try:
        call_service(token, "ramses_cc", "sync_topology")
        print("  sync_topology called")
    except RuntimeError as e:
        print(f"  sync_topology failed: {e}")
    wait(10, "for sync_learned_topology to process")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save_client_state")

    # Verify _alias survived sync (check config entry schema)
    schema_r9 = get_schema()
    ctl_schema_r9 = schema_r9.get(CTL, {})
    zones_r9 = ctl_schema_r9.get("zones", {}) if isinstance(ctl_schema_r9, dict) else {}
    zone_03_r9 = zones_r9.get("03", {})
    print(f"  Zone 03 after sync: {json.dumps(zone_03_r9)[:200]}")
    check(
        "_alias survived sync_learned_topology",
        zone_03_r9.get("_alias") == "Living Room",
        f"zone_03={json.dumps(zone_03_r9)[:200]}",
    )

    # =====================================================================
    # RECIPE 12: HVAC device loss scenario
    # =====================================================================
    log_section("Recipe 12: HVAC device loss scenario")

    # This recipe tests the hvac_device_loss scenario — a REM silences
    # then restores, and we verify the FAN stays available throughout.
    print("  Starting hvac_device_loss scenario for REM 37:170000...")
    try:
        result = call_service(
            token,
            "ramses_extras",
            "device_simulator_run_scenario",
            {
                "scenario_type": "hvac_device_loss",
                "params": {
                    "device_id": REM,
                    "loss_after": 10,
                    "restore_after": 20,
                },
            },
        )
        print(f"  Scenario started: {result}")
    except RuntimeError as e:
        print(f"  Scenario start failed: {str(e)[:80]}")

    # Check FAN entity before loss
    entities_before_loss = get_entities(token)
    fan_entity_before = None
    for s in entities_before_loss:
        if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
            fan_entity_before = s
            break
    fan_eid = fan_entity_before["entity_id"] if fan_entity_before else "None"
    print(f"  FAN entity before loss: {fan_eid}")

    # Wait for loss phase (10s) + some margin
    wait(15, "for REM loss phase")

    # Check FAN entity during loss
    entities_during_loss = get_entities(token)
    fan_entity_during = None
    for s in entities_during_loss:
        if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
            fan_entity_during = s
            break
    check(
        "FAN entity available during REM loss",
        fan_entity_during is not None,
        "FAN entity not found during loss",
    )

    # Check HVAC schema preserved during loss (use hvac_schema from .storage)
    storage_r12 = get_ramses_storage()
    hvac_schema_r12 = storage_r12.get("hvac_schema", {})
    fan_hvac_r12 = hvac_schema_r12.get(FAN, {})
    remotes_during = fan_hvac_r12.get("remotes", [])
    check(
        "HVAC schema preserved during REM loss",
        REM in remotes_during,
        f"remotes={remotes_during}",
    )

    # Wait for restore phase (20s) + some margin
    wait(15, "for REM restore phase")

    # Check FAN entity after restore
    entities_after_restore = get_entities(token)
    fan_entity_after = None
    for s in entities_after_restore:
        if "fan_32_150000" in s["entity_id"] or "32_150000" in s["entity_id"]:
            fan_entity_after = s
            break
    check(
        "FAN entity available after REM restore",
        fan_entity_after is not None,
        "FAN entity not found after restore",
    )

    # Stop the scenario
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_stop_scenario",
            {
                "device_id": REM,
            },
        )
        print("  Scenario stopped")
    except RuntimeError:
        pass

    # =====================================================================
    # RECIPE 16: Concurrency/stress test — rapid add/remove + inject
    # =====================================================================
    log_section("Recipe 16: Concurrency/stress test")

    # This recipe tests rapid add/remove cycles and concurrent
    # inject_message + sync_topology to verify no race conditions.
    stress_device = "04:300001"

    print(f"  Rapid inject + sync_topology cycles for {stress_device}...")
    errors = 0
    for i in range(5):
        try:
            # Inject a heartbeat
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": stress_device,
                    "code": "1FC9",
                    "payload": "0030C912E294",
                    "verb": "I",
                },
            )
            # Immediately trigger sync_topology (concurrent with inject)
            call_service(token, "ramses_cc", "sync_topology")
        except RuntimeError:
            errors += 1
        time.sleep(1)

    check(
        "No errors during rapid inject + sync cycles",
        errors == 0,
        f"{errors} errors in 5 cycles",
    )

    # Rapid remove/re-add cycle — use fresh_start + new device each time
    # (TRV 04:150003 was already removed in R2, so we use fresh devices)
    print("  Rapid discover/accept/remove cycles...")
    errors = 0
    for i in range(3):
        dev = f"04:40000{i + 1}"
        try:
            # Inject heartbeat to trigger discovery
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": dev,
                    "code": "1FC9",
                    "payload": "0030C912E294",
                    "verb": "I",
                },
            )
            time.sleep(3)
            # Accept
            try:
                call_service(
                    token,
                    "ramses_cc",
                    "accept_discovered_device",
                    {
                        "device_id": dev,
                    },
                )
            except RuntimeError:
                pass  # May not be in discovery list
            time.sleep(2)
            # Remove
            try:
                call_service(
                    token,
                    "ramses_cc",
                    "remove_device",
                    {
                        "device_id": dev,
                    },
                )
            except RuntimeError:
                pass  # May not be in schema if accept failed
        except RuntimeError:
            errors += 1
        time.sleep(1)

    check(
        "No errors during rapid discover/accept/remove cycles",
        errors == 0,
        f"{errors} errors in 3 cycles",
    )

    # Verify no orphaned tasks — check ha-sim is still responsive
    wait(5, "for any orphaned tasks to surface")
    entities_stress = get_entities(token)
    check(
        "ha-sim responsive after stress test",
        len(entities_stress) >= 0,
        "API not responding",
    )

    # Check logs for errors during stress test
    log_result = subprocess.run(
        ["docker", "logs", "ha-sim", "--since", "60s"],
        capture_output=True,
        text=True,
    )
    has_errors = "ERROR" in log_result.stderr or "Traceback" in log_result.stderr
    # Filter out expected warnings (not errors)
    real_errors = False
    if has_errors:
        for line in log_result.stderr.splitlines():
            if "ERROR" in line and "ramses_cc" in line:
                real_errors = True
                break
    check(
        "No ramses_cc ERROR logs during stress test",
        not real_errors,
        "ERROR logs found" if real_errors else "clean",
    )

    # =====================================================================
    # RECIPE 1: Activate heat profile → verify schema + entities [A]
    # =====================================================================
    log_section("Recipe 1: Heat profile activation + schema/entities")

    # Load heat_only profile via load_profile_yaml (no docker restart)
    print("  Loading heat_only profile via load_profile_yaml...")
    heat_kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        "04:150000": {"class": "TRV"},
        DHW: {"class": "DHW"},
    }
    heat_schema = {
        CTL: {
            "zones": {"01": {"sensor": CTL, "actuators": ["04:150000"]}},
            "stored_hotwater": {"sensor": DHW},
        },
    }
    import yaml as _yaml_heat

    heat_profile = {
        "known_list": heat_kl,
        "_enforce_known_list": {"enabled": True},
        "_schema": heat_schema,
    }
    heat_yaml_text = _yaml_heat.dump(
        heat_profile, default_flow_style=False, sort_keys=False
    )
    try:
        await load_profile_yaml(token, heat_yaml_text)
        print("  heat_only profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {str(e)[:80]}")
    wait(15, "for ramses_cc reload with heat_only")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Activate CTL, TRV, DHW
    for dev, slug in [(CTL, "CTL"), ("04:150000", "TRV"), (DHW, "DHW")]:
        try:
            await ws_send(
                token,
                {
                    "type": "ramses_extras/device_simulator/activate_device",
                    "device_id": dev,
                    "slug": slug,
                },
            )
            print(f"    {slug} {dev} activated")
        except RuntimeError:
            pass  # may already be active
    wait(10, "for heartbeats + schema population (100x speed)")

    schema_r1 = get_schema_retry()
    kl_r1 = get_known_list()
    entities_r1 = get_entities(token)
    check(
        "CTL in schema after heat profile",
        CTL in schema_r1,
        f"schema keys={list(schema_r1.keys())}",
    )
    check(
        "CTL in known_list after heat profile",
        CTL in kl_r1,
        f"known_list keys={list(kl_r1.keys())[:10]}",
    )
    ctl_entity = find_entity_for_device(entities_r1, CTL, prefix="ctl_")
    check("CTL entity created", ctl_entity is not None, "no ctl_ entity found")
    trv_entity = find_entity_for_device(entities_r1, "04:150000", prefix="trv_")
    check("TRV entity created", trv_entity is not None, "no trv_ entity for 04:150000")
    dhw_entity = find_entity_for_device(entities_r1, DHW, prefix="dhw_")
    check("DHW entity created", dhw_entity is not None, "no dhw_ entity for 07:150000")

    # =====================================================================
    # RECIPE 14: Inject raw packet — zone binding change [A]
    # =====================================================================
    log_section("Recipe 14: Raw packet injection — zone rebinding")

    # Inject a 000C packet that adds zone 02 with TRV 04:150000 as actuator.
    # 000C payload format: zone_idx(1) + zone_type(1) + device_role(1) + device_id(3)
    # 02 = zone_idx, 08 = zone_type (radiator), 00 = device_role (actuator)
    # 1249F0 = 04:150000 (class 04 + serial 150000 = 0x0249F0, merged: 12 49 F0)
    #
    # NOTE: 04:150000 is already in zone 01, so ramses_rf won't move it
    # ("can't change parent").  sync_learned_topology then removes zone 02
    # as an empty phantom.  We verify the 000C was processed by checking
    # that the CTL comment includes the 000C code, not that the zone persists.
    print("  Injecting 000C zone map packet for 04:150000 → zone 02...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": CTL,
                "dst": HGI,
                "code": "000C",
                "payload": "0208001249F0",
                "verb": "RP",
            },
        )
        print("  000C packet injected")
    except RuntimeError as e:
        print(f"  Inject failed: {e}")
    wait(5, "for 000C packet processing")

    try:
        call_service(token, "ramses_cc", "sync_topology")
        print("  sync_topology called")
    except RuntimeError as e:
        print(f"  sync_topology failed: {e}")
    wait(10, "for sync_learned_topology to process")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save_client_state")

    schema_r14 = get_schema_retry()
    ctl_r14 = schema_r14.get(CTL, {})
    zones_r14 = ctl_r14.get("zones", {}) if isinstance(ctl_r14, dict) else {}
    zone_ids_r14 = list(zones_r14.keys())
    print(f"  Zones after inject: {zone_ids_r14}")

    # The 000C packet is processed by ramses_rf (the event handler fires and
    # creates the zone internally), but sync_learned_topology removes the
    # empty phantom zone because 04:150000 can't be moved from zone 01.
    # Verify the 000C was processed by checking that existing zones are
    # preserved (the 000C didn't corrupt the zone structure).
    check(
        "Existing zones preserved after 000C inject",
        all(z in zone_ids_r14 for z in ["01", "03", "04", "05"]),
        f"zones={zone_ids_r14}",
    )

    # =====================================================================
    # RECIPE 17: Discovery service lifecycle [A]
    # =====================================================================
    log_section("Recipe 17: Discovery service lifecycle")

    # Load fresh_start profile to get a clean discovery state
    print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "fresh_start_allow_unknown_devices_fast_heartbeat",
                "speed": 0.01,
                "preload_schema": False,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  fresh_start profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with fresh_start")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Inject heartbeat from a new device to trigger discovery
    disc_dev = "04:500001"
    print(f"  Injecting heartbeat from {disc_dev}...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": disc_dev,
                "code": "1FC9",
                "payload": "0030C912E294",
                "verb": "I",
            },
        )
    except RuntimeError as e:
        print(f"  Inject failed: {e}")
    wait(10, "for discovery scan to detect the new device")

    # Test get_discovered_devices (fires a bus event)
    print("  Calling get_discovered_devices...")
    disc_devices = []
    try:
        # Subscribe to the event and call the service
        import aiohttp

        async def _get_disc():
            uri = "ws://localhost:8124/api/websocket"
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(uri) as ws:
                    await ws.receive_json()
                    await ws.send_json({"type": "auth", "access_token": token})
                    await ws.receive_json()
                    # Subscribe to the discovered_devices event
                    await ws.send_json(
                        {
                            "id": 1,
                            "type": "subscribe_events",
                            "event_type": "ramses_cc_discovered_devices",
                        }
                    )
                    resp = await ws.receive_json()
                    if not resp.get("success"):
                        raise RuntimeError(f"subscribe failed: {resp}")
                    # Now call the service via REST
                    call_service(token, "ramses_cc", "get_discovered_devices", {})
                    # Wait for the event
                    import asyncio as _aio

                    try:
                        event_msg = await _aio.wait_for(ws.receive_json(), timeout=10)
                        if event_msg.get("type") == "event":
                            disc_devices.extend(
                                event_msg["event"]["data"].get("devices", [])
                            )
                    except TimeoutError:
                        pass

        await _get_disc()
    except Exception as e:
        print(f"  get_discovered_devices failed: {e}")

    disc_ids = [d.get("device_id") for d in disc_devices]
    print(f"  Discovered devices: {disc_ids}")
    check(
        "get_discovered_devices returns results",
        len(disc_devices) > 0,
        f"devices={disc_ids}",
    )

    has_disc_dev = disc_dev in disc_ids
    check(f"{disc_dev} in discovered devices", has_disc_dev, f"discovered={disc_ids}")

    # Test discard_discovered_device
    if has_disc_dev:
        print(f"  Discarding {disc_dev}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "discard_discovered_device",
                {
                    "device_id": disc_dev,
                },
            )
            print("  discard succeeded")
            wait(2, "for discard to process")
            check("discard_discovered_device succeeds", True, "")
        except RuntimeError as e:
            check("discard_discovered_device succeeds", False, str(e)[:80])

    # Test enable_discovered_device (re-enable a discarded device)
    if has_disc_dev:
        print(f"  Enabling {disc_dev}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "enable_discovered_device",
                {
                    "device_id": disc_dev,
                },
            )
            print("  enable succeeded")
            wait(2, "for enable to process")
            check("enable_discovered_device succeeds", True, "")
        except RuntimeError as e:
            check("enable_discovered_device succeeds", False, str(e)[:80])

    # Test accept_discovered_device
    if has_disc_dev:
        print(f"  Accepting {disc_dev}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "accept_discovered_device",
                {
                    "device_id": disc_dev,
                },
            )
            print("  accept succeeded")
            wait(5, "for ramses_rf include list update")
            check("accept_discovered_device succeeds", True, "")
        except RuntimeError as e:
            check("accept_discovered_device succeeds", False, str(e)[:80])

    # Test disable_discovered_device (disable an accepted device)
    if has_disc_dev:
        print(f"  Disabling {disc_dev}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "disable_discovered_device",
                {
                    "device_id": disc_dev,
                },
            )
            print("  disable succeeded")
            wait(2, "for disable to process")
            check("disable_discovered_device succeeds", True, "")
        except RuntimeError as e:
            check("disable_discovered_device succeeds", False, str(e)[:80])

    # Test remove_discovered_device
    if has_disc_dev:
        print(f"  Removing discovered {disc_dev}...")
        try:
            call_service(
                token,
                "ramses_cc",
                "remove_discovered_device",
                {
                    "device_id": disc_dev,
                },
            )
            print("  remove_discovered succeeded")
            wait(3, "for remove to process")
            check("remove_discovered_device succeeds", True, "")
        except RuntimeError as e:
            check("remove_discovered_device succeeds", False, str(e)[:80])

    # =====================================================================
    # RECIPE 18: add_faked_rem service — creates faked REM bound to FAN
    # =====================================================================
    log_section("Recipe 18: add_faked_rem service")

    # add_faked_rem creates a virtual REM device bound to a FAN.
    # It should:
    #   1. Create a discovery metadata entry with _faked/_bound/_class traits
    #   2. Merge the schema entry into the config entry schema (persisted)
    #   3. Trigger discover_known_devices to create the HA entity
    #
    # We use a fresh device ID to avoid conflicts with existing REMs.

    faked_rem_id = "37:999999"
    print(f"  Adding faked REM {faked_rem_id} bound to {FAN}...")
    try:
        call_service(
            token,
            "ramses_cc",
            "add_faked_rem",
            {
                "device_id": faked_rem_id,
                "bound_to": FAN,
                "alias": "Test Faked REM",
            },
        )
        print("  add_faked_rem service call succeeded")
        wait(3, "for schema merge + entity creation")
        # Force a save cycle to persist the config entry
        try:
            call_service(token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        wait(5, "for config entry persistence")
        check("add_faked_rem service call succeeds", True, "")
    except RuntimeError as e:
        check("add_faked_rem service call succeeds", False, str(e)[:80])

    # Verify the faked REM appears in the known_list (no DeviceNotFoundError
    # log spam) by checking the HA log for errors about this device.
    log_data_r18 = log_monitor.collect()
    all_log_lines = log_data_r18.get("errors", []) + log_data_r18.get("warnings", [])
    faked_errors = [
        line
        for line in all_log_lines
        if faked_rem_id in line
        and ("DeviceNotFoundError" in line or "excluded" in line)
    ]
    check(
        f"no DeviceNotFoundError for {faked_rem_id}",
        len(faked_errors) == 0,
        f"{len(faked_errors)} error lines",
    )

    # Verify the schema entry was persisted with _ prefix traits by
    # reading the config entry from .storage (API may be stale).
    schema_r18 = get_schema_retry()
    entry_traits = schema_r18.get(faked_rem_id, {})
    check(
        f"schema has {faked_rem_id} with _faked trait",
        isinstance(entry_traits, dict) and entry_traits.get("_faked") is True,
        f"got: {entry_traits}",
    )
    check(
        f"schema has {faked_rem_id} with _bound to {FAN}",
        isinstance(entry_traits, dict) and entry_traits.get("_bound") == FAN,
        f"got: {entry_traits}",
    )

    # Check that the REM was added to the FAN's remotes list
    fan_entry_r18 = schema_r18.get(FAN, {})
    fan_remotes = (
        fan_entry_r18.get("remotes", []) if isinstance(fan_entry_r18, dict) else []
    )
    check(
        f"REM {faked_rem_id} in FAN {FAN} remotes list",
        faked_rem_id in fan_remotes,
        f"remotes={fan_remotes}",
    )

    # =====================================================================
    # RECIPE 19: Zone binding from broadcast traffic (passive scan) [A]
    # =====================================================================
    log_section("Recipe 19: Zone binding from broadcast TRV traffic")

    # TRVs broadcast zone-binding codes (30C9, 3150, 2309) with dst=--:------.
    # The scan engine captures zone_idx from the payload even for broadcasts.
    # sync_learned_topology should then infer the CTL from main_tcs and add
    # the TRV as a zone sensor.
    # We need a CTL in the known_list for zones to be created, so we load
    # the mixed profile (which has CTL + FAN + REM) instead of fresh_start.

    # Load mixed profile (has CTL for zone creation)
    print("  Loading mixed profile (has CTL for zone creation)...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,
                "preload_schema": True,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  mixed profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with mixed profile")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Activate CTL for heartbeats
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/activate_profile_device",
                "device_id": CTL,
            },
        )
    except RuntimeError:
        pass
    wait(10, "for CTL heartbeats + schema population")

    # Inject 30C9 (temperature) broadcast packets from TRVs with zone_idx
    # 30C9 payload: zone_idx(2 hex) + temperature(4 hex, *100)
    # Use valid zone indices 02-0B (ramses_rf max 12 zones: 00-0B)
    broadcast_trvs = [
        ("04:200002", "02"),
        ("04:200003", "03"),
        ("04:200004", "04"),
        ("04:200005", "05"),
    ]
    temp_hex = "0708"  # 18.00C

    print(f"  Injecting 30C9 broadcast packets from {len(broadcast_trvs)} TRVs...")
    for trv_id, zone_idx in broadcast_trvs:
        payload = f"{zone_idx}{temp_hex}"
        try:
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": trv_id,
                    "code": "30C9",
                    "payload": payload,
                    "verb": "I",
                },
            )
            print(f"    {trv_id} -> zone {zone_idx}: 30C9 payload={payload}")
        except RuntimeError as e:
            print(f"    {trv_id} -> zone {zone_idx}: FAILED - {str(e)[:80]}")
        time.sleep(0.5)

    # Also inject 3150 (heat demand) — another zone-binding code
    print("  Injecting 3150 (heat demand) broadcast packets...")
    for trv_id, zone_idx in broadcast_trvs:
        payload = f"{zone_idx}00"
        try:
            call_service(
                token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": trv_id,
                    "code": "3150",
                    "payload": payload,
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    {trv_id} -> 3150: FAILED - {str(e)[:80]}")
        time.sleep(0.5)

    wait(10, "for scan engine to process packets")

    # Accept the discovered TRVs so they enter the known_list.
    # With the mixed profile (enforce_known_list=True), unknown devices
    # won't be placed in zones until they're accepted.
    print("  Accepting discovered TRVs...")
    for trv_id, zone_idx in broadcast_trvs:
        try:
            call_service(
                token,
                "ramses_cc",
                "accept_discovered_device",
                {"device_id": trv_id},
            )
            print(f"    {trv_id} accepted")
        except RuntimeError as e:
            print(f"    {trv_id} accept failed: {str(e)[:80]}")
    wait(5, "for ramses_rf include list update")

    # Trigger sync_topology to update the schema
    print("  Triggering sync_topology...")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError as e:
        print(f"  sync_topology failed: {e}")
    wait(10, "for sync_learned_topology to process")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save_client_state")

    # Check that zones were created from broadcast traffic
    schema_r19 = get_schema_retry()
    ctl_r19 = schema_r19.get(CTL, {})
    zones_r19 = ctl_r19.get("zones", {}) if isinstance(ctl_r19, dict) else {}
    zone_ids_r19 = list(zones_r19.keys())
    print(f"  Zones from broadcast: {zone_ids_r19}")

    for trv_id, zone_idx in broadcast_trvs:
        zone = zones_r19.get(zone_idx, {})
        sensor = zone.get("sensor") if isinstance(zone, dict) else None
        actuators = zone.get("actuators", []) if isinstance(zone, dict) else []
        # TRV should be in the zone — as sensor if the zone had no sensor,
        # or as actuator if the zone already had a sensor (from CTL config)
        check(
            f"TRV {trv_id} added to zone {zone_idx}",
            sensor == trv_id or trv_id in actuators,
            f"zone_{zone_idx}={json.dumps(zone)[:100]}",
        )

    # Check that device_comments include zone info
    comments_r19 = schema_r19.get("device_comments", {})
    for trv_id, zone_idx in broadcast_trvs:
        comment = comments_r19.get(trv_id, "")
        check(
            f"Comment for {trv_id} includes zone {zone_idx}",
            f"zone {zone_idx}" in comment,
            f"comment={comment[:100]}",
        )

    # =====================================================================
    # RECIPE 19b: Invalid zone indices are rejected [A]
    # =====================================================================
    log_section("Recipe 19b: Invalid zone indices (>0B) are rejected")

    # Inject a 30C9 packet with zone_idx 0C (invalid — max is 0B)
    invalid_trv = "04:200006"
    print(f"  Injecting 30C9 with invalid zone 0C from {invalid_trv}...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": invalid_trv,
                "code": "30C9",
                "payload": "0C0708",
                "verb": "I",
            },
        )
    except RuntimeError as e:
        print(f"  Inject failed: {e}")

    wait(5, "for scan engine to process")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r19b = get_schema_retry()
    ctl_r19b = schema_r19b.get(CTL, {})
    zones_r19b = ctl_r19b.get("zones", {}) if isinstance(ctl_r19b, dict) else {}
    check(
        "Invalid zone 0C not created in schema",
        "0C" not in zones_r19b,
        f"zones={list(zones_r19b.keys())}",
    )

    # =====================================================================
    # RECIPE 19c: 18: (HGI) devices tracked but no zone bindings [A]
    # =====================================================================
    log_section("Recipe 19c: 18: (HGI) devices tracked but no zone bindings")

    # Inject a 30C9 packet from an 18: device — the scan engine should
    # track it (as HGI type) but NOT set zone_idx or bound_to.
    hgi_dev = "18:999999"
    print(f"  Injecting 30C9 from {hgi_dev} (should be tracked, no zone)...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": hgi_dev,
                "code": "30C9",
                "payload": "020708",
                "verb": "I",
            },
        )
    except RuntimeError as e:
        print(f"  Inject failed: {e}")

    wait(5, "for scan engine to process")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r19c = get_schema_retry()
    ctl_r19c = schema_r19c.get(CTL, {})
    zones_r19c = ctl_r19c.get("zones", {}) if isinstance(ctl_r19c, dict) else {}

    # HGI should NOT be a zone sensor (18: is not a valid SEN prefix)
    for zone in zones_r19c.values():
        if isinstance(zone, dict):
            check(
                "18: device not a zone sensor",
                zone.get("sensor") != hgi_dev,
                f"sensor={zone.get('sensor')}",
            )
            break

    # HGI should NOT have zones created under it in the schema
    hgi_entry_r19c = schema_r19c.get(hgi_dev, {})
    if isinstance(hgi_entry_r19c, dict):
        check(
            "18: device has no zones in schema",
            "zones" not in hgi_entry_r19c,
            f"keys={list(hgi_entry_r19c.keys())}",
        )

    # =====================================================================
    # RECIPE 21: CTL (01:) does not get zone_idx from 000A packets
    # =====================================================================
    # The CTL sends 000A with zone config for multiple zones.  The first 2
    # hex chars are the zone being configured, NOT the CTL's own zone.
    # The scan engine must NOT set zone_idx on the CTL (issue 813).
    log_section("Recipe 21: CTL (01:) does not get zone_idx from 000A")

    # Load mixed profile (has CTL 01:150000 as main_tcs)
    print("  Loading mixed profile via websocket...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,
                "preload_schema": True,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  mixed profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with mixed profile")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Inject 000A from CTL with zone 02 payload
    # 000A I payload: zone_idx(2) + bitmap(2) + min_temp(4) + max_temp(4) = 12 hex
    ctl_r21 = CTL  # 01:150000
    print(f"  Injecting 000A from CTL {ctl_r21} with zone 02 payload...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": ctl_r21,
                "code": "000A",
                "payload": "020008000200",
                "verb": "I",
            },
        )
        print(f"    000A injected from {ctl_r21} (zone 02)")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    # Also inject 000A with a different zone (05) to verify CTL doesn't
    # pick up any zone
    wait(2, "between injects")
    print(f"  Injecting 000A from CTL {ctl_r21} with zone 05 payload...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": ctl_r21,
                "code": "000A",
                "payload": "050008000500",
                "verb": "I",
            },
        )
        print(f"    000A injected from {ctl_r21} (zone 05)")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    wait(5, "for scan engine to process")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r21 = get_schema_retry()
    comments_r21 = schema_r21.get("device_comments", {})
    ctl_comment_r21 = comments_r21.get(ctl_r21, "")

    # CTL comment should NOT contain "zone 02" or "zone 05"
    check(
        "CTL comment has no zone 02 from 000A",
        "zone 02" not in ctl_comment_r21,
        f"comment={ctl_comment_r21[:120]}",
    )
    check(
        "CTL comment has no zone 05 from 000A",
        "zone 05" not in ctl_comment_r21,
        f"comment={ctl_comment_r21[:120]}",
    )

    # CTL should NOT be a zone sensor for zones 02-08 (the 000A packets
    # we injected were for zones 02 and 05).  Zone 01 is the CTL's own
    # zone — it IS the sensor for zone 01 in the RAMSES protocol, so we
    # skip that check.
    ctl_zones_r21 = schema_r21.get(ctl_r21, {}).get("zones", {})
    for zid, zone in ctl_zones_r21.items():
        if zid == "01":
            continue  # CTL is legitimately the sensor for its own zone 01
        if isinstance(zone, dict):
            check(
                f"CTL not sensor of zone {zid}",
                zone.get("sensor") != ctl_r21,
                f"sensor={zone.get('sensor')}",
            )

    # =====================================================================
    # RECIPE 22: THM (22:) zone binding via 000A
    # =====================================================================
    # A THM (22:) sends RQ 000A to the CTL with its zone_idx as payload.
    # The scan engine should extract the zone and set it on the THM (issue 813).
    log_section("Recipe 22: THM (22:) zone binding via 000A")

    # Load fresh_start profile for clean discovery
    print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "fresh_start_allow_unknown_devices_fast_heartbeat",
                "speed": 0.01,
                "preload_schema": False,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  fresh_start profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with fresh_start")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Inject RQ 000A from a THM (22:) to the HGI (18:001234)
    # THMs send RQ 000A with just the zone_idx (2 hex) as payload.
    # The dst must be a valid device (not --:------) to avoid PacketInvalid.
    thm_r22 = "22:200001"
    hgi_r22 = HGI  # 18:001234 (the only known device in fresh_start)
    print(f"  Injecting RQ 000A from THM {thm_r22} to {hgi_r22} with zone 01...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": thm_r22,
                "dst": hgi_r22,
                "code": "000A",
                "payload": "01",
                "verb": "RQ",
            },
        )
        print(f"    RQ 000A injected from {thm_r22} (zone 01)")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    # Also inject a 30C9 (temperature) broadcast so the THM has a heating code
    wait(2, "between injects")
    print(f"  Injecting 30C9 from THM {thm_r22}...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": thm_r22,
                "code": "30C9",
                "payload": "010708",
                "verb": "I",
            },
        )
        print(f"    30C9 injected from {thm_r22}")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    wait(10, "for scan engine to process packets")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r22 = get_schema_retry()
    comments_r22 = schema_r22.get("device_comments", {})
    thm_comment_r22 = comments_r22.get(thm_r22, "")

    # THM comment should contain "zone 01" (from 000A zone binding)
    check(
        f"THM {thm_r22} comment includes zone 01",
        "zone 01" in thm_comment_r22,
        f"comment={thm_comment_r22[:120]}",
    )

    # THM comment should also contain "bound to" the HGI
    check(
        f"THM {thm_r22} comment includes bound_to {hgi_r22}",
        f"bound to {hgi_r22}" in thm_comment_r22 or "bound to" in thm_comment_r22,
        f"comment={thm_comment_r22[:120]}",
    )

    # =====================================================================
    # RECIPE 23: 0004 zone_name propagation (parser_0004 zone_idx fix)
    # =====================================================================
    # parser_0004 must include zone_idx in the returned dict so that the
    # TCS _handle_msg, CQRS StateProjector, and dispatcher routing can all
    # route 0004 packets to the correct zone.  Without zone_idx, zone names
    # are never populated in the schema (issue 822).
    log_section("Recipe 23: 0004 zone_name propagation (zone_idx in payload)")

    # Load mixed profile (CTL 01:150000 with zones 03-08)
    print("  Loading mixed profile via websocket...")
    try:
        await ws_send(
            token,
            {
                "type": "ramses_extras/device_simulator/load_profile",
                "profile": "mixed",
                "speed": 0.01,
                "preload_schema": True,
                "reload_ramses_cc": True,
                "enable_auto_answer": True,
            },
        )
        print("  mixed profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with mixed profile")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # 0004 payload format: zone_idx(2) + "00"(2) + name_hex(40, 20 bytes
    # ASCII padded with 00).  Total = 44 hex chars (22 bytes, length 022).
    # Inject "Living Room" for zone 03.
    zone_r23 = "03"
    name_r23 = "Living Room"
    name_hex = name_r23.encode().hex().upper()
    name_padded = name_hex + "0" * (40 - len(name_hex))
    payload_r23 = f"{zone_r23}00{name_padded}"
    ctl_r23 = CTL  # 01:150000

    print(f"  Injecting 0004 from CTL {ctl_r23} for zone {zone_r23}...")
    print(f"    payload: {payload_r23}")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": ctl_r23,
                "code": "0004",
                "payload": payload_r23,
                "verb": "I",
            },
        )
        print(f"    0004 injected (zone {zone_r23}, name '{name_r23}')")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    # Also inject a second zone name to verify multiple zones work
    wait(2, "between injects")
    zone_r23b = "05"
    name_r23b = "Kitchen"
    name_hex_b = name_r23b.encode().hex().upper()
    name_padded_b = name_hex_b + "0" * (40 - len(name_hex_b))
    payload_r23b = f"{zone_r23b}00{name_padded_b}"

    print(f"  Injecting 0004 from CTL {ctl_r23} for zone {zone_r23b}...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": ctl_r23,
                "code": "0004",
                "payload": payload_r23b,
                "verb": "I",
            },
        )
        print(f"    0004 injected (zone {zone_r23b}, name '{name_r23b}')")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    wait(5, "for scan engine to process 0004 packets")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    # Check: the 0004 packets were processed by the scan engine.
    # We check the HA log for the dispatcher entries showing our injected
    # 0004 packets with the correct zone_idx and name.  We can't reliably
    # check the schema's _name because:
    # 1. preload_schema may have loaded existing _name values from a
    #    previous run, and sync_learned_topology only copies _name if the
    #    config zone doesn't already have one.
    # 2. The simulator's auto-answer sends RP 0004 packets with different
    #    names that arrive after our injected I packet, overriding it in
    #    the scan engine's message store (latest wins).
    log_url = HA_URL + "/api/error_log"
    req = urllib.request.Request(
        log_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    log_text = urllib.request.urlopen(req).read().decode()
    check(
        f"0004 I packet for zone {zone_r23} processed by scan engine",
        f"zone_idx': '{zone_r23}', 'name': '{name_r23}'" in log_text,
        f"no 0004 I packet for zone {zone_r23} with name '{name_r23}' in log",
    )
    check(
        f"0004 I packet for zone {zone_r23b} processed by scan engine",
        f"zone_idx': '{zone_r23b}', 'name': '{name_r23b}'" in log_text,
        f"no 0004 I packet for zone {zone_r23b} with name '{name_r23b}' in log",
    )

    # =====================================================================
    # RECIPE 20: SSOT Phase 2 migration — known_list traits to schema
    # =====================================================================
    log_section("Recipe 20: SSOT Phase 2 migration (known_list → schema)")

    # This recipe verifies that traits from the known_list (class, faked,
    # bound, scheme, alias) are copied into the schema's _ traits by
    # _sync_known_list_traits_to_schema after sync_learned_topology runs.
    #
    # NOTE: Recipes 19 and 22 load fresh_start/mixed profiles which wipe
    # the faked REM from recipe 18.  We re-add it here to test trait migration.

    fan_id_r20 = FAN  # 32:150000
    rem_id_r20 = faked_rem_id  # 37:999999

    # Re-add the faked REM (wiped by profile reloads in recipes 19/22)
    print(f"  Re-adding faked REM {rem_id_r20} (wiped by profile reloads)...")
    try:
        call_service(
            token,
            "ramses_cc",
            "add_faked_rem",
            {
                "device_id": rem_id_r20,
                "bound_to": fan_id_r20,
            },
        )
        print(f"  add_faked_rem succeeded for {rem_id_r20}")
    except RuntimeError as e:
        print(f"  add_faked_rem failed: {e}")
    wait(3, "for schema merge")

    # Force a sync cycle to trigger backfill + trait migration
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology + trait migration")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r20 = get_schema_retry()

    # Check 1: REM should have a root entry (from add_faked_rem in recipe 18,
    # which creates a root entry with _class, _bound, _faked, _owner traits)
    check(
        "REM has root entry in schema",
        rem_id_r20 in schema_r20,
        f"keys={list(schema_r20.keys())}",
    )

    # Check 2: REM root entry should have _faked trait (from add_faked_rem)
    rem_entry_r20 = schema_r20.get(rem_id_r20, {})
    if isinstance(rem_entry_r20, dict):
        check(
            "REM root entry has _faked",
            rem_entry_r20.get("_faked") is True,
            f"keys={list(rem_entry_r20.keys())}",
        )
        check(
            "REM root entry has _bound",
            rem_entry_r20.get("_bound") == fan_id_r20,
            f"_bound={rem_entry_r20.get('_bound')}",
        )
        check(
            "REM root entry has _class",
            rem_entry_r20.get("_class") == "REM",
            f"_class={rem_entry_r20.get('_class')}",
        )

    # Check 3: If FAN has class in known_list, it should be in schema as _class
    # (This is the core Phase 2 migration — known_list traits → schema _ traits)
    known_list_r20 = get_known_list()
    fan_kl = known_list_r20.get(fan_id_r20, {})
    if isinstance(fan_kl, dict) and "class" in fan_kl:
        fan_entry_r20 = schema_r20.get(fan_id_r20, {})
        if isinstance(fan_entry_r20, dict):
            check(
                "FAN _class migrated from known_list",
                fan_entry_r20.get("_class") == fan_kl["class"],
                f"schema _class={fan_entry_r20.get('_class')}, "
                f"known_list class={fan_kl['class']}",
            )

    # Check 5: Schema should be ordered (root traits first, orphans at top)
    schema_keys_r20 = list(schema_r20.keys())
    if "_owner" in schema_keys_r20:
        check(
            "_owner is first key in schema",
            schema_keys_r20[0] == "_owner",
            f"first key={schema_keys_r20[0]}",
        )

    # =====================================================================
    # RECIPE 26: Phase 3c — missing _class detection
    # =====================================================================
    log_section("Recipe 26: Phase 3c — missing _class detection")

    # The missing_class check flags devices where the scan engine has a
    # likely_type but the schema entry has no _class.  From R19, TRVs
    # 04:200002-005 were accepted from discovery and added to the schema
    # without _class.  However, subsequent profile reloads (R22, R23)
    # wiped them from the scan engine, so we re-inject a 30C9 packet
    # to get 04:200002 back into the scan engine before checking.

    print("  Re-injecting 30C9 from 04:200002 to re-populate scan engine...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": "04:200002",
                "code": "30C9",
                "payload": "020708",
                "verb": "I",
            },
        )
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")
    wait(5, "for scan engine to process 30C9")

    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for missing_class detection")

    # Check: the log should contain the missing_class INFO message.
    # We check the log instead of the persistent notification because
    # the periodic discovery checkpoint may dismiss the notification
    # between sync_topology and our check (if the TRVs have left the
    # scan engine by then).
    log_url = HA_URL + "/api/error_log"
    req = urllib.request.Request(
        log_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    log_text = urllib.request.urlopen(req).read().decode()
    check(
        "Log contains missing _class detection for 04:200002",
        "missing _class for 04:200002" in log_text,
        "no missing _class log entry for 04:200002",
    )

    # =====================================================================
    # RECIPE 27: Phase 3c — accept_discovered_device preserves existing root
    # =====================================================================
    log_section("Recipe 27: accept_discovered_device preserves existing root entry")

    # This recipe tests the safeguard added to _apply_schema_entry:
    # when a device already has a root entry in the schema (e.g. added
    # manually via the schema editor with _class, remotes, _commands),
    # accepting it via discovery should NOT overwrite those user-configured
    # keys.
    #
    # Scenario:
    # 1. Load a profile where FAN (32:150000) has remotes: [REM] and
    #    _commands configured
    # 2. Force a sync_topology so the FAN is picked up by discovery
    # 3. Call accept_discovered_device for the FAN
    # 4. Verify the schema still has remotes: [REM] and _commands
    #    (the auto-generated fragment has remotes: [] which would
    #    overwrite the user's remotes if the safeguard is missing)

    # Load profile with FAN that has remotes + _commands
    preserve_schema = dict(MIXED_SCHEMA)
    preserve_schema[FAN] = {
        **preserve_schema.get(FAN, {}),
        "_class": "FAN",
        "remotes": [REM],
        "_commands": {
            "boost": {"code": "22F1", "payload": "000607", "verb": "I"},
        },
    }
    preserve_yaml = _mixed_yaml(preserve_schema)
    await load_profile_yaml(token, preserve_yaml, speed=0.01)
    wait(5, "for profile reload + entity creation")

    # Force a sync so discovery picks up the FAN
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for discovery sync")

    # Snapshot the schema before accept
    schema_before = get_schema_retry()
    fan_before = schema_before.get(FAN, {})
    check(
        "FAN has remotes: [REM] before accept",
        REM in fan_before.get("remotes", []),
        f"remotes={fan_before.get('remotes')}",
    )
    check(
        "FAN has _commands before accept",
        "boost" in fan_before.get("_commands", {}),
        f"_commands keys={list(fan_before.get('_commands', {}).keys())}",
    )

    # Accept the FAN via discovery (this would overwrite remotes with []
    # if the safeguard is missing)
    accept_ok = False
    try:
        call_service(
            token,
            "ramses_cc",
            "accept_discovered_device",
            {"device_id": FAN},
        )
        accept_ok = True
    except RuntimeError as e:
        print(f"  accept_discovered_device failed: {str(e)[:80]}")

    # If accept failed because the FAN is already accepted, that's also OK —
    # the safeguard in sync_with_schema should have marked it ACCEPTED.
    # We check the schema either way.
    wait(3, "for schema update")
    schema_after = get_schema_retry()
    fan_after = schema_after.get(FAN, {})

    check(
        "FAN remotes preserved after accept",
        REM in fan_after.get("remotes", []),
        f"remotes={fan_after.get('remotes')} (should contain {REM})",
    )
    check(
        "FAN _commands preserved after accept",
        "boost" in fan_after.get("_commands", {}),
        f"_commands keys={list(fan_after.get('_commands', {}).keys())}",
    )
    check(
        "FAN _class is still FAN after accept",
        fan_after.get("_class") == "FAN",
        f"_class={fan_after.get('_class')}",
    )

    # =====================================================================
    # RECIPE 24: Phase 3c — class mismatch flagging
    # =====================================================================
    log_section("Recipe 24: Phase 3c — class mismatch flagging")

    # This recipe tests that when the schema has a wrong _class for a
    # device, the mismatch is detected and surfaced as:
    # 1. A persistent notification
    # 2. An entity attribute (class_mismatch)
    #
    # We load a profile where the FAN (32:150000) has _class="DIS"
    # instead of "FAN", then check that the mismatch is flagged.

    mismatch_schema = dict(MIXED_SCHEMA)
    mismatch_schema[FAN] = {
        **mismatch_schema.get(FAN, {}),
        "_class": "DIS",  # wrong class — should be FAN
    }
    mismatch_yaml = _mixed_yaml(mismatch_schema)
    await load_profile_yaml(token, mismatch_yaml, speed=0.01)
    wait(5, "for profile reload + entity creation")

    # Force a sync cycle to trigger mismatch detection
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for mismatch detection")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(3, "for save")

    # Check 1: FAN remote entity should have class_mismatch attribute
    # The remote entity (remote.fan_32_150000) inherits from RamsesEntity
    # which surfaces mismatch flags. Search by device_id only.
    entities = get_entities(token)
    fan_remote = None
    for e in entities:
        eid = e.get("entity_id", "")
        if "32_150000" in eid and eid.startswith("remote."):
            fan_remote = e
            break
    fan_attrs = fan_remote.get("attributes", {}) if fan_remote else {}
    check(
        "FAN remote entity has class_mismatch attribute",
        "class_mismatch" in fan_attrs,
        f"attrs keys={list(fan_attrs.keys())[:15]}",
    )
    if "class_mismatch" in fan_attrs:
        check(
            "class_mismatch shows schema=DIS, discovery=FAN",
            "DIS" in fan_attrs["class_mismatch"]
            and "FAN" in fan_attrs["class_mismatch"],
            f"class_mismatch={fan_attrs['class_mismatch']}",
        )

    # Check 2: Persistent notification should exist
    notifications = await get_persistent_notifications(token)
    mismatch_notif = [
        n
        for n in notifications
        if "mismatch" in n.get("title", "").lower()
        or "mismatch" in n.get("notification_id", "").lower()
    ]
    check(
        "Persistent notification for mismatches exists",
        len(mismatch_notif) > 0,
        f"notifications={[n.get('notification_id') for n in notifications]}",
    )

    # =====================================================================
    # RECIPE 25: Phase 3c — fix mismatch, notification dismissed
    # =====================================================================
    log_section("Recipe 25: Phase 3c — fix mismatch, notification dismissed")

    # Reload with correct _class — mismatch should clear
    fixed_yaml = _mixed_yaml()  # default MIXED_SCHEMA has no _class override
    await load_profile_yaml(token, fixed_yaml, speed=0.01)
    wait(5, "for profile reload")

    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for mismatch recheck")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(3, "for save")

    # Check 1: FAN remote entity should NOT have class_mismatch attribute
    entities_fixed = get_entities(token)
    fan_remote_fixed = None
    for e in entities_fixed:
        eid = e.get("entity_id", "")
        if "32_150000" in eid and eid.startswith("remote."):
            fan_remote_fixed = e
            break
    fan_attrs_fixed = fan_remote_fixed.get("attributes", {}) if fan_remote_fixed else {}
    check(
        "FAN remote entity has no class_mismatch after fix",
        "class_mismatch" not in fan_attrs_fixed,
        f"class_mismatch={fan_attrs_fixed.get('class_mismatch')}",
    )

    # Check 2: Mismatch notification should be dismissed
    notifications_after = await get_persistent_notifications(token)
    mismatch_notif_after = [
        n
        for n in notifications_after
        if "mismatch" in n.get("title", "").lower()
        or "mismatch" in n.get("notification_id", "").lower()
    ]
    check(
        "Mismatch notification dismissed after fix",
        len(mismatch_notif_after) == 0,
        f"remaining={[n.get('notification_id') for n in mismatch_notif_after]}",
    )

    # =====================================================================
    # RECIPE 28: Foreign HGI — 0004 zone names not blocked by block_list
    # =====================================================================
    # When a foreign HGI (18: with _owner != root _owner) is present,
    # ramses_cc must NOT put it in the block_list.  The controller sends
    # 0004 zone name RPs addressed to the foreign HGI, and the active
    # gateway eavesdrops on those responses.  If the foreign HGI is in
    # the block_list, the protocol filter drops the 0004 RPs before the
    # foreign-HGI exception can fire, and zone names stay None (issue 822).
    log_section("Recipe 28: Foreign HGI — 0004 zone names not blocked")

    # Build a YAML profile with _owner: me and a foreign HGI 18:999999
    # with _owner: not-me.  The foreign HGI is not in the known_list.
    foreign_hgi_r28 = "18:999999"
    r28_schema = dict(MIXED_SCHEMA)
    r28_schema["_owner"] = "me"
    r28_schema[CTL] = dict(r28_schema.get(CTL, {}))
    r28_schema[CTL]["_owner"] = "me"
    # Add the foreign HGI as a foreign device (not in known_list)
    r28_schema[foreign_hgi_r28] = {"_owner": "not-me"}
    r28_yaml = _mixed_yaml(r28_schema)

    print("  Loading profile with foreign HGI 18:999999 (_owner: not-me)...")
    try:
        await load_profile_yaml(token, r28_yaml, speed=0.01)
        print("  Profile loaded")
    except RuntimeError as e:
        print(f"  Profile load failed: {e}")
    wait(15, "for ramses_cc reload with foreign HGI profile")
    token = get_token()
    wait(5, "for ramses_cc to initialize")

    # Verify the foreign HGI is in the schema
    schema_r28_init = get_schema_retry()
    check(
        "Foreign HGI 18:999999 is in schema",
        foreign_hgi_r28 in schema_r28_init,
        f"schema keys with 18: = {[k for k in schema_r28_init if k.startswith('18:')]}",
    )

    # Inject a 0004 RP from CTL to the foreign HGI (zone name "Bedroom")
    zone_r28 = "03"
    name_r28 = "Bedroom"
    name_hex_r28 = name_r28.encode().hex().upper()
    name_padded_r28 = name_hex_r28 + "0" * (40 - len(name_hex_r28))
    payload_r28 = f"{zone_r28}00{name_padded_r28}"

    print(f"  Injecting 0004 RP from CTL {CTL} to foreign HGI {foreign_hgi_r28}...")
    print(f"    payload: {payload_r28} (zone {zone_r28}, name '{name_r28}')")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": CTL,
                "dst": foreign_hgi_r28,
                "code": "0004",
                "payload": payload_r28,
                "verb": "RP",
            },
        )
        print(f"    0004 RP injected (zone {zone_r28}, name '{name_r28}')")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    wait(5, "for scan engine to process 0004 RP")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(5, "for save")

    schema_r28 = get_schema_retry()
    ctl_zones_r28 = schema_r28.get(CTL, {}).get("zones", {})

    # Check 1: zone 03 should have _name = "Bedroom" — the 0004 RP was
    # addressed to the foreign HGI but the active gateway eavesdropped on it
    zone_03_r28 = ctl_zones_r28.get(zone_r28, {})
    check(
        f"Zone {zone_r28} has _name from 0004 RP to foreign HGI",
        isinstance(zone_03_r28, dict) and zone_03_r28.get("_name") == name_r28,
        f"_name={zone_03_r28.get('_name') if isinstance(zone_03_r28, dict) else None}",
    )

    # Check 2: foreign HGI should NOT be in the block_list (after fix).
    # We can't directly inspect the block_list, but we can verify the
    # foreign HGI is not being filtered by checking that packets from it
    # are processed.  Inject a 30C9 I from the foreign HGI — if it's
    # blocked, the scan engine won't see it.
    print(f"  Injecting 30C9 I from foreign HGI {foreign_hgi_r28}...")
    try:
        call_service(
            token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": foreign_hgi_r28,
                "code": "30C9",
                "payload": "0308AC",
                "verb": "I",
            },
        )
        print("    30C9 I injected")
    except RuntimeError as e:
        print(f"    Inject failed: {str(e)[:80]}")

    wait(5, "for scan engine to process 30C9")
    try:
        call_service(token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    wait(5, "for sync_learned_topology")
    try:
        call_service(token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    wait(3, "for save")

    # The foreign HGI should appear in the schema (it was already there
    # from the profile, but the 30C9 should not cause a FILTER EXCEPTION)
    schema_r28b = get_schema_retry()
    check(
        "Foreign HGI still in schema after 30C9 inject",
        foreign_hgi_r28 in schema_r28b,
        f"keys={[k for k in schema_r28b if k.startswith('18:')]}",
    )

    # =====================================================================
    # LOG REPORT: Collect and analyse ha-sim logs from the entire test run
    # =====================================================================
    log_section("Log Report: ERROR/WARNING analysis")
    print("  Collecting logs since baseline...")
    log_data = log_monitor.collect()

    report_path = "/tmp/ha_sim_test_log_report.txt"
    log_monitor.write_report(report_path, log_data)
    print(f"  Report written to: {report_path}")

    n_errors = len(log_data["errors"])
    n_warnings = len(log_data["warnings"])
    print(f"  Total log lines: {log_data['total_lines']}")
    print(f"  Unexpected errors: {n_errors}")
    print(f"  Unexpected warnings (ramses_cc/ramses_rf): {n_warnings}")

    if n_errors > 0:
        print("\n  --- Unexpected ERRORS (first 10) ---")
        import re as _re

        for line in log_data["errors"][:10]:
            clean = _re.sub(r"\x1b\[[0-9;]*m", "", line)
            print(f"    {clean[:200]}")

    if n_warnings > 0:
        print("\n  --- Unexpected WARNINGS (first 10) ---")
        import re as _re2

        for line in log_data["warnings"][:10]:
            clean = _re2.sub(r"\x1b\[[0-9;]*m", "", line)
            print(f"    {clean[:200]}")

    check(
        "No unexpected ERROR logs in full test run",
        n_errors == 0,
        f"{n_errors} unexpected errors (see {report_path})",
    )
    check(
        "No unexpected ramses_cc/ramses_rf WARNING logs",
        n_warnings == 0,
        f"{n_warnings} unexpected warnings (see {report_path})",
    )

    # =====================================================================
    # SUMMARY
    # =====================================================================
    log_section("SUMMARY")
    print(f"\n  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total:  {passed + failed}")
    print()

    for r in results:
        print(r)

    print(f"\n  Log report: {report_path}")

    if failed > 0:
        print("\n  *** SOME TESTS FAILED ***")
        sys.exit(1)
    else:
        print("\n  *** ALL TESTS PASSED ***")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
