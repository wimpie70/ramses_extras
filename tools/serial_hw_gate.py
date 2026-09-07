#!/usr/bin/env python3
"""Serial hardware feasibility gate — ESP32 USB reset characterization.

This script characterizes the ESP32 USB reset behavior that blocks Phase 2
(pooled serial transmission). It runs a series of controlled tests with
precise timing and logs all serial traffic + timing data.

Usage:
    source ~/venvs/extras/bin/activate
    python tools/serial_hw_gate.py /dev/ttyACM0 [--baud 115200] [--log-dir logs]

The tests (from multi-hgi-plan.md, "Hardware feasibility gate"):

  T1: Port open + DTR/RTS transitions without a write
  T2: One immediate 7FFF probe
  T3: Repeated immediate 7FFF probes
  T4: One delayed probe after a firmware-ready indication or grace period
  T5: An ordinary RF write after the device is ready
  T6: Close/reopen cycle
  T7: Unplug/reconnect cycle (manual — script pauses and waits)

Each test logs:
  - Timestamps (relative to port open, in ms)
  - Raw bytes sent/received
  - DTR/RTS state changes
  - Whether the ESP32 reset (detected by reboot banner or silence)

The ESP32 reset is detected by:
  - ramses_esp prints a boot banner on startup (e.g. "ramses_esp ..." or
    esptool-style "ets Jun  8 2016 ..." rst cause)
  - The serial output goes silent for >2s after a write (suggests crash/reset)
  - The device re-enumerates (port disappears and reappears)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import serial  # pyserial — serialx has a Python 3.14 fileno bug

# --- Constants ---

SIGNATURE_FRAME = "I 18:000730 01:000730 01:000730 7FFF 0010"
ORDINARY_RF_CMD = "I 18:000730 01:145038 01:145038 1F09 00"

BOOT_BANNER_MARKERS = [
    b"ramses_esp",
    b"ets Jun",
    b"ets Dec",
    b"rst:",
    b"boot:",
    b"load:",
    b"WiFi",
    b"MQTT",
    b"Connecting",
    b"Ready",
]

SILENCE_THRESHOLD_SECS = 2.0
DEFAULT_GRACE_SECS = 3.0  # ESP32 boot time estimate
IMMEDIATE_PROBE_DELAY = 0.0  # no delay
REPEATED_PROBE_COUNT = 10
REPEATED_PROBE_GAP = 0.05  # matches _SIGNATURE_GAP_SECS in port.py


@dataclass
class SerialEvent:
    """A single serial event (sent or received)."""

    t_ms: float  # milliseconds relative to port open
    direction: str  # "TX" or "RX"
    data: bytes
    note: str = ""


@dataclass
class TestResult:
    """Result of a single test."""

    test_id: str
    name: str
    events: list[SerialEvent] = field(default_factory=list)
    reset_detected: bool = False
    reset_reason: str = ""
    duration_ms: float = 0.0
    notes: str = ""

    def summary(self) -> str:
        status = "RESET DETECTED" if self.reset_detected else "OK"
        lines = [
            f"--- {self.test_id}: {self.name} ---",
            f"  Status: {status}",
            f"  Duration: {self.duration_ms:.0f} ms",
            f"  Events: {len(self.events)}",
        ]
        if self.reset_reason:
            lines.append(f"  Reset reason: {self.reset_reason}")
        if self.notes:
            lines.append(f"  Notes: {self.notes}")
        # Show first/last few events
        if self.events:
            lines.append("  First events:")
            for ev in self.events[:5]:
                lines.append(
                    f"    {ev.t_ms:8.1f}ms {ev.direction} {ev.data!r} {ev.note}"
                )
            if len(self.events) > 10:
                lines.append(f"    ... ({len(self.events) - 10} more)")
                for ev in self.events[-5:]:
                    lines.append(
                        f"    {ev.t_ms:8.1f}ms {ev.direction} {ev.data!r} {ev.note}"
                    )
            elif len(self.events) > 5:
                for ev in self.events[5:]:
                    lines.append(
                        f"    {ev.t_ms:8.1f}ms {ev.direction} {ev.data!r} {ev.note}"
                    )
        return "\n".join(lines)


class SerialMonitor:
    """Monitors a serial port and records all events with timing."""

    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self.serial: serial.Serial | None = None
        self.events: list[SerialEvent] = []
        self._t0: float = 0.0
        self._read_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.reset_markers_seen: list[tuple[float, bytes]] = []

    def _now_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    async def open(self, *, dtr: bool | None = None, rts: bool | None = None) -> None:
        """Open the serial port and start monitoring."""
        self.serial = serial.Serial(
            self.port,
            baudrate=self.baud,
            timeout=0.1,
            exclusive=True,
        )
        self._t0 = time.monotonic()

        # Record DTR/RTS state after open
        try:
            cur_dtr = self.serial.dtr
            cur_rts = self.serial.rts
            self.events.append(
                SerialEvent(
                    t_ms=0.0,
                    direction="DTR/RTS",
                    data=f"DTR={cur_dtr} RTS={cur_rts}".encode(),
                    note="post-open state",
                )
            )
        except Exception as e:
            self.events.append(
                SerialEvent(
                    t_ms=0.0,
                    direction="DTR/RTS",
                    data=f"error reading DTR/RTS: {e}".encode(),
                )
            )

        # Optionally set DTR/RTS
        if dtr is not None:
            self.serial.dtr = dtr
            self.events.append(
                SerialEvent(
                    t_ms=self._now_ms(),
                    direction="DTR",
                    data=f"DTR={dtr}".encode(),
                    note="manually set",
                )
            )
        if rts is not None:
            self.serial.rts = rts
            self.events.append(
                SerialEvent(
                    t_ms=self._now_ms(),
                    direction="RTS",
                    data=f"RTS={rts}".encode(),
                    note="manually set",
                )
            )

        # Start background reader
        self._stop.clear()
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Background task that reads and records all incoming data."""
        if not self.serial:
            return
        buf = b""
        while not self._stop.is_set():
            try:
                # serialx sync read in executor to avoid blocking
                data = await asyncio.to_thread(self.serial.read, 256)
                if data:
                    buf += data
                    while b"\r\n" in buf:
                        line, buf = buf.split(b"\r\n", 1)
                        line += b"\r\n"
                        t = self._now_ms()
                        self.events.append(
                            SerialEvent(t_ms=t, direction="RX", data=line)
                        )
                        # Check for reset markers
                        for marker in BOOT_BANNER_MARKERS:
                            if marker in line:
                                self.reset_markers_seen.append((t, line))
                                self.events.append(
                                    SerialEvent(
                                        t_ms=t,
                                        direction="RESET?",
                                        data=marker,
                                        note=f"boot marker in: {line!r}",
                                    )
                                )
                                break
                    # Also record partial data (no CRLF yet)
                    if buf:
                        t = self._now_ms()
                        self.events.append(
                            SerialEvent(
                                t_ms=t,
                                direction="RX",
                                data=buf,
                                note="partial (no CRLF)",
                            )
                        )
                        buf = b""
            except Exception as e:
                self.events.append(
                    SerialEvent(
                        t_ms=self._now_ms(),
                        direction="ERROR",
                        data=str(e).encode(),
                        note="read error",
                    )
                )
                await asyncio.sleep(0.1)

    async def write(self, data: str | bytes, note: str = "") -> None:
        """Write data to the serial port and record the event."""
        if not self.serial:
            return
        if isinstance(data, str):
            raw = bytes(data, "ascii") + b"\r\n"
        else:
            raw = data
        t = self._now_ms()
        try:
            await asyncio.to_thread(self.serial.write, raw)
            self.events.append(
                SerialEvent(
                    t_ms=t,
                    direction="TX",
                    data=raw,
                    note=note,
                )
            )
        except Exception as e:
            self.events.append(
                SerialEvent(
                    t_ms=t,
                    direction="ERROR",
                    data=str(e).encode(),
                    note=f"write error: {note}",
                )
            )

    async def wait(self, secs: float, note: str = "") -> None:
        """Wait and record a gap."""
        t_start = self._now_ms()
        await asyncio.sleep(secs)
        self.events.append(
            SerialEvent(
                t_ms=t_start,
                direction="WAIT",
                data=f"{secs}s".encode(),
                note=note,
            )
        )

    async def close(self) -> None:
        """Close the serial port."""
        self._stop.set()
        if self._read_task:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(self._read_task, timeout=2.0)
        if self.serial:
            self.serial.close()
            self.serial = None

    def check_reset(self) -> tuple[bool, str]:
        """Check if a reset was detected."""
        if self.reset_markers_seen:
            t, line = self.reset_markers_seen[0]
            return True, f"boot marker at {t:.1f}ms: {line!r}"

        # Check for silence after writes
        tx_times = [e.t_ms for e in self.events if e.direction == "TX"]
        rx_times = [e.t_ms for e in self.events if e.direction == "RX"]
        if tx_times and rx_times:
            last_tx = tx_times[-1]
            post_tx_rx = [t for t in rx_times if t > last_tx]
            if not post_tx_rx:
                silence = (self._now_ms() - last_tx) / 1000.0
                if silence > SILENCE_THRESHOLD_SECS:
                    return True, f"silence after last TX: {silence:.1f}s"

        return False, ""

    def get_result(self, test_id: str, name: str, notes: str = "") -> TestResult:
        reset, reason = self.check_reset()
        return TestResult(
            test_id=test_id,
            name=name,
            events=list(self.events),
            reset_detected=reset,
            reset_reason=reason,
            duration_ms=self._now_ms(),
            notes=notes,
        )


async def run_test(
    test_id: str,
    name: str,
    port: str,
    baud: int,
    test_fn: object,
    notes: str = "",
) -> TestResult:
    """Run a single test and return its result."""
    print(f"\n{'=' * 60}")
    print(f"  {test_id}: {name}")
    print(f"{'=' * 60}")

    mon = SerialMonitor(port, baud)
    try:
        await mon.open()
        await asyncio.sleep(0.1)  # let reader start
        await test_fn(mon)
        await mon.wait(2.0, "post-test observation window")  # observe for resets
    except Exception as e:
        print(f"  ERROR during test: {e}")
        mon.events.append(
            SerialEvent(
                t_ms=mon._now_ms(),
                direction="ERROR",
                data=str(e).encode(),
                note="test exception",
            )
        )
    finally:
        result = mon.get_result(test_id, name, notes)
        await mon.close()

    print(result.summary())
    return result


# --- Individual tests ---


async def test_dtr_rts_no_write(mon: SerialMonitor) -> None:
    """T1: Open port, observe DTR/RTS transitions, write nothing."""
    # Just wait and observe — the open() already recorded DTR/RTS state
    await mon.wait(5.0, "observing ESP32 boot after port open (no writes)")


async def test_one_immediate_probe(mon: SerialMonitor) -> None:
    """T2: Send one 7FFF signature probe immediately after open."""
    await mon.write(SIGNATURE_FRAME, note="immediate 7FFF signature probe")
    await mon.wait(5.0, "observing response to immediate probe")


async def test_repeated_immediate_probes(mon: SerialMonitor) -> None:
    """T3: Send repeated 7FFF probes with 50ms gap (matches port.py)."""
    for i in range(REPEATED_PROBE_COUNT):
        await mon.write(
            SIGNATURE_FRAME, note=f"repeated probe {i + 1}/{REPEATED_PROBE_COUNT}"
        )
        await mon.wait(REPEATED_PROBE_GAP, "gap before next probe")
    await mon.wait(5.0, "observing response to repeated probes")


async def test_delayed_probe(mon: SerialMonitor) -> None:
    """T4: Wait for boot/grace period, then send one probe."""
    await mon.wait(
        DEFAULT_GRACE_SECS, f"waiting {DEFAULT_GRACE_SECS}s grace period before probe"
    )
    await mon.write(SIGNATURE_FRAME, note="delayed 7FFF signature probe (after grace)")
    await mon.wait(5.0, "observing response to delayed probe")


async def test_ordinary_write_after_ready(mon: SerialMonitor) -> None:
    """T5: Wait for ready, then send an ordinary RF command."""
    await mon.wait(DEFAULT_GRACE_SECS, f"waiting {DEFAULT_GRACE_SECS}s grace period")
    await mon.write(ORDINARY_RF_CMD, note="ordinary RF write (1F09 RQ)")
    await mon.wait(5.0, "observing response to ordinary RF write")


async def test_close_reopen(mon: SerialMonitor) -> None:
    """T6: Close and reopen the port, observe behavior."""
    # The monitor already opened the port. We'll close it, wait, and
    # the test runner will reopen for the next test.
    await mon.wait(1.0, "pre-close observation")
    # Close is handled by the test runner, but we record the intent
    mon.events.append(
        SerialEvent(
            t_ms=mon._now_ms(),
            direction="CLOSE",
            data=b"closing port",
            note="close/reopen test",
        )
    )


async def test_no_dtr_rts(mon: SerialMonitor) -> None:
    """T8: Open with DTR=False, RTS=False to avoid ESP32 auto-reset."""
    # Set DTR/RTS to False immediately after open
    if mon.serial:
        mon.serial.dtr = False
        mon.serial.rts = False
        mon.events.append(
            SerialEvent(
                t_ms=mon._now_ms(),
                direction="DTR/RTS",
                data=b"DTR=False RTS=False",
                note="set immediately after open",
            )
        )
    await mon.wait(3.0, "observing after DTR/RTS=False (no writes)")
    await mon.write(SIGNATURE_FRAME, note="probe after DTR/RTS=False")
    await mon.wait(5.0, "observing response")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Serial hardware feasibility gate — ESP32 USB reset characterization"
        )
    )
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--log-dir", default="logs", help="Directory for log files")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Test IDs to skip (e.g. T3 T7)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Only run these test IDs (e.g. T1 T4)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.port):
        print(f"ERROR: port {args.port} does not exist")
        print("Available ports:")
        os.system("ls /dev/serial/by-id/ 2>/dev/null || echo '  (none)'")
        os.system(
            "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo '  (no ttyUSB/ttyACM)'"
        )
        sys.exit(1)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"serial_hw_gate_{timestamp}.log"

    print("Serial Hardware Feasibility Gate")
    print(f"Port: {args.port}")
    print(f"Baud: {args.baud}")
    print(f"Log:  {log_file}")
    print()

    # Define tests in order
    all_tests = [
        ("T1", "Port open + DTR/RTS (no write)", test_dtr_rts_no_write, ""),
        ("T2", "One immediate 7FFF probe", test_one_immediate_probe, ""),
        (
            "T3",
            "Repeated immediate 7FFF probes (50ms gap)",
            test_repeated_immediate_probes,
            "",
        ),
        (
            "T4",
            f"Delayed probe (after {DEFAULT_GRACE_SECS}s grace)",
            test_delayed_probe,
            "",
        ),
        ("T5", "Ordinary RF write after ready", test_ordinary_write_after_ready, ""),
        (
            "T6",
            "Close/reopen cycle",
            test_close_reopen,
            "Port is closed and reopened between tests",
        ),
        (
            "T8",
            "DTR=False/RTS=False + probe",
            test_no_dtr_rts,
            "Test if disabling auto-reset pins helps",
        ),
    ]

    # Filter tests
    tests = []
    for tid, name, fn, notes in all_tests:
        if args.only and tid not in args.only:
            continue
        if tid in args.skip:
            continue
        tests.append((tid, name, fn, notes))

    results: list[TestResult] = []

    for i, (tid, name, fn, notes) in enumerate(tests):
        # For T6, we need to close and wait before reopening
        if tid == "T6" and i > 0:
            print("\n  Closing port, waiting 3s before reopen...")
            await asyncio.sleep(3.0)

        result = await run_test(tid, name, args.port, args.baud, fn, notes)
        results.append(result)

        # Wait between tests to let ESP32 settle
        if i < len(tests) - 1:
            wait = 3.0
            print(f"\n  Waiting {wait}s before next test...")
            await asyncio.sleep(wait)

    # T7: Unplug/reconnect (manual)
    if "T7" not in args.skip and (not args.only or "T7" in args.only):
        print(f"\n{'=' * 60}")
        print("  T7: Unplug/reconnect cycle (MANUAL)")
        print(f"{'=' * 60}")
        print()
        if os.path.exists(args.port):
            print(f"  Port {args.port} is present. Running delayed probe")
            print("  (assumes ESP32 was just replugged — port open will reset it).")
            result = await run_test(
                "T7",
                "Unplug/reconnect cycle",
                args.port,
                args.baud,
                test_delayed_probe,  # reuse: wait for grace, then probe
                notes="Manual unplug/replug, then delayed probe",
            )
            results.append(result)
        else:
            print(f"  Port {args.port} not found. Skipping T7.")
            results.append(
                TestResult(
                    test_id="T7",
                    name="Unplug/reconnect cycle",
                    notes="SKIPPED — port not found",
                )
            )

    # --- Summary ---
    print(f"\n\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}\n")

    resets = 0
    for r in results:
        status = "RESET!" if r.reset_detected else "OK"
        print(f"  {r.test_id}: {r.name:45s} {status}")
        if r.reset_detected:
            resets += 1

    print(f"\n  Total tests: {len(results)}")
    print(f"  Resets detected: {resets}")
    print(f"  Clean tests: {len(results) - resets}")

    if resets == 0:
        print("\n  CONCLUSION: No resets detected. Serial pooling may be feasible.")
        print("  Next step: verify two-USB and USB+MQTT hybrid pool scenarios.")
    else:
        print(f"\n  CONCLUSION: {resets} test(s) detected ESP32 resets.")
        print("  The delayed/grace-period tests (T4/T5) are the most important.")
        print("  If T4/T5 are clean but T2/T3 reset, a delayed signature policy")
        print("  is the likely Phase 2 approach.")

    # Write full log
    with open(log_file, "w") as f:
        f.write("Serial Hardware Feasibility Gate\n")
        f.write(f"Date: {datetime.now().isoformat()}\n")
        f.write(f"Port: {args.port}\n")
        f.write(f"Baud: {args.baud}\n\n")
        for r in results:
            f.write(r.summary())
            f.write("\n\n")
            for ev in r.events:
                f.write(f"  {ev.t_ms:10.1f}ms {ev.direction:6s} {ev.data!r}")
                if ev.note:
                    f.write(f"  # {ev.note}")
                f.write("\n")
            f.write("\n")

    print(f"\n  Full log written to: {log_file}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
