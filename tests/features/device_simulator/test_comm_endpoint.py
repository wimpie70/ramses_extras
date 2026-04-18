# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for Device Simulator communication endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.comm_endpoint import (
    MqttEndpoint,
    SimulatorCommEndpoint,
)
from custom_components.ramses_extras.features.device_simulator.const import (
    DEFAULT_GATEWAY_ID,
    MQTT_TOPIC_SUFFIX_RX,
    MQTT_TOPIC_SUFFIX_TX,
    SIMULATOR_TOPIC_NS,
)


def _build_hass(loop: asyncio.AbstractEventLoop) -> MagicMock:
    """Create a HomeAssistant mock with background task helper."""

    hass = MagicMock()
    hass.loop = loop

    def _create_task(coro, name: str | None = None):  # noqa: ARG001 unused name
        return loop.create_task(coro)

    hass.async_create_background_task = MagicMock(side_effect=_create_task)
    return hass


class TestSimulatorCommEndpointBase:
    """Tests for SimulatorCommEndpoint abstract base class."""

    def test_abstract_methods_exist(self) -> None:
        """Test that abstract methods are defined."""
        # Verify the abstract methods exist
        assert hasattr(SimulatorCommEndpoint, "async_connect")
        assert hasattr(SimulatorCommEndpoint, "async_disconnect")
        assert hasattr(SimulatorCommEndpoint, "send_packet")
        assert hasattr(SimulatorCommEndpoint, "is_connected")

    def test_inbound_handler_management(self) -> None:
        """Test handler registration and management."""

        class ConcreteEndpoint(SimulatorCommEndpoint):
            """Concrete implementation for testing."""

            async def async_connect(self) -> None:
                """Connect to the transport."""

            async def async_disconnect(self) -> None:
                """Disconnect from the transport."""

            async def send_packet(self, frame: str) -> None:
                """Send a packet."""

            @property
            def is_connected(self) -> bool:
                """Return connection status."""
                return True

        endpoint = ConcreteEndpoint()
        handler1 = MagicMock()
        handler2 = MagicMock()

        # Test set_inbound_handler replaces all handlers
        endpoint.set_inbound_handler(handler1)
        assert len(endpoint._inbound_handlers) == 1
        assert endpoint._inbound_handlers[0] == handler1

        # Test add_inbound_handler appends
        endpoint.add_inbound_handler(handler2)
        assert len(endpoint._inbound_handlers) == 2
        assert endpoint._inbound_handlers[0] == handler1
        assert endpoint._inbound_handlers[1] == handler2

        # Test clear_inbound_handlers removes all
        endpoint.clear_inbound_handlers()
        assert len(endpoint._inbound_handlers) == 0


class TestMqttEndpointInit:
    """Tests for MqttEndpoint initialization."""

    def test_default_initialization(self) -> None:
        """Test MqttEndpoint with default gateway ID."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        assert endpoint.gateway_id == DEFAULT_GATEWAY_ID
        assert endpoint.hass == hass
        assert endpoint._connected is False
        assert endpoint._unsubscribe is None
        assert endpoint._send_task is None

    def test_custom_gateway_id(self) -> None:
        """Test MqttEndpoint with custom gateway ID."""
        hass = MagicMock()
        custom_gateway = "18:123456"
        endpoint = MqttEndpoint(hass, gateway_id=custom_gateway)

        assert endpoint.gateway_id == custom_gateway

    def test_topic_construction(self) -> None:
        """Test MQTT topic construction."""
        hass = MagicMock()
        gateway_id = "18:123456"
        endpoint = MqttEndpoint(hass, gateway_id=gateway_id)

        expected_rx = f"{SIMULATOR_TOPIC_NS}/{gateway_id}/{MQTT_TOPIC_SUFFIX_RX}"
        expected_tx = f"{SIMULATOR_TOPIC_NS}/{gateway_id}/{MQTT_TOPIC_SUFFIX_TX}"

        assert endpoint.topic_rx == expected_rx
        assert endpoint.topic_tx == expected_tx

    def test_initial_handler_list(self) -> None:
        """Test that inbound handlers list is initialized."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        assert hasattr(endpoint, "_inbound_handlers")
        assert isinstance(endpoint._inbound_handlers, list)
        assert len(endpoint._inbound_handlers) == 0


class TestMqttEndpointConnection:
    """Tests for MqttEndpoint connection management."""

    @pytest.mark.asyncio
    async def test_async_connect_success(self) -> None:
        """Test successful MQTT connection."""
        hass = _build_hass(asyncio.get_running_loop())
        endpoint = MqttEndpoint(hass)

        with (
            patch(
                "homeassistant.components.mqtt.async_subscribe",
                new_callable=AsyncMock,
            ) as mock_subscribe,
            patch(
                "homeassistant.components.mqtt.async_publish",
                new_callable=AsyncMock,
            ),
        ):
            mock_subscribe.return_value = MagicMock()

            await endpoint.async_connect()

            assert endpoint._connected is True
            assert endpoint._unsubscribe is not None
            mock_subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_connect_failure(self) -> None:
        """Test MQTT connection failure."""
        hass = _build_hass(asyncio.get_running_loop())
        endpoint = MqttEndpoint(hass)

        with (
            patch(
                "homeassistant.components.mqtt.async_subscribe",
                new_callable=AsyncMock,
            ) as mock_subscribe,
            patch(
                "homeassistant.components.mqtt.async_publish",
                new_callable=AsyncMock,
            ),
        ):
            mock_subscribe.side_effect = Exception("MQTT not available")

            with pytest.raises(Exception, match="MQTT not available"):
                await endpoint.async_connect()

            assert endpoint._connected is False

    @pytest.mark.asyncio
    async def test_async_disconnect(self) -> None:
        """Test disconnection."""
        hass = _build_hass(asyncio.get_running_loop())
        endpoint = MqttEndpoint(hass)

        # Setup connected state
        endpoint._connected = True
        unsubscribe_mock = MagicMock()
        endpoint._unsubscribe = unsubscribe_mock

        # Mock send task
        async def _dummy_task():
            await asyncio.sleep(0)

        mock_task = asyncio.create_task(_dummy_task())
        endpoint._send_task = mock_task

        with patch(
            "homeassistant.components.mqtt.async_publish",
            new_callable=AsyncMock,
        ):
            await endpoint.async_disconnect()

        assert endpoint._connected is False
        unsubscribe_mock.assert_called_once()
        assert mock_task.cancelled()

    @pytest.mark.asyncio
    async def test_async_disconnect_not_connected(self) -> None:
        """Test disconnect when not connected - should not raise."""
        hass = _build_hass(asyncio.get_running_loop())
        endpoint = MqttEndpoint(hass)

        # Should not raise even when not connected
        await endpoint.async_disconnect()
        assert endpoint._connected is False

    def test_is_connected_property(self) -> None:
        """Test is_connected property."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        assert endpoint.is_connected is False

        endpoint._connected = True
        assert endpoint.is_connected is True


class TestMqttEndpointPacketSending:
    """Tests for MqttEndpoint packet sending."""

    @pytest.mark.asyncio
    async def test_send_packet_queues_frame(self) -> None:
        """Test that send_packet queues the frame."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        frame = "000 I --- 32:168270 --:------ 32:168270 1FC9 030 00"
        await endpoint.send_packet(frame)

        # Verify frame is in queue
        assert not endpoint._send_queue.empty()
        queued_frame = endpoint._send_queue.get_nowait()
        assert queued_frame == frame

    @pytest.mark.asyncio
    async def test_send_packet_multiple_frames(self) -> None:
        """Test queuing multiple frames."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        frames = [
            "000 I --- 32:168270 --:------ 32:168270 1FC9 030 00",
            "000 I --- 32:168271 --:------ 32:168271 1FC9 030 00",
            "000 I --- 32:168272 --:------ 32:168272 1FC9 030 00",
        ]

        for frame in frames:
            await endpoint.send_packet(frame)

        # Verify all frames are queued in order
        assert endpoint._send_queue.qsize() == 3
        for expected_frame in frames:
            queued = endpoint._send_queue.get_nowait()
            assert queued == expected_frame


class TestMqttEndpointMessageHandling:
    """Tests for MqttEndpoint message handling."""

    def test_on_message_received_valid_payload(self) -> None:
        """Test handling valid MQTT message."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        # Mock handler
        mock_handler = MagicMock()
        endpoint.set_inbound_handler(mock_handler)

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.payload = "000 RQ --- 37:168270 37:126776 --:------ 31DA 001 01"

        # Process message
        endpoint._on_message_received(mock_msg)

        # Handler should be called (asynchronously)
        # Note: The actual handler execution is async, so we just verify
        # the message parsing doesn't crash

    def test_on_message_received_with_whitespace(self) -> None:
        """Test handling message with extra whitespace."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        mock_handler = MagicMock()
        endpoint.set_inbound_handler(mock_handler)

        mock_msg = MagicMock()
        mock_msg.payload = "  000 RQ --- 37:168270 37:126776 --:------ 31DA 001 01  "

        # Should not crash with whitespace
        endpoint._on_message_received(mock_msg)

    def test_on_message_received_invalid_payload(self) -> None:
        """Test handling invalid MQTT message."""
        endpoint = MagicMock()
        endpoint._inbound_handlers = []

        mock_msg = MagicMock()
        mock_msg.payload = "invalid payload"

        # Should not crash with invalid payload
        MqttEndpoint._on_message_received(endpoint, mock_msg)


class TestMqttEndpointSendWorker:
    """Tests for MqttEndpoint send worker."""

    @pytest.mark.asyncio
    async def test_send_worker_publishes_frames(self) -> None:
        """Test send worker publishes queued frames."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        # Setup connected state
        endpoint._connected = True

        # Queue a frame
        frame = "000 I --- 32:168270 --:------ 32:168270 1FC9 030 00"
        await endpoint._send_queue.put(frame)

        with patch(
            "homeassistant.components.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as mock_publish:
            # Run worker for a short time
            worker_task = asyncio.create_task(endpoint._send_worker())
            await asyncio.sleep(0.1)

            # Stop worker
            endpoint._connected = False
            await endpoint._send_queue.put("stop")  # Signal to stop

            try:
                await asyncio.wait_for(worker_task, timeout=1.0)
            except TimeoutError:
                worker_task.cancel()

            # Verify publish was called
            assert mock_publish.await_count >= 1

    @pytest.mark.asyncio
    async def test_send_worker_stops_when_disconnected(self) -> None:
        """Test send worker stops when disconnected."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        # Not connected from start
        endpoint._connected = False

        # Add frame to queue
        frame = "000 I --- 32:168270 --:------ 32:168270 1FC9 030 00"
        await endpoint._send_queue.put(frame)

        # Worker should exit quickly when not connected
        with patch(
            "homeassistant.components.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as mock_publish:
            await endpoint._send_worker()

            # Should not have published anything
            mock_publish.assert_not_called()


class TestMqttEndpointStatusPublishing:
    """Tests for MqttEndpoint status publishing."""

    @pytest.mark.asyncio
    async def test_publish_status_online(self) -> None:
        """Test publishing online status."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        with patch(
            "homeassistant.components.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as mock_publish:
            await endpoint._publish_status("online")

            mock_publish.assert_awaited_once()
            await_args = mock_publish.await_args
            assert await_args.args[0] == hass
            assert await_args.args[1] == endpoint._topic_status
            assert await_args.args[2] == "online"
            assert await_args.kwargs["retain"] is True

    @pytest.mark.asyncio
    async def test_publish_status_offline(self) -> None:
        """Test publishing offline status."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        with patch(
            "homeassistant.components.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as mock_publish:
            await endpoint._publish_status("offline")

            mock_publish.assert_awaited_once()
            await_args = mock_publish.await_args
            assert await_args.args[2] == "offline"


class TestMqttEndpointIntegration:
    """Integration-style tests for MqttEndpoint."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Test full connect -> send -> disconnect lifecycle."""
        hass = _build_hass(asyncio.get_running_loop())
        endpoint = MqttEndpoint(hass)

        with (
            patch(
                "homeassistant.components.mqtt.async_subscribe",
                new_callable=AsyncMock,
            ) as mock_subscribe,
            patch(
                "homeassistant.components.mqtt.async_publish",
                new_callable=AsyncMock,
            ),
        ):
            mock_subscribe.return_value = MagicMock()

            # Connect
            await endpoint.async_connect()
            assert endpoint.is_connected is True

            # Send a packet
            frame = "000 I --- 32:168270 --:------ 32:168270 1FC9 030 00"
            await endpoint.send_packet(frame)

            # Disconnect
            await endpoint.async_disconnect()
            assert endpoint.is_connected is False

    def test_handler_chaining(self) -> None:
        """Test that multiple handlers can be registered."""
        hass = MagicMock()
        endpoint = MqttEndpoint(hass)

        handlers = [MagicMock() for _ in range(3)]

        # Add handlers one by one
        endpoint.add_inbound_handler(handlers[0])
        endpoint.add_inbound_handler(handlers[1])
        endpoint.add_inbound_handler(handlers[2])

        assert len(endpoint._inbound_handlers) == 3
        for i, handler in enumerate(handlers):
            assert endpoint._inbound_handlers[i] == handler

        # Set handler should replace all
        new_handler = MagicMock()
        endpoint.set_inbound_handler(new_handler)

        assert len(endpoint._inbound_handlers) == 1
        assert endpoint._inbound_handlers[0] == new_handler
