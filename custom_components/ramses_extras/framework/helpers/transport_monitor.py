"""Transport State Monitor for Ramses RF.

This module provides monitoring of the Ramses RF transport state and
implements graceful degradation when the transport is unavailable.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

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
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        self._last_command_sent_times: dict[str, float] = {}  # When we sent a command
        self._last_device_reply_times: dict[str, float] = {}  # When device replied
        self._device_timeout_tasks: dict[str, asyncio.Task] = {}  # One timer per device
        self._device_states: dict[str, bool] = {}  # Current online/offline state
        self._command_timeout: float = 61.0  # Wait 61s for reply after sending command
        self._hass: HomeAssistant | None = None
        self._event_unsub: Callable[[], None] | None = None
        self._msg_handler_unsub: Callable[[], None] | None = None

    def register_callback(
        self,
        name: str,
        callback: Callable[[bool], None],
        device_id: str | None = None,
    ) -> None:
        """Register a callback for transport state changes.

        :param name: Unique identifier for the callback
        :param callback: Function to call when transport state changes
                     (receives boolean: True=available, False=unavailable)
        :param device_id: Optional target device ID for per-device liveness tracking
        """
        normalized_device_id = device_id.replace("_", ":") if device_id else None
        self._callbacks[name] = (normalized_device_id, callback)
        _LOGGER.info(
            "Registered transport state callback: %s%s (total callbacks: %d)",
            name,
            f" for {normalized_device_id}" if normalized_device_id else "",
            len(self._callbacks),
        )
        # Trigger an immediate check to update the new callback with current state
        if self._hass and normalized_device_id:
            current_state = self._device_states.get(normalized_device_id, True)
            _LOGGER.debug(
                "Setting initial state for %s to %s",
                normalized_device_id,
                current_state,
            )
            try:
                callback(current_state)
            except Exception as e:
                _LOGGER.error("Error in initial callback for %s: %s", name, e)

    def unregister_callback(self, name: str) -> None:
        """Unregister a transport state callback.

        :param name: Identifier of the callback to remove
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

    def _refresh_coordinator(self) -> None:
        if not self._hass:
            return

        ramses_cc_data = self._hass.data.get("ramses_cc", {})
        for coordinator_instance in ramses_cc_data.values():
            if not hasattr(coordinator_instance, "client"):
                continue
            client = getattr(coordinator_instance, "client", None)
            if client is None:
                continue

            self._coordinator = coordinator_instance
            self._ensure_msg_handler(client)
            return

        self._coordinator = None
        self._ensure_msg_handler(None)

    def _ensure_msg_handler(self, client: Any | None) -> None:
        if client is self._client:
            _LOGGER.debug("_ensure_msg_handler: client unchanged, skipping")
            return

        if self._msg_handler_unsub:
            _LOGGER.debug("_ensure_msg_handler: removing old handler")
            try:
                self._msg_handler_unsub()
            except Exception:
                pass
            self._msg_handler_unsub = None

        self._client = client
        _LOGGER.debug("_ensure_msg_handler: client updated to %s", client)

        add_msg_handler = getattr(client, "add_msg_handler", None) if client else None
        if callable(add_msg_handler):
            try:
                self._msg_handler_unsub = add_msg_handler(self._handle_msg)
                _LOGGER.info(
                    "Transport monitor registered message handler with ramses_cc"
                )
            except Exception as e:
                _LOGGER.error("Failed to register message handler: %s", e)
        else:
            _LOGGER.warning("Transport monitor: client has no add_msg_handler method")

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

    def mark_device_offline_immediate(self, device_id: str) -> None:
        normalized_device_id = device_id.replace("_", ":")

        old_state = self._device_states.get(normalized_device_id, True)
        if not old_state:
            return

        self._device_states[normalized_device_id] = False

        existing_task = self._device_timeout_tasks.pop(normalized_device_id, None)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        _LOGGER.warning(
            "Device %s marked offline immediately - command send failed",
            normalized_device_id,
        )

        if self._hass:
            self._hass.loop.call_soon_threadsafe(
                self._hass.async_create_task,
                self._notify_device_state_changed(normalized_device_id, False),
            )

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

        self._refresh_coordinator()

        if not self._is_transport_active():
            return

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

        :param coordinator: RamsesCC coordinator instance
        :param hass: Home Assistant instance for event listening
        """
        async with self._lock:
            if self._monitor_task and not self._monitor_task.done():
                _LOGGER.warning("Transport monitor is already running")
                return

            self._coordinator = coordinator
            self._hass = hass

            client = getattr(self._coordinator, "client", None)
            if client is None:
                _LOGGER.warning(
                    "Transport monitor: coordinator has no client, "
                    "will retry via _refresh_coordinator"
                )
            self._ensure_msg_handler(client)

            # NOTE: ramses_cc_message event bus is deprecated in newer ramses_cc
            # We rely on add_msg_handler callback instead
            if self._hass and not self._event_unsub:
                # Try to listen for legacy event (for backward compatibility)
                try:
                    self._event_unsub = self._hass.bus.async_listen(
                        "ramses_cc_message",
                        self._handle_ramses_cc_message,
                    )
                    _LOGGER.debug(
                        "Transport monitor listening for ramses_cc_message "
                        "events (legacy)"
                    )
                except Exception as e:
                    _LOGGER.debug(
                        "Transport monitor: could not listen for ramses_cc_message: %s",
                        e,
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

            if self._msg_handler_unsub:
                self._msg_handler_unsub()
                self._msg_handler_unsub = None
                _LOGGER.debug("Stopped listening via ramses_cc client message handler")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - just keeps transport state updated."""
        _LOGGER.debug("Transport monitor loop started")
        last_transport_state = None

        while True:
            try:
                await asyncio.sleep(self._check_interval)
                # Just update global transport state
                self._refresh_coordinator()
                transport_active = self._is_transport_active()
                self._transport_available = transport_active

                # Only log when state changes
                if transport_active != last_transport_state:
                    if transport_active:
                        _LOGGER.info("Global transport active")
                    else:
                        _LOGGER.warning("Global transport inactive")
                        await self._mark_all_tracked_devices_offline()
                    last_transport_state = transport_active
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in transport monitor loop: %s", e)

    async def _mark_all_tracked_devices_offline(self) -> None:
        tracked_device_ids = {
            device_id
            for device_id, _ in self._callbacks.values()
            if device_id is not None
        }

        for device_id in tracked_device_ids:
            existing_task = self._device_timeout_tasks.pop(device_id, None)
            if existing_task and not existing_task.done():
                existing_task.cancel()
            await self._mark_device_offline(device_id)

    def _handle_ramses_cc_message(self, event: Event) -> None:
        """Handle ramses_cc_message events to track device replies.

        :param event: Home Assistant event containing ramses_cc_message data
        """
        try:
            self._refresh_coordinator()
            data = event.data
            if not isinstance(data, dict):
                return

            src = data.get("src")
            dst = data.get("dst")

            # Only process messages FROM devices we're monitoring, not TO them
            if isinstance(src, str) and ":" in src:
                normalized_src = src.replace("_", ":")
                tracked_device_ids = {
                    device_id
                    for device_id, _ in self._callbacks.values()
                    if device_id is not None
                }

                if normalized_src in tracked_device_ids:
                    _LOGGER.debug("Message FROM %s (TO %s) - processing", src, dst)
                    self.update_device_message_received(src)
        except Exception as e:
            _LOGGER.error("Error handling ramses_cc_message event: %s", e)

    def _handle_msg(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Handle live ramses_cc client messages to track device replies."""
        try:
            self._refresh_coordinator()
            src = getattr(getattr(msg, "src", None), "id", None)
            dst = getattr(getattr(msg, "dst", None), "id", None)
            code = getattr(msg, "code", None)

            _LOGGER.debug(
                "Transport monitor received message: src=%s dst=%s code=%s",
                src,
                dst,
                code,
            )

            if isinstance(src, str) and ":" in src:
                normalized_src = src.replace("_", ":")
                tracked_device_ids = {
                    device_id
                    for device_id, _ in self._callbacks.values()
                    if device_id is not None
                }

                if normalized_src in tracked_device_ids:
                    _LOGGER.debug("Message FROM %s (TO %s) - processing", src, dst)
                    self.update_device_message_received(src)
                else:
                    _LOGGER.debug(
                        "Message FROM %s not in tracked devices: %s",
                        normalized_src,
                        tracked_device_ids,
                    )
        except Exception as e:
            _LOGGER.error("Error handling ramses_cc client message: %s", e)

    def _is_transport_active(self) -> bool:
        if not self._coordinator or not getattr(self._coordinator, "client", None):
            return False

        return True

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

    :return: TransportMonitor instance
    """
    global _transport_monitor
    if _transport_monitor is None:
        _transport_monitor = TransportMonitor()
    return _transport_monitor
