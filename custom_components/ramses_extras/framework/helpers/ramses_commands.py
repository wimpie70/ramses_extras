"""Ramses RF Command Definitions.

This module provides command definitions for Ramses RF devices,
particularly ventilation/HVAC systems. Commands are organized by device type
and functionality for easy access and extension.
"""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


# Fan command definitions for ventilation systems
# Supports Orcon and other compatible systems
FAN_COMMANDS = {
    # Basic fan speed commands
    "request10D0": {
        "code": "10D0",
        "verb": "RQ",
        "payload": "00",  # Request 10D0
        "description": "Request system status",
    },
    # Fan mode commands
    "away": {
        "code": "22F1",
        "verb": " I",
        "payload": "000007",  # Away mode
        "description": "Set fan to away mode",
    },
    "low": {
        "code": "22F1",
        "verb": " I",
        "payload": "000107",  # Low speed
        "description": "Set fan to low speed",
    },
    "medium": {
        "code": "22F1",
        "verb": " I",
        "payload": "000207",  # Medium speed
        "description": "Set fan to medium speed",
    },
    "high": {
        "code": "22F1",
        "verb": " I",
        "payload": "000307",  # High speed
        "description": "Set fan to high speed",
    },
    "auto": {
        "code": "22F1",
        "verb": " I",
        "payload": "000407",  # Auto mode
        "description": "Set fan to auto mode",
    },
    "auto2": {
        "code": "22F1",
        "verb": " I",
        "payload": "000507",  # Auto2 mode
        "description": "Set fan to auto2 mode",
    },
    "boost": {
        "code": "22F1",
        "verb": " I",
        "payload": "000607",  # Boost mode
        "description": "Set fan to boost mode",
    },
    "disable": {
        "code": "22F1",
        "verb": " I",
        "payload": "000707",  # Disable mode
        "description": "Disable fan",
    },
    "active": {
        "code": "22F1",
        "verb": " I",
        "payload": "000807",  # Active mode
        "description": "Set fan to active mode",
    },
    # Maintenance commands
    "filter_reset": {
        "code": "10D0",
        "verb": " W",
        "payload": "00FF",  # Filter reset
        "description": "Reset filter timer",
    },
    # Timer commands
    "high_15": {
        "code": "22F3",
        "verb": " I",
        "payload": "00120F03040404",  # 15 minutes timer
        "description": "Set 15 minute timer",
    },
    "high_30": {
        "code": "22F3",
        "verb": " I",
        "payload": "00121E03040404",  # 30 minutes timer
        "description": "Set 30 minute timer",
    },
    "high_60": {
        "code": "22F3",
        "verb": " I",
        "payload": "00123C03040404",  # 60 minutes timer
        "description": "Set 60 minute timer",
    },
    # Bypass commands
    "bypass_close": {
        "code": "22F7",
        "verb": " W",
        "payload": "0000EF",  # Bypass close
        "description": "Close bypass",
    },
    "bypass_open": {
        "code": "22F7",
        "verb": " W",
        "payload": "00C8EF",  # Bypass open
        "description": "Open bypass",
    },
    "bypass_auto": {
        "code": "22F7",
        "verb": " W",
        "payload": "00FFEF",  # Bypass auto
        "description": "Set bypass to auto mode",
    },
    # Status request commands
    "request31DA": {
        "code": "31DA",
        "verb": "RQ",
        "payload": "00",
        "description": "Request 31DA status",
    },
}


class RamsesCommands:
    """Ramses RF command manager for sending device commands."""

    def __init__(self, hass: Any) -> None:
        """Initialize Ramses commands manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass

    async def send_fan_command(self, device_id: str, command: str) -> bool:
        """Send a fan command to a Ramses RF device.

        Args:
            device_id: Device identifier (e.g., "32_153289")
            command: Command name from FAN_COMMANDS

        Returns:
            True if command sent successfully
        """
        if command not in FAN_COMMANDS:
            _LOGGER.error(f"Unknown fan command: {command}")
            return False

        cmd_def = FAN_COMMANDS[command]
        return await self._send_packet(device_id, cmd_def)

    async def _send_packet(self, device_id: str, cmd_def: dict[str, str]) -> bool:
        """Send a packet using the ramses_cc send_packet service.

        Args:
            device_id: Target device ID
            cmd_def: Command definition with code, verb, payload

        Returns:
            True if packet sent successfully
        """
        try:
            # Convert device_id format if needed (32_153289 -> 32:153289)
            device_id_formatted = device_id.replace("_", ":")

            _LOGGER.info(
                f"Sending Ramses command to {device_id}: {cmd_def['code']} "
                f"{cmd_def['description']}"
            )

            # Prepare service call data
            service_data = {
                "device_id": device_id_formatted,
                "verb": cmd_def["verb"],
                "code": cmd_def["code"],
                "payload": cmd_def["payload"],
            }

            # Try to get the bound REM device as from_id (source address)
            # This is required for FAN devices to respond to commands
            from_id = await self._get_bound_rem_device(device_id_formatted)
            if from_id:
                service_data["from_id"] = from_id
                _LOGGER.debug(
                    f"Using bound REM device {from_id} as source for command to "
                    f"{device_id}"
                )
            else:
                _LOGGER.debug(
                    f"No bound REM device found for {device_id}, using default source"
                )

            # Call the ramses_cc send_packet service with parameters
            await self.hass.services.async_call(
                "ramses_cc", "send_packet", service_data
            )

            _LOGGER.debug(f"Ramses command sent: {cmd_def['description']}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to send Ramses command {cmd_def['code']}: {e}")
            return False

    async def _get_bound_rem_device(self, device_id: str) -> str | None:
        """Get the bound REM device ID for a FAN device.

        Args:
            device_id: Device identifier (e.g., "32:153289")

        Returns:
            Bound REM device ID or None if not found
        """
        try:
            # Access the ramses_cc broker to get device information
            # This follows the same pattern as used in ramses_cc broker
            broker = None
            ramses_cc_data = self.hass.data.get("ramses_cc", {})

            # Find the broker instance (there should be one per config entry)
            for entry_id, broker_instance in ramses_cc_data.items():
                if hasattr(broker_instance, "_get_device"):
                    broker = broker_instance
                    break

            if broker and hasattr(broker, "_get_device"):
                device = broker._get_device(device_id)
                if device and hasattr(device, "get_bound_rem"):
                    bound_rem = device.get_bound_rem()
                    if bound_rem:
                        return str(bound_rem)

        except Exception as e:
            _LOGGER.debug(f"Could not get bound REM device for {device_id}: {e}")

        return None

    def get_available_commands(self) -> dict[str, dict[str, str]]:
        """Get all available fan commands.

        Returns:
            Dictionary of command definitions
        """
        return FAN_COMMANDS.copy()

    def get_command_description(self, command: str) -> str:
        """Get description for a command.

        Args:
            command: Command name

        Returns:
            Command description or empty string if not found
        """
        return FAN_COMMANDS.get(command, {}).get("description", "")


# Global instance for easy access
def create_ramses_commands(hass: Any) -> RamsesCommands:
    """Create Ramses commands instance.

    Args:
        hass: Home Assistant instance

    Returns:
        RamsesCommands instance
    """
    return RamsesCommands(hass)


__all__ = [
    "FAN_COMMANDS",
    "RamsesCommands",
    "create_ramses_commands",
]
