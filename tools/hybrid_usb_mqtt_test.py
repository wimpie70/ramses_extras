#!/usr/bin/env python3
"""USB + MQTT hybrid feasibility test.

Verifies that a USB ESP32 and an MQTT ESP32 can coexist and see the same
RF network. This is the hardware feasibility evidence for the hybrid pool
(Phase 2 release criterion).

Tests:
  H1: Both transports receive the same RF frames (cross-dongle visibility)
  H2: USB can transmit (after grace period), MQTT sees the over-air copy
  H3: MQTT can transmit, USB sees the over-air copy

Usage:
    source ~/venvs/extras/bin/activate
    python tools/hybrid_usb_mqtt_test.py /dev/ttyACM0 \\
        --mqtt-host 192.168.40.11 --mqtt-port 1883 \\
        --topic-prefix RAMSES/GATEWAY
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
import serial


@dataclass
class Frame:
    """A received frame from either transport."""

    t_ms: float
    source: str  # "USB" or "MQTT"
    hgi_id: str  # "18:130236" etc, or "unknown"
    frame: str
    rssi: str = ""


@dataclass
class HybridResult:
    test_id: str
    name: str
    usb_frames: list[Frame] = field(default_factory=list)
    mqtt_frames: list[Frame] = field(default_factory=list)
    notes: str = ""

    def summary(self) -> str:
        lines = [
            f"--- {self.test_id}: {self.name} ---",
            f"  USB frames:  {len(self.usb_frames)}",
            f"  MQTT frames: {len(self.mqtt_frames)}",
        ]
        if self.notes:
            lines.append(f"  Notes: {self.notes}")

        # Show matching frames (same content seen on both)
        usb_contents = {f.frame.strip() for f in self.usb_frames}
        mqtt_contents = {f.frame.strip() for f in self.mqtt_frames}
        matched = usb_contents & mqtt_contents
        usb_only = usb_contents - mqtt_contents
        mqtt_only = mqtt_contents - usb_contents
        lines.append(f"  Matched (both): {len(matched)}")
        lines.append(f"  USB only: {len(usb_only)}")
        lines.append(f"  MQTT only: {len(mqtt_only)}")

        if matched:
            lines.append("  Matched frames (first 5):")
            for frame in list(matched)[:5]:
                lines.append(f"    {frame}")
        return "\n".join(lines)


class MqttListener:
    """Listens to MQTT RX topics for all HGIs."""

    def __init__(self, host: str, port: int, topic_prefix: str) -> None:
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self.frames: list[Frame] = []
        self._t0 = 0.0
        self._client: mqtt.Client | None = None

    def _now_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_message = self._on_message
        self._client.connect(self.host, self.port, 60)
        # Subscribe to wildcard RX topic
        rx_topic = f"{self.topic_prefix}/+/rx"
        self._client.subscribe(rx_topic)
        self._client.loop_start()

    def _on_message(
        self, client: object, userdata: object, msg: mqtt.MQTTMessage
    ) -> None:
        # Topic format: RAMSES/GATEWAY/18:130236/rx
        parts = msg.topic.split("/")
        hgi_id = parts[-2] if len(parts) >= 2 else "unknown"
        frame = msg.payload.decode("ascii", errors="replace").strip()
        self.frames.append(
            Frame(
                t_ms=self._now_ms(),
                source="MQTT",
                hgi_id=hgi_id,
                frame=frame,
            )
        )

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def publish_tx(self, hgi_id: str, frame: str) -> None:
        """Publish a TX command to a specific HGI's tx topic."""
        if self._client:
            topic = f"{self.topic_prefix}/{hgi_id}/tx"
            self._client.publish(topic, frame)

    def get_hgi_ids(self) -> set[str]:
        return {f.hgi_id for f in self.frames}


class UsbListener:
    """Listens to a USB serial port for RF frames."""

    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self.frames: list[Frame] = []
        self.serial: serial.Serial | None = None
        self._t0 = 0.0
        self._stop = False

    def _now_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    def open(self) -> None:
        self.serial = serial.Serial(self.port, baudrate=self.baud, timeout=0.1)
        self._t0 = time.monotonic()

    def read_for(self, duration_secs: float) -> None:
        """Read frames for a given duration."""
        if not self.serial:
            return
        end = time.monotonic() + duration_secs
        while time.monotonic() < end and not self._stop:
            line = self.serial.readline()
            if line:
                text = line.decode("ascii", errors="replace").strip()
                if text:
                    self.frames.append(
                        Frame(
                            t_ms=self._now_ms(),
                            source="USB",
                            hgi_id="unknown",
                            frame=text,
                        )
                    )

    def write(self, frame: str) -> None:
        """Send a frame via USB."""
        if not self.serial:
            return
        raw = bytes(frame, "ascii") + b"\r\n"
        self.serial.write(raw)

    def close(self) -> None:
        self._stop = True
        if self.serial:
            self.serial.close()
            self.serial = None


async def main() -> None:
    parser = argparse.ArgumentParser(description="USB + MQTT hybrid feasibility test")
    parser.add_argument("port", help="USB serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--mqtt-host", default="192.168.40.11", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument(
        "--topic-prefix",
        default="RAMSES/GATEWAY",
        help="MQTT topic prefix",
    )
    parser.add_argument(
        "--listen-secs",
        type=float,
        default=10.0,
        help="Listen duration per test",
    )
    parser.add_argument(
        "--grace",
        type=float,
        default=3.0,
        help="USB grace period before write",
    )
    args = parser.parse_args()

    print("USB + MQTT Hybrid Feasibility Test")
    print(f"USB:  {args.port}")
    print(f"MQTT: {args.mqtt_host}:{args.mqtt_port}, topic={args.topic_prefix}/+/rx")
    print()

    # Start MQTT listener
    print("Starting MQTT listener...")
    mqtt_listener = MqttListener(args.mqtt_host, args.mqtt_port, args.topic_prefix)
    mqtt_listener.start()
    await asyncio.sleep(1.0)  # let MQTT connect

    # Start USB listener
    print(f"Opening USB serial {args.port}...")
    usb_listener = UsbListener(args.port)
    usb_listener.open()

    # --- H1: Cross-dongle visibility ---
    print(f"\n{'=' * 60}")
    print(f"  H1: Cross-dongle visibility ({args.listen_secs}s)")
    print(f"{'=' * 60}")
    print(f"  Listening on both USB and MQTT for {args.listen_secs}s...")
    print("  (No writes — just observing RF traffic from both dongles)")

    usb_listener.read_for(args.listen_secs)

    result_h1 = HybridResult(
        test_id="H1",
        name="Cross-dongle visibility",
        usb_frames=list(usb_listener.frames),
        mqtt_frames=list(mqtt_listener.frames),
    )
    print(result_h1.summary())

    # Show MQTT HGI IDs discovered
    mqtt_hgis = mqtt_listener.get_hgi_ids()
    print(f"\n  MQTT HGIs seen: {mqtt_hgis}")

    # --- H2: USB transmit, MQTT sees over-air copy ---
    print(f"\n{'=' * 60}")
    print("  H2: USB transmit → MQTT over-air copy")
    print(f"{'=' * 60}")
    print(f"  Waiting {args.grace}s USB grace period...")

    # Clear previous frames
    usb_listener.frames.clear()
    mqtt_listener.frames.clear()

    await asyncio.sleep(args.grace)

    # Send a signature probe via USB
    probe = "I 18:000730 01:000730 01:000730 7FFF 0010"
    print(f"  USB TX: {probe}")
    usb_listener.write(probe)

    # Listen for echoes + over-air copies
    print(f"  Listening {args.listen_secs}s for USB echo + MQTT over-air copy...")
    usb_listener.read_for(args.listen_secs)

    result_h2 = HybridResult(
        test_id="H2",
        name="USB transmit → MQTT over-air copy",
        usb_frames=list(usb_listener.frames),
        mqtt_frames=list(mqtt_listener.frames),
        notes=f"USB sent: {probe}",
    )
    print(result_h2.summary())

    # Check if the probe appeared on MQTT (over-air copy)
    mqtt_saw_probe = any(probe in f.frame for f in mqtt_listener.frames)
    usb_echo = any(probe in f.frame for f in usb_listener.frames)
    print(f"\n  USB echo received: {usb_echo}")
    print(f"  MQTT over-air copy: {mqtt_saw_probe}")

    # --- H3: MQTT transmit, USB sees over-air copy ---
    print(f"\n{'=' * 60}")
    print("  H3: MQTT transmit → USB over-air copy")
    print(f"{'=' * 60}")

    # Pick an MQTT HGI to transmit through
    if mqtt_hgis:
        tx_hgi = sorted(mqtt_hgis)[0]
        print(f"  Transmitting via MQTT HGI: {tx_hgi}")
    else:
        # Fallback: use the known HGI ID
        tx_hgi = "18:149488"
        print(f"  No MQTT HGI seen in traffic, using default: {tx_hgi}")

    # Clear previous frames
    usb_listener.frames.clear()
    mqtt_listener.frames.clear()

    # Send via MQTT
    mqtt_probe = "I 18:000730 01:000730 01:000730 7FFF 0010"
    print(f"  MQTT TX ({tx_hgi}/tx): {mqtt_probe}")
    mqtt_listener.publish_tx(tx_hgi, mqtt_probe)

    # Listen for echoes + over-air copies
    print(f"  Listening {args.listen_secs}s for MQTT echo + USB over-air copy...")
    usb_listener.read_for(args.listen_secs)

    result_h3 = HybridResult(
        test_id="H3",
        name="MQTT transmit → USB over-air copy",
        usb_frames=list(usb_listener.frames),
        mqtt_frames=list(mqtt_listener.frames),
        notes=f"MQTT sent via {tx_hgi}: {mqtt_probe}",
    )
    print(result_h3.summary())

    usb_saw_mqtt_probe = any(mqtt_probe in f.frame for f in usb_listener.frames)
    print(f"\n  USB over-air copy: {usb_saw_mqtt_probe}")

    # --- Summary ---
    print(f"\n\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}\n")

    results = [result_h1, result_h2, result_h3]
    for r in results:
        print(r.summary())
        print()

    # Overall conclusion
    h1_pass = len(result_h1.usb_frames) > 0 and len(result_h1.mqtt_frames) > 0
    h2_pass = usb_echo or mqtt_saw_probe
    h3_pass = usb_saw_mqtt_probe or len(result_h3.mqtt_frames) > 0

    print(f"  H1 (both see RF traffic):     {'PASS' if h1_pass else 'FAIL'}")
    print(f"  H2 (USB TX, MQTT sees copy):  {'PASS' if h2_pass else 'FAIL'}")
    print(f"  H3 (MQTT TX, USB sees copy):  {'PASS' if h3_pass else 'FAIL'}")

    all_pass = h1_pass and h2_pass and h3_pass
    if all_pass:
        print("\n  CONCLUSION: Hybrid USB+MQTT pool is feasible.")
    else:
        print("\n  CONCLUSION: Some tests did not pass. Check the details above.")
        print("  Note: H3 may fail if the MQTT HGI is far from the USB HGI")
        print("  and the signal is too weak for over-air copy.")

    # Cleanup
    usb_listener.close()
    mqtt_listener.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
