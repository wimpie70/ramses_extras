# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Periodic Emitter for Device Simulator.

Emits periodic I (information) messages from virtual devices
at configured intervals.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .const import LOGGER, SIMULATOR_HGI_ID

if TYPE_CHECKING:
    from .comm_endpoint import MqttEndpoint
    from .device_db import AutonomousEntry, DeviceDatabase


@dataclass
class ActiveDevice:
    """Configuration for an active virtual device."""

    device_id: str  # e.g., "37:168270"
    device_type: str  # e.g., "FAN"
    variant_id: str | None = None
    enabled: bool = True
    speed_multiplier: float = 1.0  # 1.0 = normal, 10.0 = 10x faster

    # Per-code exclusions
    excluded_codes: set[str] = field(default_factory=set)

    # Last emission timestamps per code (for interval calculation)
    _last_emission: dict[str, float] = field(default_factory=dict, repr=False)

    def should_emit(
        self, code: str, current_time: float, interval_seconds: float
    ) -> bool:
        """Check if a code should be emitted now.

        :param code: The message code
        :param current_time: Current time in seconds
        :param interval_seconds: Configured interval
        :return: True if should emit
        """
        if not self.enabled or code in self.excluded_codes:
            return False

        # Apply speed multiplier
        effective_interval = interval_seconds / self.speed_multiplier

        last_time = self._last_emission.get(code, 0)
        return (current_time - last_time) >= effective_interval

    def record_emission(self, code: str, timestamp: float) -> None:
        """Record that a code was emitted.

        :param code: The message code
        :param timestamp: Emission timestamp
        """
        self._last_emission[code] = timestamp


class PeriodicEmitter:
    """Emits periodic I messages from virtual devices.

    Manages background tasks for each active device, emitting
    periodic messages at configured intervals.

    :param device_db: Device database for periodic message definitions
    :param endpoint: MQTT endpoint for sending messages
    """

    def __init__(
        self,
        device_db: DeviceDatabase,
        endpoint: MqttEndpoint,
    ) -> None:
        """Initialize the periodic emitter.

        :param device_db: Device database instance
        :param endpoint: MQTT endpoint for sending messages
        """
        self._db = device_db
        self._endpoint = endpoint

        # Active devices by device_id
        self._active_devices: dict[str, ActiveDevice] = {}

        # Background task for the emitter loop
        self._emitter_task: asyncio.Task | None = None

        # Control flags
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Global speed multiplier (applies to all devices)
        self._global_speed = 1.0

        # Default simulator source address for broadcasts
        self._default_src = "18:001234"

    async def start(self) -> None:
        """Start the periodic emitter background task."""
        if self._running:
            LOGGER.warning("PeriodicEmitter: already running")
            return

        self._running = True
        self._shutdown_event.clear()
        self._emitter_task = asyncio.create_task(
            self._emitter_loop(),
            name="periodic_emitter",
        )
        LOGGER.info("PeriodicEmitter: started")

    async def stop(self) -> None:
        """Stop the periodic emitter."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        if self._emitter_task:
            self._emitter_task.cancel()
            try:
                await self._emitter_task
            except asyncio.CancelledError:
                pass
            self._emitter_task = None

        LOGGER.info("PeriodicEmitter: stopped")

    def add_device(
        self,
        device_id: str,
        device_type: str,
        variant_id: str | None = None,
        speed_multiplier: float = 1.0,
    ) -> ActiveDevice:
        """Add a virtual device to emit periodic messages.

        :param device_id: Device address (e.g., "37:168270")
        :param device_type: Device type slug (e.g., "FAN")
        :param variant_id: Optional variant ID
        :param speed_multiplier: Speed multiplier for intervals
        :return: The created ActiveDevice
        """
        device = ActiveDevice(
            device_id=device_id,
            device_type=device_type,
            variant_id=variant_id,
            speed_multiplier=speed_multiplier,
        )
        self._active_devices[device_id] = device
        LOGGER.debug("PeriodicEmitter: added device %s (%s)", device_id, device_type)
        return device

    def remove_device(self, device_id: str) -> bool:
        """Remove a virtual device.

        :param device_id: Device address
        :return: True if removed, False if not found
        """
        if device_id in self._active_devices:
            del self._active_devices[device_id]
            LOGGER.debug("PeriodicEmitter: removed device %s", device_id)
            return True
        return False

    def enable_device(self, device_id: str) -> bool:
        """Enable a device's periodic emissions.

        :param device_id: Device address
        :return: True if found and enabled
        """
        device = self._active_devices.get(device_id)
        if device:
            device.enabled = True
            LOGGER.debug("PeriodicEmitter: enabled device %s", device_id)
            return True
        return False

    def disable_device(self, device_id: str) -> bool:
        """Disable a device's periodic emissions.

        :param device_id: Device address
        :return: True if found and disabled
        """
        device = self._active_devices.get(device_id)
        if device:
            device.enabled = False
            LOGGER.debug("PeriodicEmitter: disabled device %s", device_id)
            return True
        return False

    def set_device_speed(self, device_id: str, speed: float) -> bool:
        """Set speed multiplier for a device.

        :param device_id: Device address
        :param speed: Speed multiplier (1.0 = normal, 10.0 = 10x)
        :return: True if found and updated
        """
        device = self._active_devices.get(device_id)
        if device:
            device.speed_multiplier = max(0.01, speed)
            LOGGER.debug(
                "PeriodicEmitter: set device %s speed to %.2f", device_id, speed
            )
            return True
        return False

    def set_global_speed(self, speed: float) -> None:
        """Set global speed multiplier for all devices.

        :param speed: Speed multiplier
        """
        self._global_speed = max(0.01, speed)
        LOGGER.info("PeriodicEmitter: global speed set to %.2f", speed)

    def exclude_code(self, device_id: str, code: str) -> bool:
        """Exclude a specific code from a device's emissions.

        :param device_id: Device address
        :param code: Code to exclude (e.g., "31DA")
        :return: True if found and updated
        """
        device = self._active_devices.get(device_id)
        if device:
            device.excluded_codes.add(code)
            LOGGER.debug(
                "PeriodicEmitter: excluded code %s for device %s", code, device_id
            )
            return True
        return False

    def include_code(self, device_id: str, code: str) -> bool:
        """Re-include a previously excluded code.

        :param device_id: Device address
        :param code: Code to include
        :return: True if found and updated
        """
        device = self._active_devices.get(device_id)
        if device:
            device.excluded_codes.discard(code)
            LOGGER.debug(
                "PeriodicEmitter: included code %s for device %s", code, device_id
            )
            return True
        return False

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Get status of a virtual device.

        :param device_id: Device address
        :return: Status dict or None if not found
        """
        device = self._active_devices.get(device_id)
        if not device:
            return None

        # Get periodic definitions
        periodic = self._db.get_periodic(device.device_type, device.variant_id)

        return {
            "device_id": device_id,
            "device_type": device.device_type,
            "variant_id": device.variant_id,
            "enabled": device.enabled,
            "speed_multiplier": device.speed_multiplier,
            "excluded_codes": list(device.excluded_codes),
            "periodic_codes": [p.code for p in periodic],
        }

    def list_devices(self) -> list[str]:
        """List all registered device IDs.

        :return: List of device addresses
        """
        return list(self._active_devices.keys())

    async def _emitter_loop(self) -> None:
        """Main emitter loop - checks and emits periodic messages."""
        LOGGER.debug("PeriodicEmitter: emitter loop started")

        try:
            while self._running:
                # Wait with timeout to allow periodic checks
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=1.0,  # Check every second
                    )
                    # Shutdown event was set
                    break
                except TimeoutError:
                    pass

                if not self._endpoint.is_connected:
                    continue

                await self._check_and_emit()

        except asyncio.CancelledError:
            LOGGER.debug("PeriodicEmitter: emitter loop cancelled")
            raise
        except Exception:
            LOGGER.exception("PeriodicEmitter: error in emitter loop")
            raise

    async def _check_and_emit(self) -> None:
        """Check all devices and emit periodic messages as needed."""
        import time

        current_time = time.monotonic()

        for device in self._active_devices.values():
            if not device.enabled:
                continue

            # Get periodic definitions for this device
            periodic = self._db.get_periodic(device.device_type, device.variant_id)

            for entry in periodic:
                # Apply global speed multiplier
                effective_speed = device.speed_multiplier * self._global_speed
                effective_interval = entry.interval_seconds / effective_speed

                if device.should_emit(entry.code, current_time, effective_interval):
                    await self._emit_message(device, entry)
                    device.record_emission(entry.code, current_time)

    async def _emit_message(self, device: ActiveDevice, entry: AutonomousEntry) -> None:
        """Emit a single periodic message.

        :param device: Active device
        :param entry: Autonomous entry definition
        """
        # Get payload (use first available or empty)
        payload = entry.payloads[0] if entry.payloads else ""
        payload_len = len(payload) // 2 if payload else 0

        # Build I frame in production format:
        # RSSI VERB --- SRC DST BROADCAST CODE LEN PAYLOAD
        # For inbound I frames (device broadcasting), BROADCAST = SRC
        # Example: 082  I --- 32:022222 --:------ 32:022222 31DA 030 00EF...
        dst = "--:------"
        broadcast = device.device_id  # BROADCAST = SRC for I frames
        frame = (
            f"082  I --- {device.device_id} {dst} {broadcast} {entry.code} "
            f"{payload_len:03d} {payload}"
        )

        # Send via endpoint
        try:
            await self._endpoint.send_packet(frame)
            LOGGER.debug(
                "PeriodicEmitter: emitted %s from %s", entry.code, device.device_id
            )
        except Exception:
            LOGGER.exception(
                "PeriodicEmitter: failed to emit %s from %s",
                entry.code,
                device.device_id,
            )

    async def emit_once(
        self, device_id: str, code: str, payload: str | None = None
    ) -> bool:
        """Emit a single message immediately (for manual trigger).

        :param device_id: Device address
        :param code: Message code
        :param payload: Optional payload (uses DB default if None)
        :return: True if emitted
        """
        device = self._active_devices.get(device_id)
        if not device:
            return False

        if not self._endpoint.is_connected:
            LOGGER.warning("PeriodicEmitter: endpoint not connected")
            return False

        # Get default payload from DB if not provided
        if payload is None:
            periodic = self._db.get_periodic(device.device_type, device.variant_id)
            for entry in periodic:
                if entry.code == code and entry.payloads:
                    payload = entry.payloads[0]
                    break

        if payload is None:
            payload = ""

        payload_len = len(payload) // 2 if payload else 0
        dst = "--:------"
        broadcast = device_id  # BROADCAST = SRC for I frames
        frame = (
            f"082  I --- {device_id} {dst} {broadcast} {code} "
            f"{payload_len:03d} {payload}"
        )

        try:
            await self._endpoint.send_packet(frame)
            LOGGER.debug("PeriodicEmitter: manual emit %s from %s", code, device_id)
            return True
        except Exception:
            LOGGER.exception(
                "PeriodicEmitter: failed manual emit %s from %s", code, device_id
            )
            return False
