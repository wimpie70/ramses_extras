"""Ramses RF Command Definitions and Execution.

This module provides command definitions for Ramses RF devices with centralized
command management, queuing, and rate limiting. Commands are feature-owned and
organized by device type for easy access and extension.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .commands.registry import get_command_registry

_LOGGER = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    error_message: str = ""
    response_data: dict[str, Any] | None = None
    queued: bool = False
    execution_time: float = 0.0


class DeviceCommandManager:
    """Manages command queuing and execution per device to prevent
    overwhelming the communication layer."""

    def __init__(self, ramses_commands: "RamsesCommands"):
        # Reference to RamsesCommands for actual command execution
        self._ramses_commands = ramses_commands
        # Per-device queues: {device_id: asyncio.Queue}
        self._queues: dict[str, asyncio.Queue] = {}
        # Background processors: {device_id: asyncio.Task}
        self._processors: dict[str, asyncio.Task] = {}
        # Rate limiting: last command time per device
        self._last_command_time: dict[str, float] = {}
        # Minimum interval between commands (seconds)
        self._min_interval = 1.0

    def _get_device_queue(self, device_id: str) -> asyncio.Queue:
        """Get or create queue for a device."""
        if device_id not in self._queues:
            self._queues[device_id] = asyncio.Queue()
        return self._queues[device_id]

    async def send_command_to_device(
        self,
        device_id: str,
        command_def: dict[str, Any],
        priority: str = "normal",
        timeout: float = 30.0,
    ) -> CommandResult:
        """Send command to device with queuing and rate limiting.

        Args:
            device_id: Target device identifier
            command_def: Command definition with code, verb, payload
            priority: Command priority ("high", "normal", "low")
            timeout: Command timeout in seconds

        Returns:
            CommandResult with execution status
        """
        # Rate limiting check
        current_time = time.time()
        last_time = self._last_command_time.get(device_id, 0)
        if current_time - last_time < self._min_interval:
            # Queue the command for later execution
            queue = self._get_device_queue(device_id)
            await queue.put(
                {
                    "command_def": command_def,
                    "priority": priority,
                    "timeout": timeout,
                    "queued_time": current_time,
                }
            )

            # Start background processor if needed
            if device_id not in self._processors:
                self._processors[device_id] = asyncio.create_task(
                    self._process_device_queue(device_id)
                )

            return CommandResult(success=True, queued=True)

        # Execute immediately
        return await self._execute_command(device_id, command_def, timeout)

    async def _process_device_queue(self, device_id: str) -> None:
        """Background processor for queued commands."""
        queue = self._queues[device_id]

        while True:
            try:
                # Wait for next command with timeout
                command_data = await asyncio.wait_for(queue.get(), timeout=0.5)

                # Execute the command
                result = await self._execute_command(
                    device_id, command_data["command_def"], command_data["timeout"]
                )

                # Log result
                if not result.success:
                    _LOGGER.warning(
                        f"Queued command failed for device {device_id}: "
                        f"{result.error_message}"
                    )

            except TimeoutError:
                # No commands pending, exit processor
                break
            except Exception as e:
                _LOGGER.error(f"Queue processing error for device {device_id}: {e}")
                continue

        # Clean up processor
        if device_id in self._processors:
            del self._processors[device_id]

    async def _execute_command(
        self, device_id: str, command_def: dict[str, Any], timeout: float
    ) -> CommandResult:
        """Execute a command directly (internal method)."""
        start_time = time.time()

        try:
            # Update rate limiting
            self._last_command_time[device_id] = start_time

            # Execute command using the RamsesCommands instance
            success = await self._ramses_commands._send_packet(device_id, command_def)
            execution_time = time.time() - start_time

            return CommandResult(success=success, execution_time=execution_time)

        except Exception as e:
            execution_time = time.time() - start_time
            return CommandResult(
                success=False, error_message=str(e), execution_time=execution_time
            )


class RamsesCommands:
    """Ramses RF command manager for sending device commands with
    queuing and registry integration."""

    def __init__(self, hass: Any) -> None:
        """Initialize Ramses commands manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._command_registry = get_command_registry()
        self._device_manager = DeviceCommandManager(self)

    async def send_fan_command(self, device_id: str, command: str) -> CommandResult:
        """Send a fan command to a Ramses RF device.

        Args:
            device_id: Device identifier (e.g., "32_153289")
            command: Command name from HvacVentilator standard commands
                    Use prefixed names like "fan_high", "fan_low", "fan_auto", etc.

        Returns:
            CommandResult with execution status and error details
        """
        # Get command from registry (HvacVentilator standard commands)
        cmd_def = self._command_registry.get_command(command)
        if not cmd_def:
            error_msg = f"Fan command '{command}' not found in registry"
            _LOGGER.error(error_msg)
            return CommandResult(success=False, error_message=error_msg)

        # Send the packet
        success = await self._send_packet(device_id, cmd_def)
        if success:
            return CommandResult(success=True)
        error_msg = f"Failed to send fan command '{command}' to device {device_id}"
        return CommandResult(success=False, error_message=error_msg)

    async def send_command(
        self,
        device_id: str,
        command_name: str,
        queue: bool = True,
        priority: str = "normal",
        timeout: float = 30.0,
    ) -> CommandResult:
        """Send a command to a device using the command registry.

        Args:
            device_id: Target device identifier
            command_name: Name of registered command
            queue: Whether to queue command if rate limited
            priority: Command priority ("high", "normal", "low")
            timeout: Command timeout in seconds

        Returns:
            CommandResult with execution status
        """
        # Get command definition from registry
        cmd_def = self._command_registry.get_command(command_name)
        _LOGGER.debug(f"Send Command - Command definition: {cmd_def}")
        if not cmd_def:
            return CommandResult(
                success=False,
                error_message=f"Command '{command_name}' not found in registry",
            )

        # Send command with queuing
        return await self._device_manager.send_command_to_device(
            device_id, cmd_def, priority, timeout
        )

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
        """Get all available commands from the registry.

        Returns:
            Dictionary of command definitions with metadata
        """
        return self._command_registry.get_registered_commands()

    def get_command_description(self, command: str) -> str:
        """Get description for a command.

        Args:
            command: Command name

        Returns:
            Command description or empty string if not found
        """
        cmd_def = self._command_registry.get_command(command)
        return str(cmd_def.get("description", "")) if cmd_def else ""


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
    "RamsesCommands",
    "create_ramses_commands",
    "CommandResult",
    "DeviceCommandManager",
]
