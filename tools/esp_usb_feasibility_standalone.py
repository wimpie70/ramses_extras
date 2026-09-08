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


def run_feasibility_gate(port: str, repeats: int = 1, delay: float = 2.0) -> FeasibilityReport:
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
    args = parser.parse_args()

    report = run_feasibility_gate(args.port, repeats=args.repeats, delay=args.delay)
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
