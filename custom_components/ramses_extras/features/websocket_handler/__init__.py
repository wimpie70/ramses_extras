"""WebSocket Handler Feature.

This module provides WebSocket communication infrastructure for all features,
including message handling, protocol management, and real-time updates.
"""

from typing import Any, Dict

from .handler import WebSocketHandler
from .protocols import WebSocketProtocols

__all__ = [
    "WebSocketHandler",
    "WebSocketProtocols",
]


def create_websocket_handler_feature(hass: Any, config_entry: Any) -> dict[str, Any]:
    """Factory function to create WebSocket handler feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        WebSocket handler feature instance
    """
    return {
        "handler": WebSocketHandler(hass, config_entry),
        "protocols": WebSocketProtocols(hass, config_entry),
    }
