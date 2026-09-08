#!/usr/bin/env python3
"""Standalone ESP32/evofw3 USB feasibility gate test.

This script is self-contained — it only needs pyserial (or serialx) and
can be run on any machine with a USB serial HGI device connected.

Usage:
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0
    python esp_usb_feasibility_standalone.py COM3
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0 --report report.md
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0 --nanocul
    python esp_usb_feasibility_standalone.py /dev/ttyUSB0 --nanocul --pace-ms 2.0

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

SIGNATURE_FRAME = (
    " I --- 18:000730 --:------ 18:000730 7FFF 012 0010{ts:012X}76357635763576357635"
)
PING_FRAME = " R --- 18:000730 00:000730 --:------ 10E0 001 00"

# evofw3 debug command: "!V\r" → "# evofw3 0.7.3\r\n"
# culfw  debug command: "V\r"  → "V 1.67 nanoCUL868\r\n"
# The nanoCUL ships with culfw by default; evofw3 must be flashed
# separately.  culfw uses bare single-letter commands (no "!" prefix),
# while evofw3 uses "!" as the command prefix.
EVOFW3_VERSION_CMD = b"!V\r"
CULFW_VERSION_CMD = b"V\r"


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


def write_with_pacing(ser: serial.Serial, data: bytes, delay_ms: float) -> None:
    """Write bytes one at a time with a delay between each byte.

    The ATmega328p (nanoCUL) has a 32-byte software ring buffer for the
    host USART.  If the main loop is busy with radio RX (software UART
    interrupts), the buffer can overflow before a long frame is fully
    received.  Pacing gives the main loop time to drain each byte.
    """
    delay_s = delay_ms / 1000.0
    for byte in data:
        ser.write(bytes([byte]))
        ser.flush()
        time.sleep(delay_s)


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
        return TestResult(
            "Port open (no write)", False, time.perf_counter() - start, notes=str(e)
        )


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
        return TestResult(
            "Immediate 7FFF probe", False, time.perf_counter() - start, notes=str(e)
        )


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
        return TestResult(
            f"Repeated probes ({count}x)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


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
        return TestResult(
            f"Delayed probe (after {delay}s)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


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
        return TestResult(
            "Ordinary RF write", False, time.perf_counter() - start, notes=str(e)
        )


def test_boot_banner(port: str) -> TestResult:
    """Capture the raw boot banner bytes to identify the firmware.

    evofw3 prints "# evofw3 0.7.3\\r\\n" on boot (gateway_init).
    culfw does NOT print a boot banner by default — any bytes seen on
    open are likely received RF traffic.

    This test captures whatever the device sends in the first 2 seconds
    after port open and prints it raw, so we can identify the firmware
    from the actual output.
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        data = read_for_duration(ser, 2.0)
        ser.close()
        duration = time.perf_counter() - start
        raw = data.decode(errors="replace").strip()
        is_evofw3 = "evofw3" in raw
        is_culfw = raw.startswith("V ") and "CUL" in raw
        if is_evofw3:
            notes = f"evofw3 banner: {raw!r}"
        elif is_culfw:
            notes = f"culfw banner: {raw!r}"
        elif raw:
            notes = f"Unknown: {raw!r}"
        else:
            notes = "No banner (0 bytes)"
        return TestResult(
            name="Boot banner capture",
            success=True,  # informational, always "passes"
            duration=duration,
            bytes_received=len(data),
            notes=notes,
            received_data=data,
        )
    except Exception as e:
        return TestResult(
            "Boot banner capture", False, time.perf_counter() - start, notes=str(e)
        )


def test_version_command(port: str) -> TestResult:
    """Send version commands for both evofw3 and culfw.

    evofw3 uses "!V\\r" -> "# evofw3 0.7.3\\r\\n"
    culfw  uses "V\\r"  -> "V 1.67 nanoCUL868\\r\\n"

    The nanoCUL ships with culfw by default.  evofw3 must be flashed
    separately and uses a different command syntax ("!" prefix).

    This test sends both commands and reports which (if any) responded,
    so we can identify the firmware regardless of which is installed.
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(0.5)  # let any boot banner drain
        ser.reset_input_buffer()

        # Try culfw first (bare "V\r")
        ser.write(CULFW_VERSION_CMD)
        ser.flush()
        culfw_data = read_for_duration(ser, 1.0)
        ser.reset_input_buffer()

        # Try evofw3 ("!V\r")
        ser.write(EVOFW3_VERSION_CMD)
        ser.flush()
        evofw3_data = read_for_duration(ser, 1.0)

        ser.close()
        duration = time.perf_counter() - start

        culfw_resp = culfw_data.decode(errors="replace").strip()
        evofw3_resp = evofw3_data.decode(errors="replace").strip()

        got_culfw = "CUL" in culfw_resp or culfw_resp.startswith("V ")
        got_evofw3 = "evofw3" in evofw3_resp

        if got_evofw3:
            notes = f"evofw3: {evofw3_resp!r}"
            success = True
        elif got_culfw:
            notes = f"culfw: {culfw_resp!r}"
            success = True
        elif culfw_resp or evofw3_resp:
            notes = f"culfw_resp={culfw_resp!r} evofw3_resp={evofw3_resp!r}"
            success = False
        else:
            notes = "No response to either !V or V"
            success = False

        total_bytes = len(culfw_data) + len(evofw3_data)
        return TestResult(
            name="Version command (!V + V)",
            success=success,
            duration=duration,
            bytes_received=total_bytes,
            notes=notes,
            received_data=culfw_data + evofw3_data,
        )
    except Exception as e:
        return TestResult(
            "Version command (!V + V)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_version_command_delayed(port: str, boot_wait: float = 3.0) -> TestResult:
    """Send version command after waiting for the device to finish booting.

    pyserial sets DTR=True on port open by default.  On many nanoCUL /
    Arduino boards, DTR is connected to the ATmega reset line, so opening
    the port resets the device.  The device then takes 1-2s to boot
    before it can receive commands.

    The standard test_version_command waits only 0.5s, which may be too
    short.  This test waits 3s (configurable) before sending, to ensure
    the device has finished booting.

    If this test passes where test_version_command failed, the root cause
    is not a broken RX path but a timing issue: commands were sent
    before the device finished booting.
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        # Wait for the device to finish booting after DTR reset
        boot_data = read_for_duration(ser, boot_wait)
        ser.reset_input_buffer()

        # Send evofw3 version command
        ser.write(EVOFW3_VERSION_CMD)
        ser.flush()
        evofw3_data = read_for_duration(ser, 1.0)
        ser.reset_input_buffer()

        # Send culfw version command
        ser.write(CULFW_VERSION_CMD)
        ser.flush()
        culfw_data = read_for_duration(ser, 1.0)

        ser.close()
        duration = time.perf_counter() - start

        boot_str = boot_data.decode(errors="replace").strip()
        evofw3_resp = evofw3_data.decode(errors="replace").strip()
        culfw_resp = culfw_data.decode(errors="replace").strip()

        got_evofw3 = "evofw3" in evofw3_resp
        got_culfw = "CUL" in culfw_resp or culfw_resp.startswith("V ")

        if got_evofw3:
            notes = f"evofw3: {evofw3_resp!r} (boot: {boot_str!r})"
            success = True
        elif got_culfw:
            notes = f"culfw: {culfw_resp!r} (boot: {boot_str!r})"
            success = True
        elif evofw3_resp or culfw_resp:
            notes = (
                f"evofw3_resp={evofw3_resp!r} culfw_resp={culfw_resp!r}"
                f" (boot: {boot_str!r})"
            )
            success = False
        else:
            notes = f"No response after {boot_wait}s wait (boot: {boot_str!r})"
            success = False

        total_bytes = len(boot_data) + len(evofw3_data) + len(culfw_data)
        return TestResult(
            name=f"Version command (delayed {boot_wait}s)",
            success=success,
            duration=duration,
            bytes_received=total_bytes,
            notes=notes,
            received_data=boot_data + evofw3_data + culfw_data,
        )
    except Exception as e:
        return TestResult(
            f"Version command (delayed {boot_wait}s)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_version_command_no_dtr(port: str) -> TestResult:
    """Send version command with DTR/RTS disabled to prevent reset on open.

    pyserial sets DTR=True on port open by default.  On nanoCUL boards
    where DTR is wired to the ATmega reset line, this resets the device
    on every port open.  Using dsrdtr=True prevents the DTR toggle.

    If this test passes where the standard version command failed, the
    root cause is DTR-triggered reset, not a broken RX path.
    """
    start = time.perf_counter()
    try:
        # dsrdtr=True prevents pyserial from toggling DTR on open
        ser = serial.Serial(port, baudrate=115200, timeout=0.1, dsrdtr=True)
        # Explicitly set DTR=False to ensure reset line is not asserted
        ser.setDTR(False)
        time.sleep(0.5)
        ser.reset_input_buffer()

        # Send evofw3 version command
        ser.write(EVOFW3_VERSION_CMD)
        ser.flush()
        evofw3_data = read_for_duration(ser, 1.0)
        ser.reset_input_buffer()

        # Send culfw version command
        ser.write(CULFW_VERSION_CMD)
        ser.flush()
        culfw_data = read_for_duration(ser, 1.0)

        ser.close()
        duration = time.perf_counter() - start

        evofw3_resp = evofw3_data.decode(errors="replace").strip()
        culfw_resp = culfw_data.decode(errors="replace").strip()

        got_evofw3 = "evofw3" in evofw3_resp
        got_culfw = "CUL" in culfw_resp or culfw_resp.startswith("V ")

        if got_evofw3:
            notes = f"evofw3: {evofw3_resp!r}"
            success = True
        elif got_culfw:
            notes = f"culfw: {culfw_resp!r}"
            success = True
        elif evofw3_resp or culfw_resp:
            notes = f"evofw3_resp={evofw3_resp!r} culfw_resp={culfw_resp!r}"
            success = False
        else:
            notes = "No response (DTR disabled)"
            success = False

        total_bytes = len(evofw3_data) + len(culfw_data)
        return TestResult(
            name="Version command (no DTR reset)",
            success=success,
            duration=duration,
            bytes_received=total_bytes,
            notes=notes,
            received_data=evofw3_data + culfw_data,
        )
    except Exception as e:
        return TestResult(
            "Version command (no DTR reset)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_version_command_slow_baud(
    port: str, baudrate: int = 57600, boot_wait: float = 3.0
) -> TestResult:
    """Send version command at a slower baud rate.

    The evofw3 README and ramses_rf's port.py comment both note that the
    ATmega328p host baud rate is "57600 (or 115200, YMMV)".  Some nanoCUL
    builds may use 57600 as the default.  If the device is running at
    57600 and we open at 115200, the boot banner would be garbled — but
    we see a clean 17-byte banner, so 115200 is likely correct.

    This test tries 57600 as a fallback, with a 3s boot wait.  If it
    gets a response where the 115200 version command failed, the device
    is running at 57600 (and the 17 "clean" bytes at 115200 were a
    coincidence).
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=baudrate, timeout=0.1)
        boot_data = read_for_duration(ser, boot_wait)
        ser.reset_input_buffer()

        ser.write(EVOFW3_VERSION_CMD)
        ser.flush()
        evofw3_data = read_for_duration(ser, 1.0)
        ser.reset_input_buffer()

        ser.write(CULFW_VERSION_CMD)
        ser.flush()
        culfw_data = read_for_duration(ser, 1.0)

        ser.close()
        duration = time.perf_counter() - start

        boot_str = boot_data.decode(errors="replace").strip()
        evofw3_resp = evofw3_data.decode(errors="replace").strip()
        culfw_resp = culfw_data.decode(errors="replace").strip()

        got_evofw3 = "evofw3" in evofw3_resp
        got_culfw = "CUL" in culfw_resp or culfw_resp.startswith("V ")

        if got_evofw3:
            notes = f"evofw3 @ {baudrate}: {evofw3_resp!r} (boot: {boot_str!r})"
            success = True
        elif got_culfw:
            notes = f"culfw @ {baudrate}: {culfw_resp!r} (boot: {boot_str!r})"
            success = True
        elif evofw3_resp or culfw_resp:
            notes = f"@{baudrate}: evofw3={evofw3_resp!r} culfw={culfw_resp!r}"
            success = False
        else:
            notes = f"No response @ {baudrate} baud"
            success = False

        total_bytes = len(boot_data) + len(evofw3_data) + len(culfw_data)
        return TestResult(
            name=f"Version command @ {baudrate} baud",
            success=success,
            duration=duration,
            bytes_received=total_bytes,
            notes=notes,
            received_data=boot_data + evofw3_data + culfw_data,
        )
    except Exception as e:
        return TestResult(
            f"Version command @ {baudrate} baud",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_slow_paced_probe(
    port: str, byte_delay_ms: float = 10.0, boot_wait: float = 3.0
) -> TestResult:
    """Send _PUZZ with very slow pacing (10ms/byte) after a long boot wait.

    This combines all timing mitigations:
    - 3s boot wait (lets the device finish booting after DTR reset)
    - 10ms/byte pacing (avoids 32-byte RX buffer overflow)
    - 3s read after send (gives time for RF TX + loopback echo)

    If this test passes, we know the device CAN echo — the issue was
    purely timing.  If it still fails, the device's RF TX path is
    broken (known nanoCUL/ATmega328p limitation).
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        boot_data = read_for_duration(ser, boot_wait)
        ser.reset_input_buffer()

        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        write_with_pacing(ser, frame, byte_delay_ms)
        data = read_for_duration(ser, 3.0)
        ser.close()
        duration = time.perf_counter() - start

        boot_str = boot_data.decode(errors="replace").strip()
        got_echo = b"7FFF" in data
        return TestResult(
            name=f"Slow paced probe ({byte_delay_ms}ms/byte, {boot_wait}s boot)",
            success=got_echo,
            duration=duration,
            bytes_received=len(data),
            notes=(
                f"Got echo (boot: {boot_str!r})"
                if got_echo
                else f"No echo (boot: {boot_str!r})"
            ),
            received_data=data,
        )
    except Exception as e:
        return TestResult(
            f"Slow paced probe ({byte_delay_ms}ms/byte, {boot_wait}s boot)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_paced_probe(port: str, byte_delay_ms: float = 1.0) -> TestResult:
    """Send the _PUZZ signature frame with inter-byte pacing.

    The ATmega328p (nanoCUL) has a 32-byte software ring buffer for the
    host USART (RXBUF in tty.h).  The _PUZZ frame is 82 bytes.  If the
    main loop is busy with radio RX (software UART interrupts), the
    buffer overflows before the full frame is received, and no echo is
    produced.  Pacing gives the main loop time to drain each byte.

    If this test passes where test_immediate_probe failed, the root
    cause is buffer overflow, and the fix is byte-pacing in ramses_rf
    for nanoCUL devices.
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(0.5)  # let any boot banner drain
        ser.reset_input_buffer()
        ts = int(time.time() * 1000)
        frame = (SIGNATURE_FRAME.format(ts=ts) + "\r\n").encode()
        write_with_pacing(ser, frame, byte_delay_ms)
        data = read_for_duration(ser, 2.0)
        ser.close()
        duration = time.perf_counter() - start
        got_echo = b"7FFF" in data or b"I ---" in data
        return TestResult(
            name=f"Paced 7FFF probe ({byte_delay_ms}ms/byte)",
            success=got_echo,
            duration=duration,
            bytes_received=len(data),
            notes="Got echo" if got_echo else "No echo",
            received_data=data,
        )
    except Exception as e:
        return TestResult(
            f"Paced 7FFF probe ({byte_delay_ms}ms/byte)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


def test_paced_write(port: str, byte_delay_ms: float = 1.0) -> TestResult:
    """Send an ordinary RF write with inter-byte pacing.

    Same as test_ordinary_write but with pacing, to test whether a
    normal RF command works once the buffer overflow issue is avoided.
    """
    start = time.perf_counter()
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.1)
        time.sleep(0.5)
        ser.reset_input_buffer()
        frame = (PING_FRAME + "\r\n").encode()
        write_with_pacing(ser, frame, byte_delay_ms)
        data = read_for_duration(ser, 2.0)
        ser.close()
        duration = time.perf_counter() - start
        got_response = b"10E0" in data or b"RP" in data or b"I ---" in data
        return TestResult(
            name=f"Paced RF write ({byte_delay_ms}ms/byte)",
            success=got_response,
            duration=duration,
            bytes_received=len(data),
            notes="Got response" if got_response else "No response",
            received_data=data,
        )
    except Exception as e:
        return TestResult(
            f"Paced RF write ({byte_delay_ms}ms/byte)",
            False,
            time.perf_counter() - start,
            notes=str(e),
        )


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
        return TestResult(
            "Close/reopen", False, time.perf_counter() - start, notes=str(e)
        )


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
            results.append(
                TestResult(
                    name=f"DTR/RTS: {label}",
                    success=True,
                    duration=duration,
                    bytes_received=len(data),
                    reset_detected=reset_detected,
                    notes="RESET detected" if reset_detected else "No reset",
                    received_data=data,
                )
            )
        except Exception as e:
            results.append(
                TestResult(
                    name=f"DTR/RTS: {label}",
                    success=False,
                    duration=time.perf_counter() - start,
                    notes=str(e),
                )
            )
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
                print("  >>> Unplug detected, waiting for reconnect... <<<")
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
    include_nanocul: bool = False,
    nanocul_pace_ms: float = 1.0,
) -> FeasibilityReport:
    report = FeasibilityReport(port=port)
    print("\nESP32/evofw3 USB Feasibility Gate Test")
    print(f"Port: {port}")
    print(f"Repeats: {repeats}")
    print(f"Delay: {delay}s")
    if include_nanocul:
        print(f"nanoCUL tests: enabled (pace={nanocul_pace_ms}ms/byte)")
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
        if i == 0 and include_nanocul:
            print("\n--- nanoCUL / ATmega328p diagnostic tests ---")
            report.add(test_boot_banner(port))
            report.add(test_version_command(port))
            report.add(test_version_command_delayed(port))
            report.add(test_version_command_no_dtr(port))
            report.add(test_version_command_slow_baud(port))
            report.add(test_paced_probe(port, nanocul_pace_ms))
            report.add(test_paced_write(port, nanocul_pace_ms))
            report.add(test_slow_paced_probe(port))
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
            lines.append(
                f"| {r.name} | {status} | {r.duration:.3f}s"
                f" | {r.bytes_received} | {reset} | {notes} |"
            )
        lines.append("")
    all_passed = all(r.all_passed for r in reports)
    total_resets = sum(
        sum(1 for r in rep.results if r.reset_detected) for rep in reports
    )
    lines.append("## Summary\n")
    lines.append(f"- **Overall:** {'PASSED' if all_passed else 'FAILED'}")
    lines.append(f"- **Total resets detected:** {total_resets}")
    lines.append(f"- **Ports tested:** {', '.join(r.port for r in reports)}")
    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to: {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32/evofw3 USB feasibility gate test"
    )
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument(
        "--repeats", type=int, default=1, help="Number of full test cycles"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Grace period delay (seconds)"
    )
    parser.add_argument("--report", "-r", help="Write markdown report to this file")
    parser.add_argument(
        "--dtr-test",
        action="store_true",
        help="Test DTR/RTS open modes to find reset-preventing settings",
    )
    parser.add_argument(
        "--unplug-test",
        action="store_true",
        help="Test physical unplug/reconnect (interactive — prompts to unplug)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests: basic + DTR/RTS + unplug/reconnect",
    )
    parser.add_argument(
        "--nanocul",
        action="store_true",
        help="Run nanoCUL/ATmega328p diagnostic tests: version command, "
        "paced probe (inter-byte delay to avoid 32-byte RX buffer overflow), "
        "and paced RF write",
    )
    parser.add_argument(
        "--pace-ms",
        type=float,
        default=1.0,
        help="Inter-byte delay in ms for paced tests (default: 1.0ms)",
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
        include_nanocul=args.nanocul,
        nanocul_pace_ms=args.pace_ms,
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
