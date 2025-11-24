"""WebSocket Base Classes and Utilities.

This module provides minimal WebSocket infrastructure for Ramses Extras features.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


class BaseWebSocketCommand:
    """Base class for WebSocket commands in Ramses Extras features.

    This provides a minimal foundation for WebSocket commands while maintaining
    feature-centric organization and integration with existing systems.
    """

    def __init__(self, hass: Any, feature_name: str) -> None:
        """Initialize base WebSocket command handler.

        Args:
            hass: Home Assistant instance
            feature_name: Name of the feature this command belongs to
        """
        self.hass = hass
        self.feature_name = feature_name
        self._logger = logging.getLogger(f"{__name__}.{feature_name}")

    async def execute(self, connection: "WebSocket", msg: dict[str, Any]) -> None:
        """Execute the WebSocket command.

        Args:
            connection: WebSocket connection
            msg: WebSocket message data
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def _send_success(self, connection: "WebSocket", msg_id: Any, result: Any) -> None:
        """Send successful response.

        Args:
            connection: WebSocket connection
            msg_id: Message ID for correlation
            result: Result data to send
        """
        connection.send_result(msg_id, result)

    def _send_error(
        self, connection: "WebSocket", msg_id: Any, error_code: str, error_message: str
    ) -> None:
        """Send error response.

        Args:
            connection: WebSocket connection
            msg_id: Message ID for correlation
            error_code: Error code
            error_message: Error message
        """
        connection.send_error(msg_id, error_code, error_message)

    def _log_command(self, command: str, device_id: str | None = None) -> None:
        """Log command execution.

        Args:
            command: Command name
            device_id: Device ID if applicable
        """
        if device_id:
            self._logger.debug(f"Executing {command} for device {device_id}")
        else:
            self._logger.debug(f"Executing {command}")

    def _log_error(
        self, command: str, error: Exception, device_id: str | None = None
    ) -> None:
        """Log command error.

        Args:
            command: Command name
            error: Exception that occurred
            device_id: Device ID if applicable
        """
        if device_id:
            self._logger.error(
                f"Error executing {command} for device {device_id}: {error}"
            )
        else:
            self._logger.error(f"Error executing {command}: {error}")


class DeviceWebSocketCommand(BaseWebSocketCommand):
    """Base class for device-related WebSocket commands.

    Provides device-specific functionality and integration with ramses_cc.
    """

    def __init__(self, hass: Any, feature_name: str) -> None:
        """Initialize device WebSocket command handler.

        Args:
            hass: Home Assistant instance
            feature_name: Name of the feature this command belongs to
        """
        super().__init__(hass, feature_name)
        self._ramses_data = hass.data.get("ramses_cc", {})

    def _get_device_from_broker(self, device_id: str) -> Any | None:
        """Get device object from ramses_cc broker.

        Args:
            device_id: Device ID to find

        Returns:
            Device object or None if not found
        """
        for _entry_id, data in self._ramses_data.items():
            # Handle both direct broker storage and dict storage
            if hasattr(data, "__class__") and "Broker" in data.__class__.__name__:
                broker = data
            elif isinstance(data, dict) and "broker" in data:
                broker = data["broker"]
            else:
                continue
            if not broker:
                continue

            # Each broker has devices as a list (_devices)
            devices = getattr(broker, "_devices", None)
            if devices is None:
                devices = getattr(broker, "devices", [])
            if not devices:
                continue

            # Find device by ID
            for device in devices:
                device_id_attr = getattr(device, "id", str(device))
                if device_id_attr == device_id:
                    return device

        return None

    def _get_bound_rem_for_device(self, device_id: str) -> str | None:
        """Get bound REM device ID for a device.

        Args:
            device_id: Device ID to get bound REM for

        Returns:
            Bound REM device ID or None if not found
        """
        device = self._get_device_from_broker(device_id)
        if device and hasattr(device, "get_bound_rem"):
            bound = device.get_bound_rem()
            return bound.id if bound else None
        return None


# WebSocket command registry for feature-centric organization
WEBSOCKET_COMMANDS: dict[str, dict[str, Callable]] = {}


def register_websocket_command(
    feature_name: str, command_name: str, handler_class: type[BaseWebSocketCommand]
) -> None:
    """Register a WebSocket command for a feature.

    Args:
        feature_name: Name of the feature
        command_name: Name of the command
        handler_class: Handler class for the command
    """
    if feature_name not in WEBSOCKET_COMMANDS:
        WEBSOCKET_COMMANDS[feature_name] = {}
    WEBSOCKET_COMMANDS[feature_name][command_name] = handler_class
    _LOGGER.debug(
        f"Registered WebSocket command {command_name} for feature {feature_name}"
    )


def get_websocket_commands_for_feature(feature_name: str) -> dict[str, Callable]:
    """Get all WebSocket commands for a feature.

    Args:
        feature_name: Name of the feature

    Returns:
        Dictionary of command name to handler class mappings
    """
    return WEBSOCKET_COMMANDS.get(feature_name, {})


def get_all_websocket_commands() -> dict[str, dict[str, Callable]]:
    """Get all registered WebSocket commands.

    Returns:
        Dictionary of feature name to command mappings
    """
    return WEBSOCKET_COMMANDS.copy()


def discover_websocket_commands() -> list[str]:
    """Discover all features that have WebSocket commands registered.

    Returns:
        List of feature names with WebSocket commands
    """
    return list(WEBSOCKET_COMMANDS.keys())
