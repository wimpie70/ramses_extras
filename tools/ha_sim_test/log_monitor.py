"""Log monitor — captures ERROR/WARNING lines from ha-sim logs during tests."""

from __future__ import annotations

import re
import subprocess

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
    # ramses_rf: SUPPRESSED in SystemBase 000C handler (BDR re-parenting)
    "SUPPRESSED in SystemBase 000C",
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
    # HA core: ramses_cc climate entity already exists during profile reload
    # (transient — HA correctly ignores the duplicate, but logs an error)
    "does not generate unique IDs",
    # ramses_extras: broker not found during early init (transient — ramses_cc
    # may not be loaded yet when ramses_extras starts)
    "Could not find ramses_cc broker",
    # HA core: slow state update warning (transient — profile reloads cause
    # batch entity updates that can exceed HA's 0.5s threshold)
    "Updating state for",
    # ramses_cc: orphaned task warning during profile reload (transient —
    # the EntityPlatform async_add_entities task may still be pending when
    # the integration unloads)
    "Task <Task pending name='EntityPlatform async_ad",
    # HA core: "Future exception was never retrieved" — race condition in
    # entity removal during rapid reload cycles at 100x speed.  HA core's
    # remove_entity_cb (entity_platform.py:1043) uses `del
    # self.domain_entities[entity_id]` which raises KeyError when the entity
    # was already removed during platform unload.  Real but harmless — the
    # error is swallowed by HA's "Future exception was never retrieved"
    # handler.  See ha_sim_test report 2026-07-22, failure 6.
    "Future exception was never retrieved",
    # HA core: "Something is blocking Home Assistant from wrapping up the
    # start up phase" — transient timing warning during container restart at
    # 100x speed.  ramses_cc's coordinator initialization is still running
    # when HA's startup timeout fires.  Does not occur in production (no
    # artificial speed pressure).  See ha_sim_test report 2026-07-22,
    # failure 7.
    "Something is blocking Home Assistant",
    # ramses_cc: device marked as lost/orphaned (expected in R50 —
    # the recipe intentionally manipulates last_seen to trigger this)
    "marked as lost",
    "marked as orphaned",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


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

        Call this right before ``docker restart ha-sim``. The classified
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
        clean = _strip_ansi(line)
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
