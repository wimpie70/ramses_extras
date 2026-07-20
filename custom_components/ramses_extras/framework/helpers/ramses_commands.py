"""Ramses RF Command Definitions and Execution.

This module provides command definitions for Ramses RF devices with centralized
command management, queuing, and rate limiting. Commands are feature-owned and
organized by device type for easy access and extension.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from .commands.registry import get_command_registry
from .transport_monitor import get_transport_monitor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

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

    def __init__(self, ramses_commands: RamsesCommands):
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
        # Command metrics for monitoring
        self._command_stats = {
            "total_commands": 0,
            "successful_commands": 0,
            "failed_commands": 0,
            "queued_commands": 0,
            "total_execution_time": 0.0,
        }
        # Queue depth tracking: {device_id: current_depth}
        self._queue_depths: dict[str, int] = {}
        # Dedup tracking: signatures of commands currently in each device's
        # queue, so we don't pile up identical commands when the caller
        # re-fires rapidly (e.g. automation feedback loops).
        self._queued_signatures: dict[str, set[str]] = {}

    def _get_device_queue(self, device_id: str) -> asyncio.Queue:
        """Get or create queue for a device."""
        if device_id not in self._queues:
            self._queues[device_id] = asyncio.Queue()
            self._queue_depths[device_id] = 0
            self._queued_signatures[device_id] = set()
        return self._queues[device_id]

    @staticmethod
    def _command_signature(command_def: dict[str, Any]) -> str:
        """Build a hashable signature from a command definition for dedup."""
        code = command_def.get("code")
        verb = command_def.get("verb")
        payload = command_def.get("payload")
        return f"{code}|{verb}|{payload}"

    async def send_command_to_device(
        self,
        device_id: str,
        command_def: dict[str, Any],
        priority: str = "normal",
        timeout: float = 30.0,
    ) -> CommandResult:
        """Send command to device with queuing and rate limiting.

        :param device_id: Target device identifier
        :param command_def: Command definition with code, verb, payload
        :param priority: Command priority ("high", "normal", "low")
        :param timeout: Command timeout in seconds
        :return: CommandResult with execution status
        """
        # Update command statistics
        self._command_stats["total_commands"] += 1

        # Rate limiting check
        current_time = time.time()
        last_time = self._last_command_time.get(device_id, 0)
        if current_time - last_time < self._min_interval:
            # Deduplicate: if an identical command is already queued for
            # this device, skip it instead of piling up redundant sends.
            queue = self._get_device_queue(device_id)
            sig = self._command_signature(command_def)
            pending = self._queued_signatures.get(device_id, set())
            if sig in pending:
                _LOGGER.debug(
                    "Dedup: skipping queued command %s for %s (already pending)",
                    sig,
                    device_id,
                )
                return CommandResult(success=True, queued=True)

            await queue.put(
                {
                    "command_def": command_def,
                    "priority": priority,
                    "timeout": timeout,
                    "queued_time": current_time,
                    "signature": sig,
                }
            )
            pending.add(sig)
            # Update queue depth
            self._queue_depths[device_id] = queue.qsize()

            # Update statistics
            self._command_stats["queued_commands"] += 1

            # Start background processor if needed
            if device_id not in self._processors:
                self._processors[device_id] = asyncio.create_task(
                    self._process_device_queue(device_id)
                )

            return CommandResult(success=True, queued=True)

        # Execute immediately
        result = await self._execute_command(device_id, command_def, timeout)

        # Update statistics based on result
        if result.success:
            self._command_stats["successful_commands"] += 1
        else:
            self._command_stats["failed_commands"] += 1

        self._command_stats["total_execution_time"] += result.execution_time

        return result

    async def _process_device_queue(self, device_id: str) -> None:
        """Background processor for queued commands."""
        queue = self._queues[device_id]

        while True:
            try:
                # Wait for next command with timeout
                command_data = await asyncio.wait_for(queue.get(), timeout=0.5)

                # Remove from pending signatures so future dedup allows
                # the same command to be queued again after execution.
                sig = command_data.get("signature")
                if sig:
                    self._queued_signatures.get(device_id, set()).discard(sig)

                # Execute the command
                result = await self._execute_command(
                    device_id, command_data["command_def"], command_data["timeout"]
                )

                # Update queue depth
                self._queue_depths[device_id] = queue.qsize()

                # Update statistics
                if result.success:
                    self._command_stats["successful_commands"] += 1
                else:
                    self._command_stats["failed_commands"] += 1

                self._command_stats["total_execution_time"] += result.execution_time

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
                self._command_stats["failed_commands"] += 1
                continue

        # Clean up processor
        if device_id in self._processors:
            del self._processors[device_id]

        # Clean up queue depth tracking
        if device_id in self._queue_depths:
            del self._queue_depths[device_id]

        # Clean up dedup signature tracking
        self._queued_signatures.pop(device_id, None)

        # Clean up the queue itself (no more commands pending)
        self._queues.pop(device_id, None)

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

    def get_queue_statistics(self) -> dict[str, Any]:
        """Get comprehensive queue statistics for monitoring.

        :return: Dictionary containing queue statistics and metrics
        """
        total_commands = self._command_stats["total_commands"]
        success_rate = (
            (self._command_stats["successful_commands"] / total_commands * 100)
            if total_commands > 0
            else 0
        )
        avg_execution_time = (
            self._command_stats["total_execution_time"] / total_commands
            if total_commands > 0
            else 0
        )

        return {
            "command_statistics": {
                "total_commands": total_commands,
                "successful_commands": self._command_stats["successful_commands"],
                "failed_commands": self._command_stats["failed_commands"],
                "queued_commands": self._command_stats["queued_commands"],
                "success_rate_percent": round(success_rate, 2),
                "average_execution_time": round(avg_execution_time, 3),
            },
            "queue_status": {
                "active_queues": len(self._queues),
                "active_processors": len(self._processors),
                "device_queue_depths": dict(self._queue_depths),
            },
            "configuration": {
                "rate_limit_interval": self._min_interval,
                "total_devices": len(self._last_command_time),
            },
            "failed_commands": {},  # DeviceCommandManager doesn't track failed commands
        }


class RamsesCommands:
    """Ramses RF command manager for sending device commands with
    queuing and registry integration."""

    def __init__(self, hass: Any) -> None:
        """Initialize Ramses commands manager.

        :param hass: Home Assistant instance
        """
        self.hass = hass
        self._command_registry = get_command_registry()
        self._device_manager = DeviceCommandManager(self)
        # Track running update_fan_params tasks per device
        self._update_fan_params_tasks: dict[str, asyncio.Task] = {}
        # Track failed commands for monitoring and retry logic
        self._failed_commands: dict[str, dict[str, Any]] = {}

    async def send_fan_command(self, device_id: str, command: str) -> CommandResult:
        """Send a fan command to a Ramses RF device.

        :param device_id: Device identifier (e.g., "32_153289")
        :param command: Command name from HvacVentilator standard commands
                       Use prefixed names like "fan_high", "fan_low", "fan_auto", etc.
        :return: CommandResult with execution status and error details
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

    # Mapping of fan_bypass_* commands to the corresponding 2411 parameter
    # "4B" (Bypass Valve) value used by Orcon and other units that do not
    # respond to 22F7.  See ramses_rf `_2411_PARAMS_SCHEMA["4B"]`:
    #   0 = auto, 1 = open, 2 = closed.
    # We send BOTH the 22F7 packet and the 2411/4B parameter so the bypass
    # works regardless of which mechanism the FAN implements.  The 2411
    # send is best-effort: some units lack a bound REM or 2411 support, in
    # which case the 22F7 leg is still the authoritative one.
    _BYPASS_2411_PARAM_ID = "4B"
    _BYPASS_COMMAND_TO_2411_VALUE: dict[str, int] = {
        "fan_bypass_open": 1,
        "fan_bypass_close": 2,
        "fan_bypass_auto": 0,
    }

    async def send_command(
        self,
        device_id: str,
        command_name: str,
        queue: bool = True,
        priority: str = "normal",
        timeout: float = 30.0,
    ) -> CommandResult:
        """Send a command to a device using the command registry.

        :param device_id: Target device identifier
        :param command_name: Name of registered command
        :param queue: Whether to queue command if rate limited
        :param priority: Command priority ("high", "normal", "low")
        :param timeout: Command timeout in seconds
        :return: CommandResult with execution status
        """
        # Get command definition from registry
        cmd_def = self._command_registry.get_command(command_name)
        if not cmd_def:
            return CommandResult(
                success=False,
                error_message=f"Command '{command_name}' not found in registry",
            )

        # Send command with queuing
        result = await self._device_manager.send_command_to_device(
            device_id, cmd_def, priority, timeout
        )

        # For bypass commands, also send the 2411/4B parameter that some
        # Orcon/HRC units use instead of (or in addition to) 22F7.  This is
        # best-effort: failures are logged but never override the primary
        # 22F7 result, since not every FAN supports 2411 or has a bound REM.
        param_value = self._BYPASS_COMMAND_TO_2411_VALUE.get(command_name)
        if param_value is not None:
            await self._send_bypass_2411_param(device_id, param_value)

        return result

    async def _send_bypass_2411_param(self, device_id: str, value: int) -> None:
        """Best-effort send of the 2411 bypass-valve parameter (4B).

        Some Orcon HRC units drive the bypass via 2411 param 4B rather than
        22F7.  We send it alongside the 22F7 bypass command so both unit
        types are covered.  Any error is logged at debug level only — the
        22F7 leg is authoritative for the overall command result.

        :param device_id: Target FAN device identifier
        :param value: 2411/4B value (0=auto, 1=open, 2=closed)
        """
        try:
            param_result = await self.set_fan_param(
                device_id, self._BYPASS_2411_PARAM_ID, value
            )
            if not param_result.success:
                _LOGGER.debug(
                    "Best-effort 2411/%s bypass send for %s did not succeed: %s",
                    self._BYPASS_2411_PARAM_ID,
                    device_id,
                    param_result.error_message,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Best-effort 2411/%s bypass send for %s raised: %s",
                self._BYPASS_2411_PARAM_ID,
                device_id,
                err,
            )

    async def update_fan_params(
        self, device_id: str, from_id: str | None = None
    ) -> CommandResult:
        """Update all fan parameters for a device by calling ramses_cc broker directly.

        This bypasses HA service validation warnings about referenced devices.
        Uses task tracking to prevent concurrent calls that cause protocol timeouts.

        :param device_id: Target device ID
        :param from_id: Optional source device ID
        :return: CommandResult with execution status
        """
        # Convert device_id format if needed (32_153289 -> 32:153289)
        device_id_formatted = device_id.replace("_", ":")

        # Resolve the ramses_cc broker first — without it nothing works.
        ramses_cc_data = self.hass.data.get("ramses_cc", {})
        broker = None
        for _entry_id, broker_instance in ramses_cc_data.items():
            if hasattr(broker_instance, "get_all_fan_params"):
                broker = broker_instance
                break

        if not broker:
            return CommandResult(
                success=False, error_message="ramses_cc broker not found"
            )

        # Only block when the device can't be found at all.  The
        # supports_2411 flag defaults to False in ramses_rf and is only
        # set to True *after* the device receives a 2411 message — so
        # blocking on False creates a chicken-and-egg: the refresh is
        # the mechanism that triggers 2411 messages, but it's blocked
        # because no 2411 messages have arrived yet (e.g. after HA
        # restart).  Since update_fan_params is only called from the
        # FAN card/service, the device is always a FAN that may support
        # 2411; allow the refresh and let the requests fail naturally
        # if the device truly doesn't support it.
        supports_2411 = await self._device_supports_2411(device_id_formatted)
        if supports_2411 is None:
            msg = (
                f"Device {device_id_formatted} not found in ramses_rf; "
                "skipping update_fan_params"
            )
            _LOGGER.info(msg)
            return CommandResult(success=False, error_message=msg)

        # Check if already running for this device
        if device_id_formatted in self._update_fan_params_tasks:
            task = self._update_fan_params_tasks[device_id_formatted]
            if not task.done():
                _LOGGER.info(
                    f"update_fan_params already running for {device_id_formatted}, "
                    "skipping"
                )
                return CommandResult(
                    success=False,
                    error_message=(
                        f"Parameter update already in progress for "
                        f"{device_id_formatted}"
                    ),
                )
            # Clean up completed task
            del self._update_fan_params_tasks[device_id_formatted]

        try:
            call_data = {"device_id": device_id_formatted}
            if from_id:
                call_data["from_id"] = from_id

            _LOGGER.debug(f"Starting update_fan_params for {device_id_formatted}")

            # Call broker method directly (spawns async task internally)
            # Store reference to track it, but don't await it
            broker.get_all_fan_params(call_data)

            # Track a placeholder task to prevent immediate re-entry
            # Use a simple delay task that doesn't block the event loop
            async def _track_completion() -> None:
                await asyncio.sleep(0.5)  # Minimal delay, non-blocking

            self._update_fan_params_tasks[device_id_formatted] = (
                self.hass.async_create_task(_track_completion())
            )

            return CommandResult(success=True)

        except Exception as e:
            _LOGGER.error(f"Failed to trigger update_fan_params: {e}")
            return CommandResult(success=False, error_message=str(e))

    async def set_fan_param(
        self, device_id: str, param_id: str, value: Any, from_id: str | None = None
    ) -> CommandResult:
        """Set a fan parameter by calling ramses_cc broker directly.

        This bypasses HA service validation warnings about referenced devices.

        :param device_id: Target device ID
        :param param_id: Parameter ID (2-digit hex)
        :param value: Value to set
        :param from_id: Optional source device ID
        :return: CommandResult with execution status
        """
        try:
            # Convert device_id format if needed (32_153289 -> 32:153289)
            device_id_formatted = device_id.replace("_", ":")

            ramses_cc_data = self.hass.data.get("ramses_cc", {})
            broker = None
            for entry_id, broker_instance in ramses_cc_data.items():
                if hasattr(broker_instance, "async_set_fan_param"):
                    broker = broker_instance
                    break

            if not broker:
                return CommandResult(
                    success=False, error_message="ramses_cc broker not found"
                )

            call_data = {
                "device_id": device_id_formatted,
                "param_id": param_id,
                "value": value,
            }
            if from_id:
                call_data["from_id"] = from_id

            # Call broker method directly
            await broker.async_set_fan_param(call_data)
            return CommandResult(success=True)

        except Exception as e:
            _LOGGER.error(f"Failed to set fan parameter: {e}")
            return CommandResult(success=False, error_message=str(e))

    async def _send_packet(self, device_id: str, cmd_def: dict[str, str]) -> bool:
        """Send a packet directly via ramses_cc coordinator client.

        This bypasses the service layer to avoid requiring the send_packet
        advanced feature to be enabled in ramses_cc.

        :param device_id: Target device ID
        :param cmd_def: Command definition with code, verb, payload
        :return: True if packet sent successfully
        """
        try:
            device_id_formatted = device_id.replace("_", ":")

            _LOGGER.debug(
                f"Sending Ramses command to {device_id}: {cmd_def['code']} "
                f"{cmd_def['description']}"
            )

            transport_monitor = get_transport_monitor()
            is_monitoring = transport_monitor.is_monitoring
            is_available = transport_monitor.is_device_available(device_id_formatted)
            if is_monitoring and not is_available:
                _LOGGER.warning(
                    f"Skipping command {cmd_def['code']} - transport unavailable "
                    f"(device {device_id_formatted} marked offline)"
                )
                return False

            coordinator = await self._get_ramses_cc_coordinator()
            if not coordinator:
                # RF disabled / integration not loaded: mark device offline immediately
                get_transport_monitor().mark_device_offline_immediate(
                    device_id_formatted
                )
                _LOGGER.error(
                    f"Failed to send Ramses command {cmd_def['code']}: "
                    "ramses_cc coordinator not found. "
                    "Ensure ramses_cc integration is installed and loaded."
                )
                return False

            if not coordinator.client:
                get_transport_monitor().mark_device_offline_immediate(
                    device_id_formatted
                )
                _LOGGER.error(
                    f"Failed to send Ramses command {cmd_def['code']}: "
                    "ramses_cc client is not initialized."
                )
                return False

            kwargs = {
                "device_id": device_id_formatted,
                "verb": cmd_def["verb"],
                "code": cmd_def["code"],
                "payload": cmd_def["payload"],
            }

            from_id = await self._get_bound_rem_device(device_id_formatted)
            if from_id:
                kwargs["from_id"] = from_id

            if (
                kwargs["device_id"] == "18:000730"
                and kwargs.get("from_id", "18:000730") == "18:000730"
                and coordinator.client.hgi.id
            ):
                kwargs["device_id"] = coordinator.client.hgi.id

            cmd = coordinator.client.create_cmd(**kwargs)

            # Handle new timeout behavior in ramses_rf 0.55.6
            # In version 0.55.6, async_send_cmd raises exceptions on timeout
            # instead of silently failing. We need to handle this gracefully.
            try:
                await coordinator.client.async_send_cmd(cmd)
            except Exception as e:
                # Check if this is a timeout error from the new ramses_rf version
                # These errors indicate the command was sent but no acknowledgment
                # received
                if "Expired global timer" in str(e) or "send_timeout" in str(e):
                    # Log detailed command information for timeout monitoring
                    # This helps with debugging and allows custom retry logic
                    _LOGGER.warning(
                        f"Command timeout for device {device_id_formatted}: "
                        f"{cmd_def['code']} {cmd_def['verb']} {cmd_def['payload']} "
                        f"({cmd_def['description']}) - {e}"
                    )

                    # Store failed command for potential retry or monitoring
                    # This creates a history of timeouts that can be used by:
                    # - Custom retry logic
                    # - Health monitoring dashboards
                    # - Automatic device recovery mechanisms
                    if not hasattr(self, "_failed_commands"):
                        self._failed_commands = {}
                    self._failed_commands[device_id_formatted] = {
                        "command": cmd_def,  # Full command definition for retry
                        "timestamp": time.time(),  # When the timeout occurred
                        "error": str(e),  # Full error details for analysis
                    }

                    # Still notify transport monitor and return True
                    # The command was likely sent successfully, just no echo received
                    # Not notifying would incorrectly mark the device as offline
                    transport_monitor.notify_command_sent(device_id_formatted)
                    _LOGGER.debug(
                        f"Ramses command sent (with timeout): {cmd_def['description']}"
                    )
                    return True
                # Re-raise non-timeout errors as they indicate real problems
                # Examples: device not found, transport disconnected, etc.
                transport_monitor.mark_device_offline_immediate(device_id_formatted)
                raise

            # Notify transport monitor that we sent a command
            transport_monitor.notify_command_sent(device_id_formatted)

            _LOGGER.debug(f"Ramses command sent: {cmd_def['description']}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to send Ramses command {cmd_def['code']}: {e}")
            return False

    def get_failed_commands(self) -> dict[str, dict[str, Any]]:
        """Get failed commands for monitoring and potential retry.

        This method provides access to the history of timed-out commands,
        which can be used for:
        - Health monitoring dashboards
        - Custom retry logic
        - Device availability analysis
        - Troubleshooting communication issues

        :return: Dictionary mapping device_id to failed command info containing:
                 - command: Full command definition (code, verb, payload, description)
                 - timestamp: When the timeout occurred (Unix timestamp)
                 - error: Full error message from ramses_rf

        Note: Automatically cleans up failures older than 5 minutes
        to prevent memory growth.
        """
        if not hasattr(self, "_failed_commands"):
            return {}

        # Clean up old failures (older than 5 minutes)
        # This prevents the failed commands dict from growing indefinitely
        # and ensures we only track recent issues
        current_time = time.time()
        cutoff_time = current_time - 300  # 5 minutes

        self._failed_commands = {
            device_id: info
            for device_id, info in self._failed_commands.items()
            if isinstance(info.get("timestamp"), (int, float))
            and info["timestamp"] > cutoff_time
        }

        return self._failed_commands.copy()

    def clear_failed_commands(self, device_id: str | None = None) -> None:
        """Clear failed commands for monitoring.

        Use this method to reset the failure tracking, typically after:
        - Successfully retrying a failed command
        - Device comes back online
        - Manual intervention to fix communication issues

        :param device_id: Specific device ID to clear (format: 32_153289 or 32:153289)
                          If None, clears all failed commands for all devices
        """
        if not hasattr(self, "_failed_commands"):
            return

        if device_id:
            # Convert device ID format to match what we store
            device_id_formatted = device_id.replace("_", ":")
            self._failed_commands.pop(device_id_formatted, None)
        else:
            # Clear all failures - useful for global reset or maintenance
            self._failed_commands.clear()

    async def _get_ramses_cc_coordinator(self) -> RamsesCoordinator | None:
        """Get the ramses_cc coordinator instance.

        :return: RamsesCoordinator instance or None if not found
        """
        try:
            ramses_cc_data = self.hass.data.get("ramses_cc", {})

            # Find the coordinator instance (there should be one per config entry)
            for entry_id, coordinator_instance in ramses_cc_data.items():
                if hasattr(coordinator_instance, "client"):
                    return coordinator_instance

        except Exception as e:
            _LOGGER.debug(f"Could not get ramses_cc coordinator: {e}")

        return None

    async def _get_ramses_device(self, device_id: str) -> Any | None:
        """Return the underlying ramses_rf device for the given ID."""

        coordinator = await self._get_ramses_cc_coordinator()
        if not coordinator or not hasattr(coordinator, "_get_device"):
            return None

        lookup_id = device_id.replace("_", ":")
        try:
            return coordinator._get_device(lookup_id)
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Failed to resolve device %s: %s", lookup_id, err)
            return None

    async def _device_supports_2411(self, device_id: str) -> bool | None:
        """Return True if the resolved device advertises 2411 support."""

        device = await self._get_ramses_device(device_id)
        if device is None:
            return None

        supports_attr = getattr(device, "supports_2411", None)
        if supports_attr is None:
            return False

        return bool(supports_attr)

    async def _get_bound_rem_device(self, device_id: str) -> str | None:
        """Get the bound REM device ID for a FAN device.

        :param device_id: Device identifier (e.g., "32:153289")
        :return: Bound REM device ID or None if not found
        """
        try:
            # Get the coordinator to access device information
            coordinator = await self._get_ramses_cc_coordinator()
            if coordinator and hasattr(coordinator, "_get_device"):
                device = coordinator._get_device(device_id)
                if device and hasattr(device, "get_bound_rem"):
                    bound_rem = device.get_bound_rem()
                    if bound_rem:
                        return str(bound_rem)

        except Exception as e:
            _LOGGER.debug(f"Could not get bound REM device for {device_id}: {e}")

        return None

    def get_available_commands(self) -> dict[str, dict[str, str]]:
        """Get all available commands from the registry.

        :return: Dictionary of command definitions with metadata
        """
        commands = self._command_registry.get_registered_commands()
        # Type assertion to ensure correct return type
        return commands if isinstance(commands, dict) else {}

    def get_command_description(self, command: str) -> str:
        """Get description for a command.

        :param command: Command name
        :return: Command description or empty string if not found
        """
        cmd_def = self._command_registry.get_command(command)
        return str(cmd_def.get("description", "")) if cmd_def else ""

    def get_queue_statistics(self) -> dict[str, Any]:
        """Get comprehensive queue statistics for monitoring.

        :return: Dictionary containing queue statistics and metrics
        """
        return self._device_manager.get_queue_statistics()


# Global instance for easy access
def create_ramses_commands(hass: Any) -> RamsesCommands:
    """Create Ramses commands instance.

    :param hass: Home Assistant instance
    :return: RamsesCommands instance
    """
    return RamsesCommands(hass)


__all__ = [
    "RamsesCommands",
    "create_ramses_commands",
    "CommandResult",
    "DeviceCommandManager",
]
