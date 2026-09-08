#!/usr/bin/env python3
"""ESP32 USB serial feasibility gate test for Phase 2.

Characterizes the ESP32 USB behavior when used as a pooled serial child:
- Port open and DTR/RTS transitions without a write
- One immediate 7FFF probe
- Repeated immediate probes
- One delayed probe after a firmware-ready indication or grace period
- An ordinary RF write after the device is ready
- Close/reopen and unplug/reconnect cycles

Usage:
    python -m tools.esp_usb_feasibility_test /dev/ttyACM0
    python -m tools.esp_usb_feasibility_test /dev/ttyACM0 --repeats 3
    python -m tools.esp_usb_feasibility_test /dev/ttyACM0 --delay 2.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field

import serialx

_LOGGER = logging.getLogger("esp_usb_feasibility")

SIGNATURE_FRAME = " I --- 18:000730 --:------ 18:000730 7FFF 012 0010{ts:012X}76357635763576357635"
PING_FRAME = " R --- 18:000730 00:000730 --:------ 10E0 001 00"


@dataclass
class TestResult:
    """Result of a single feasibility test step."""

    name: str
    success: bool
    duration: float
    bytes_received: int = 0
    reset_detected: bool = False
    notes: str = ""
    received_data: bytes = b""


@dataclass
class FeasibilityReport:
    """Full feasibility test report."""

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
        return (
            f"\nSummary: {passed}/{total} steps passed, "
            f"{resets} reset(s) detected"
        )


async def read_for_duration(
    ser: serialx.AsyncSerial, duration: float
) -> bytes:
    """Read all data received for a given duration."""
    chunks: list[bytes] = []
    deadline = time.perf_counter() + duration
    while time.perf_counter() < deadline:
        try:
            data = await asyncio.wait_for(
                ser.read(1024), timeout=0.1
            )
            if data:
                chunks.append(data)
        except (TimeoutError, asyncio.TimeoutError):
            continue
    return b"".join(chunks)


def detect_reset(data: bytes) -> bool:
    """Check if ESP reset signature is in the data."""
    lower = data.lower()
    return (
        b"ets" in lower
        or b"rst:" in lower
        or b"boot:" in lower
        or b"ready" in lower
    )


async def test_port_open_no_write(port: str) -> TestResult:
    """Test 1: Open port and DTR/RTS transitions without any write."""
    start = time.perf_counter()
    try:
        ser = serialx.AsyncSerial(port, baudrate=115200)
        await ser.open()
        # Wait 2 seconds to see if the ESP resets or sends anything
        data = await read_for_duration(ser, 2.0)
        await ser.close()
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
        return TestResult(
            name="Port open (no write)",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def test_dtr_rts_modes(port: str) -> list[TestResult]:
    """Test opening the port with different DTR/RTS settings.

    This tests whether serialx's dtr_on_open/rts_on_open options can
    prevent the ESP32 reset-on-open behavior.
    """
    from serialx.common import PinState

    modes = [
        ("default (DTR=H, RTS=H)", {}),
        ("dtr_on_open=LOW", {"dtr_on_open": PinState.LOW}),
        ("rts_on_open=LOW", {"rts_on_open": PinState.LOW}),
        ("both LOW", {
            "dtr_on_open": PinState.LOW,
            "rts_on_open": PinState.LOW,
        }),
        ("both UNDEFINED", {
            "dtr_on_open": PinState.UNDEFINED,
            "rts_on_open": PinState.UNDEFINED,
        }),
    ]

    results: list[TestResult] = []
    for label, kwargs in modes:
        start = time.perf_counter()
        try:
            ser = serialx.AsyncSerial(
                port, baudrate=115200, **kwargs
            )
            await ser.open()
            data = await read_for_duration(ser, 2.0)
            await ser.close()
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


async def test_immediate_probe(port: str) -> TestResult:
    """Test 2: One immediate 7FFF signature probe after port open."""
    start = time.perf_counter()
    try:
        ser = serialx.AsyncSerial(port, baudrate=115200)
        await ser.open()
        # Send signature immediately
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        ser.write_nowait(frame)
        data = await read_for_duration(ser, 1.0)
        await ser.close()
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
        return TestResult(
            name="Immediate 7FFF probe",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def test_repeated_probes(port: str, count: int = 5) -> TestResult:
    """Test 3: Repeated immediate probes to check for reset loop."""
    start = time.perf_counter()
    try:
        ser = serialx.AsyncSerial(port, baudrate=115200)
        await ser.open()
        for _ in range(count):
            ts = int(time.time() * 1000)
            frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
            ser.write_nowait(frame)
            await asyncio.sleep(0.05)
        data = await read_for_duration(ser, 1.0)
        await ser.close()
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
        return TestResult(
            name=f"Repeated probes ({count}x)",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def test_delayed_probe(port: str, delay: float = 2.0) -> TestResult:
    """Test 4: One delayed probe after a grace period."""
    start = time.perf_counter()
    try:
        ser = serialx.AsyncSerial(port, baudrate=115200)
        await ser.open()
        # Wait for grace period
        await asyncio.sleep(delay)
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        ser.write_nowait(frame)
        data = await read_for_duration(ser, 1.0)
        await ser.close()
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
        return TestResult(
            name=f"Delayed probe (after {delay}s)",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def test_ordinary_write(port: str) -> TestResult:
    """Test 5: An ordinary RF write after the device is ready."""
    start = time.perf_counter()
    try:
        ser = serialx.AsyncSerial(port, baudrate=115200)
        await ser.open()
        # Wait 2s for readiness
        await asyncio.sleep(2.0)
        frame = (PING_FRAME + "\r\n").encode()
        ser.write_nowait(frame)
        data = await read_for_duration(ser, 2.0)
        await ser.close()
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
        return TestResult(
            name="Ordinary RF write",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def test_close_reopen(port: str) -> TestResult:
    """Test 6: Close/reopen cycle."""
    start = time.perf_counter()
    try:
        ser1 = serialx.AsyncSerial(port, baudrate=115200)
        await ser1.open()
        await asyncio.sleep(0.5)
        await ser1.close()

        # Reopen
        ser2 = serialx.AsyncSerial(port, baudrate=115200)
        await ser2.open()
        data = await read_for_duration(ser2, 1.0)
        await ser2.close()
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
        return TestResult(
            name="Close/reopen",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )


async def run_feasibility_gate(
    port: str, repeats: int = 1, delay: float = 2.0
) -> FeasibilityReport:
    """Run the full feasibility gate test suite."""
    report = FeasibilityReport(port=port)

    print(f"\nESP32 USB Feasibility Gate Test")
    print(f"Port: {port}")
    print(f"Repeats: {repeats}")
    print(f"Delay: {delay}s")
    print("-" * 60)

    for i in range(repeats):
        if repeats > 1:
            print(f"\n--- Run {i + 1}/{repeats} ---")
        report.add(await test_port_open_no_write(port))
        report.add(await test_immediate_probe(port))
        report.add(await test_repeated_probes(port))
        report.add(await test_delayed_probe(port, delay))
        report.add(await test_ordinary_write(port))
        report.add(await test_close_reopen(port))

    print(report.summary())
    return report


async def run_dual_port_test(
    port1: str, port2: str, delay: float = 2.0
) -> tuple[FeasibilityReport, FeasibilityReport]:
    """Run feasibility tests on two ports simultaneously."""
    print(f"\nDual-Port USB Feasibility Test")
    print(f"Port 1: {port1}")
    print(f"Port 2: {port2}")
    print(f"Delay: {delay}s")
    print("-" * 60)

    # Run both tests concurrently
    report1, report2 = await asyncio.gather(
        run_feasibility_gate(port1, repeats=1, delay=delay),
        run_feasibility_gate(port2, repeats=1, delay=delay),
    )

    # Additional dual-port specific tests
    print("\n--- Dual-port simultaneous write test ---")
    start = time.perf_counter()
    try:
        ser1 = serialx.AsyncSerial(port1, baudrate=115200)
        ser2 = serialx.AsyncSerial(port2, baudrate=115200)
        await ser1.open()
        await ser2.open()

        # Send signature to both simultaneously
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        ser1.write_nowait(frame)
        ser2.write_nowait(frame)

        # Read from both concurrently
        data1, data2 = await asyncio.gather(
            read_for_duration(ser1, 1.0),
            read_for_duration(ser2, 1.0),
        )
        await ser1.close()
        await ser2.close()
        duration = time.perf_counter() - start

        echo1 = b"7FFF" in data1
        echo2 = b"7FFF" in data2
        reset1 = detect_reset(data1)
        reset2 = detect_reset(data2)

        result = TestResult(
            name="Dual simultaneous write",
            success=echo1 and echo2,
            duration=duration,
            bytes_received=len(data1) + len(data2),
            reset_detected=reset1 or reset2,
            notes=f"Port1: {'echo' if echo1 else 'no echo'}{' (RESET)' if reset1 else ''}, "
            f"Port2: {'echo' if echo2 else 'no echo'}{' (RESET)' if reset2 else ''}",
        )
        report1.add(result)
        print(
            f"  [{'PASS' if result.success else 'FAIL'}] {result.name}: "
            f"{result.duration:.3f}s — {result.notes}"
        )
    except Exception as e:
        result = TestResult(
            name="Dual simultaneous write",
            success=False,
            duration=time.perf_counter() - start,
            notes=str(e),
        )
        report1.add(result)
        print(f"  [FAIL] {result.name}: {result.notes}")

    print(report1.summary())
    return report1, report2


def generate_report(
    reports: list[FeasibilityReport],
    output_file: str | None = None,
) -> str:
    """Generate a markdown report for sharing."""
    lines = [
        "# ESP32 USB Feasibility Gate Report",
        f"\n**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Tool:** tools/esp_usb_feasibility_test.py",
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
            lines.append(
                f"| {r.name} | {status} | {r.duration:.3f}s | "
                f"{r.bytes_received} | {reset} | {notes} |"
            )
        lines.append("")

    all_passed = all(r.all_passed for r in reports)
    total_resets = sum(
        sum(1 for r in report.results if r.reset_detected) for report in reports
    )
    lines.append("## Summary\n")
    lines.append(f"- **Overall:** {'PASSED' if all_passed else 'FAILED'}")
    lines.append(f"- **Total resets detected:** {total_resets}")
    lines.append(
        f"- **Ports tested:** {', '.join(r.port for r in reports)}"
    )

    report_text = "\n".join(lines)
    if output_file:
        with open(output_file, "w") as f:
            f.write(report_text)
        print(f"\nReport written to: {output_file}")
    return report_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 USB feasibility gate test for Phase 2"
    )
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument(
        "--port2", help="Second serial port for dual-port test"
    )
    parser.add_argument(
        "--repeats", type=int, default=1, help="Number of full test cycles"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Grace period delay (seconds)"
    )
    parser.add_argument(
        "--report", "-r", help="Write markdown report to this file"
    )
    parser.add_argument(
        "--dtr-test", action="store_true",
        help="Test DTR/RTS open modes to find reset-preventing settings",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.dtr_test:
        print(f"\nDTR/RTS Open Mode Test")
        print(f"Port: {args.port}")
        print("-" * 60)
        results = asyncio.run(test_dtr_rts_modes(args.port))
        for r in results:
            status = "PASS" if r.success else "FAIL"
            reset = " [RESET]" if r.reset_detected else ""
            print(
                f"  [{status}] {r.name}: {r.duration:.3f}s, "
                f"{r.bytes_received} bytes{reset} — {r.notes}"
            )
        resets = sum(1 for r in results if r.reset_detected)
        print(f"\n{len(results)} modes tested, {resets} reset(s) detected")
        sys.exit(0 if resets == 0 else 1)

    if args.port2:
        reports = asyncio.run(
            run_dual_port_test(args.port, args.port2, delay=args.delay)
        )
        all_passed = all(r.all_passed for r in reports)
    else:
        report = asyncio.run(
            run_feasibility_gate(
                args.port, repeats=args.repeats, delay=args.delay
            )
        )
        reports = [report]
        all_passed = report.all_passed

    if args.report:
        generate_report(reports, args.report)

    if all_passed:
        print("\nFEASIBILITY GATE: PASSED")
        sys.exit(0)
    else:
        print("\nFEASIBILITY GATE: FAILED (see results above)")
        sys.exit(1)


if __name__ == "__main__":
    main()
