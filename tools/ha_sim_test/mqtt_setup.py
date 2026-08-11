"""MQTT broker setup for ha_sim_test.

Publishes retained "online" messages to the MQTT broker for each HGI
topic.  ramses_rf's MQTT transport requires a retained "online" message
on the status topic to set `_topic_pub` (the publish topic).  Without
it, the first publish attempt fails with "invalid UTF-8" / "malformed
packet" because `_topic_pub` is an empty string.

The remote production broker at 192.168.40.11:1883 has these retained
messages from previous ramses_esp connections.  A fresh local broker
does not, so we must publish them before starting tests.
"""

from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from .const import MQTT_BROKER_URL, MQTT_TOPIC_NS

_LOGGER = logging.getLogger(__name__)


def is_mqtt_broker_ready(timeout: float = 5.0) -> bool:
    """Check if the MQTT broker is reachable (TCP connect).

    :param timeout: Socket connect timeout in seconds.
    :return: True if the broker accepted a TCP connection.
    """
    parsed = urlparse(MQTT_BROKER_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1883
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError, ConnectionRefusedError:
        return False


def publish_retained_online_messages(hgi_ids: list[str]) -> None:
    """Publish retained 'online' messages for each HGI topic.

    :param hgi_ids: List of HGI device IDs (e.g. ['18:001234', '18:002234'])
    """
    parsed = urlparse(MQTT_BROKER_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1883
    username = parsed.username or ""
    password = parsed.password or ""

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"ha_sim_mqtt_setup_{int(__import__('time').time())}",
        protocol=mqtt.MQTTv5,
    )
    if username:
        client.username_pw_set(username, password)

    client.connect(host, port, 60)
    client.loop_start()

    for hgi_id in hgi_ids:
        topic = f"{MQTT_TOPIC_NS}/{hgi_id}"
        client.publish(topic, payload="online", qos=0, retain=True)
        _LOGGER.info("Published retained 'online' to %s", topic)

    client.loop_stop()
    client.disconnect()
