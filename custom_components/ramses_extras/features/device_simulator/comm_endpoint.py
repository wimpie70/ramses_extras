# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Communication endpoint for Device Simulator.

The simulator acts as a second MQTT client on the same broker that ramses_rf uses.

MQTT topic layout (from ramses_rf MqttTransport):
  ramses_rf  subscribes to:  RAMSES/GATEWAY_SIM/{gwy_id}/rx   (inbound to rf)
  ramses_rf  publishes  to:  RAMSES/GATEWAY_SIM/{gwy_id}/tx   (outbound from rf)

  simulator  publishes  to:  RAMSES/GATEWAY_SIM/{gwy_id}/rx   (inject device msgs
  + status)
  simulator  subscribes to:  RAMSES/GATEWAY_SIM/{gwy_id}/tx   (see RQ commands)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_GATEWAY_ID,
    LOGGER,
    MQTT_TOPIC_SUFFIX_RX,
    MQTT_TOPIC_SUFFIX_TX,
    SIMULATOR_TOPIC_NS,
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
        self._inbound_handlers = [handler]

    def add_inbound_handler(self, handler: InboundHandler) -> None:
        """Append a handler without removing existing ones."""
        self._inbound_handlers.append(handler)

    def clear_inbound_handlers(self) -> None:
        """Remove all inbound handlers."""
        self._inbound_handlers.clear()


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
        topic_base: str = SIMULATOR_TOPIC_NS,
    ) -> None:
        """Initialize the MQTT endpoint.

        :param hass: Home Assistant instance.
        :param gateway_id: RAMSES gateway device ID (e.g. '18:001234').
        :param topic_base: MQTT topic root (default: 'RAMSES/GATEWAY_SIM').
        """
        self.hass = hass
        self.gateway_id = gateway_id
        self._topic_base = topic_base

        self._topic_status = f"{topic_base}/{gateway_id}"
        self._topic_rx = f"{topic_base}/{gateway_id}/{MQTT_TOPIC_SUFFIX_RX}"
        self._topic_tx = f"{topic_base}/{gateway_id}/{MQTT_TOPIC_SUFFIX_TX}"

        self._connected = False
        self._unsubscribe: Any = None
        self._inbound_handlers: list[InboundHandler] = []
        self._send_queue: asyncio.Queue[str] = asyncio.Queue()
        self._send_task: asyncio.Task | None = None

    async def async_connect(self) -> None:
        """Subscribe to the /tx topic and start the send queue worker."""
        try:
            from homeassistant.components import mqtt

            # Unsubscribe any existing subscription to avoid stale callbacks
            if self._unsubscribe:
                LOGGER.info("Unsubscribing existing MQTT callback before reconnecting")
                self._unsubscribe()
                self._unsubscribe = None

            self._unsubscribe = await mqtt.async_subscribe(
                self.hass,
                self._topic_tx,
                self._on_message_received,
            )
            self._connected = True

            await self._publish_status("online")

            self._send_task = self.hass.async_create_background_task(
                self._send_worker(),
                name="device_simulator_mqtt_send",
            )

            LOGGER.info(
                "Simulator MQTT endpoint %s connected. sub=%s pub=%s",
                id(self),
                self._topic_tx,
                self._topic_rx,
            )
        except Exception as err:
            LOGGER.error("Failed to connect MQTT endpoint: %s", err)
            raise

    async def async_disconnect(self) -> None:
        """Unsubscribe and stop the send worker."""
        self._connected = False

        await self._publish_status("offline")

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
            payload = (
                msg.payload.decode("utf-8")
                if isinstance(msg.payload, bytes)
                else msg.payload
            )
            LOGGER.debug("Simulator MQTT msg on %s: %s", msg.topic, payload[:80])
            # Parse JSON wrapper from ramses_rf: {"msg": "RQ --- ...", "ts": "..."}
            try:
                data = json.loads(payload)
                frame = data.get("msg", "")
            except json.JSONDecodeError:
                # Fallback: treat as raw frame (for backward compatibility)
                frame = payload

            LOGGER.debug("Simulator received from ramses_rf: %s", frame[:80])
            if not self._inbound_handlers:
                LOGGER.warning(
                    "Endpoint %s: no inbound handlers registered, dropping frame",
                    id(self),
                )
            else:
                LOGGER.debug(
                    "Endpoint %s: dispatching frame to %d handler(s)",
                    id(self),
                    len(self._inbound_handlers),
                )
                for handler in list(self._inbound_handlers):
                    LOGGER.debug(
                        "Endpoint %s: scheduling handler %s for frame: %s",
                        id(self),
                        id(handler),
                        frame[:50],
                    )
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            handler(frame),
                            self.hass.loop,
                        )

                        handler_id = id(handler)

                        def _on_handler_done(
                            fut: concurrent.futures.Future[Any], hid: int = handler_id
                        ) -> None:
                            try:
                                exc = fut.exception()
                                if exc:
                                    LOGGER.error(
                                        "Handler %s failed with exception: %s",
                                        hid,
                                        exc,
                                        exc_info=exc,
                                    )
                                else:
                                    LOGGER.debug(
                                        "Handler %s completed successfully",
                                        hid,
                                    )
                            except Exception as cb_err:
                                LOGGER.error("Error in done callback: %s", cb_err)

                        future.add_done_callback(_on_handler_done)
                    except Exception as sched_err:
                        LOGGER.error("Failed to schedule handler: %s", sched_err)
        except Exception as err:
            LOGGER.warning("Error handling inbound MQTT message: %s", err)

    async def _send_worker(self) -> None:
        """Background task: drain the send queue and publish to /rx."""
        import json
        from datetime import datetime

        from homeassistant.components import mqtt

        while self._connected:
            try:
                frame = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                # ramses_rf expects JSON format with msg first, then ts
                payload = json.dumps({"msg": frame, "ts": datetime.now().isoformat()})
                await mqtt.async_publish(self.hass, self._topic_rx, payload)
                LOGGER.debug(
                    "Simulator published to %s: %s", self._topic_rx, frame[:80]
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.warning("Error publishing MQTT packet: %s", err)

    async def _publish_status(self, status: str) -> None:
        """Publish a retained status payload (online/offline) on the base topic."""
        from homeassistant.components import mqtt

        try:
            await mqtt.async_publish(
                self.hass,
                self._topic_status,
                status,
                retain=True,
            )
            LOGGER.debug(
                "Simulator published status '%s' to %s", status, self._topic_status
            )
        except Exception as err:  # pragma: no cover - defensive
            LOGGER.warning("Error publishing simulator status: %s", err)
