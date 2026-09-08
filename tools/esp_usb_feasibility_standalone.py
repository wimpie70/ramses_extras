#!/usr/bin/env python3
"""Standalone ESP32/evofw3 USB feasibility gate test.

This script is self-contained — it only needs pyserial (or serialx) and
can be run on any machine with a USB serial HGI device connected.

Usage:
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0
    python esp_usb_feasibility_standalone.py COM3
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0 --report report.md

Install:
    pip install pyserial
"""

from __future__ import annotations

import argparse
import select
import sys
import time
from dataclasses import dataclass, field

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)

SIGNATURE_FRAME = " I --- 18:000730 --:------ 18:000730 7FFF 012 0010{ts:012X}76357635763576357635"
PING_FRAME = " R --- 18:000730 00:000730 --:------ 10E0 001 00"


@dataclass
class TestResult:
    name: str
    success: bool
    duration: float
    bytes_received: int = 0
    reset_detected: bool = False
    notes: str = ""
    received_data: bytes = b""


@dataclass
class FeasibilityReport:
    port: str
    results: list[TestResult] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        status = "PASS" if result.success else "FAIL"
        reset = " [RESET DETECTED]" if result.reset_detected else ""
        print(
            f"  [{status}] {result.name}: {result.duration:.3f}s, "
            f"{result.bytes_received} bytes received{reset}"
            + (f" — {result.notes}" if result.notes else "")
        )

    @property
    def all_passed(self) -> bool:
        return all(r.success for r in self.results)

    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.success)
        total = len(self.results)
        resets = sum(1 for r in self.results if r.reset_detected)
        return f"\nSummary: {passed}/{total} steps passed, {resets} reset(s) detected"


def detect_reset(data: bytes) -> bool:
    lower = data.lower()
    return b"ets" in lower or b"rst:" in lower or b"boot:" in lower or b"ready" in lower


def read_for_duration(ser: serial.Serial, duration: float) -> bytes:
    chunks: list[bytes] = []
    deadline = time.perf_counter() + duration
    while time.perf_counter() < deadline:
        ready, _, _ = select.select([ser], [], [], 0.1)
        if ready:
            data = ser.read(1024)
            if data:
                chunks.append(data)
    return b"".join(chunks)


def test_port_open_no_write(port: str) -> TestResult:
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        data = read_for_duration(ser, 2.0)
        ser.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        return TestResult(
            name="Port open (no write)",
            success=True,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes="ESP reset detected" if reset_detected else "No reset",
            received_data=data,
        )
    except Exception as e:
        return TestResult("Port open (no write)", False, time.perf_counter() - start, notes=str(e))


def test_immediate_probe(port: str) -> TestResult:
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        ser.write(frame)
        data = read_for_duration(ser, 1.0)
        ser.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        got_echo = b"7FFF" in data or b"I ---" in data
        return TestResult(
            name="Immediate 7FFF probe",
            success=got_echo,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes="Got echo" if got_echo else "No echo",
            received_data=data,
        )
    except Exception as e:
        return TestResult("Immediate 7FFF probe", False, time.perf_counter() - start, notes=str(e))


def test_repeated_probes(port: str, count: int = 5) -> TestResult:
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        for _ in range(count):
            ts = int(time.time() * 1000)
            frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
            ser.write(frame)
            time.sleep(0.05)
        data = read_for_duration(ser, 1.0)
        ser.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        echo_count = data.count(b"7FFF")
        return TestResult(
            name=f"Repeated probes ({count}x)",
            success=echo_count > 0,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes=f"{echo_count} echo(s)",
            received_data=data,
        )
    except Exception as e:
        return TestResult(f"Repeated probes ({count}x)", False, time.perf_counter() - start, notes=str(e))


def test_delayed_probe(port: str, delay: float = 2.0) -> TestResult:
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(delay)
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        ser.write(frame)
        data = read_for_duration(ser, 1.0)
        ser.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        got_echo = b"7FFF" in data or b"I ---" in data
        return TestResult(
            name=f"Delayed probe (after {delay}s)",
            success=got_echo,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes="Got echo" if got_echo else "No echo",
            received_data=data,
        )
    except Exception as e:
        return TestResult(f"Delayed probe (after {delay}s)", False, time.perf_counter() - start, notes=str(e))


def test_ordinary_write(port: str) -> TestResult:
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(2.0)
        frame = (PING_FRAME + "\r\n").encode()
        ser.write(frame)
        data = read_for_duration(ser, 2.0)
        ser.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        got_response = b"10E0" in data or b"RP" in data or b"I ---" in data
        return TestResult(
            name="Ordinary RF write",
            success=got_response,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes="Got response" if got_response else "No response",
            received_data=data,
        )
    except Exception as e:
        return TestResult("Ordinary RF write", False, time.perf_counter() - start, notes=str(e))


def test_close_reopen(port: str) -> TestResult:
    start = time.perf_counter()
    try:
        ser1 = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(0.5)
        ser1.close()
        ser2 = serial.Serial(port, baudrate=115200, timeout=0.1)
        data = read_for_duration(ser2, 1.0)
        ser2.close()
        duration = time.perf_counter() - start
        reset_detected = detect_reset(data)
        return TestResult(
            name="Close/reopen",
            success=True,
            duration=duration,
            bytes_received=len(data),
            reset_detected=reset_detected,
            notes="Reopened OK",
            received_data=data,
        )
    except Exception as e:
        return TestResult("Close/reopen", False, time.perf_counter() - start, notes=str(e))


def test_dtr_rts_modes(port: str) -> list[TestResult]:
    """Test opening the port with different DTR/RTS settings.

    pyserial sets DTR=True/RTS=True on open by default.  On boards with a
    USB-to-UART bridge (CP2102, CH340, FT232), DTR/RTS are wired to EN/GPIO0
    through a transistor circuit and the transition can reset the ESP32.
    This test tries different combinations to find which prevent the reset.
    """
    modes = [
        ("default (dsrdtr=False)", {"dsrdtr": False}),
        ("dsrdtr=True (no auto DTR/RTS)", {"dsrdtr": True}),
        ("DTR=LOW after open", {"dsrdtr": True, "_set_dtr": False}),
        ("RTS=LOW after open", {"dsrdtr": True, "_set_rts": False}),
        ("both LOW after open", {"dsrdtr": True, "_set_dtr": False, "_set_rts": False}),
    ]

    results: list[TestResult] = []
    for label, kwargs in modes:
        set_dtr = kwargs.pop("_set_dtr", None)
        set_rts = kwargs.pop("_set_rts", None)
        start = time.perf_counter()
        try:
            ser = serial.Serial(port, baudrate=115200, timeout=0.1, **kwargs)
            if set_dtr is not None:
                ser.setDTR(set_dtr)
            if set_rts is not None:
                ser.setRTS(set_rts)
            data = read_for_duration(ser, 2.0)
            ser.close()
            duration = time.perf_counter() - start
            reset_detected = detect_reset(data)
            results.append(TestResult(
                name=f"DTR/RTS: {label}",
                success=True,
                duration=duration,
                bytes_received=len(data),
                reset_detected=reset_detected,
                notes="RESET detected" if reset_detected else "No reset",
                received_data=data,
            ))
        except Exception as e:
            results.append(TestResult(
                name=f"DTR/RTS: {label}",
                success=False,
                duration=time.perf_counter() - start,
                notes=str(e),
            ))
    return results


def test_unplug_reconnect(port: str, timeout: float = 30.0) -> TestResult:
    """Test physical unplug/reconnect cycle.

    Opens the port, waits for the user to unplug and reconnect the USB
    cable, then verifies the port can be reopened and the device responds.
    Interactive — prints prompts to stdout.
    """
    import os
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        print(f"  >>> UNPLUG {port} now, then plug it back in <<<")
        # Wait for the port to disappear (unplug)
        unplugged = False
        deadline_unplug = time.perf_counter() + timeout
        while time.perf_counter() < deadline_unplug:
            if not os.path.exists(port):
                unplugged = True
                print(f"  >>> Unplug detected, waiting for reconnect... <<<")
                break
            time.sleep(0.3)
        if not unplugged:
            ser.close()
            return TestResult(
                name="Unplug/reconnect",
                success=False,
                duration=time.perf_counter() - start,
                notes="Unplug not detected within timeout",
            )
        # Close the broken port
        try:
            ser.close()
        except Exception:
            pass

        # Wait for the port to reappear (reconnect)
        reconnected = False
        boot_data = b""
        data = b""
        deadline_reconnect = time.perf_counter() + timeout
        while time.perf_counter() < deadline_reconnect:
            if os.path.exists(port):
                try:
                    ser2 = serial.Serial(port, baudrate=115200, timeout=0.1)
                    # Wait for device to boot
                    boot_data = read_for_duration(ser2, 3.0)
                    # Send a signature probe
                    ts = int(time.time() * 1000)
                    frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
                    ser2.write(frame)
                    data = read_for_duration(ser2, 1.0)
                    ser2.close()
                    reconnected = True
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                time.sleep(0.3)

        duration = time.perf_counter() - start
        if not reconnected:
            return TestResult(
                name="Unplug/reconnect",
                success=False,
                duration=duration,
                notes="Reconnect not detected within timeout",
            )
        all_data = boot_data + data
        reset_detected = detect_reset(all_data)
        got_echo = b"7FFF" in data or b"I ---" in data
        return TestResult(
            name="Unplug/reconnect",
            success=got_echo,
            duration=duration,
            bytes_received=len(all_data),
            reset_detected=reset_detected,
            notes="Reconnected, echo received" if got_echo else "Reconnected, no echo",
            received_data=all_data,
        )
    except Exception as e:
        return TestResult(
            name="Unplug/reconnect",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


def run_feasibility_gate(
    port: str,
    repeats: int = 1,
    delay: float = 2.0,
    include_dtr: bool = False,
    include_unplug: bool = False,
) -> FeasibilityReport:
    report = FeasibilityReport(port=port)
    print(f"\nESP32/evofw3 USB Feasibility Gate Test")
    print(f"Port: {port}")
    print(f"Repeats: {repeats}")
    print(f"Delay: {delay}s")
    print("-" * 60)
    for i in range(repeats):
        if repeats > 1:
            print(f"\n--- Run {i + 1}/{repeats} ---")
        report.add(test_port_open_no_write(port))
        report.add(test_immediate_probe(port))
        report.add(test_repeated_probes(port))
        report.add(test_delayed_probe(port, delay))
        report.add(test_ordinary_write(port))
        report.add(test_close_reopen(port))
        if i == 0 and include_dtr:
            print("\n--- DTR/RTS open mode test ---")
            for r in test_dtr_rts_modes(port):
                report.add(r)
        if i == 0 and include_unplug:
            print("\n--- Unplug/reconnect test ---")
            report.add(test_unplug_reconnect(port))
    print(report.summary())
    return report


def generate_report(reports: list[FeasibilityReport], output_file: str) -> None:
    lines = [
        "# ESP32/evofw3 USB Feasibility Gate Report",
        f"\n**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Results\n",
    ]
    for report in reports:
        lines.append(f"### Port: `{report.port}`\n")
        lines.append("| Test | Result | Duration | Bytes | Reset | Notes |")
        lines.append("|------|--------|----------|-------|-------|-------|")
        for r in report.results:
            status = "PASS" if r.success else "FAIL"
            reset = "YES" if r.reset_detected else "no"
            notes = r.notes.replace("|", "\\|")
            lines.append(f"| {r.name} | {status} | {r.duration:.3f}s | {r.bytes_received} | {reset} | {notes} |")
        lines.append("")
    all_passed = all(r.all_passed for r in reports)
    total_resets = sum(sum(1 for r in rep.results if r.reset_detected) for rep in reports)
    lines.append("## Summary\n")
    lines.append(f"- **Overall:** {'PASSED' if all_passed else 'FAILED'}")
    lines.append(f"- **Total resets detected:** {total_resets}")
    lines.append(f"- **Ports tested:** {', '.join(r.port for r in reports)}")
    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to: {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32/evofw3 USB feasibility gate test")
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--repeats", type=int, default=1, help="Number of full test cycles")
    parser.add_argument("--delay", type=float, default=2.0, help="Grace period delay (seconds)")
    parser.add_argument("--report", "-r", help="Write markdown report to this file")
    parser.add_argument(
        "--dtr-test", action="store_true",
        help="Test DTR/RTS open modes to find reset-preventing settings",
    )
    parser.add_argument(
        "--unplug-test", action="store_true",
        help="Test physical unplug/reconnect (interactive — prompts to unplug)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all tests: basic + DTR/RTS + unplug/reconnect",
    )
    args = parser.parse_args()

    include_dtr = args.dtr_test or args.all
    include_unplug = args.unplug_test or args.all

    report = run_feasibility_gate(
        args.port,
        repeats=args.repeats,
        delay=args.delay,
        include_dtr=include_dtr,
        include_unplug=include_unplug,
    )
    reports = [report]

    if args.report:
        generate_report(reports, args.report)

    if report.all_passed:
        print("\nFEASIBILITY GATE: PASSED")
        sys.exit(0)
    else:
        print("\nFEASIBILITY GATE: FAILED (see results above)")
        sys.exit(1)


if __name__ == "__main__":
    main()
