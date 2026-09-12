"""Transport State Monitor for Ramses RF.

This module provides monitoring of the Ramses RF transport state and
implements graceful degradation when the transport is unavailable.

The primary source of transport availability is the ramses_cc pool health
entities (``binary_sensor.pool_status_*`` and per-HGI ``*_online``
entities introduced with the multi-HGI pool work).  When those entities
are not yet available (e.g. before ramses_cc has created them), the
monitor falls back to its own command-based liveness detection.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.core import callback as ha_callback

if TYPE_CHECKING:
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

_LOGGER = logging.getLogger(__name__)

# Entity ID patterns for ramses_cc pool health entities.
# The unique_id format is ``{entry_id}_pool_status_online`` and
# ``{entry_id}_pool_child_{hgi_id}_online``; the resulting entity_id
# is ``binary_sensor.pool_status_N`` and ``binary_sensor.hgi_{hgi}_online_N``.
_POOL_STATUS_ENTITY_PREFIX = "binary_sensor.pool_status_"
_HGI_ONLINE_ENTITY_PREFIX = "binary_sensor.hgi_"


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
        self._msg_handler_unsub: Callable[[], None] | None = None
        # Pool health entity integration (primary source of truth).
        self._pool_status_entity_id: str | None = None
        self._hgi_online_entity_ids: dict[str, str] = {}  # hgi_id -> entity_id
        self._pool_state_unsub: Callable[[], None] | None = None
        self._pool_entity_available: bool = False  # Have we seen the entity?

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
        _LOGGER.debug(
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
            return

        # Start new timeout task
        if self._hass:
            task = self._hass.async_create_task(
                self._device_timeout_handler(normalized_device_id)
            )
            self._device_timeout_tasks[normalized_device_id] = task

    def _refresh_coordinator(self) -> None:
        if not self._hass:
            return

        # Modern ramses_cc stores the coordinator in entry.runtime_data
        ramses_cc_entries = self._hass.config_entries.async_entries("ramses_cc")
        for entry in ramses_cc_entries:
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None and hasattr(coordinator, "client"):
                client = getattr(coordinator, "client", None)
                if client is not None:
                    self._coordinator = coordinator
                    self._ensure_msg_handler(client)
                    return

        # Legacy fallback: hass.data["ramses_cc"]
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
            return

        if self._msg_handler_unsub:
            _LOGGER.debug("_ensure_msg_handler: removing old handler")
            try:
                self._msg_handler_unsub()
            except Exception:
                pass
            self._msg_handler_unsub = None

        self._client = client

        if client is None:
            _LOGGER.debug(
                "_ensure_msg_handler: no client available, "
                "will retry via _refresh_coordinator"
            )
            return

        _LOGGER.debug("_ensure_msg_handler: client updated to %s", client)

        add_msg_handler = getattr(client, "add_msg_handler", None)
        if callable(add_msg_handler):
            try:
                self._msg_handler_unsub = add_msg_handler(self._handle_msg)
                _LOGGER.info(
                    "Transport monitor registered message handler with ramses_cc"
                )
            except Exception as e:
                _LOGGER.error("Failed to register message handler: %s", e)
        else:
            _LOGGER.warning(
                "Transport monitor: client %s has no add_msg_handler method "
                "(ramses_rf may be too old)",
                type(client).__name__,
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

    def _discover_pool_health_entities(self) -> None:
        """Discover ramses_cc pool health entity IDs from the entity registry.

        Populates ``_pool_status_entity_id`` and ``_hgi_online_entity_ids``
        by scanning the HA entity registry for ramses_cc pool entities.
        """
        if not self._hass:
            return
        try:
            from homeassistant.helpers import entity_registry as er

            reg = er.async_get(self._hass)
            pool_entity_id: str | None = None
            hgi_entities: dict[str, str] = {}
            for entity in reg.entities.values():
                if entity.platform != "ramses_cc":
                    continue
                eid = entity.entity_id
                uid = entity.unique_id
                if eid.startswith(_POOL_STATUS_ENTITY_PREFIX):
                    # Prefer the pool_status entity (aggregate).
                    pool_entity_id = eid
                elif uid.endswith("_online") and "_pool_child_" in uid:
                    # Per-HGI: unique_id = {entry_id}_pool_child_{hgi_id}_online
                    # Extract hgi_id from the unique_id.
                    parts = uid.split("_pool_child_")
                    if len(parts) == 2:
                        hgi_id = parts[1].removesuffix("_online")
                        hgi_entities[hgi_id] = eid
            self._pool_status_entity_id = pool_entity_id
            self._hgi_online_entity_ids = hgi_entities
            if pool_entity_id or hgi_entities:
                _LOGGER.info(
                    "Transport monitor: discovered pool health entities: "
                    "pool_status=%s, hgi_online=%s",
                    pool_entity_id,
                    hgi_entities,
                )
        except Exception as e:
            _LOGGER.debug(
                "Could not discover pool health entities: %s", e, exc_info=True
            )

    def _get_pool_status_from_entity(self) -> bool | None:
        """Read the pool status from the ramses_cc entity.

        :return: True if pool is online, False if offline, None if entity
                 not available or state unknown.
        """
        if not self._hass or not self._pool_status_entity_id:
            return None
        state = self._hass.states.get(self._pool_status_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return bool(state.state == "on")

    def _get_hgi_online_from_entity(self, hgi_id: str) -> bool | None:
        """Read a specific HGI's online status from the ramses_cc entity.

        :param hgi_id: HGI device ID (e.g. ``18:130236``)
        :return: True if online, False if offline, None if entity not
                 available or state unknown.
        """
        if not self._hass:
            return None
        entity_id = self._hgi_online_entity_ids.get(hgi_id)
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        return bool(state.state == "on")

    async def start_monitoring(
        self, coordinator: RamsesCoordinator, hass: HomeAssistant
    ) -> None:
        """Start monitoring the transport state.

        :param coordinator: RamsesCC coordinator instance
        :param hass: Home Assistant instance for event listening
        """
        async with self._lock:
            if self._monitor_task and not self._monitor_task.done():
                _LOGGER.debug("Transport monitor is already running")
                return

            self._coordinator = coordinator
            self._hass = hass

            client = getattr(self._coordinator, "client", None)
            if client is None:
                _LOGGER.info(
                    "Transport monitor: coordinator has no client yet, "
                    "will retry via _refresh_coordinator"
                )
            self._ensure_msg_handler(client)

            self._monitor_task = asyncio.create_task(self._monitor_loop())
            _LOGGER.info("Started transport state monitoring")

            # Discover ramses_cc pool health entities and subscribe to
            # their state changes.  These are the primary source of truth
            # for transport availability; the internal command-based
            # detection remains as a fallback.
            self._discover_pool_health_entities()
            self._subscribe_pool_state_changes()

    def _subscribe_pool_state_changes(self) -> None:
        """Subscribe to pool health entity state changes.

        Re-discovers entities on each state change so that entities
        created after monitoring starts are picked up.
        """
        if not self._hass:
            return
        from homeassistant.helpers.event import async_track_state_change_event

        # Re-discover on each state change to catch entities created
        # after monitoring starts.
        self._discover_pool_health_entities()

        target_entities: list[str] = []
        if self._pool_status_entity_id:
            target_entities.append(self._pool_status_entity_id)
        target_entities.extend(self._hgi_online_entity_ids.values())

        if not target_entities:
            _LOGGER.debug(
                "Transport monitor: no pool health entities found yet, "
                "will retry on next discovery cycle"
            )
            return

        @ha_callback  # type: ignore[untyped-decorator]
        def _on_pool_state_changed(event: Any) -> None:
            """Handle pool health entity state change."""
            entity_id = event.data.get("entity_id")
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            is_on = new_state.state == "on"
            _LOGGER.debug(
                "Transport monitor: pool entity %s -> %s",
                entity_id,
                new_state.state,
            )
            # Update global transport availability from the pool
            # status entity (aggregate: any HGI online).
            if entity_id == self._pool_status_entity_id:
                self._pool_entity_available = True
                self._transport_available = is_on
                if not is_on:
                    self._hass.async_create_task(  # type: ignore[union-attr]
                        self._mark_all_tracked_devices_offline()
                    )

        # Subscribe to all pool health entities.  We use a single
        # subscription for all of them.
        self._pool_state_unsub = async_track_state_change_event(
            self._hass, target_entities, _on_pool_state_changed
        )
        _LOGGER.info(
            "Transport monitor: subscribed to %d pool health entities",
            len(target_entities),
        )

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

            if self._msg_handler_unsub:
                self._msg_handler_unsub()
                self._msg_handler_unsub = None
                _LOGGER.debug("Stopped listening via ramses_cc client message handler")

            if self._pool_state_unsub:
                self._pool_state_unsub()
                self._pool_state_unsub = None
                _LOGGER.debug("Stopped listening to pool health entities")

            # Cancel any per-device timeout timers still pending
            for task in self._device_timeout_tasks.values():
                if not task.done():
                    task.cancel()
            self._device_timeout_tasks.clear()

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - just keeps transport state updated.

        Uses the ramses_cc pool health entity as the primary source of
        truth for transport availability.  Falls back to the internal
        ``_is_transport_active()`` check when the entity is not yet
        available.
        """
        _LOGGER.debug("Transport monitor loop started")
        last_transport_state = None

        while True:
            try:
                await asyncio.sleep(self._check_interval)

                # Re-discover pool health entities periodically in case
                # they were created after monitoring started.
                if not self._pool_status_entity_id:
                    self._discover_pool_health_entities()
                    # _discover_pool_health_entities may set
                    # _pool_status_entity_id; re-check and subscribe if
                    # newly found and not yet subscribed.
                    if (
                        self._pool_status_entity_id is not None
                        and self._pool_state_unsub is None
                    ):
                        self._subscribe_pool_state_changes()

                # Primary: read from the pool health entity.
                pool_state = self._get_pool_status_from_entity()
                if pool_state is not None:
                    self._pool_entity_available = True
                    transport_active = pool_state
                else:
                    # Fallback: internal transport check.
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

    def _handle_msg(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Handle live ramses_cc client messages to track device replies.

        The ramses_rf gateway passes a PacketDTO (or, in older versions,
        a Message object).  PacketDTO has addr1/addr2/addr3 string fields;
        Message has src/dst Address objects with .id.  We support both.

        Any message from a device proves it is online — mark it online
        even if no callback is explicitly tracking it.  This prevents a
        device from being stuck offline after a transient command failure.
        """
        try:
            self._refresh_coordinator()

            # PacketDTO uses addr1 (str); Message uses src (Address with .id)
            src = getattr(msg, "addr1", None)
            if src is None:
                src = getattr(getattr(msg, "src", None), "id", None)

            if isinstance(src, str) and ":" in src:
                # Mark the device online — receiving a message from it
                # proves it is reachable.  This also covers devices that
                # were marked offline by a failed command but are still
                # broadcasting info packets.
                self.update_device_message_received(src)
        except Exception as e:
            _LOGGER.error("Error handling ramses_cc client message: %s", e)

    def _is_transport_active(self) -> bool:
        if not self._coordinator or not getattr(self._coordinator, "client", None):
            return False

        # For pooled transports (multi-HGI), check if at least one child
        # is connected.  The Gateway object exists even when all children
        # are offline, so checking client existence alone is insufficient.
        client = self._coordinator.client
        engine = getattr(client, "_engine", None)
        if engine is not None:
            transport = getattr(engine, "_transport", None)
            if transport is not None:
                # PooledTransport exposes _connected_children
                connected_children = getattr(transport, "_connected_children", None)
                if connected_children is not None:
                    return len(connected_children) > 0

        return True

    def is_device_available(self, device_id: str) -> bool:
        """Return whether a specific device is currently online.

        Uses the ramses_cc pool health entity as the primary source of
        truth for transport availability.  Falls back to the internal
        command-based liveness detection when the entity is not yet
        available.

        A device is online if:
        - The pool status entity says the pool is online (primary), OR
        - We haven't sent a command yet (assume online), OR
        - We sent a command and got a reply before timeout, OR
        - We sent a command and timeout hasn't expired yet

        :param device_id: Device ID (with or without underscores)
        :return: True if the device is considered online
        """
        normalized_device_id = device_id.replace("_", ":")

        # Primary: check the pool status entity.  If the pool is offline,
        # no device can be available.
        pool_state = self._get_pool_status_from_entity()
        if pool_state is not None:
            if not pool_state:
                return False
            # Pool is online — fall through to per-device check below.
            # The pool entity tells us the transport is up, but the
            # device may still be offline (e.g. no RF response).
            return self._device_states.get(normalized_device_id, True)

        # Fallback: when the pool entity is not available, use the
        # internal command-based liveness detection.
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
