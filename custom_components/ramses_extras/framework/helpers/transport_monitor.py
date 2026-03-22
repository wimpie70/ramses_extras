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
    """

    def __init__(self) -> None:
        self._transport_available: bool = False
        self._last_check: float = 0
        self._check_interval: float = 5.0  # Check every 5 seconds
        self._monitor_task: asyncio.Task | None = None
        self._callbacks: dict[str, Callable[[bool], None]] = {}
        self._coordinator: RamsesCoordinator | None = None
        self._lock = asyncio.Lock()
        self._last_31da_time: float = 0  # Track last 31DA message time
        self._message_timeout: float = (
            30.0  # Consider offline after 30 seconds without 31DA
        )
        self._hass: HomeAssistant | None = None
        self._event_unsub: Callable[[], None] | None = None

    def register_callback(self, name: str, callback: Callable[[bool], None]) -> None:
        """Register a callback for transport state changes.

        Args:
            name: Unique identifier for the callback
            callback: Function to call when transport state changes
                     (receives boolean: True=available, False=unavailable)
        """
        self._callbacks[name] = callback
        _LOGGER.debug("Registered transport state callback: %s", name)

    def unregister_callback(self, name: str) -> None:
        """Unregister a transport state callback.

        Args:
            name: Identifier of the callback to remove
        """
        self._callbacks.pop(name, None)
        _LOGGER.debug("Unregistered transport state callback: %s", name)

    def update_31da_received(self) -> None:
        """Called when a 31DA message is received.

        This updates the timestamp of the last received 31DA message,
        which is used to determine if the WTW unit is online.
        """
        self._last_31da_time = time.time()
        _LOGGER.debug("31DA message received, updating last message time")

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

            # Set up event listener for 31DA messages
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
        """Main monitoring loop."""
        _LOGGER.debug("Transport monitor loop started")

        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_transport_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in transport monitor loop: %s", e)
                # Continue monitoring despite errors

    def _handle_ramses_cc_message(self, event: Event) -> None:
        """Handle ramses_cc_message events to track 31DA messages.

        Args:
            event: Home Assistant event containing ramses_cc_message data
        """
        try:
            data = event.data
            if not isinstance(data, dict):
                return

            code = data.get("code")
            if code == "31DA":
                self.update_31da_received()
                _LOGGER.debug("31DA message detected via event")
        except Exception as e:
            _LOGGER.error("Error handling ramses_cc_message event: %s", e)

    async def _check_transport_state(self) -> None:
        """Check the current transport state and notify callbacks if changed."""
        if not self._coordinator or not self._coordinator.client:
            current_state = False
        else:
            # Check if transport is active by trying to access its state
            transport_active = False
            try:
                # The transport is active if we can access the client's transport
                # and it's not in an error/inactive state
                transport = self._coordinator.client.transport
                transport_active = (
                    hasattr(transport, "state") and transport.state.name != "Inactive"
                )
            except Exception:
                transport_active = False

            # Also check if we've received 31DA messages recently
            # This is a better indicator of whether the WTW unit is actually online
            time_since_31da = time.time() - self._last_31da_time
            messages_recent = time_since_31da < self._message_timeout

            # Consider available if both transport is active AND
            # we've received messages recently
            # OR if we just started and haven't received messages yet (grace period)
            current_state = transport_active and (
                messages_recent or self._last_31da_time == 0
            )

            # Log state for debugging
            if not current_state:
                _LOGGER.debug(
                    "Transport unavailable: transport_active=%s, "
                    "time_since_31da=%.1fs, messages_recent=%s",
                    transport_active,
                    time_since_31da,
                    messages_recent,
                )

        if current_state != self._transport_available:
            self._transport_available = current_state
            _LOGGER.info(
                "Transport state changed: %s -> %s",
                "Available" if current_state else "Unavailable",
                current_state,
            )

            # Notify all callbacks
            for name, callback in self._callbacks.items():
                try:
                    callback(current_state)
                except Exception as e:
                    _LOGGER.error("Error in transport state callback %s: %s", name, e)

    @property
    def is_transport_available(self) -> bool:
        """Check if transport is currently available."""
        return self._transport_available

    async def force_check(self) -> bool:
        """Force an immediate transport state check.

        Returns:
            Current transport availability state
        """
        await self._check_transport_state()
        return self._transport_available


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
