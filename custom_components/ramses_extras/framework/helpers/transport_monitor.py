"""Transport State Monitor for Ramses RF.

This module provides monitoring of the Ramses RF transport state and
implements graceful degradation when the transport is unavailable.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

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

    async def start_monitoring(self, coordinator: "RamsesCoordinator") -> None:
        """Start monitoring the transport state.

        Args:
            coordinator: RamsesCC coordinator instance
        """
        async with self._lock:
            if self._monitor_task and not self._monitor_task.done():
                _LOGGER.warning("Transport monitor is already running")
                return

            self._coordinator = coordinator
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

    async def _check_transport_state(self) -> None:
        """Check the current transport state and notify callbacks if changed."""
        if not self._coordinator or not self._coordinator.client:
            current_state = False
        else:
            # Check if transport is active by trying to access its state
            try:
                # The transport is active if we can access the client's transport
                # and it's not in an error/inactive state
                transport = self._coordinator.client.transport
                current_state = (
                    hasattr(transport, "state") and transport.state.name != "Inactive"
                )
            except Exception:
                current_state = False

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
