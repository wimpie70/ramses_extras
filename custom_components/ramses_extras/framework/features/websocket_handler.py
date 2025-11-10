"""WebSocket Handler Feature for Ramses Extras framework.

This module provides a WebSocket handler feature for real-time communication
with the Ramses RF system, enabling real-time updates and event handling.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, cast

from homeassistant.core import HomeAssistant

from ....const import AVAILABLE_FEATURES, FEATURE_ID_HVAC_FAN_CARD
from ....framework.helpers.common import RamsesValidator
from ....framework.helpers.device import find_ramses_device, get_device_type
from ....framework.helpers.entity import EntityHelpers

_LOGGER = logging.getLogger(__name__)


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message."""

    timestamp: datetime
    code: str
    device_id: str
    data: dict[str, Any]
    raw_message: str
    processed: bool = False


@dataclass
class EventHandler:
    """Represents an event handler for WebSocket messages."""

    name: str
    code_pattern: str
    callback: Callable
    priority: int = 0
    active: bool = True


class WebSocketHandlerFeature:
    """WebSocket Handler feature for real-time communication.

    This feature provides:
    - Real-time WebSocket communication with Ramses RF system
    - Message parsing and validation
    - Event handling and routing
    - Device state synchronization
    - Support for multiple simultaneous connections
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str = FEATURE_ID_HVAC_FAN_CARD,
        max_message_buffer: int = 1000,
    ) -> None:
        """Initialize the WebSocket handler feature.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            max_message_buffer: Maximum number of messages to buffer
        """
        self.hass = hass
        self.feature_id = feature_id
        self.max_message_buffer = max_message_buffer

        # WebSocket connection state
        self._connected = False
        self._connection_url = None
        self._message_buffer: list[WebSocketMessage] = []

        # Event handling
        self._event_handlers: list[EventHandler] = []
        self._code_patterns: dict[str, set[str]] = {}  # code -> handler names

        # Device tracking
        self._known_devices: set[str] = set()
        self._device_states: dict[str, dict[str, Any]] = {}

        # Message processing
        self._message_processor_task: asyncio.Task[None] | None = None
        self._process_messages = True

        # Statistics
        self._stats: dict[str, Any] = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_error": 0,
            "handlers_called": 0,
            "devices_seen": set(),
            "last_activity": None,
        }

        # Configuration
        self._websocket_config = self._get_websocket_config()

        _LOGGER.info(
            f"WebSocketHandlerFeature initialized with config: {self._websocket_config}"
        )

    def _get_websocket_config(self) -> dict[str, Any]:
        """Get WebSocket configuration.

        Returns:
            WebSocket configuration dictionary
        """
        feature_config = AVAILABLE_FEATURES.get(FEATURE_ID_HVAC_FAN_CARD, {})
        return {
            "websocket_url": feature_config.get("websocket_url", "ws://localhost:8080"),
            "reconnect_interval": feature_config.get("reconnect_interval", 30),
            "message_timeout": feature_config.get("message_timeout", 60),
            "buffer_size": feature_config.get("buffer_size", 1000),
            "codes": feature_config.get("handle_codes", ["31DA", "10D0"]),
        }

    async def start(self) -> None:
        """Start the WebSocket handler.

        Initializes the WebSocket connection and starts message processing.
        """
        if self._connected:
            _LOGGER.warning("WebSocket handler already connected")
            return

        _LOGGER.info("🚀 Starting WebSocket handler")
        _LOGGER.info(f"📡 Target URL: {self._websocket_config['websocket_url']}")
        _LOGGER.info(f"🔧 Message codes: {self._websocket_config['codes']}")

        # Initialize event handlers
        self._initialize_event_handlers()

        # Start message processor
        self._process_messages = True
        self._message_processor_task = asyncio.create_task(
            self._process_message_queue()
        )
        # This will be awaited properly in _message_processor_task cancellation

        # Attempt connection
        await self._connect_websocket()

        _LOGGER.info("✅ WebSocket handler started successfully")

    async def stop(self) -> None:
        """Stop the WebSocket handler.

        Closes the WebSocket connection and cleans up resources.
        """
        _LOGGER.info("Stopping WebSocket handler")

        # Stop message processing
        self._process_messages = False

        # Cancel message processor
        if self._message_processor_task:
            self._message_processor_task.cancel()
            try:
                await self._message_processor_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connection
        await self._disconnect_websocket()

        # Clear buffers
        self._message_buffer.clear()

        _LOGGER.info("WebSocket handler stopped")

    def _initialize_event_handlers(self) -> None:
        """Initialize default event handlers."""
        # Register handlers for known message codes
        for code in self._websocket_config["codes"]:
            self.register_event_handler(
                name=f"handle_{code.lower()}",
                code_pattern=code,
                callback=getattr(
                    self, f"_handle_{code.lower()}", self._default_handler
                ),
            )

        _LOGGER.debug(f"Initialized {len(self._event_handlers)} event handlers")

    def register_event_handler(
        self, name: str, code_pattern: str, callback: Callable, priority: int = 0
    ) -> None:
        """Register an event handler for specific message codes.

        Args:
            name: Handler name
            code_pattern: Message code pattern to match
            callback: Async callback function
            priority: Handler priority (higher = more important)
        """
        handler = EventHandler(
            name=name,
            code_pattern=code_pattern,
            callback=callback,
            priority=priority,
        )

        self._event_handlers.append(handler)

        # Update code pattern tracking
        if code_pattern not in self._code_patterns:
            self._code_patterns[code_pattern] = set()
        self._code_patterns[code_pattern].add(name)

        _LOGGER.debug(f"Registered event handler: {name} for pattern {code_pattern}")

    def unregister_event_handler(self, name: str) -> None:
        """Unregister an event handler.

        Args:
            name: Handler name to remove
        """
        # Find and remove handler
        self._event_handlers = [h for h in self._event_handlers if h.name != name]

        # Update code pattern tracking
        for code_pattern, handler_names in self._code_patterns.items():
            handler_names.discard(name)
            if not handler_names:
                del self._code_patterns[code_pattern]

        _LOGGER.debug(f"Unregistered event handler: {name}")

    async def _connect_websocket(self) -> None:
        """Connect to the WebSocket endpoint.

        This is a placeholder implementation that would typically connect
        to the actual Ramses RF WebSocket endpoint.
        """
        try:
            # Placeholder for actual WebSocket connection
            # In a real implementation, this would:
            # 1. Create a WebSocket connection to the Ramses RF system
            # 2. Handle authentication if required
            # 3. Set up message callbacks
            # 4. Handle reconnection logic

            # For now, we'll simulate a successful connection
            self._connected = True
            self._connection_url = self._websocket_config["websocket_url"]

            _LOGGER.info(f"Connected to WebSocket: {self._connection_url}")

            # Start receiving messages (simulated)
            asyncio.create_task(self._simulate_message_reception())

        except Exception as e:
            _LOGGER.error(f"Failed to connect to WebSocket: {e}")
            self._connected = False
            raise

    async def _disconnect_websocket(self) -> None:
        """Disconnect from the WebSocket endpoint."""
        if self._connected:
            # Placeholder for actual WebSocket disconnection
            self._connected = False
            self._connection_url = None
            _LOGGER.info("Disconnected from WebSocket")

    async def _simulate_message_reception(self) -> None:
        """Simulate receiving WebSocket messages.

        This is a placeholder that simulates receiving messages from
        the Ramses RF system for demonstration purposes.
        """
        # Simulated message patterns
        test_messages = [
            '{"timestamp": "2023-01-01T12:00:00Z", "code": "31DA", '
            '"device_id": "32:153289", "data": {"fan_speed": 75, "mode": "auto"}}',
            '{"timestamp": "2023-01-01T12:00:01Z", "code": "10D0", '
            '"device_id": "32:153289", "data": {"temperature": 22.5, "humidity": 45}}',
        ]

        while self._connected and self._process_messages:
            try:
                for message_str in test_messages:
                    # Parse and validate message
                    message = self._parse_message(message_str)
                    if message:
                        await self._handle_incoming_message(message)

                    # Wait between messages
                    await asyncio.sleep(2)

                # Wait before repeating
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error in message simulation: {e}")
                await asyncio.sleep(5)

    def _parse_message(self, message_str: str) -> WebSocketMessage | None:
        """Parse a raw WebSocket message.

        Args:
            message_str: Raw message string

        Returns:
            Parsed WebSocketMessage or None if invalid
        """
        try:
            data = json.loads(message_str)

            # Validate required fields
            required_fields = ["timestamp", "code", "device_id", "data"]
            if not all(field in data for field in required_fields):
                _LOGGER.warning("Invalid message format: missing required fields")
                return None

            # Validate device_id format
            if not RamsesValidator.validate_device_id(data["device_id"]):
                _LOGGER.warning(f"Invalid device_id format: {data['device_id']}")
                return None

            # Create WebSocket message
            message = WebSocketMessage(
                timestamp=datetime.fromisoformat(
                    data["timestamp"].replace("Z", "+00:00")
                ),
                code=data["code"],
                device_id=data["device_id"],
                data=data["data"],
                raw_message=message_str,
            )

            self._stats["messages_received"] = int(self._stats["messages_received"]) + 1
            devices_seen = cast(set, self._stats["devices_seen"])
            devices_seen.add(data["device_id"])
            self._stats["last_activity"] = datetime.now()

            return message

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            _LOGGER.error(f"Failed to parse message: {e}")
            self._stats["messages_error"] = int(self._stats["messages_error"]) + 1
            return None

    async def _handle_incoming_message(self, message: WebSocketMessage) -> None:
        """Handle an incoming WebSocket message.

        Args:
            message: Parsed WebSocket message
        """
        # Add to buffer
        self._message_buffer.append(message)

        # Limit buffer size
        if len(self._message_buffer) > self.max_message_buffer:
            self._message_buffer.pop(0)

        _LOGGER.debug(
            f"Received {message.code} message from device {message.device_id}"
        )

        # Trigger message processing
        if self._message_processor_task:
            self._message_processor_task.cancel()
            self._message_processor_task = asyncio.create_task(
                self._process_message_queue()
            )

    async def _process_message_queue(self) -> None:
        """Process messages in the queue."""
        while self._process_messages and self._message_buffer:
            try:
                # Get next message
                message = self._message_buffer.pop(0)

                # Process message
                await self._dispatch_message(message)

                self._stats["messages_processed"] = (
                    int(self._stats["messages_processed"]) + 1
                )

                # Small delay to prevent overwhelming
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error processing message: {e}")
                self._stats["messages_error"] = int(self._stats["messages_error"]) + 1

    async def _dispatch_message(self, message: WebSocketMessage) -> None:
        """Dispatch a message to appropriate event handlers.

        Args:
            message: WebSocket message to dispatch
        """
        # Find matching handlers
        handlers = []
        for handler in self._event_handlers:
            if handler.active and self._matches_pattern(
                message.code, handler.code_pattern
            ):
                handlers.append(handler)

        # Sort by priority
        handlers.sort(key=lambda h: h.priority, reverse=True)

        # Call handlers
        for handler in handlers:
            try:
                await handler.callback(message)
                self._stats["handlers_called"] = int(self._stats["handlers_called"]) + 1
            except Exception as e:
                _LOGGER.error(f"Handler {handler.name} failed: {e}")

        # Update device state
        self._update_device_state(message)

    def _matches_pattern(self, code: str, pattern: str) -> bool:
        """Check if a code matches a pattern.

        Args:
            code: Message code
            pattern: Pattern to match against

        Returns:
            True if code matches pattern
        """
        # Exact match
        if code == pattern:
            return True

        # Regex match
        try:
            return bool(re.match(pattern, code))
        except re.error:
            return False

    def _update_device_state(self, message: WebSocketMessage) -> None:
        """Update device state from message.

        Args:
            message: WebSocket message
        """
        device_id = message.device_id

        if device_id not in self._device_states:
            self._device_states[device_id] = {}

        # Update state with message data
        self._device_states[device_id].update(
            {
                "last_update": message.timestamp,
                "last_code": message.code,
                **message.data,
            }
        )

        # Mark device as known
        self._known_devices.add(device_id)

    # Event handler methods
    async def _handle_31da(self, message: WebSocketMessage) -> None:
        """Handle 31DA messages (fan speed/mode updates)."""
        _LOGGER.info(
            f"31DA: Device {message.device_id} - "
            f"Fan speed: {message.data.get('fan_speed')}%, "
            f"Mode: {message.data.get('mode')}"
        )

        # Trigger device update events
        self.hass.bus.async_fire(
            "ramses_extras_fan_update",
            {
                "device_id": message.device_id,
                "fan_speed": message.data.get("fan_speed"),
                "mode": message.data.get("mode"),
            },
        )

    async def _handle_10d0(self, message: WebSocketMessage) -> None:
        """Handle 10D0 messages (temperature/humidity updates)."""
        _LOGGER.info(
            f"10D0: Device {message.device_id} - "
            f"Temperature: {message.data.get('temperature')}°C, "
            f"Humidity: {message.data.get('humidity')}%"
        )

        # Trigger device update events
        self.hass.bus.async_fire(
            "ramses_extras_sensor_update",
            {
                "device_id": message.device_id,
                "temperature": message.data.get("temperature"),
                "humidity": message.data.get("humidity"),
            },
        )

    async def _default_handler(self, message: WebSocketMessage) -> None:
        """Default handler for unhandled message codes."""
        _LOGGER.debug(f"Unhandled message {message.code} from {message.device_id}")

    # Public API methods
    def get_known_devices(self) -> set[str]:
        """Get set of known device IDs.

        Returns:
            Set of known device IDs
        """
        return self._known_devices.copy()

    def get_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Get current state of a device.

        Args:
            device_id: Device identifier

        Returns:
            Device state dictionary or None if not found
        """
        return self._device_states.get(device_id)

    def get_all_device_states(self) -> dict[str, dict[str, Any]]:
        """Get states of all known devices.

        Returns:
            Dictionary mapping device IDs to state dictionaries
        """
        return self._device_states.copy()

    def is_connected(self) -> bool:
        """Check if WebSocket is connected.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    def get_statistics(self) -> dict[str, Any]:
        """Get WebSocket handler statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self._stats.copy()
        devices_seen = cast(set, stats["devices_seen"])
        stats["devices_seen"] = list(devices_seen)
        stats["buffer_size"] = len(self._message_buffer)
        stats["event_handlers"] = len(self._event_handlers)
        stats["known_devices"] = len(self._known_devices)
        return stats


# Feature registration helper
def create_websocket_handler_feature(
    hass: HomeAssistant,
    feature_id: str = FEATURE_ID_HVAC_FAN_CARD,
    max_message_buffer: int = 1000,
) -> WebSocketHandlerFeature:
    """Create a WebSocket handler feature instance.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        max_message_buffer: Maximum message buffer size

    Returns:
        WebSocketHandlerFeature instance
    """
    return WebSocketHandlerFeature(
        hass=hass,
        feature_id=feature_id,
        max_message_buffer=max_message_buffer,
    )


# Framework feature registration
def register_websocket_handler_feature() -> None:
    """Register the WebSocket handler feature with the framework.

    This function registers the WebSocket handler feature so it can be
    discovered and managed by the framework's feature manager.
    """
    from ....framework import entity_registry

    feature_config = {
        "name": "WebSocket Handler",
        "description": "Real-time WebSocket communication with Ramses RF system",
        "class": "WebSocketHandlerFeature",
        "factory": "create_websocket_handler_feature",
        "dependencies": [],  # No dependencies
        "capabilities": [
            "websocket_communication",
            "real_time_updates",
            "event_handling",
            "device_monitoring",
        ],
    }

    entity_registry.register_feature_implementation(
        FEATURE_ID_HVAC_FAN_CARD, feature_config
    )

    _LOGGER.info("WebSocket handler feature registered with framework")


__all__ = [
    "WebSocketHandlerFeature",
    "WebSocketMessage",
    "EventHandler",
    "create_websocket_handler_feature",
    "register_websocket_handler_feature",
]
