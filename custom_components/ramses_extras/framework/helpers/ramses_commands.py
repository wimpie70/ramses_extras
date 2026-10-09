"""Ramses RF Command Definitions and Execution.

This module provides command definitions for Ramses RF devices with centralized
command management, queuing, and rate limiting. Commands are feature-owned and
organized by device type for easy access and extension.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.core import Context

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
        command_name: str | None = None,
    ) -> CommandResult:
        """Send command to device with queuing and rate limiting.

        :param device_id: Target device identifier
        :param command_def: Command definition with code, verb, payload
        :param priority: Command priority ("high", "normal", "low")
        :param timeout: Command timeout in seconds
        :param command_name: Registry name of the command, used to route
            22F1 fan modes through the ramses_rf strategy layer
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
                    "command_name": command_name,
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
        result = await self._execute_command(
            device_id, command_def, timeout, command_name
        )

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
                    device_id,
                    command_data["command_def"],
                    command_data["timeout"],
                    command_data.get("command_name"),
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
        self,
        device_id: str,
        command_def: dict[str, Any],
        timeout: float,
        command_name: str | None = None,
    ) -> CommandResult:
        """Execute a command directly (internal method)."""
        start_time = time.time()

        try:
            # Update rate limiting
            self._last_command_time[device_id] = start_time

            # Execute command using the RamsesCommands instance
            success = await self._ramses_commands._dispatch_command(
                device_id, command_def, command_name
            )
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
        # Track failed commands for monitoring and retry logic
        self._failed_commands: dict[str, dict[str, Any]] = {}
        # Recently-sent command names per device.  Commands are sent with a
        # spoofed bound-REM source address, so they come back over the RF
        # listener looking like external remote presses — this map lets the
        # observer distinguish our own echoes (see default/services.py).
        self._self_sent: dict[tuple[str, str], float] = {}

    # Mapping of fan_* command names to semantic strategy mode names.
    # Used by _dispatch_command to route fan mode commands through
    # device.set_fan_mode(), which applies the vendor-specific strategy
    # (Orcon, Itho, Vasco, Nuaire, ClimaRad) instead of hardcoded Orcon
    # hex payloads.  Only 22F1 fan mode commands are mapped here —
    # bypass (22F7), filter reset (10D0), timer (22F3), and RQ commands
    # don't have usable strategy equivalents and keep the raw packet path.
    _FAN_COMMAND_TO_STRATEGY_MODE: dict[str, str] = {
        "fan_high": "high",
        "fan_medium": "medium",
        "fan_low": "low",
        "fan_auto": "auto",
        "fan_boost": "boost",
        "fan_away": "away",
        "fan_disable": "off",
    }

    # Mapping of fan_bypass_* command names to SET_BYPASS_POSITION mode
    # names.  Used by _dispatch_command to route 22F7 bypass commands
    # through the ramses_rf intent/dispatcher layer when the upstream
    # builder emits a valid 3-byte payload (fixed in ramses_rf 0.60.10;
    # older builders emit a 2-byte payload the parser rejects — see
    # https://github.com/ramses-rf/ramses_cc/issues/1298).  The raw
    # packet path remains as fallback for older ramses_rf versions.
    _BYPASS_COMMAND_TO_MODE: dict[str, str] = {
        "fan_bypass_open": "on",
        "fan_bypass_close": "off",
        "fan_bypass_auto": "auto",
    }

    async def send_fan_command(self, device_id: str, command: str) -> CommandResult:
        """Send a fan command to a Ramses RF device.

        Thin wrapper around :meth:`send_command`, which routes 22F1 fan
        mode commands through ``device.set_fan_mode()`` (vendor strategy)
        and everything else through raw packet sending.

        :param device_id: Device identifier (e.g., "32_153289")
        :param command: Command name from HvacVentilator standard commands
                       Use prefixed names like "fan_high", "fan_low", "fan_auto", etc.
        :return: CommandResult with execution status and error details
        """
        return await self.send_command(device_id, command)

    async def _send_fan_mode_via_strategy(
        self, device_id: str, mode_name: str
    ) -> CommandResult | None:
        """Send a fan mode via device.set_fan_mode() (strategy-aware).

        Returns a CommandResult if the strategy path was used, or None if
        the strategy path is unavailable (device not found, no
        set_fan_mode method, or ramses_rf too old) — in which case the
        caller falls back to raw packet sending.

        :param device_id: Device identifier (e.g., "32_153289")
        :param mode_name: Semantic fan mode name (e.g., "high", "low")
        :return: CommandResult if strategy path used, None if unavailable
        """
        try:
            device_id_formatted = device_id.replace("_", ":")

            coordinator = await self._get_ramses_cc_coordinator()
            if not coordinator or not coordinator.client:
                return None

            # Resolve the HvacVentilator from the gateway's device registry
            device_registry = getattr(coordinator.client, "device_registry", None)
            if device_registry is None:
                return None

            device = getattr(device_registry, "device_by_id", {}).get(
                device_id_formatted
            )
            if device is None:
                return None

            set_fan_mode = getattr(device, "set_fan_mode", None)
            if not callable(set_fan_mode):
                return None

            _LOGGER.debug(
                "Sending set_fan_mode '%s' to %s via strategy",
                mode_name,
                device_id_formatted,
            )
            await set_fan_mode(mode_name)

            # Notify transport monitor
            get_transport_monitor().notify_command_sent(device_id_formatted)

            return CommandResult(success=True)

        except Exception as e:
            _LOGGER.warning(
                "Strategy-based set_fan_mode('%s') failed for %s: %s, "
                "falling back to raw packet",
                mode_name,
                device_id,
                e,
            )
            return None

    async def _send_bypass_via_intent(
        self, device_id: str, mode_name: str
    ) -> CommandResult | None:
        """Send a bypass command via the SET_BYPASS_POSITION intent path.

        Returns a CommandResult if the intent path was used, or None if it
        is unavailable (imports missing, device not found, no dispatcher,
        or a ramses_rf builder that still emits the broken 2-byte 22F7
        payload) — in which case the caller falls back to raw packet
        sending.

        :param device_id: Device identifier (e.g., "32_153289")
        :param mode_name: Bypass mode name ("on", "off", "auto")
        :return: CommandResult if intent path used, None if unavailable
        """
        try:
            from ramses_rf.address import Address
            from ramses_rf.commands.builders.hvac import (
                build_set_bypass_position,
            )
            from ramses_rf.commands.core import Command as Intent
            from ramses_rf.enums import Action
            from ramses_tx import Priority
            from ramses_tx.typing import DeviceIdT
        except ImportError:
            return None

        try:
            device_id_formatted = device_id.replace("_", ":")

            coordinator = await self._get_ramses_cc_coordinator()
            if not coordinator or not coordinator.client:
                return None

            # Resolve the HvacVentilator from the gateway's device registry
            device_registry = getattr(coordinator.client, "device_registry", None)
            if device_registry is None:
                return None

            device = getattr(device_registry, "device_by_id", {}).get(
                device_id_formatted
            )
            if device is None:
                return None

            dispatcher = getattr(coordinator.client, "dispatcher", None)
            if dispatcher is None:
                return None

            # 22F7 commands to a FAN typically must originate from a bound
            # Remote (REM); fall back to the gateway HGI — the same source
            # resolution ramses_rf's set_fan_mode() applies.
            src_id = None
            get_bound_rem = getattr(device, "get_bound_rem", None)
            if callable(get_bound_rem):
                src_id = get_bound_rem()
            if not src_id:
                src_id = getattr(getattr(device, "hgi", None), "id", None)
            if not src_id:
                return None

            intent = Intent(
                src=Address(DeviceIdT(src_id)),
                dst=Address(DeviceIdT(device_id_formatted)),
                action=Action.SET_BYPASS_POSITION,
                data={"bypass_mode": mode_name},
            )

            # ramses_rf < 0.60.10 builds a 2-byte 22F7 payload that its own
            # parser rejects; only use the intent path when the builder
            # produces the valid 3-byte form (00{pos}EF).
            if len(build_set_bypass_position(intent).payload) != 6:
                return None

            _LOGGER.debug(
                "Sending bypass '%s' to %s via SET_BYPASS_POSITION intent",
                mode_name,
                device_id_formatted,
            )
            # Ventilators do not ack 22F7 commands — fire-and-forget.
            await dispatcher.send(intent, priority=Priority.HIGH, wait_for_reply=False)

            # Notify transport monitor
            get_transport_monitor().notify_command_sent(device_id_formatted)

            return CommandResult(success=True)

        except Exception as e:
            _LOGGER.warning(
                "Intent-based bypass '%s' failed for %s: %s, "
                "falling back to raw packet",
                mode_name,
                device_id,
                e,
            )
            return None

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
            device_id, cmd_def, priority, timeout, command_name=command_name
        )
        if result.success:
            self._record_command_sent(device_id, command_name)

        # For bypass commands, also send the 2411/4B parameter that some
        # Orcon/HRC units use instead of (or in addition to) 22F7.  This is
        # best-effort: failures are logged but never override the primary
        # 22F7 result, since not every FAN supports 2411 or has a bound REM.
        param_value = self._BYPASS_COMMAND_TO_2411_VALUE.get(command_name)
        if param_value is not None:
            await self._send_bypass_2411_param(device_id, param_value)

        return result

    # Window during which an observed packet matching a command we sent is
    # treated as our own echo rather than an external remote press.  Covers
    # the MQTT/serial echo delay plus listener scheduling latency.
    _SELF_SENT_WINDOW = 5.0

    def _record_command_sent(self, device_id: str, command_name: str) -> None:
        """Record that we sent ``command_name`` to ``device_id``."""
        key = (device_id.replace("_", ":"), command_name)
        self._self_sent[key] = time.monotonic()
        if len(self._self_sent) > 64:
            cutoff = time.monotonic() - self._SELF_SENT_WINDOW
            self._self_sent = {
                k: ts for k, ts in self._self_sent.items() if ts > cutoff
            }

    def was_command_recently_sent(
        self, device_id: str, command_name: str, window: float | None = None
    ) -> bool:
        """Return True if we sent this command to this device very recently.

        Used by the remote-packet observer to ignore echoes of our own
        sends (they use a spoofed bound-REM source address and would
        otherwise register as external manual overrides).

        :param device_id: Device identifier (e.g., "32:153289")
        :param command_name: Registry command name (e.g., "fan_high")
        :param window: Match window in seconds (default 5s)
        :return: True if the same command was sent within the window
        """
        ts = self._self_sent.get((device_id.replace("_", ":"), command_name))
        return ts is not None and (time.monotonic() - ts) < (
            window or self._SELF_SENT_WINDOW
        )

    async def _dispatch_command(
        self,
        device_id: str,
        cmd_def: dict[str, Any],
        command_name: str | None = None,
    ) -> bool:
        """Dispatch a command: intent/strategy-aware, raw otherwise.

        22F1 fan mode commands route through ``device.set_fan_mode()`` so
        ramses_rf's vendor strategy (Orcon, Itho, Vasco, Nuaire, ClimaRad)
        translates the semantic mode name into the correct payload.
        22F7 bypass commands route through the ``SET_BYPASS_POSITION``
        intent path when the upstream builder emits a valid 3-byte
        payload (ramses_rf >= 0.60.10;
        https://github.com/ramses-rf/ramses_cc/issues/1298).
        Everything else — filter reset (10D0), timers (22F3),
        RQ requests — keeps the raw ``create_cmd``/``async_send_raw_command``
        path: ramses_rf has no intent action for those.

        :param device_id: Target device identifier
        :param cmd_def: Command definition with code, verb, payload
        :param command_name: Registry command name for strategy routing
        :return: True if the command was sent
        """
        mode_name = self._FAN_COMMAND_TO_STRATEGY_MODE.get(command_name or "")
        if mode_name is not None:
            result = await self._send_fan_mode_via_strategy(device_id, mode_name)
            if result is not None:
                return result.success
        bypass_mode = self._BYPASS_COMMAND_TO_MODE.get(command_name or "")
        if bypass_mode is not None:
            result = await self._send_bypass_via_intent(device_id, bypass_mode)
            if result is not None:
                return result.success
        return await self._send_packet(device_id, cmd_def)

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
        self,
        device_id: str,
        from_id: str | None = None,
        context: Context | None = None,
    ) -> CommandResult:
        """Update all fan parameters via the ramses_cc ``update_fan_params`` service.

        ramses_cc owns the refresh sweep (per-parameter GET_FAN_PARAM
        intents, pacing, dedup via ``_fan_param_sequences``, entity pending
        state).  We only keep a device-existence check so a refresh for a
        device ramses_rf doesn't know is skipped instead of warning once
        per schema parameter upstream.

        :param device_id: Target device ID
        :param from_id: Optional source device ID
        :param context: Optional service-call context (forwarded so the
                        ramses_cc permission check still applies)
        :return: CommandResult with execution status
        """
        # Convert device_id format if needed (32_153289 -> 32:153289)
        device_id_formatted = device_id.replace("_", ":")

        coordinator = await self._get_ramses_cc_coordinator()
        if not coordinator:
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

        try:
            service_data: dict[str, Any] = {"device_id": device_id_formatted}
            if from_id:
                service_data["from_id"] = from_id.replace("_", ":")

            _LOGGER.debug(f"Starting update_fan_params for {device_id_formatted}")

            # The upstream sweep takes ~0.5s per schema parameter; call the
            # service non-blocking so we return immediately, matching the
            # previous fire-and-forget behaviour.
            await self.hass.services.async_call(
                "ramses_cc",
                "update_fan_params",
                service_data,
                blocking=False,
                context=context,
            )
            return CommandResult(success=True)

        except Exception as e:
            _LOGGER.error(f"Failed to trigger update_fan_params: {e}")
            return CommandResult(success=False, error_message=str(e))

    async def set_fan_param(
        self,
        device_id: str,
        param_id: str,
        value: Any,
        from_id: str | None = None,
        context: Context | None = None,
    ) -> CommandResult:
        """Set a fan parameter via the ramses_cc ``set_fan_param`` service.

        ramses_cc owns device/from_id resolution (bound REM -> gateway
        HGI), parameter validation, entity pending state and the
        SET_FAN_PARAM intent dispatch — extras no longer plumbs its own
        request into coordinator internals.

        :param device_id: Target device ID
        :param param_id: Parameter ID (2-digit hex)
        :param value: Value to set
        :param from_id: Optional source device ID
        :param context: Optional service-call context (forwarded so the
                        ramses_cc permission check still applies)
        :return: CommandResult with execution status
        """
        try:
            coordinator = await self._get_ramses_cc_coordinator()
            if not coordinator:
                return CommandResult(
                    success=False, error_message="ramses_cc broker not found"
                )

            service_data: dict[str, Any] = {
                "device_id": device_id.replace("_", ":"),
                # ramses_cc validates param_id against ^[0-9A-F]{2}$
                "param_id": str(param_id).upper(),
                "value": str(value),
            }
            if from_id:
                service_data["from_id"] = from_id.replace("_", ":")

            await self.hass.services.async_call(
                "ramses_cc",
                "set_fan_param",
                service_data,
                blocking=True,
                context=context,
            )
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

            # For pooled transports, the placeholder HGI 18:000730 is
            # patched to the selected child's HGI by PooledTransport
            # .prepare_command() at send time.  For single-transport
            # gateways, remap it here as before.
            if (
                kwargs["device_id"] == "18:000730"
                and kwargs.get("from_id", "18:000730") == "18:000730"
            ):
                client = coordinator.client
                engine = getattr(client, "_engine", None)
                transport = getattr(engine, "_transport", None) if engine else None
                # If this is a PooledTransport, let it patch the source
                # at send time — don't override with a single HGI here.
                if not hasattr(transport, "_connected_children"):
                    hgi = getattr(client, "hgi", None)
                    if hgi and hgi.id:
                        kwargs["device_id"] = hgi.id

            cmd = coordinator.client.create_cmd(**kwargs)

            # Use async_send_raw_command (ramses_rf >= 0.60.4, PR 1177) with
            # fallback to async_send_cmd for older ramses_rf versions.
            send_fn = getattr(coordinator.client, "async_send_raw_command", None)
            if send_fn is None:
                send_fn = getattr(coordinator.client, "async_send_cmd", None)
            if send_fn is None:
                _LOGGER.error(
                    "Cannot send command %s: ramses_rf Gateway has neither "
                    "async_send_raw_command nor async_send_cmd — "
                    "please upgrade ramses-rf to >= 0.60.4",
                    cmd_def["code"],
                )
                return False

            # Handle new timeout behavior in ramses_rf 0.55.6
            # In version 0.55.6, async_send_cmd raises exceptions on timeout
            # instead of silently failing. We need to handle this gracefully.
            try:
                await send_fn(cmd)
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

                # "No connected child transport available for send" means the
                # pool has no online HGI — the target device is not at fault,
                # so don't mark it offline.  Log and return False.
                if "No connected child transport" in str(e):
                    _LOGGER.warning(
                        f"Cannot send {cmd_def['code']} to {device_id_formatted}: "
                        f"no connected HGI in pool ({cmd_def['description']})"
                    )
                    return False

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

        ramses_cc stores the coordinator in ``entry.runtime_data``
        (not ``hass.data["ramses_cc"]`` as in older versions).
        The coordinator's ``client`` attribute may be None during
        early startup — we check for a non-None client.

        :return: RamsesCoordinator instance or None if not found
        """
        try:
            # New approach: iterate config entries via hass.config_entries
            entries = self.hass.config_entries.async_entries("ramses_cc")
            for entry in entries:
                coordinator = getattr(entry, "runtime_data", None)
                if (
                    coordinator is not None
                    and getattr(coordinator, "client", None) is not None
                ):
                    return coordinator

        except Exception as e:
            _LOGGER.debug(f"Could not get ramses_cc coordinator: {e}")

        return None

    async def _get_ramses_device(self, device_id: str) -> Any | None:
        """Return the underlying ramses_rf device for the given ID."""

        coordinator = await self._get_ramses_cc_coordinator()
        if coordinator is None:
            return None
        get_device = getattr(coordinator, "get_device", None) or getattr(
            coordinator, "_get_device", None
        )
        if get_device is None:
            return None

        lookup_id = device_id.replace("_", ":")
        try:
            return get_device(lookup_id)
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
            get_device = (
                (
                    getattr(coordinator, "get_device", None)
                    or getattr(coordinator, "_get_device", None)
                )
                if coordinator
                else None
            )
            if get_device:
                device = get_device(device_id)
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


def get_ramses_commands(hass: Any) -> RamsesCommands:
    """Return the shared RamsesCommands instance for this hass.

    The DeviceCommandManager's queue, rate limiting, dedup and statistics
    only work if all callers share one instance — a fresh RamsesCommands
    per service call would give every call its own (empty) rate-limit
    state.  The instance is stored in ``hass.data["ramses_extras"]``.

    :param hass: Home Assistant instance
    :return: Shared RamsesCommands instance
    """
    data: dict[str, Any] = hass.data.setdefault("ramses_extras", {})
    commands = data.get("ramses_commands")
    if not isinstance(commands, RamsesCommands):
        commands = RamsesCommands(hass)
        data["ramses_commands"] = commands
    return commands


__all__ = [
    "RamsesCommands",
    "create_ramses_commands",
    "get_ramses_commands",
    "CommandResult",
    "DeviceCommandManager",
]
