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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 USB feasibility gate test for Phase 2"
    )
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument(
        "--repeats", type=int, default=1, help="Number of full test cycles"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Grace period delay (seconds)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    report = asyncio.run(
        run_feasibility_gate(args.port, repeats=args.repeats, delay=args.delay)
    )

    if report.all_passed:
        print("\nFEASIBILITY GATE: PASSED")
        sys.exit(0)
    else:
        print("\nFEASIBILITY GATE: FAILED (see results above)")
        sys.exit(1)


if __name__ == "__main__":
    main()
