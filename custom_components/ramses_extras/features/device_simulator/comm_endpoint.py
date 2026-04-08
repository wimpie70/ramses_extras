# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Communication endpoint for Device Simulator.

The simulator acts as a second MQTT client on the same broker that ramses_rf uses.

MQTT topic layout (from ramses_rf MqttTransport):
  ramses_rf  subscribes to:  ramses_gateway/{gwy_id}/rx   (inbound to rf)
  ramses_rf  publishes  to:  ramses_gateway/{gwy_id}/tx   (outbound from rf)

  simulator  publishes  to:  ramses_gateway/{gwy_id}/rx   (inject device msgs)
  simulator  subscribes to:  ramses_gateway/{gwy_id}/tx   (see RQ commands)
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_GATEWAY_ID,
    LOGGER,
    MQTT_TOPIC_BASE,
    MQTT_TOPIC_SUFFIX_RX,
    MQTT_TOPIC_SUFFIX_TX,
)


class SimulatorCommEndpoint(ABC):
    """Abstract base for simulator communication endpoints."""

    @abstractmethod
    async def async_connect(self) -> None:
        """Connect to the transport."""

    @abstractmethod
    async def async_disconnect(self) -> None:
        """Disconnect from the transport."""

    @abstractmethod
    async def send_packet(self, frame: str) -> None:
        """Send a raw packet frame to ramses_rf (inject a device message)."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connected."""

    def set_inbound_handler(self, handler: InboundHandler) -> None:
        """Register a handler for inbound frames (RQ/W from ramses_rf)."""
        self._inbound_handler = handler


InboundHandler = Any


class MqttEndpoint(SimulatorCommEndpoint):
    """MQTT-based simulator endpoint.

    Uses HA's built-in MQTT integration so no extra broker client is needed.
    Requires the 'mqtt' integration to be configured in HA.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        gateway_id: str = DEFAULT_GATEWAY_ID,
        topic_base: str = MQTT_TOPIC_BASE,
    ) -> None:
        """Initialize the MQTT endpoint.

        :param hass: Home Assistant instance.
        :param gateway_id: RAMSES gateway device ID (e.g. '18:001234').
        :param topic_base: MQTT topic root (default: 'ramses_gateway').
        """
        self.hass = hass
        self.gateway_id = gateway_id
        self._topic_base = topic_base

        self._topic_rx = f"{topic_base}/{gateway_id}/{MQTT_TOPIC_SUFFIX_RX}"
        self._topic_tx = f"{topic_base}/{gateway_id}/{MQTT_TOPIC_SUFFIX_TX}"

        self._connected = False
        self._unsubscribe: Any = None
        self._inbound_handler: Any = None
        self._send_queue: asyncio.Queue[str] = asyncio.Queue()
        self._send_task: asyncio.Task | None = None

    async def async_connect(self) -> None:
        """Subscribe to the /tx topic and start the send queue worker."""
        try:
            from homeassistant.components import mqtt

            self._unsubscribe = await mqtt.async_subscribe(
                self.hass,
                self._topic_tx,
                self._on_message_received,
            )
            self._connected = True

            self._send_task = self.hass.async_create_background_task(
                self._send_worker(),
                name="device_simulator_mqtt_send",
            )

            LOGGER.info(
                "Simulator MQTT endpoint connected. sub=%s pub=%s",
                self._topic_tx,
                self._topic_rx,
            )
        except Exception as err:
            LOGGER.error("Failed to connect MQTT endpoint: %s", err)
            raise

    async def async_disconnect(self) -> None:
        """Unsubscribe and stop the send worker."""
        self._connected = False

        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
            self._send_task = None

        LOGGER.debug("Simulator MQTT endpoint disconnected")

    async def send_packet(self, frame: str) -> None:
        """Queue a packet frame for publishing to /rx.

        :param frame: Raw RAMSES packet string (ASCII).
        """
        await self._send_queue.put(frame)

    @property
    def is_connected(self) -> bool:
        """Return True if connected to MQTT."""
        return self._connected

    @property
    def topic_rx(self) -> str:
        """Topic the simulator publishes to (inbound to ramses_rf)."""
        return self._topic_rx

    @property
    def topic_tx(self) -> str:
        """Topic the simulator subscribes to (outbound from ramses_rf)."""
        return self._topic_tx

    def _on_message_received(self, msg: Any) -> None:
        """Handle a message received on the /tx topic (outbound from ramses_rf).

        :param msg: MQTT message with .payload and .topic.
        """
        try:
            frame = (
                msg.payload.decode("utf-8")
                if isinstance(msg.payload, bytes)
                else msg.payload
            )
            LOGGER.debug("Simulator received from ramses_rf: %s", frame[:80])
            if self._inbound_handler:
                self.hass.async_create_task(
                    self._inbound_handler(frame),
                    name="device_simulator_handle_inbound",
                )
        except Exception as err:
            LOGGER.warning("Error handling inbound MQTT message: %s", err)

    async def _send_worker(self) -> None:
        """Background task: drain the send queue and publish to /rx."""
        from homeassistant.components import mqtt

        while self._connected:
            try:
                frame = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                await mqtt.async_publish(self.hass, self._topic_rx, frame)
                LOGGER.debug(
                    "Simulator published to %s: %s", self._topic_rx, frame[:80]
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.warning("Error publishing MQTT packet: %s", err)
