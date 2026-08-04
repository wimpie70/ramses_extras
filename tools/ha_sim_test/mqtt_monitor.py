"""MQTT monitor — subscribe to all ramses_sim topics and log messages.

Usage:
    source ~/venvs/extras/bin/activate
    python -m tools.ha_sim_test.mqtt_monitor [--duration 60] [--verbose]

This subscribes to RAMSES/GATEWAY_SIM/# on the shared MQTT broker and
logs every message received, along with a timestamp and topic.  It is
useful for diagnosing whether packets injected by the device simulator
are actually reaching the MQTT broker (and thus whether drops happen
on the broker side or on the ramses_cc consumer side).

The MQTT broker is shared across all parallel containers (topic isolation
is via the HGI ID in the topic path: RAMSES/GATEWAY_SIM/<hgi_id>/...).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime as dt

import paho.mqtt.client as mqtt

# Import the broker URL from the ha_sim_test const module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
# Parse the MQTT URL: mqtt://user:pass@host:port
from urllib.parse import urlparse

from tools.ha_sim_test.const import MQTT_BROKER_URL, MQTT_TOPIC_NS  # noqa: E402

_parsed = urlparse(MQTT_BROKER_URL)
_MQTT_HOST = _parsed.hostname or "192.168.40.11"
_MQTT_PORT = _parsed.port or 1883
_MQTT_USER = _parsed.username or ""
_MQTT_PASS = _parsed.password or ""


class MqttMonitor:
    """Subscribe to all ramses_sim topics and log messages."""

    def __init__(self, duration: int = 60, verbose: bool = False) -> None:
        self.duration = duration
        self.verbose = verbose
        self.msg_count = 0
        self.topic_counts: dict[str, int] = defaultdict(int)
        self.start_time = 0.0
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"ha_sim_mqtt_monitor_{int(time.time())}",
        )
        if _MQTT_USER:
            self._client.username_pw_set(_MQTT_USER, _MQTT_PASS)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        topic = f"{MQTT_TOPIC_NS}/#"
        client.subscribe(topic)
        print(
            f"  [monitor] Connected to {_MQTT_HOST}:{_MQTT_PORT}, subscribed to {topic}"
        )

    def _on_disconnect(self, client, userdata, *args, **kwargs):
        print("  [monitor] Disconnected (will retry)")

    def _on_message(self, client, userdata, msg):
        self.msg_count += 1
        self.topic_counts[msg.topic] += 1
        if self.verbose:
            payload = msg.payload.decode("utf-8", errors="replace")[:120]
            ts = dt.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}] {msg.topic}: {payload}")

    def run(self) -> None:
        print(f"  [monitor] Connecting to {_MQTT_HOST}:{_MQTT_PORT}...")
        print(f"  [monitor] Monitoring for {self.duration}s...")
        self._client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=60)
        self._client.loop_start()
        self.start_time = time.time()

        try:
            while time.time() - self.start_time < self.duration:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  [monitor] Interrupted")

        self._client.loop_stop()
        self._client.disconnect()

        elapsed = time.time() - self.start_time
        print(f"\n  [monitor] Summary: {self.msg_count} messages in {elapsed:.1f}s")
        print(f"  [monitor] Topics ({len(self.topic_counts)}):")
        for topic, count in sorted(self.topic_counts.items()):
            print(f"    {count:5d}  {topic}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MQTT monitor for ha_sim_test")
    parser.add_argument(
        "--duration", type=int, default=60, help="Monitoring duration in seconds"
    )
    parser.add_argument("--verbose", action="store_true", help="Print every message")
    args = parser.parse_args()

    monitor = MqttMonitor(duration=args.duration, verbose=args.verbose)
    monitor.run()


if __name__ == "__main__":
    main()
