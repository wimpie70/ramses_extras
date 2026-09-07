#!/usr/bin/env python3
"""Two-USB pool feasibility test.

Verifies that two ESP32 USB serial ports can be opened simultaneously,
both receive RF frames, and both can transmit after a grace period.

Usage:
    source ~/venvs/extras/bin/activate
    python tools/two_usb_test.py /dev/ttyACM0 /dev/ttyACM1 [--grace 3.0]
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

import serial


@dataclass
class PortStats:
    port: str
    frames: list[str] = field(default_factory=list)
    echoes: list[str] = field(default_factory=list)
    boot_lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def open_and_listen(
    port: str, baud: int, duration: float, grace: float, label: str
) -> PortStats:
    """Open a port, wait grace period, listen for duration, return stats."""
    stats = PortStats(port=port)
    print(f"\n  [{label}] Opening {port}...")
    try:
        s = serial.Serial(port, baudrate=baud, timeout=0.1)
    except Exception as e:
        stats.errors.append(f"open failed: {e}")
        print(f"  [{label}] ERROR: {e}")
        return stats

    t0 = time.time()

    # Grace period — listen for boot output
    print(f"  [{label}] Waiting {grace}s grace period...")
    grace_end = t0 + grace
    while time.time() < grace_end:
        line = s.readline()
        if line:
            text = line.decode("ascii", errors="replace").strip()
            if text:
                stats.boot_lines.append(text)

    # Listen for RF frames
    print(f"  [{label}] Listening {duration}s for RF frames...")
    listen_end = time.time() + duration
    while time.time() < listen_end:
        line = s.readline()
        if line:
            text = line.decode("ascii", errors="replace").strip()
            if text:
                stats.frames.append(text)

    s.close()
    print(
        f"  [{label}] Done: {len(stats.boot_lines)} boot lines,"
        f" {len(stats.frames)} RF frames"
    )
    return stats


def open_grace_and_send(
    port: str, baud: int, grace: float, cmd: str, label: str
) -> PortStats:
    """Open a port, wait grace, send a command, listen for echo."""
    stats = PortStats(port=port)
    print(f"\n  [{label}] Opening {port}...")
    try:
        s = serial.Serial(port, baudrate=baud, timeout=0.5)
    except Exception as e:
        stats.errors.append(f"open failed: {e}")
        print(f"  [{label}] ERROR: {e}")
        return stats

    # Grace period
    print(f"  [{label}] Waiting {grace}s grace period...")
    time.sleep(grace)

    # Send command
    raw = bytes(cmd, "ascii") + b"\r\n"
    print(f"  [{label}] TX: {cmd}")
    try:
        s.write(raw)
    except Exception as e:
        stats.errors.append(f"write failed: {e}")
        print(f"  [{label}] WRITE ERROR: {e}")
        s.close()
        return stats

    # Listen for echo (5 seconds)
    print(f"  [{label}] Listening 5s for echo...")
    listen_end = time.time() + 5
    while time.time() < listen_end:
        line = s.readline()
        if line:
            text = line.decode("ascii", errors="replace").strip()
            if text:
                if cmd[:20] in text or "7FFF" in text:
                    stats.echoes.append(text)
                    print(f"  [{label}] ECHO: {text}")
                else:
                    stats.frames.append(text)

    s.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Two-USB pool feasibility test")
    parser.add_argument("port1", help="First serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("port2", help="Second serial port (e.g. /dev/ttyACM1)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument(
        "--grace", type=float, default=3.0, help="Boot grace period (s)"
    )
    parser.add_argument(
        "--listen", type=float, default=15.0, help="Listen duration (s)"
    )
    args = parser.parse_args()

    sig = "I 18:000730 01:000730 01:000730 7FFF 0010"

    print("=" * 60)
    print("  Two-USB Pool Feasibility Test")
    print("=" * 60)
    print(f"  Port 1: {args.port1}")
    print(f"  Port 2: {args.port2}")
    print(f"  Grace:  {args.grace}s")
    print(f"  Listen: {args.listen}s")

    # --- U1: Both ports open simultaneously, listen for RF ---
    print(f"\n{'=' * 60}")
    print(f"  U1: Both ports open + listen for RF ({args.listen}s)")
    print(f"{'=' * 60}")
    print("  Opening both ports at the same time...")

    # Open both ports simultaneously
    try:
        s1 = serial.Serial(args.port1, baudrate=args.baud, timeout=0.1)
        s2 = serial.Serial(args.port2, baudrate=args.baud, timeout=0.1)
    except Exception as e:
        print(f"  ERROR opening ports: {e}")
        return

    t0 = time.time()
    stats1 = PortStats(port=args.port1)
    stats2 = PortStats(port=args.port2)

    print(f"  Waiting {args.grace}s grace period (both ports)...")
    grace_end = t0 + args.grace
    while time.time() < grace_end:
        for s, stats in [(s1, stats1), (s2, stats2)]:
            line = s.readline()
            if line:
                text = line.decode("ascii", errors="replace").strip()
                if text:
                    stats.boot_lines.append(text)

    print(f"  Listening {args.listen}s for RF frames on both ports...")
    listen_end = time.time() + args.listen
    while time.time() < listen_end:
        for s, stats in [(s1, stats1), (s2, stats2)]:
            line = s.readline()
            if line:
                text = line.decode("ascii", errors="replace").strip()
                if text:
                    stats.frames.append(text)

    s1.close()
    s2.close()

    print(f"\n  --- Port 1 ({args.port1}) ---")
    print(f"  Boot lines: {len(stats1.boot_lines)}")
    if stats1.boot_lines:
        for line in stats1.boot_lines[:5]:
            print(f"    {line!r}")
    print(f"  RF frames:  {len(stats1.frames)}")
    if stats1.frames:
        for line in stats1.frames[:5]:
            print(f"    {line!r}")

    print(f"\n  --- Port 2 ({args.port2}) ---")
    print(f"  Boot lines: {len(stats2.boot_lines)}")
    if stats2.boot_lines:
        for line in stats2.boot_lines[:5]:
            print(f"    {line!r}")
    print(f"  RF frames:  {len(stats2.frames)}")
    if stats2.frames:
        for line in stats2.frames[:5]:
            print(f"    {line!r}")

    # Check for matching frames (cross-dongle visibility)
    set1 = {f.strip() for f in stats1.frames}
    set2 = {f.strip() for f in stats2.frames}
    matched = set1 & set2
    print(f"\n  Cross-dongle matched frames: {len(matched)}")
    if matched:
        for m in list(matched)[:5]:
            print(f"    {m[:80]}")

    u1_pass = len(stats1.frames) > 0 or len(stats2.frames) > 0
    u1_both = len(stats1.frames) > 0 and len(stats2.frames) > 0

    # --- U2: TX via port 1, listen on port 2 for over-air copy ---
    print(f"\n{'=' * 60}")
    print(f"  U2: TX via {args.port1}, listen on {args.port2} for over-air copy")
    print(f"{'=' * 60}")

    # Open both, wait grace, TX on port1, listen on port2
    try:
        s1 = serial.Serial(args.port1, baudrate=args.baud, timeout=0.1)
        s2 = serial.Serial(args.port2, baudrate=args.baud, timeout=0.1)
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    print(f"  Waiting {args.grace}s grace period...")
    time.sleep(args.grace)

    # TX on port 1
    raw = bytes(sig, "ascii") + b"\r\n"
    print(f"  Port 1 TX: {sig}")
    s1.write(raw)

    # Listen on both for 10s
    print("  Listening 10s on both ports...")
    p1_rx = []
    p2_rx = []
    listen_end = time.time() + 10
    while time.time() < listen_end:
        for s, rx_list in [(s1, p1_rx), (s2, p2_rx)]:
            line = s.readline()
            if line:
                text = line.decode("ascii", errors="replace").strip()
                if text:
                    rx_list.append(text)
                    port_label = args.port1 if s is s1 else args.port2
                    print(f"    {port_label} RX: {text[:80]}")

    s1.close()
    s2.close()

    p1_echo = any("7FFF" in f for f in p1_rx)
    p2_copy = any("7FFF" in f for f in p2_rx)
    print(f"\n  Port 1 echo: {p1_echo}")
    print(f"  Port 2 over-air copy: {p2_copy}")

    # --- U3: TX via port 2, listen on port 1 for over-air copy ---
    print(f"\n{'=' * 60}")
    print(f"  U3: TX via {args.port2}, listen on {args.port1} for over-air copy")
    print(f"{'=' * 60}")

    try:
        s1 = serial.Serial(args.port1, baudrate=args.baud, timeout=0.1)
        s2 = serial.Serial(args.port2, baudrate=args.baud, timeout=0.1)
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    print(f"  Waiting {args.grace}s grace period...")
    time.sleep(args.grace)

    print(f"  Port 2 TX: {sig}")
    s2.write(raw)

    print("  Listening 10s on both ports...")
    p1_rx2 = []
    p2_rx2 = []
    listen_end = time.time() + 10
    while time.time() < listen_end:
        for s, rx_list in [(s1, p1_rx2), (s2, p2_rx2)]:
            line = s.readline()
            if line:
                text = line.decode("ascii", errors="replace").strip()
                if text:
                    rx_list.append(text)
                    port_label = args.port1 if s is s1 else args.port2
                    print(f"    {port_label} RX: {text[:80]}")

    s1.close()
    s2.close()

    p2_echo = any("7FFF" in f for f in p2_rx2)
    p1_copy = any("7FFF" in f for f in p1_rx2)
    print(f"\n  Port 2 echo: {p2_echo}")
    print(f"  Port 1 over-air copy: {p1_copy}")

    # --- Summary ---
    print(f"\n\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}\n")

    u1_status = "PASS" if u1_both else "PARTIAL" if u1_pass else "FAIL"
    print(f"  U1: Both ports receive RF     {u1_status}")
    print(
        f"      Port 1 frames: {len(stats1.frames)},"
        f" Port 2 frames: {len(stats2.frames)},"
        f" matched: {len(matched)}"
    )
    u2_status = "PASS" if p1_echo and p2_copy else "PARTIAL" if p1_echo else "FAIL"
    print(f"  U2: Port 1 TX, Port 2 copy    {u2_status}")
    print(f"      Port 1 echo: {p1_echo}, Port 2 over-air: {p2_copy}")
    u3_status = "PASS" if p2_echo and p1_copy else "PARTIAL" if p2_echo else "FAIL"
    print(f"  U3: Port 2 TX, Port 1 copy    {u3_status}")
    print(f"      Port 2 echo: {p2_echo}, Port 1 over-air: {p1_copy}")

    all_pass = u1_both and p1_echo and p2_echo
    if all_pass:
        print("\n  CONCLUSION: Two-USB pool is feasible.")
    else:
        print("\n  CONCLUSION: Some tests partial/failed. Check details above.")
        print("  Note: over-air copy depends on physical proximity and RF traffic.")


if __name__ == "__main__":
    main()
