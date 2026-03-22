"""Transport State Monitor for Ramses RF.

This module provides monitoring of the Ramses RF transport state and
implements graceful degradation when the transport is unavailable.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

from homeassistant.core import Event, HomeAssistant

if TYPE_CHECKING:
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

_LOGGER = logging.getLogger(__name__)


class TransportMonitor:
    """Monitors Ramses RF transport state and manages graceful degradation.

    This class tracks the availability of the transport layer and provides
    callbacks for when the transport goes down or comes back up.

    Uses command-based liveness detection:
    - When a command is sent to a device, starts a 61s timeout timer
    - If device replies within 61s, marks it online and cancels timer
    - If no reply within 61s, marks it offline
    - Only one timer per device at a time
    """

    def __init__(self) -> None:
        self._transport_available: bool = False
        self._last_check: float = 0
        self._check_interval: float = 5.0  # Check every 5 seconds
        self._monitor_task: asyncio.Task | None = None
        self._callbacks: dict[str, tuple[str | None, Callable[[bool], None]]] = {}
        self._coordinator: RamsesCoordinator | None = None
        self._lock = asyncio.Lock()
        self._last_command_sent_times: dict[str, float] = {}  # When we sent a command
        self._last_device_reply_times: dict[str, float] = {}  # When device replied
        self._device_timeout_tasks: dict[str, asyncio.Task] = {}  # One timer per device
        self._device_states: dict[str, bool] = {}  # Current online/offline state
        self._command_timeout: float = 61.0  # Wait 61s for reply after sending command
        self._hass: HomeAssistant | None = None
        self._event_unsub: Callable[[], None] | None = None

    def register_callback(
        self,
        name: str,
        callback: Callable[[bool], None],
        device_id: str | None = None,
    ) -> None:
        """Register a callback for transport state changes.

        Args:
            name: Unique identifier for the callback
            callback: Function to call when transport state changes
                     (receives boolean: True=available, False=unavailable)
            device_id: Optional target device ID for per-device liveness tracking
        """
        normalized_device_id = device_id.replace("_", ":") if device_id else None
        self._callbacks[name] = (normalized_device_id, callback)
        _LOGGER.debug(
            "Registered transport state callback: %s%s",
            name,
            f" for {normalized_device_id}" if normalized_device_id else "",
        )

    def unregister_callback(self, name: str) -> None:
        """Unregister a transport state callback.

        Args:
            name: Identifier of the callback to remove
        """
        self._callbacks.pop(name, None)
        _LOGGER.debug("Unregistered transport state callback: %s", name)

    def notify_command_sent(self, device_id: str) -> None:
        """Notify that a command was sent to a device.

        This starts the 61s timeout timer for the device if one isn't already running.
        Only one timer runs per device at a time.
        """
        normalized_device_id = device_id.replace("_", ":")
        self._last_command_sent_times[normalized_device_id] = time.time()

        # Only start a timer if one isn't already running
        existing_task = self._device_timeout_tasks.get(normalized_device_id)
        if existing_task and not existing_task.done():
            _LOGGER.debug(
                "Command sent to %s, timer already running",
                normalized_device_id,
            )
            return

        # Start new timeout task
        if self._hass:
            task = self._hass.async_create_task(
                self._device_timeout_handler(normalized_device_id)
            )
            self._device_timeout_tasks[normalized_device_id] = task

        _LOGGER.debug(
            "Command sent to %s, started 61s timeout timer",
            normalized_device_id,
        )

    async def _device_timeout_handler(self, device_id: str) -> None:
        """Handle device timeout after 61s with no reply."""
        try:
            await asyncio.sleep(self._command_timeout)
            # If we reach here, no reply was received within 61s
            await self._mark_device_offline(device_id)
        except asyncio.CancelledError:
            # Timer was cancelled because we got a reply or new command
            pass

    async def _mark_device_offline(self, device_id: str) -> None:
        """Mark a device as offline and notify callbacks."""
        old_state = self._device_states.get(device_id, True)
        if old_state:  # Was online, now offline
            self._device_states[device_id] = False
            _LOGGER.warning(
                "Device %s marked offline - no reply within 61s of command",
                device_id,
            )
            await self._notify_device_state_changed(device_id, False)

    async def _mark_device_online(self, device_id: str) -> None:
        """Mark a device as online and notify callbacks."""
        old_state = self._device_states.get(device_id, False)
        self._device_states[device_id] = True

        if not old_state:  # State changed from offline to online
            _LOGGER.info(
                "Device %s marked online - received reply",
                device_id,
            )

        # Always notify callbacks when device replies
        await self._notify_device_state_changed(device_id, True)

    async def _notify_device_state_changed(self, device_id: str, online: bool) -> None:
        """Notify all callbacks for this device of state change."""
        for name, (callback_device_id, callback) in self._callbacks.items():
            if callback_device_id == device_id:
                try:
                    callback(online)
                except Exception as e:
                    _LOGGER.error("Error in transport state callback %s: %s", name, e)

    def update_device_message_received(self, device_id: str) -> None:
        """Record that a device has replied.

        This marks the device online and cancels any pending timeout.
        """
        normalized_device_id = device_id.replace("_", ":")
        self._last_device_reply_times[normalized_device_id] = time.time()

        # Cancel timeout task since we got a reply
        existing_task = self._device_timeout_tasks.get(normalized_device_id)
        if existing_task and not existing_task.done():
            existing_task.cancel()
            self._device_timeout_tasks.pop(normalized_device_id, None)

        # Mark device online if it wasn't already
        # Use call_soon_threadsafe since this is called from SyncWorker thread
        if self._hass:
            self._hass.loop.call_soon_threadsafe(
                self._hass.async_create_task,
                self._mark_device_online(normalized_device_id),
            )

        _LOGGER.debug(
            "Device reply received from %s, cancelled timeout and marked online",
            normalized_device_id,
        )

    async def start_monitoring(
        self, coordinator: "RamsesCoordinator", hass: HomeAssistant
    ) -> None:
        """Start monitoring the transport state.

        Args:
            coordinator: RamsesCC coordinator instance
            hass: Home Assistant instance for event listening
        """
        async with self._lock:
            if self._monitor_task and not self._monitor_task.done():
                _LOGGER.warning("Transport monitor is already running")
                return

            self._coordinator = coordinator
            self._hass = hass

            # Set up event listener for device messages
            if self._hass and not self._event_unsub:
                self._event_unsub = self._hass.bus.async_listen(
                    "ramses_cc_message",
                    self._handle_ramses_cc_message,
                )
                _LOGGER.debug(
                    "Transport monitor listening for ramses_cc_message events"
                )
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            _LOGGER.info("Started transport state monitoring")

    async def stop_monitoring(self) -> None:
        """Stop monitoring the transport state."""
        async with self._lock:
            if self._monitor_task and not self._monitor_task.done():
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                _LOGGER.info("Stopped transport state monitoring")

            # Clean up event listener
            if self._event_unsub:
                self._event_unsub()
                self._event_unsub = None
                _LOGGER.debug("Stopped listening for ramses_cc_message events")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - just keeps transport state updated."""
        _LOGGER.debug("Transport monitor loop started")
        last_transport_state = None

        while True:
            try:
                await asyncio.sleep(self._check_interval)
                # Just update global transport state
                transport_active = self._is_transport_active()
                self._transport_available = transport_active

                # Only log when state changes
                if transport_active != last_transport_state:
                    if transport_active:
                        _LOGGER.info("Global transport active")
                    else:
                        _LOGGER.warning("Global transport inactive")
                    last_transport_state = transport_active
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in transport monitor loop: %s", e)

    def _handle_ramses_cc_message(self, event: Event) -> None:
        """Handle ramses_cc_message events to track device replies.

        Args:
            event: Home Assistant event containing ramses_cc_message data
        """
        try:
            data = event.data
            if not isinstance(data, dict):
                return

            src = data.get("src")
            dst = data.get("dst")

            # Only process messages FROM devices we're monitoring, not TO them
            if isinstance(src, str) and ":" in src:
                # Check if we have a timer running for this device
                normalized_src = src.replace("_", ":")
                if normalized_src in self._device_timeout_tasks:
                    _LOGGER.debug("Message FROM %s (TO %s) - processing", src, dst)
                    self.update_device_message_received(src)
        except Exception as e:
            _LOGGER.error("Error handling ramses_cc_message event: %s", e)

    def _is_transport_active(self) -> bool:
        if not self._coordinator or not self._coordinator.client:
            return False

        try:
            transport = self._coordinator.client.transport
            return hasattr(transport, "state") and transport.state.name != "Inactive"
        except Exception:
            return False

    def is_device_available(self, device_id: str) -> bool:
        """Return whether a specific device is currently online.

        A device is online if:
        - We haven't sent a command yet (assume online)
        - We sent a command and got a reply before timeout
        - We sent a command and timeout hasn't expired yet
        """
        normalized_device_id = device_id.replace("_", ":")
        return self._device_states.get(normalized_device_id, True)

    @property
    def is_transport_available(self) -> bool:
        """Check if transport layer is currently available."""
        return self._transport_available

    @property
    def is_monitoring(self) -> bool:
        """Return whether transport monitoring is currently active."""
        return self._monitor_task is not None and not self._monitor_task.done()

    async def force_check(self) -> None:
        """Force an immediate check of transport state.

        For command-based monitoring, this just ensures callbacks get
        the current state of their devices.
        """
        for name, (device_id, callback) in self._callbacks.items():
            try:
                if device_id is not None:
                    current_state = self.is_device_available(device_id)
                    callback(current_state)
                else:
                    callback(self._transport_available)
            except Exception as e:
                _LOGGER.error("Error in transport state callback %s: %s", name, e)


# Global transport monitor instance
_transport_monitor: TransportMonitor | None = None


def get_transport_monitor() -> TransportMonitor:
    """Get the global transport monitor instance.

    Returns:
        TransportMonitor instance
    """
    global _transport_monitor
    if _transport_monitor is None:
        _transport_monitor = TransportMonitor()
    return _transport_monitor
